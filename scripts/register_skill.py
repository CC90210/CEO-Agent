"""
Register Skill — the skill-onboarding tool.

Before this tool, adding a new skill was a five-file manual mess: create
SKILL.md, manually add to brain/CAPABILITIES.md, update brain/QUICK_REFERENCE.md,
insert into the skills_registry Turso table, and hope nothing drifted.
Forgetting step 2 was the most common failure — skills existed in the
folder but weren't discoverable.

This module fixes that. Six subcommands:

  create    — scaffold a brand-new skill folder with templates
  register  — wire an existing skill into skills_registry + doc index
  sync-all  — idempotently upsert every folder skill into skills_registry
  route     — rank active skills for a plain-English task
  list      — print all skills from the registry
  audit     — find drift: skills in folder not in registry, etc.
  validate  — deep structural check on one skill

USAGE
-----
    # Start a new skill from templates
    python scripts/register_skill.py create my-new-skill --category content

    # Wire it up (idempotent)
    python scripts/register_skill.py register my-new-skill

    # Runtime-sync the whole library
    python scripts/register_skill.py sync-all --deactivate-missing --json

    # Ask the runtime catalog which skills to load
    python scripts/register_skill.py route "send follow-up emails to warm leads" --json

    # See what's registered
    python scripts/register_skill.py list --json

    # Find drift — this is the "clean the system" command
    python scripts/register_skill.py audit --json

    # Deep-check one skill
    python scripts/register_skill.py validate send-gateway

DESIGN
------
1. The `skills/` folder is the source of truth for WHAT exists.
2. The Turso `skills_registry` table is runtime truth: which skills are
   active, how they are activated, which agent owns them, usage counts, last
   used, and drift hashes. Migration 016 adds the orchestration metadata.
3. brain/CAPABILITIES.md is a human-readable doc index. This tool does NOT
   auto-edit CAPABILITIES.md — that's fragile. Instead `register` prints
   the exact one-line row for CC to paste in, and `audit` reports drift.
4. `create` scaffolds real templates, not placeholders — the SKILL.md it
   writes has real structure and the run.py it writes actually runs
   (just prints a hello message).

The whole tool follows the V5.6 conventions: reads .env.agents, --json flag,
fail-closed on DB errors, zero hardcoded credentials.
"""

from __future__ import annotations

import argparse
import hashlib
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
SKILLS_INDEX_FILE = PROJECT_ROOT / "skills" / "INDEX.md"

CORE_SKILLS = {
    "task-routing",
    "send-gateway",
    "email-safety",
    "systematic-debugging",
    "memory-management",
    "self-healing",
    "security-protocol",
    "verification-before-completion",
    "context-optimization",
    "state-sync",
    "codex-delegation",
    "agent-permissions",
    "anti-drift",
}

STANDARD_SKILLS = {
    "code-review",
    "test-driven-development",
    "ship",
    "executing-plans",
    "writing-plans",
    "supabase-patterns",
    "n8n-patterns",
    "python-daemon-automation",
    "browser-harness",
    "browser-automation",
    "web-scraping",
    "lead-management",
    "outreach-send",
    "sales-closing",
    "sales-methodology",
    "client-success",
    "proposal-generation",
    "ceo-dashboard",
    "ceo-briefing",
    "daily-planner",
}

CATEGORY_TRIGGERS = {
    "orchestration": ["route task", "delegate", "agent", "multi-agent"],
    "development": ["code", "bug", "test", "review", "ship"],
    "database": ["database", "supabase", "migration", "sql", "schema"],
    "communication": ["email", "message", "reply", "outbound"],
    "sales": ["lead", "prospect", "follow up", "close", "outreach"],
    "revenue": ["mrr", "stripe", "invoice", "revenue", "pricing"],
    "content": ["content", "post", "copy", "caption", "brand"],
    "browser": ["browser", "website", "playwright", "scrape", "click"],
    "memory": ["memory", "knowledge", "context", "recall"],
    "security": ["security", "credential", "risk", "approval"],
    "google": ["gmail", "calendar", "drive", "sheets", "docs", "google"],
    "persona": ["persona", "voice", "role"],
    "creative": ["design", "visual", "theme", "artifact"],
    "documents": ["pdf", "docx", "pptx", "xlsx", "document"],
    "operations": ["ops", "project", "meeting", "workflow", "process"],
}

CATEGORY_PREFIXES = [
    ("gws-", "google"),
    ("persona-", "persona"),
    ("browser-", "browser"),
    ("web", "browser"),
    ("n8n", "automation"),
    ("mcp", "integration"),
]

CATEGORY_OVERRIDES = {
    "agent-runtime-packaging": "orchestration",
    "algorithmic-art": "creative",
    "booking-management": "sales",
    "canvas-design": "creative",
    "client-success": "operations",
    "code-review": "development",
    "doc-coauthoring": "documents",
    "docx": "documents",
    "e2e-testing": "development",
    "email-safety": "communication",
    "ethical-hacking": "security",
    "frontend-design": "creative",
    "internal-comms": "communication",
    "pdf": "documents",
    "pptx": "documents",
    "proposal-generation": "sales",
    "python-daemon-automation": "development",
    "revenue-operations": "revenue",
    "send-gateway": "communication",
    "skool-automation": "content",
    "slack-gif-creator": "creative",
    "sop-breakdown": "operations",
    "strategic-planning": "operations",
    "team-management": "operations",
    "telegram-demo-workflows": "content",
    "test-driven-development": "development",
    "verification-before-completion": "development",
    "writing-plans": "operations",
    "writing-skills": "meta",
    "xlsx": "documents",
}

CATEGORY_KEYWORDS = [
    ("supabase", "database"),
    ("database", "database"),
    ("migration", "database"),
    ("gmail", "google"),
    ("google", "google"),
    ("outreach", "sales"),
    ("sales", "sales"),
    ("lead", "sales"),
    ("proposal", "sales"),
    ("booking", "sales"),
    ("revenue", "revenue"),
    ("stripe", "revenue"),
    ("financial", "revenue"),
    ("content", "content"),
    ("brand", "content"),
    ("linkedin", "content"),
    ("skool", "content"),
    ("video", "content"),
    ("browser", "browser"),
    ("scraping", "browser"),
    ("test", "development"),
    ("debug", "development"),
    ("review", "development"),
    ("ship", "development"),
    ("git", "development"),
    ("security", "security"),
    ("ethical-hacking", "security"),
    ("memory", "memory"),
    ("knowledge", "memory"),
    ("agent", "orchestration"),
    ("routing", "orchestration"),
    ("drift", "orchestration"),
    ("planning", "operations"),
    ("project", "operations"),
    ("meeting", "operations"),
    ("risk", "operations"),
    ("pdf", "documents"),
    ("docx", "documents"),
    ("pptx", "documents"),
    ("xlsx", "documents"),
    ("canvas", "creative"),
    ("design", "creative"),
    ("theme", "creative"),
]

ALLOWED_TIERS = {"core", "standard", "specialized", "dormant"}
TIER_ALIASES = {
    "advanced": "specialized",
    "full": "specialized",
    "special": "specialized",
    "strategic": "specialized",
}

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


# ---- Metadata synthesis -----------------------------------------------------

def _as_list(value: Any) -> list[str]:
    """Normalize frontmatter/spec values into a clean list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if item is None:
            continue
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key not in seen:
            out.append(text)
            seen.add(key)
    return out


def _limit_list(values: list[str], limit: int = 32) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        v = re.sub(r"\s+", " ", str(value).strip())
        if not v:
            continue
        key = v.lower()
        if key in seen:
            continue
        out.append(v)
        seen.add(key)
        if len(out) >= limit:
            break
    return out


def _skill_body_links(body: str, current_name: str) -> list[str]:
    """Extract skill-to-skill links from markdown body for composability."""
    links: list[str] = []
    patterns = [
        r"skills/([a-z0-9-]+)/SKILL",
        r"\[\[skills/([a-z0-9-]+)/SKILL",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, body, flags=re.IGNORECASE):
            name = match.lower()
            if name != current_name:
                links.append(name)
    return _limit_list(links, limit=24)


def _source_hash(skill_dir: Path) -> str:
    h = hashlib.sha256()
    for filename in ("SKILL.md", "spec.yaml"):
        p = skill_dir / filename
        if p.exists():
            h.update(filename.encode("utf-8"))
            h.update(p.read_bytes())
    return h.hexdigest()


def infer_category(name: str, fm: dict, spec: dict) -> str:
    if name in CATEGORY_OVERRIDES:
        return CATEGORY_OVERRIDES[name]
    explicit = (spec.get("category") or fm.get("category") or "").strip().lower()
    if explicit:
        return explicit
    for prefix, category in CATEGORY_PREFIXES:
        if name.startswith(prefix):
            return category
    haystack = f"{name} {fm.get('description') or ''}".lower()
    for keyword, category in CATEGORY_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", haystack):
            return category
    return "general"


def infer_owner_agent(name: str, category: str, fm: dict, spec: dict) -> str:
    explicit = (spec.get("owner_agent") or fm.get("owner_agent") or "").strip().lower()
    if explicit in VALID_OWNERS:
        return explicit
    if category in {"content", "creative"} or name in {
        "brand-guidelines", "content-engine", "frontend-design", "linkedin-outreach",
        "persona-content-creator", "telegram-demo-workflows",
    }:
        return "maven"
    if category == "revenue" and name in {"financial-modeling", "investor-materials"}:
        return "atlas"
    if category in {"database", "development"} or name in {
        "codex-delegation", "systematic-debugging", "code-review",
        "test-driven-development", "supabase-patterns", "python-daemon-automation",
        "e2e-testing", "webapp-testing",
    }:
        return "codex"
    if name in {"computer-control", "daily-planner"}:
        return "aura"
    return "bravo"


def infer_tier(name: str, category: str, fm: dict, spec: dict) -> str:
    explicit = (spec.get("tier") or fm.get("tier") or "").strip().lower()
    if explicit:
        return explicit if explicit in ALLOWED_TIERS else TIER_ALIASES.get(explicit, "specialized")
    if name in CORE_SKILLS:
        return "core"
    if name in STANDARD_SKILLS or category in {
        "database", "development", "operations", "orchestration", "sales",
    }:
        return "standard"
    return "specialized"


def infer_risk(name: str, category: str, fm: dict, spec: dict, body: str) -> tuple[str, bool]:
    explicit = (spec.get("risk_level") or fm.get("risk_level") or "").strip().lower()
    tags = {t.lower() for t in _as_list(fm.get("tags")) + _as_list(spec.get("tags"))}
    text = f"{name} {category} {' '.join(tags)} {body[:2000]}".lower()
    requires_approval = bool(spec.get("requires_approval") or fm.get("requires_approval"))
    if explicit:
        return explicit, requires_approval or explicit in {"approval", "destructive"}
    if "destructive" in tags:
        return "destructive", True
    if re.search(r"\b(rm\s+-rf|drop\s+table|truncate\s+table|force[- ]push)\b", text):
        return "sensitive", requires_approval
    if category in {"communication", "sales"} or name in {
        "send-gateway", "outreach-send", "email-safety", "gws-gmail-send",
        "gws-chat-send", "booking-management",
    }:
        return "approval", True
    if category in {"security", "database"} or "credential" in text or "production" in text:
        return "sensitive", requires_approval
    return "normal", requires_approval


def synthesize_triggers(name: str, category: str, fm: dict, spec: dict) -> list[str]:
    description = str(fm.get("description") or "")
    values = []
    values.extend(_as_list(fm.get("triggers")))
    values.extend(_as_list(spec.get("triggers")))
    values.extend(_as_list(spec.get("when_to_use")))
    values.append(name)
    values.append(name.replace("-", " "))
    values.extend(part for part in name.split("-") if len(part) > 2)
    values.extend(CATEGORY_TRIGGERS.get(category, []))
    # Pull short "Use when:" hints out of one-line descriptions.
    for match in re.findall(r"use when(?:ever)?:?\s*([^.;]+)", description, flags=re.IGNORECASE):
        values.append(match.strip())
    return _limit_list(values, limit=32)


def build_skill_row(name: str, report: dict, now: str) -> dict[str, Any]:
    fm = report["frontmatter"]
    spec = report["spec"]
    skill_dir = SKILLS_DIR / name
    _, body = parse_skill_md(skill_dir / "SKILL.md")
    category = infer_category(name, fm, spec)
    owner_agent = infer_owner_agent(name, category, fm, spec)
    tier = infer_tier(name, category, fm, spec)
    risk_level, requires_approval = infer_risk(name, category, fm, spec, body)
    tags = _limit_list(_as_list(fm.get("tags")) + _as_list(spec.get("tags")), limit=24)
    dependencies = _limit_list(
        _as_list(fm.get("dependencies"))
        + _as_list(spec.get("dependencies"))
        + _skill_body_links(body, name),
        limit=24,
    )
    when_to_use = _limit_list(
        _as_list(spec.get("when_to_use")) + _as_list(fm.get("when_to_use")),
        limit=24,
    )
    cli_entry = spec.get("cli_entry")
    if not cli_entry and (skill_dir / "run.py").exists():
        cli_entry = f"python skills/{name}/run.py"

    # Frontmatter `archived: <date>` deactivates a skill at the registry level
    # without deleting the file (per the EVOLVE-not-DELETE principle). The
    # `superseded_by:` field is informational — surfaced via orchestration_notes
    # so the operator sees the redirect target.
    # PyYAML parses bare ISO dates as datetime.date objects which json.dumps
    # rejects later in sync-all; coerce to string at read-time.
    raw_archived = fm.get("archived") or spec.get("archived")
    archived = str(raw_archived) if raw_archived else None
    # disable-model-invocation: true → also deactivate at the registry level
    # (auto-generated CLI references like gws-gmail-send opt out of being routable;
    # see memory/feedback_skill_routing_disable_invocation.md, 2026-05-16).
    disable_invoke = bool(fm.get("disable-model-invocation") or fm.get("disable_model_invocation"))
    is_active = not (bool(archived) or disable_invoke)

    return {
        "skill_name": fm.get("name") or name,
        "skill_path": str(skill_dir.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "description": fm.get("description"),
        "category": category,
        "dependencies": dependencies,
        "is_active": is_active,
        "updated_at": now,
        "triggers": synthesize_triggers(name, category, fm, spec),
        "tags": tags,
        "tier": tier,
        "owner_agent": owner_agent,
        "when_to_use": when_to_use,
        "inputs": spec.get("inputs") or {},
        "outputs": spec.get("outputs") or {},
        "preconditions": _as_list(spec.get("preconditions")),
        "side_effects": _as_list(spec.get("side_effects")),
        "cli_entry": cli_entry,
        "risk_level": risk_level,
        "requires_approval": requires_approval,
        "source_hash": _source_hash(skill_dir),
        "frontmatter": fm,
        "spec": spec,
        "orchestration_notes": (
            f"tier={tier}; owner={owner_agent}; risk={risk_level}; "
            f"category={category}"
            + (f"; archived={archived}" if archived else "")
            + (f"; superseded_by={fm.get('superseded_by')}"
               if fm.get("superseded_by") else "")
        ),
    }


# ---- Structural validation --------------------------------------------------

VALID_CATEGORIES = {
    "revenue", "content", "infrastructure", "operations", "sales",
    "communication", "automation", "memory", "security", "compliance",
    "integration", "analytics", "meta", "general", "admin", "browser",
    "business", "code", "database", "development", "documents", "google",
    "orchestration", "persona", "creative",
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
    else:
        fm_name = fm.get("name")
        # Accept either full path match (for top-level skills) or basename match
        # (for nested skills like auto-generated/<slug> where frontmatter holds the slug).
        basename = name.rsplit("/", 1)[-1] if "/" in name else name
        if fm_name != name and fm_name != basename:
            report["valid"] = False
            report["issues"].append({
                "severity": "error",
                "message": f"frontmatter name '{fm_name}' does not match folder '{name}' (or basename '{basename}')",
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

def _script_refs_in_skill(name: str) -> list[dict]:
    """Scan a skill's SKILL.md body for `scripts/<x>.py` references and check
    each exists on disk. Returns list of {ref, exists} dicts.

    Catches the case where a new SKILL.md confidently references a backing
    script that was never written (or got renamed). Per the Architecture
    Certification verification contract: a skill claiming a script must
    actually have that script on disk.
    """
    skill_md = SKILLS_DIR / name / "SKILL.md"
    if not skill_md.exists():
        return []
    body = skill_md.read_text(encoding="utf-8", errors="replace")
    # Match `scripts/<slug>.py` with optional path-y prefix; slug is alnum + _ + -
    refs = re.findall(r"scripts/([A-Za-z0-9_\-]+\.py)", body)
    seen = []
    out = []
    for ref in refs:
        if ref in seen:
            continue
        seen.append(ref)
        exists = (PROJECT_ROOT / "scripts" / ref).exists()
        out.append({"ref": f"scripts/{ref}", "exists": exists})
    return out


def cmd_register(args) -> int:
    name = args.name.strip()
    report = validate_skill(name)
    if not report["valid"]:
        print(f"ERROR: skill '{name}' is invalid. Fix these issues first:",
              file=sys.stderr)
        for i in report["issues"]:
            print(f"  [{i['severity']}] {i['message']}", file=sys.stderr)
        return 1

    # Smoke check — every script the skill claims to use must exist on disk.
    script_refs = _script_refs_in_skill(name)
    missing_refs = [r for r in script_refs if not r["exists"]]
    if missing_refs and not getattr(args, "skip_script_check", False):
        print(f"ERROR: skill '{name}' references scripts that don't exist:",
              file=sys.stderr)
        for r in missing_refs:
            print(f"  • {r['ref']}", file=sys.stderr)
        print("\nFix the references in SKILL.md, write the missing script(s), "
              "or pass --skip-script-check if these are intentional placeholders.",
              file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc).isoformat()
    row = build_skill_row(name, report, now)
    # PyYAML parses ISO datetime strings in frontmatter into datetime objects.
    # Supabase/postgrest serializes via json.dumps which rejects datetime — coerce
    # the entire row to JSON-safe primitives before the upsert.
    row = json.loads(json.dumps(row, default=str))
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


# ---- Sync all ---------------------------------------------------------------

def _folder_skill_names() -> list[str]:
    if not SKILLS_DIR.exists():
        return []
    return sorted(
        entry.name
        for entry in SKILLS_DIR.iterdir()
        if entry.is_dir() and (entry / "SKILL.md").exists()
    )


def cmd_sync_all(args) -> int:
    """Upsert every valid folder skill into skills_registry.

    This is the production path for turning the markdown skill library into a
    runtime orchestration catalog. It is idempotent and preserves usage counts
    by not writing usage_count/success_count on existing rows.
    """
    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []

    for name in _folder_skill_names():
        report = validate_skill(name)
        if not report["valid"]:
            invalid.append({"name": name, "issues": report["issues"]})
            continue
        rows.append(build_skill_row(name, report, now))

    if invalid and not args.skip_invalid:
        result = {
            "status": "blocked",
            "reason": "invalid skills present",
            "invalid": invalid,
            "valid_rows": len(rows),
        }
        if args.output_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print("ERROR: sync blocked because invalid skills exist.", file=sys.stderr)
            for item in invalid:
                print(f"  {item['name']}", file=sys.stderr)
                for issue in item["issues"]:
                    print(f"    [{issue['severity']}] {issue['message']}", file=sys.stderr)
        return 1

    try:
        db = get_supabase()
        before_rows = (db.table("skills_registry")
                       .select("skill_name,is_active")
                       .limit(1000).execute().data) or []
        before_names = {r["skill_name"] for r in before_rows}
        # PyYAML parses ISO dates in frontmatter as datetime.date; postgrest
        # rejects those. Same fix as cmd_register: round-trip through json
        # with default=str to coerce all date/datetime objects to strings.
        rows = json.loads(json.dumps(rows, default=str))
        result = db.table("skills_registry").upsert(
            rows,
            on_conflict="skill_name",
        ).execute()

        deactivated: list[str] = []
        if args.deactivate_missing:
            folder_names = {r["skill_name"] for r in rows}
            missing = sorted(before_names - folder_names)
            for skill_name in missing:
                update_row = {
                    "is_active": False,
                    "updated_at": now,
                }
                # Migration 016 columns may not exist in older installs; if
                # they do, this gives old rows a clear retired state.
                update_row["tier"] = "dormant"
                update_row["risk_level"] = "normal"
                update_row["orchestration_notes"] = "No matching folder skill; deactivated by sync-all."
                db.table("skills_registry").update(update_row).eq(
                    "skill_name", skill_name,
                ).execute()
                deactivated.append(skill_name)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: skills_registry sync failed: {exc}", file=sys.stderr)
        return 1

    inserted_or_updated = len(result.data or rows)
    summary = {
        "status": "synced",
        "folder_skills": len(_folder_skill_names()),
        "upserted": inserted_or_updated,
        "invalid_skipped": len(invalid),
        "deactivated_missing": deactivated,
        "owners": {},
        "tiers": {},
        "categories": {},
    }
    for row in rows:
        summary["owners"][row["owner_agent"]] = summary["owners"].get(row["owner_agent"], 0) + 1
        summary["tiers"][row["tier"]] = summary["tiers"].get(row["tier"], 0) + 1
        summary["categories"][row["category"]] = summary["categories"].get(row["category"], 0) + 1

    if args.output_json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        print(f"Synced {inserted_or_updated} skills into skills_registry.")
        print(f"  Folder skills: {summary['folder_skills']}")
        print(f"  Invalid skipped: {summary['invalid_skipped']}")
        print(f"  Deactivated missing rows: {len(deactivated)}")
        print(f"  Tiers: {summary['tiers']}")
        print(f"  Owners: {summary['owners']}")
    return 0


# ---- Route ------------------------------------------------------------------

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "for",
    "from", "have", "i", "in", "is", "it", "me", "my", "of", "on", "or",
    "our", "the", "this", "to", "we", "with", "you",
}


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9-]{2,}", text.lower())
        if token not in STOP_WORDS
    }


def _score_route(query: str, row: dict[str, Any]) -> tuple[int, list[str]]:
    q = query.lower()
    q_tokens = _tokens(query)
    score = 0
    reasons: list[str] = []

    name = (row.get("skill_name") or "").lower()
    name_text = name.replace("-", " ")
    if name and (name in q or name_text in q):
        score += 12
        reasons.append("name match")

    category = (row.get("category") or "").lower()
    if category and category in q_tokens:
        score += 5
        reasons.append(f"category:{category}")

    tier = (row.get("tier") or "").lower()
    if tier == "core":
        score += 1

    triggers = row.get("triggers") or []
    for trigger in triggers:
        t = str(trigger).lower().strip()
        if not t:
            continue
        if t in q:
            score += 10
            reasons.append(f"trigger:{trigger}")
            continue
        overlap = q_tokens & _tokens(t)
        if overlap:
            score += min(6, 2 * len(overlap))
            reasons.append(f"trigger overlap:{','.join(sorted(overlap))}")

    desc = str(row.get("description") or "")
    desc_overlap = q_tokens & _tokens(desc)
    if desc_overlap:
        score += min(6, len(desc_overlap))
        reasons.append(f"description overlap:{','.join(sorted(desc_overlap)[:5])}")

    return score, _limit_list(reasons, limit=6)


def cmd_route(args) -> int:
    try:
        db = get_supabase()
        rows = (db.table("skills_registry")
                .select("skill_name,skill_path,description,category,tier,owner_agent,risk_level,requires_approval,triggers,is_active")
                .eq("is_active", True)
                .limit(1000).execute().data) or []
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: skills_registry route read failed: {exc}", file=sys.stderr)
        return 1

    ranked: list[dict[str, Any]] = []
    for row in rows:
        score, reasons = _score_route(args.query, row)
        if score <= 0:
            continue
        ranked.append({
            "score": score,
            "skill_name": row.get("skill_name"),
            "skill_path": row.get("skill_path"),
            "category": row.get("category"),
            "tier": row.get("tier"),
            "owner_agent": row.get("owner_agent"),
            "risk_level": row.get("risk_level"),
            "requires_approval": row.get("requires_approval"),
            "reasons": reasons,
            "description": row.get("description"),
        })

    ranked.sort(
        key=lambda r: (
            r["score"],
            1 if r.get("tier") == "core" else 0,
            r.get("skill_name") or "",
        ),
        reverse=True,
    )
    ranked = ranked[:args.limit]

    result = {
        "query": args.query,
        "matches": ranked,
        "count": len(ranked),
    }
    if args.output_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if not ranked:
            print("No skill matches found.")
            return 0
        print(f"Top skill matches for: {args.query}\n")
        for r in ranked:
            approval = " approval" if r.get("requires_approval") else ""
            print(
                f"  {r['score']:>2}  {r['skill_name']:28} "
                f"{r.get('tier')}/{r.get('category')} "
                f"owner={r.get('owner_agent')} risk={r.get('risk_level')}{approval}"
            )
            if r.get("reasons"):
                print(f"      {', '.join(r['reasons'])}")
    return 0


# ---- List -------------------------------------------------------------------

def cmd_list(args) -> int:
    try:
        db = get_supabase()
        rows = (db.table("skills_registry")
                .select("skill_name,description,category,tier,owner_agent,risk_level,usage_count,last_used,is_active")
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
              f"{(r.get('category') or '—'):14}  "
              f"{(r.get('tier') or '—'):11}  "
              f"{(r.get('owner_agent') or '—'):6}  "
              f"{(r.get('risk_level') or '—'):11}  "
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

    # 3. Scan human-facing docs for mentions
    doc_mentions: set[str] = set()
    doc_text = ""
    for doc in (CAPABILITIES_FILE, SKILLS_INDEX_FILE):
        if doc.exists():
            doc_text += "\n" + doc.read_text(encoding="utf-8")
    for name in folder_skills.keys():
        # Any mention of skills/<name>, Obsidian link, or the skill name in backticks
        if (
            f"skills/{name}" in doc_text
            or f"[[skills/{name}/SKILL" in doc_text
            or f"`{name}`" in doc_text
        ):
            doc_mentions.add(name)

    # 4. Compute drift
    folder_names = set(folder_skills.keys())
    registry_names = set(registry_skills.keys())

    in_folder_not_registered = sorted(folder_names - registry_names)
    in_registry_folder_missing = sorted(
        name for name in (registry_names - folder_names)
        if registry_skills.get(name, {}).get("is_active")
    )
    inactive_registry_folder_missing = sorted(
        name for name in (registry_names - folder_names)
        if not registry_skills.get(name, {}).get("is_active")
    )
    in_folder_not_in_docs = sorted(folder_names - doc_mentions)
    invalid_skills = [name for name, r in folder_skills.items() if not r["valid"]]

    report = {
        "summary": {
            "total_in_folder": len(folder_skills),
            "total_in_registry": len(registry_skills),
            "total_in_docs": len(doc_mentions),
            "total_in_capabilities_md": len(doc_mentions),
            "invalid": len(invalid_skills),
            "in_folder_not_registered": len(in_folder_not_registered),
            "in_registry_folder_missing": len(in_registry_folder_missing),
            "inactive_registry_folder_missing": len(inactive_registry_folder_missing),
            "in_folder_not_in_docs": len(in_folder_not_in_docs),
        },
        "invalid_skills": invalid_skills,
        "in_folder_not_registered": in_folder_not_registered,
        "in_registry_folder_missing": in_registry_folder_missing,
        "inactive_registry_folder_missing": inactive_registry_folder_missing,
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
    print(f"  Docs indexed:     {s['total_in_docs']} mentioned")
    print()
    if invalid_skills:
        print(f"  X INVALID STRUCTURE ({len(invalid_skills)}):")
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
        print(f"\n  X IN REGISTRY, FOLDER MISSING ({len(in_registry_folder_missing)}):")
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
    pc.add_argument("--json", dest="output_json", action="store_true",
                    default=argparse.SUPPRESS)

    pr = sub.add_parser("register",
                         help="Wire an existing skill into skills_registry + docs")
    pr.add_argument("name")
    pr.add_argument("--skip-script-check", action="store_true",
                    help="Skip the smoke check that every scripts/<x>.py reference "
                         "in the SKILL.md body actually exists on disk")
    pr.add_argument("--json", dest="output_json", action="store_true",
                    default=argparse.SUPPRESS)

    ps = sub.add_parser("sync-all",
                         help="Upsert every folder skill into skills_registry")
    ps.add_argument("--deactivate-missing", action="store_true",
                    help="Mark registry rows inactive when their folder is gone")
    ps.add_argument("--skip-invalid", action="store_true",
                    help="Sync valid skills even if invalid skills exist")
    ps.add_argument("--json", dest="output_json", action="store_true",
                    default=argparse.SUPPRESS)

    proute = sub.add_parser("route",
                            help="Rank active skills for a plain-English task")
    proute.add_argument("query", help="Task or user request to match")
    proute.add_argument("--limit", type=int, default=8)
    proute.add_argument("--json", dest="output_json", action="store_true",
                        default=argparse.SUPPRESS)

    pl = sub.add_parser("list", help="List all skills in the registry")
    pl.add_argument("--json", dest="output_json", action="store_true",
                    default=argparse.SUPPRESS)

    pa = sub.add_parser("audit",
                         help="Report drift between folder, registry, and CAPABILITIES.md")
    pa.add_argument("--json", dest="output_json", action="store_true",
                    default=argparse.SUPPRESS)

    pv = sub.add_parser("validate", help="Deep-check one skill's structure")
    pv.add_argument("name")
    pv.add_argument("--json", dest="output_json", action="store_true",
                    default=argparse.SUPPRESS)

    args = p.parse_args()
    if args.command == "create":
        sys.exit(cmd_create(args))
    elif args.command == "register":
        sys.exit(cmd_register(args))
    elif args.command == "sync-all":
        sys.exit(cmd_sync_all(args))
    elif args.command == "route":
        sys.exit(cmd_route(args))
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
