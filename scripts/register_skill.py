"""
Register Skill — the skill-onboarding tool.

Before this tool, adding a new skill was a five-file manual mess: create
SKILL.md, manually add to brain/CAPABILITIES.md, update brain/QUICK_REFERENCE.md,
insert into the skills_registry Supabase table, and hope nothing drifted.
Forgetting step 2 was the most common failure — skills existed in the
folder but weren't discoverable.

This module fixes that. Five subcommands:

  create    — scaffold a brand-new skill folder with templates
  register  — wire an existing skill into skills_registry + doc index
  list      — print all skills from the registry
  audit     — find drift: skills in folder not in registry, etc.
  validate  — deep structural check on one skill

USAGE
-----
    # Start a new skill from templates
    python scripts/register_skill.py create my-new-skill --category content

    # Wire it up (idempotent)
    python scripts/register_skill.py register my-new-skill

    # See what's registered
    python scripts/register_skill.py list --json

    # Find drift — this is the "clean the system" command
    python scripts/register_skill.py audit --json

    # Deep-check one skill
    python scripts/register_skill.py validate send-gateway

DESIGN
------
1. The `skills/` folder is the source of truth for WHAT exists.
2. The Supabase `skills_registry` table (migration 001) is runtime truth:
   which skills are active, usage counts, last used.
3. brain/CAPABILITIES.md is a human-readable doc index. This tool does NOT
   auto-edit CAPABILITIES.md — that's fragile. Instead `register` prints
   the exact one-line row for CC to paste in, and `audit` reports drift.
4. `create` scaffolds real templates, not placeholders — the SKILL.md it
   writes has real structure and the run.py it writes actually runs
   (just prints a hello message).

The whole tool follows the V5.6 conventions: reads .env.agents, --json flag,
fail-closed on Supabase errors, zero hardcoded credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"
CAPABILITIES_FILE = PROJECT_ROOT / "brain" / "CAPABILITIES.md"

# Windows default cp1252 can't encode checkmarks / bullets / em-dashes —
# force UTF-8 on stdout/stderr so our plain-English output works everywhere.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ---- Env + DB ---------------------------------------------------------------

def load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env.agents"
    if not env_path.exists():
        return {}
    env_vars: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env_vars[k.strip()] = v.strip()
    for k, v in env_vars.items():
        os.environ.setdefault(k, v)
    return env_vars


def get_supabase(env: Optional[dict[str, str]] = None):
    e = env if env is not None else load_env()
    url = e.get("BRAVO_SUPABASE_URL") or os.environ.get("BRAVO_SUPABASE_URL")
    key = (e.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
           or os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY"))
    if not url or not key:
        raise RuntimeError("Bravo Supabase credentials missing")
    from supabase import create_client
    return create_client(url, key)


# ---- Frontmatter parsing ----------------------------------------------------

def parse_skill_md(path: Path) -> tuple[dict, str]:
    """Parse a SKILL.md — return (frontmatter_dict, body_markdown). Frontmatter
    must be delimited by --- at top of file. Returns empty dict if missing."""
    if not path.exists():
        raise FileNotFoundError(f"SKILL.md not found at {path}")
    text = path.read_text(encoding="utf-8")
    if not text.lstrip().startswith("---"):
        return {}, text
    try:
        import yaml
    except ImportError:
        raise RuntimeError("pyyaml not installed — cannot parse skill frontmatter")
    # Split on first --- after the opening one
    match = re.match(r"^\s*---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    frontmatter_raw, body = match.group(1), match.group(2)
    try:
        fm = yaml.safe_load(frontmatter_raw) or {}
    except yaml.YAMLError as exc:
        raise RuntimeError(f"invalid YAML frontmatter in {path}: {exc}")
    if not isinstance(fm, dict):
        raise RuntimeError(f"SKILL.md frontmatter must be a mapping ({path})")
    return fm, body


def parse_spec_yaml(path: Path) -> dict:
    """Read optional spec.yaml alongside a skill. Returns empty dict if missing."""
    if not path.exists():
        return {}
    import yaml
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RuntimeError(f"invalid spec.yaml ({path}): {exc}")
    if not isinstance(data, dict):
        raise RuntimeError(f"spec.yaml must be a mapping ({path})")
    return data


# ---- Structural validation --------------------------------------------------

VALID_CATEGORIES = {
    "revenue", "content", "infrastructure", "operations", "sales",
    "communication", "automation", "memory", "security", "compliance",
    "integration", "analytics", "meta", "general",
}
VALID_OWNERS = {"bravo", "codex", "atlas", "maven", "aura"}


def validate_skill(name: str) -> dict:
    """Check one skill's structure. Returns a report dict with status +
    issues list (empty list = valid)."""
    skill_dir = SKILLS_DIR / name
    report: dict[str, Any] = {
        "name": name,
        "path": str(skill_dir),
        "exists": skill_dir.exists(),
        "valid": True,
        "issues": [],
        "runnable": False,
        "has_test": False,
        "has_spec": False,
        "frontmatter": {},
        "spec": {},
    }
    if not skill_dir.exists():
        report["valid"] = False
        report["issues"].append({"severity": "error", "message": "skill folder does not exist"})
        return report

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        report["valid"] = False
        report["issues"].append({"severity": "error", "message": "SKILL.md missing"})
        return report

    try:
        fm, body = parse_skill_md(skill_md)
    except Exception as exc:  # noqa: BLE001
        report["valid"] = False
        report["issues"].append({"severity": "error", "message": f"frontmatter parse failed: {exc}"})
        return report

    report["frontmatter"] = fm
    if not fm.get("name"):
        report["valid"] = False
        report["issues"].append({"severity": "error", "message": "frontmatter missing 'name'"})
    elif fm.get("name") != name:
        report["valid"] = False
        report["issues"].append({
            "severity": "error",
            "message": f"frontmatter name '{fm.get('name')}' does not match folder '{name}'",
        })
    if not fm.get("description"):
        report["valid"] = False
        report["issues"].append({"severity": "error", "message": "frontmatter missing 'description'"})
    if len(body.strip()) < 50:
        report["issues"].append({
            "severity": "warn",
            "message": "SKILL.md body is very short — expected at least a usage example",
        })

    # Optional: spec.yaml
    spec_yaml = skill_dir / "spec.yaml"
    if spec_yaml.exists():
        try:
            spec = parse_spec_yaml(spec_yaml)
            report["has_spec"] = True
            report["spec"] = spec
            cat = spec.get("category")
            if cat and cat not in VALID_CATEGORIES:
                report["issues"].append({
                    "severity": "warn",
                    "message": f"spec.category '{cat}' not in known set {sorted(VALID_CATEGORIES)}",
                })
            owner = spec.get("owner_agent")
            if owner and owner not in VALID_OWNERS:
                report["issues"].append({
                    "severity": "warn",
                    "message": f"spec.owner_agent '{owner}' not in known set {sorted(VALID_OWNERS)}",
                })
        except Exception as exc:  # noqa: BLE001
            report["issues"].append({"severity": "error", "message": f"spec.yaml parse: {exc}"})
            report["valid"] = False

    # Optional: run.py
    run_py = skill_dir / "run.py"
    if run_py.exists():
        report["runnable"] = True
        test_py = skill_dir / "test.py"
        if not test_py.exists():
            report["issues"].append({
                "severity": "warn",
                "message": "run.py exists but test.py is missing — runnable skills should have tests",
            })
        else:
            report["has_test"] = True

    return report


# ---- Create (scaffold) ------------------------------------------------------

SKILL_MD_TEMPLATE = """---
name: {name}
description: {description}
---

# {title}

> **One-line summary.** What this skill does, in the sentence a busy
> founder would read.

## Why this skill exists

Explain the problem this solves. Be concrete — what was broken / missing
before, what this closes, and what downstream systems now rely on it.

## Usage

### From Python (importable)

```python
from scripts.{module_name} import main_function

result = main_function(
    arg1="...",
    arg2=...,
)
```

### From the CLI

```
python scripts/{module_name}.py <command> [--flags]
```

## When to use this

- Trigger 1: <plain-English phrase CC might say>
- Trigger 2: <another phrase>

## When NOT to use this

- <situation>: use `<other skill>` instead
- <situation>: escalate to CC

## Related files

- `scripts/{module_name}.py` — the implementation
- `scripts/test_{module_name}.py` — the tests
- `skills/{name}/spec.yaml` — structured metadata

## Tests

Run: `python scripts/test_{module_name}.py`

All tests must pass before any change to this skill ships.
"""

SPEC_YAML_TEMPLATE = """# Structured metadata for skill "{name}"
# Consumed by register_skill.py + future skill composition tools.

name: {name}
description: {description}
category: {category}
owner_agent: bravo

# When CC might trigger this (plain-English phrases the router matches)
when_to_use:
  - "TODO add trigger phrase"

# What the skill takes in (JSON-schema style, loose)
inputs:
  example_input:
    type: string
    required: true
    description: "TODO"

# What the skill produces
outputs:
  example_output:
    type: dict
    description: "TODO"

# What must be true before calling
preconditions:
  - "TODO (e.g. '.env.agents contains FOO_API_KEY')"

# What this skill changes (writes, network calls, side effects)
side_effects:
  - "TODO (e.g. 'writes to lead_interactions table')"

# CLI entry point, if runnable
cli_entry: "python scripts/{module_name}.py"

# Version + ownership
version: "0.1.0"
created: {today}
"""

RUN_PY_TEMPLATE = '''"""
{title} — skill implementation.

See skills/{name}/SKILL.md for the full contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main_function(arg1: str = "", arg2: int = 0) -> dict:
    """TODO — replace with the actual implementation."""
    return {{
        "status": "ok",
        "arg1": arg1,
        "arg2": arg2,
        "note": "replace main_function body with real logic",
    }}


def main() -> None:
    p = argparse.ArgumentParser(description="{title}")
    p.add_argument("--json", dest="output_json", action="store_true")
    p.add_argument("--arg1", default="")
    p.add_argument("--arg2", type=int, default=0)
    args = p.parse_args()

    result = main_function(arg1=args.arg1, arg2=args.arg2)
    if args.output_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(result)


if __name__ == "__main__":
    main()
'''

TEST_PY_TEMPLATE = '''"""Tests for the {name} skill."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from {module_name} import main_function


class Test{class_name}(unittest.TestCase):

    def test_main_function_returns_ok(self):
        result = main_function(arg1="hello", arg2=42)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["arg1"], "hello")
        self.assertEqual(result["arg2"], 42)


if __name__ == "__main__":
    unittest.main()
'''


def cmd_create(args) -> int:
    name = args.name.strip().lower().replace(" ", "-")
    if not re.match(r"^[a-z][a-z0-9-]{1,48}$", name):
        print(f"ERROR: invalid skill name '{name}' "
              "(must be kebab-case, 2-49 chars, start with a letter)",
              file=sys.stderr)
        return 1
    skill_dir = SKILLS_DIR / name
    if skill_dir.exists() and not args.force:
        print(f"ERROR: skill folder already exists: {skill_dir}\n"
              "Use --force to overwrite.",
              file=sys.stderr)
        return 1

    description = args.description or f"TODO: describe what '{name}' does in one sentence."
    category = args.category or "general"
    title = " ".join(w.capitalize() for w in name.split("-"))
    module_name = name.replace("-", "_")
    class_name = "".join(w.capitalize() for w in name.split("-"))
    today = datetime.now(timezone.utc).date().isoformat()

    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        SKILL_MD_TEMPLATE.format(
            name=name, description=description, title=title, module_name=module_name,
        ),
        encoding="utf-8",
    )
    (skill_dir / "spec.yaml").write_text(
        SPEC_YAML_TEMPLATE.format(
            name=name, description=description, category=category,
            module_name=module_name, today=today,
        ),
        encoding="utf-8",
    )
    if args.runnable:
        (skill_dir / "run.py").write_text(
            RUN_PY_TEMPLATE.format(name=name, title=title),
            encoding="utf-8",
        )
        (skill_dir / "test.py").write_text(
            TEST_PY_TEMPLATE.format(
                name=name, module_name=module_name, class_name=class_name,
            ),
            encoding="utf-8",
        )

    result = {
        "status": "created",
        "name": name,
        "path": str(skill_dir),
        "files": sorted(p.name for p in skill_dir.iterdir()),
        "runnable": args.runnable,
        "next_step": f"python scripts/register_skill.py register {name}",
    }
    if args.output_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"Skill scaffolded at {skill_dir}")
        print(f"  Files: {', '.join(result['files'])}")
        print(f"\n  Next: {result['next_step']}")
    return 0


# ---- Register ---------------------------------------------------------------

def cmd_register(args) -> int:
    name = args.name.strip()
    report = validate_skill(name)
    if not report["valid"]:
        print(f"ERROR: skill '{name}' is invalid. Fix these issues first:",
              file=sys.stderr)
        for i in report["issues"]:
            print(f"  [{i['severity']}] {i['message']}", file=sys.stderr)
        return 1

    fm = report["frontmatter"]
    spec = report["spec"]
    now = datetime.now(timezone.utc).isoformat()

    row = {
        "skill_name": fm.get("name") or name,
        "skill_path": str((SKILLS_DIR / name).relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "description": fm.get("description"),
        "category": spec.get("category"),
        "is_active": True,
        "updated_at": now,
    }
    existing_id: Optional[str] = None
    try:
        db = get_supabase()
        existing = (db.table("skills_registry")
                    .select("id,usage_count")
                    .eq("skill_name", row["skill_name"])
                    .limit(1).execute().data) or []
        if existing:
            existing_id = existing[0]["id"]
            db.table("skills_registry").update(row).eq("id", existing_id).execute()
            status = "updated"
        else:
            row["usage_count"] = 0
            row["success_count"] = 0
            res = db.table("skills_registry").insert(row).execute()
            existing_id = res.data[0]["id"] if res.data else None
            status = "inserted"
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: skills_registry write failed: {exc}", file=sys.stderr)
        return 1

    # Build the one-line row CC should paste into brain/CAPABILITIES.md
    # under whatever Skills table he maintains.
    docs_line = (
        f"| `{row['skill_name']}` | {row.get('category') or '—'} | "
        f"{row.get('description') or ''} | [SKILL.md]({row['skill_path']}/SKILL.md) |"
    )

    result = {
        "status": status,
        "skill_name": row["skill_name"],
        "skill_id": existing_id,
        "validation": report,
        "paste_into_capabilities_md": docs_line,
    }
    if args.output_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"Skill '{row['skill_name']}' {status} in skills_registry.")
        print(f"  id: {existing_id}")
        print(f"  runnable: {report['runnable']}  test: {report['has_test']}  spec: {report['has_spec']}")
        if report["issues"]:
            print("  warnings:")
            for i in report["issues"]:
                if i["severity"] == "warn":
                    print(f"    • {i['message']}")
        print()
        print("If you want it in the docs, paste this row under a Skills table in brain/CAPABILITIES.md:")
        print(f"  {docs_line}")
    return 0


# ---- List -------------------------------------------------------------------

def cmd_list(args) -> int:
    try:
        db = get_supabase()
        rows = (db.table("skills_registry")
                .select("skill_name,description,category,usage_count,last_used,is_active")
                .order("skill_name", desc=False)
                .limit(1000).execute().data) or []
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.output_json:
        print(json.dumps(rows, indent=2, default=str))
        return 0
    if not rows:
        print("No skills registered yet.")
        return 0
    print(f"Registered skills ({len(rows)}):\n")
    for r in rows:
        active = "✓" if r.get("is_active") else "✗"
        last = (r.get("last_used") or "")[:10] or "—"
        print(f"  {active}  {r['skill_name']:30}  "
              f"{(r.get('category') or '—'):15}  "
              f"used={r.get('usage_count') or 0:>4}  "
              f"last={last}")
    return 0


# ---- Audit ------------------------------------------------------------------

def cmd_audit(args) -> int:
    """Cross-check folder skills vs registry vs CAPABILITIES.md mentions."""
    # 1. Scan the skills folder
    folder_skills: dict[str, dict] = {}
    if SKILLS_DIR.exists():
        for entry in sorted(SKILLS_DIR.iterdir()):
            if not entry.is_dir():
                continue
            if (entry / "SKILL.md").exists():
                folder_skills[entry.name] = validate_skill(entry.name)

    # 2. Pull the registry
    registry_skills: dict[str, dict] = {}
    try:
        db = get_supabase()
        rows = (db.table("skills_registry")
                .select("skill_name,skill_path,is_active")
                .limit(1000).execute().data) or []
        for r in rows:
            registry_skills[r["skill_name"]] = r
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: skills_registry read failed: {exc}", file=sys.stderr)

    # 3. Scan CAPABILITIES.md for mentions
    capabilities_mentions: set[str] = set()
    if CAPABILITIES_FILE.exists():
        cap_text = CAPABILITIES_FILE.read_text(encoding="utf-8")
        for name in folder_skills.keys():
            # Any mention of skills/<name> or the skill name in backticks
            if f"skills/{name}" in cap_text or f"`{name}`" in cap_text:
                capabilities_mentions.add(name)

    # 4. Compute drift
    folder_names = set(folder_skills.keys())
    registry_names = set(registry_skills.keys())

    in_folder_not_registered = sorted(folder_names - registry_names)
    in_registry_folder_missing = sorted(registry_names - folder_names)
    in_folder_not_in_docs = sorted(folder_names - capabilities_mentions)
    invalid_skills = [name for name, r in folder_skills.items() if not r["valid"]]

    report = {
        "summary": {
            "total_in_folder": len(folder_skills),
            "total_in_registry": len(registry_skills),
            "total_in_capabilities_md": len(capabilities_mentions),
            "invalid": len(invalid_skills),
            "in_folder_not_registered": len(in_folder_not_registered),
            "in_registry_folder_missing": len(in_registry_folder_missing),
            "in_folder_not_in_docs": len(in_folder_not_in_docs),
        },
        "invalid_skills": invalid_skills,
        "in_folder_not_registered": in_folder_not_registered,
        "in_registry_folder_missing": in_registry_folder_missing,
        "in_folder_not_in_docs": in_folder_not_in_docs,
    }
    if args.output_json:
        print(json.dumps(report, indent=2, default=str))
        return 0

    s = report["summary"]
    print("Skill library audit")
    print("-" * 60)
    print(f"  Folder:          {s['total_in_folder']} skills with SKILL.md")
    print(f"  Registry:        {s['total_in_registry']} rows in skills_registry")
    print(f"  CAPABILITIES.md: {s['total_in_capabilities_md']} mentioned")
    print()
    if invalid_skills:
        print(f"  ✗ INVALID STRUCTURE ({len(invalid_skills)}):")
        for n in invalid_skills:
            r = folder_skills[n]
            for issue in r["issues"]:
                if issue["severity"] == "error":
                    print(f"      {n}: {issue['message']}")
    if in_folder_not_registered:
        print(f"\n  • IN FOLDER, NOT REGISTERED ({len(in_folder_not_registered)}):")
        for n in in_folder_not_registered[:20]:
            print(f"      {n}")
        if len(in_folder_not_registered) > 20:
            print(f"      ... and {len(in_folder_not_registered)-20} more")
        print(f"    Fix: python scripts/register_skill.py register <name>")
    if in_registry_folder_missing:
        print(f"\n  ✗ IN REGISTRY, FOLDER MISSING ({len(in_registry_folder_missing)}):")
        for n in in_registry_folder_missing:
            print(f"      {n}")
        print(f"    Fix: either restore the folder or deactivate the registry row.")
    if in_folder_not_in_docs:
        print(f"\n  • IN FOLDER, NOT MENTIONED IN brain/CAPABILITIES.md "
              f"({len(in_folder_not_in_docs)}):")
        for n in in_folder_not_in_docs[:10]:
            print(f"      {n}")
        if len(in_folder_not_in_docs) > 10:
            print(f"      ... and {len(in_folder_not_in_docs)-10} more")
    if (not invalid_skills and not in_folder_not_registered
            and not in_registry_folder_missing and not in_folder_not_in_docs):
        print("  All clean. Zero drift.")
    return 0


# ---- Validate (single skill) -----------------------------------------------

def cmd_validate(args) -> int:
    report = validate_skill(args.name)
    if args.output_json:
        print(json.dumps(report, indent=2, default=str))
        return 0 if report["valid"] else 1

    print(f"Validating skill '{args.name}':")
    print(f"  path: {report['path']}")
    print(f"  valid: {report['valid']}")
    print(f"  runnable: {report['runnable']}   test: {report['has_test']}   spec: {report['has_spec']}")
    if report["frontmatter"]:
        print(f"  name (frontmatter): {report['frontmatter'].get('name')}")
        print(f"  description: {(report['frontmatter'].get('description') or '')[:120]}")
    if report["issues"]:
        print("  Issues:")
        for i in report["issues"]:
            print(f"    [{i['severity']}] {i['message']}")
    else:
        print("  No issues. Clean.")
    return 0 if report["valid"] else 1


# ---- CLI --------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        prog="register_skill.py",
        description="Onboard and audit skills. The 'clean the system' command.",
    )
    p.add_argument("--json", dest="output_json", action="store_true")
    sub = p.add_subparsers(dest="command")

    pc = sub.add_parser("create", help="Scaffold a new skill folder")
    pc.add_argument("name", help="Kebab-case skill name (e.g. 'lead-scoring')")
    pc.add_argument("--description", default=None)
    pc.add_argument("--category", default=None, choices=sorted(VALID_CATEGORIES))
    pc.add_argument("--runnable", action="store_true",
                     help="Include run.py + test.py scaffolds")
    pc.add_argument("--force", action="store_true", help="Overwrite existing folder")

    pr = sub.add_parser("register",
                         help="Wire an existing skill into skills_registry + docs")
    pr.add_argument("name")

    sub.add_parser("list", help="List all skills in the registry")

    pa = sub.add_parser("audit",
                         help="Report drift between folder, registry, and CAPABILITIES.md")
    pa  # no extra args

    pv = sub.add_parser("validate", help="Deep-check one skill's structure")
    pv.add_argument("name")

    args = p.parse_args()
    if args.command == "create":
        sys.exit(cmd_create(args))
    elif args.command == "register":
        sys.exit(cmd_register(args))
    elif args.command == "list":
        sys.exit(cmd_list(args))
    elif args.command == "audit":
        sys.exit(cmd_audit(args))
    elif args.command == "validate":
        sys.exit(cmd_validate(args))
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
