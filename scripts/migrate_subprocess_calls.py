"""One-shot codemod: migrate raw subprocess.{Popen,run,...} calls to
safe_run/safe_popen from _subprocess_helpers, OR add creationflags
where the migration would be too invasive.

Strategy
--------
For each violation surfaced by audit_no_visible_subprocess.py:
  1. Parse the file's AST.
  2. For each violating call, inject `creationflags=WINDOWLESS_FLAGS`
     as the first keyword argument (preserving existing kwargs).
  3. Add `from _subprocess_helpers import WINDOWLESS_FLAGS` near the
     top of the file (after existing imports) if not already imported.
  4. Add `sys.path` injection if the file lives outside `scripts/`.

Dry-run by default. Pass `--apply` to write changes.

Usage
-----
  python scripts/migrate_subprocess_calls.py            # dry-run, all violations
  python scripts/migrate_subprocess_calls.py --apply    # write changes
  python scripts/migrate_subprocess_calls.py path/file  # single file
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from audit_no_visible_subprocess import audit_file, _is_excluded  # noqa: E402

HELPER_IMPORT = "from _subprocess_helpers import WINDOWLESS_FLAGS"
# Walk up from __file__ until we find the repo's scripts/ dir, then
# prepend it to sys.path. Robust against any file depth — scripts/hooks/X.py,
# bravo_cli/Y.py, agents/foo/Z.py all work identically.
SYS_PATH_BLOCK = """_p = Path(__file__).resolve()
while _p.parent != _p and not (_p / "scripts" / "_subprocess_helpers.py").exists():
    _p = _p.parent
sys.path.insert(0, str(_p / "scripts"))"""


def _file_needs_sys_path_shim(path: Path) -> bool:
    """True if `from _subprocess_helpers import …` would fail when the
    file runs as __main__. That's the case unless the file lives DIRECTLY
    in scripts/ (e.g., scripts/foo.py runs with scripts/ on sys.path[0],
    but scripts/hooks/foo.py runs with scripts/hooks/ on sys.path[0])."""
    rel_parts = path.relative_to(REPO_ROOT).parts
    if len(rel_parts) == 2 and rel_parts[0] == "scripts":
        # scripts/foo.py — sys.path[0] is scripts/, import works
        return False
    return True


def _patch_source(path: Path, source: str) -> tuple[str, int]:
    """Return (patched_source, count_of_calls_patched)."""
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return source, 0

    # Collect (lineno, col_offset, end_lineno, end_col_offset) for each
    # violation call, plus the location to insert creationflags.
    violations = audit_file(path)
    if not violations:
        return source, 0

    # Walk again to get full Call nodes
    call_nodes: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_nodes.append(node)

    # Match violations to AST calls by (lineno, col)
    by_key = {(c.lineno, c.col_offset): c for c in call_nodes}
    target_calls: list[ast.Call] = []
    for v in violations:
        key = (v["line"], v["col"])
        if key in by_key:
            target_calls.append(by_key[key])

    if not target_calls:
        return source, 0

    # Patch each call's source. We'll insert
    # `creationflags=WINDOWLESS_FLAGS, ` immediately after the opening `(`.
    # To avoid offset drift, patch from the END of the file backwards.
    lines = source.splitlines(keepends=True)
    # Build a flat character-offset map by line
    line_offsets = [0]
    for line in lines:
        line_offsets.append(line_offsets[-1] + len(line))

    def loc_to_offset(lineno: int, col: int) -> int:
        return line_offsets[lineno - 1] + col

    # For each call, insert `creationflags=WINDOWLESS_FLAGS` just before
    # the call's closing paren. Inserting AFTER the opening paren would
    # put a keyword arg before existing positional args, which is a
    # SyntaxError. Using AST end positions to find the closing paren is
    # the safe way.
    edits: list[tuple[int, str]] = []  # (offset, insertion)
    patched_count = 0
    for call in sorted(target_calls, key=lambda c: (c.lineno, c.col_offset), reverse=True):
        if call.end_lineno is None or call.end_col_offset is None:
            continue
        end_offset = loc_to_offset(call.end_lineno, call.end_col_offset)
        # end_offset points to the character AFTER the closing `)`.
        # Walk back over whitespace to find the actual `)`.
        idx = end_offset - 1
        while idx > 0 and source[idx] != ")":
            idx -= 1
        if idx <= 0 or source[idx] != ")":
            continue
        close_paren_at = idx

        # Look back past whitespace/newlines to find what immediately
        # precedes the `)`. If it's the opening `(`, the call is empty.
        # If it's a comma, the call already has a trailing comma so we
        # just inject `creationflags=…`. Otherwise we need a leading
        # `, ` separator.
        scan = close_paren_at - 1
        while scan > 0 and source[scan] in " \t\n\r":
            scan -= 1
        prev_char = source[scan] if scan >= 0 else ""

        if prev_char == "(":
            insertion = "creationflags=WINDOWLESS_FLAGS"
        elif prev_char == ",":
            insertion = " creationflags=WINDOWLESS_FLAGS"
        else:
            insertion = ", creationflags=WINDOWLESS_FLAGS"

        edits.append((close_paren_at, insertion))
        patched_count += 1

    # Apply edits from end → start so earlier offsets stay valid
    patched = source
    for offset, text in edits:
        patched = patched[:offset] + text + patched[offset:]

    # Add the import if it's not there already
    if HELPER_IMPORT not in patched:
        # Insert after the LAST top-level `import` or `from … import …`
        # so we don't break docstrings or `from __future__ import …`.
        # Use AST on the patched source for safety.
        try:
            tree2 = ast.parse(patched, filename=str(path))
        except SyntaxError:
            return source, 0  # bail — don't write a broken file

        last_import_end_lineno = 0
        for node in tree2.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                last_import_end_lineno = node.end_lineno or node.lineno

        if last_import_end_lineno == 0:
            # No imports — insert after module docstring if any, else at top
            if tree2.body and isinstance(tree2.body[0], ast.Expr) and isinstance(tree2.body[0].value, ast.Constant):
                last_import_end_lineno = tree2.body[0].end_lineno or 1

        lines2 = patched.splitlines(keepends=True)
        insertion_lines: list[str] = []
        # Add sys.path shim if needed (file outside scripts/)
        if _file_needs_sys_path_shim(path):
            # Ensure `import sys` and `from pathlib import Path` exist
            has_sys = any("import sys" in ln for ln in lines2[:last_import_end_lineno])
            has_path = any("from pathlib import Path" in ln for ln in lines2[:last_import_end_lineno]) \
                       or any("import pathlib" in ln for ln in lines2[:last_import_end_lineno])
            if not has_sys:
                insertion_lines.append("import sys\n")
            if not has_path:
                insertion_lines.append("from pathlib import Path\n")
            insertion_lines.append(SYS_PATH_BLOCK + "\n")
        insertion_lines.append(HELPER_IMPORT + "  # noqa: E402\n")
        # Insert as a block
        prefix = "".join(lines2[:last_import_end_lineno])
        suffix = "".join(lines2[last_import_end_lineno:])
        patched = prefix + "".join(insertion_lines) + suffix

    return patched, patched_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="files to migrate (default: all files with violations)")
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.paths:
        targets = [Path(p).resolve() for p in args.paths]
    else:
        # Discover all files with violations
        violation_files: set[Path] = set()
        for root in [REPO_ROOT / "scripts", REPO_ROOT / "bravo_cli", REPO_ROOT / "agents"]:
            if not root.exists():
                continue
            for path in root.rglob("*.py"):
                if _is_excluded(path):
                    continue
                if audit_file(path):
                    violation_files.add(path)
            for path in root.rglob("*.pyw"):
                if _is_excluded(path):
                    continue
                if audit_file(path):
                    violation_files.add(path)
        targets = sorted(violation_files)

    results: list[dict] = []
    for path in targets:
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            results.append({"file": str(path), "error": str(e)})
            continue
        patched, count = _patch_source(path, source)
        if count > 0 and patched != source:
            rel = path.relative_to(REPO_ROOT).as_posix()
            results.append({"file": rel, "patched": count})
            if args.apply:
                path.write_text(patched, encoding="utf-8")

    if args.json:
        print(json.dumps({"applied": args.apply, "results": results}, indent=2))
    else:
        for r in results:
            marker = "APPLY" if args.apply else "DRY"
            print(f"[{marker}] {r['file']} — {r.get('patched', 0)} call(s) patched")
        total = sum(r.get("patched", 0) for r in results)
        print(f"\n[migrate] {len(results)} file(s), {total} call(s) {'patched' if args.apply else 'would-patch'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
