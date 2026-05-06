"""Deterministic drift auto-fix — adds missing `triggers:` to skills and
module docstrings to scripts WITHOUT calling any LLM. Zero API cost.

Triggers are generated from the skill's existing `description:` field (which
all skills already have); docstrings are generated from the script's filename
and first function/class signature. Both are intentionally minimal — they
get the capability graph clean enough to stop alerting, and humans can
hand-tune later.

Usage:
    python scripts/drift_autofix.py scan          # report only, no writes
    python scripts/drift_autofix.py apply         # write fixes
    python scripts/drift_autofix.py apply --json  # machine output
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def split_words(name: str) -> list[str]:
    """Split a kebab-case or snake_case name into words."""
    return re.split(r"[-_\s]+", name)


def triggers_from_skill(skill_dir: Path) -> list[str]:
    """Generate triggers via register_skill.synthesize_triggers (the
    canonical skill-onboarding primitive). Deterministic, no LLM. Falls back
    to a name-only list if register_skill imports fail (e.g. supabase
    optional dep)."""
    name = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    try:
        from register_skill import synthesize_triggers, parse_skill_md, infer_category
        if skill_md.exists():
            fm, _ = parse_skill_md(skill_md)
        else:
            fm = {}
        spec: dict = {}
        category = infer_category(name, fm, spec)
        triggers = synthesize_triggers(name, category, fm, spec)
        return triggers[:8] if triggers else [name.replace("-", " ")]
    except (ImportError, ModuleNotFoundError):
        # Minimal fallback if register_skill isn't importable
        base = " ".join(split_words(name))
        return [base, f"use {base}", f"run {base}"]


def docstring_for_script(script_path: Path) -> str:
    """Generate a one-line module docstring from filename + first
    function/class. Returns the docstring TEXT (no triple-quotes)."""
    name = script_path.stem
    words = split_words(name)
    readable = " ".join(words).strip()

    first_def = ""
    try:
        tree = ast.parse(script_path.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                first_def = node.name
                break
    except (SyntaxError, ValueError):
        pass

    if first_def and not first_def.startswith("_"):
        return f"{readable.capitalize()} — provides {first_def.replace('_', ' ')}."
    return f"{readable.capitalize()}."


def fix_skill_triggers(skill_md: Path, triggers: list[str]) -> bool:
    """Insert `triggers: [...]` into the frontmatter if missing. Returns True
    if file was modified."""
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return False
    end = text.find("---", 3)
    if end == -1:
        return False
    frontmatter = text[3:end]
    if re.search(r"^triggers:", frontmatter, flags=re.MULTILINE):
        return False  # already has triggers (drift may be stale)

    quoted = ", ".join(json.dumps(t) for t in triggers)
    new_line = f"triggers: [{quoted}]\n"
    new_frontmatter = frontmatter.rstrip("\n") + "\n" + new_line
    new_text = "---" + new_frontmatter + text[end:]
    skill_md.write_text(new_text, encoding="utf-8")
    return True


def fix_script_docstring(script_path: Path) -> bool:
    """Insert a one-line module docstring at the top if missing. Returns True
    if file was modified."""
    text = script_path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return False
    if (tree.body and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
            and isinstance(tree.body[0].value.value, str)):
        return False  # already has docstring

    docstring_text = docstring_for_script(script_path)
    lines = text.splitlines(keepends=True)
    insert_at = 0
    for i, ln in enumerate(lines[:5]):
        s = ln.strip()
        if s.startswith("#!") or (s.startswith("#") and "coding" in s) or s.startswith("# -*-"):
            insert_at = i + 1
        else:
            break

    new_block = f'"""{docstring_text}"""\n'
    if insert_at < len(lines) and lines[insert_at].strip():
        new_block += "\n"
    lines.insert(insert_at, new_block)
    script_path.write_text("".join(lines), encoding="utf-8")
    return True


def get_drift(repo: Path) -> list[dict]:
    import subprocess
    r = subprocess.run(
        [sys.executable, str(repo / "scripts" / "capability_query.py"), "drift"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0 or not r.stdout.strip().startswith("["):
        return []
    return json.loads(r.stdout)


def run(repo: Path, apply: bool) -> dict:
    drift = get_drift(repo)
    skill_fixes = []
    script_fixes = []
    skipped = []

    for item in drift:
        node = item.get("node", "")
        issue = item.get("issue", "")
        if node.startswith("skill:") and "no triggers" in issue:
            slug = node.split(":", 1)[1]
            skill_md = repo / "skills" / slug / "SKILL.md"
            if not skill_md.exists():
                skipped.append({"node": node, "reason": "SKILL.md missing"})
                continue
            triggers = triggers_from_skill(skill_md.parent)
            if apply:
                if fix_skill_triggers(skill_md, triggers):
                    skill_fixes.append({"slug": slug, "triggers": triggers})
                else:
                    skipped.append({"node": node, "reason": "already has triggers or no frontmatter"})
            else:
                skill_fixes.append({"slug": slug, "triggers": triggers, "would_write": True})

        elif node.startswith("script:") and "missing module docstring" in issue:
            slug = node.split(":", 1)[1]
            script_path = repo / "scripts" / f"{slug}.py"
            if not script_path.exists():
                skipped.append({"node": node, "reason": "script missing"})
                continue
            doc = docstring_for_script(script_path)
            if apply:
                if fix_script_docstring(script_path):
                    script_fixes.append({"slug": slug, "docstring": doc})
                else:
                    skipped.append({"node": node, "reason": "already has docstring"})
            else:
                script_fixes.append({"slug": slug, "docstring": doc, "would_write": True})

    return {
        "drift_total": len(drift),
        "skill_fixes": skill_fixes,
        "script_fixes": script_fixes,
        "skipped": skipped,
        "applied": apply,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for c in ("scan", "apply"):
        sp = sub.add_parser(c)
        sp.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run(REPO_ROOT, apply=(args.cmd == "apply"))

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        verb = "would fix" if not result["applied"] else "fixed"
        print(f"Drift: {result['drift_total']} total")
        print(f"  {verb} {len(result['skill_fixes'])} skills (added triggers)")
        print(f"  {verb} {len(result['script_fixes'])} scripts (added docstrings)")
        print(f"  skipped {len(result['skipped'])}")
        if result['applied'] and (result['skill_fixes'] or result['script_fixes']):
            print("  → run `python scripts/build_capability_graph.py` to refresh the graph")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
