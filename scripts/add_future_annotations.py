#!/usr/bin/env python3
"""Add `from __future__ import annotations` to Python files that use PEP 604
union syntax (X | None) without it.

Background: CC's Mac defaults to Python 3.9 (CommandLineTools), which can't
parse PEP 604 unions at module import. Adding the future-annotations import
defers annotation evaluation so 3.9 stops choking. No runtime behavior
change on 3.10+.

USAGE: python scripts/add_future_annotations.py [--dry-run] [path ...]
       (paths default to scripts/ and bravo_cli/)

Skips files that already have the future import. Skips _archive/ trees.
Insertion: right after the module docstring closes, with a blank line on
either side. If no module docstring, insertion goes at the top after any
shebang.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

PEP604_PATTERN = re.compile(
    r'(:\s*(str|int|bool|float|dict|list|Path|bytes|Any|tuple|set)\s*\|\s*None)'
    r'|(->\s*(str|int|bool|float|dict|list|Path|bytes|Any|tuple|set)\s*\|\s*None)'
    r'|(:\s*(str|int|bool|float|dict|list|Path|bytes|Any|tuple|set)\s*\|\s*'
    r'(str|int|bool|float|dict|list|Path|bytes|Any|tuple|set))'
)


def needs_fix(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    if "from __future__ import annotations" in text[:3000]:
        return False
    return bool(PEP604_PATTERN.search(text))


def find_insertion_point(text: str) -> int:
    """Return the byte index where we'd insert the import.

    Strategy: parse with ast, find Module.body[0] if it's an Expression+Str
    (i.e. module docstring). Insert right AFTER that statement. If no
    docstring, insert after any shebang and encoding-cookie lines at the
    very top.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return 0
    body = tree.body
    if body and isinstance(body[0], ast.Expr) and isinstance(
        body[0].value, ast.Constant
    ) and isinstance(body[0].value.value, str):
        # Use end_lineno when available (Python 3.8+). Convert to byte offset.
        end_line = body[0].end_lineno or body[0].lineno
        lines = text.splitlines(keepends=True)
        offset = sum(len(line) for line in lines[:end_line])
        return offset
    # No docstring — insert after shebang / encoding lines.
    lines = text.splitlines(keepends=True)
    insert_after = 0
    for i, line in enumerate(lines[:2]):
        if line.startswith("#!") or re.match(r"#.*coding[:=]", line):
            insert_after = i + 1
    return sum(len(line) for line in lines[:insert_after])


def patch(path: Path, dry_run: bool) -> bool:
    text = path.read_text(encoding="utf-8")
    insert_at = find_insertion_point(text)
    before = text[:insert_at]
    after = text[insert_at:]
    # Make sure we have exactly one blank line on each side.
    if before and not before.endswith("\n"):
        before += "\n"
    sep_before = "\n" if before and not before.endswith("\n\n") else ""
    sep_after = "" if after.startswith("\n") else "\n"
    new_text = (
        before + sep_before + "from __future__ import annotations\n" + sep_after + after
    )
    if dry_run:
        return True
    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("paths", nargs="*", default=["scripts", "bravo_cli"])
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    repo = Path(__file__).resolve().parents[1]
    candidates: list[Path] = []
    for root in args.paths:
        root_path = (repo / root) if not Path(root).is_absolute() else Path(root)
        for path in root_path.rglob("*.py"):
            if "/_archive/" in str(path) or "/cli_templates/" in str(path):
                continue
            if needs_fix(path):
                candidates.append(path)

    if not candidates:
        print("Nothing to fix.")
        return

    print(f"{'DRY-RUN — would patch' if args.dry_run else 'Patching'} "
          f"{len(candidates)} file(s):")
    for p_ in candidates:
        rel = p_.relative_to(repo)
        print(f"  {rel}")
        patch(p_, args.dry_run)

    if args.dry_run:
        print("\n(dry-run — no files modified)")


if __name__ == "__main__":
    main()
