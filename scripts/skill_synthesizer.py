"""
Skill Synthesizer — autonomous skill extraction pipeline.

Watches agent_decisions for high-confidence successful outcomes, extracts
procedural knowledge, renders SKILL.md, validates the result, and registers
it via register_skill.py. This closes the loop between what the agent *does*
and what the skill library *knows*.

Auto-generated skills land in skills/auto-generated/<slug>/SKILL.md with
status '[NEW]'. After 3 tracked successes (via skill_metrics.py), they are
promoted to '[VALIDATED]' and moved to skills/<slug>/.

SUBCOMMANDS
-----------
    scan --since 7d         Query agent_decisions for high-confidence successes
    extract --decision-id X Read one decision trace, return a structured procedure
    generate --procedure-file F  Render SKILL.md from a procedure JSON file
    register --skill-path P Wire the skill into skills_registry via register_skill.py
    validate --skill-path P Structural + safety check on a generated SKILL.md
    synthesize --decision-id X  Full pipeline: extract -> generate -> validate -> register

SAFETY
------
Auto-generated skills are blocked from destructive operations at the validate
step. Any procedure containing rm, drop, delete, force, send, post, publish,
or pay will be rejected with a clear error — the operator must manually
override by editing the file and calling register directly.

USAGE
-----
    python scripts/skill_synthesizer.py scan --since 7d --json
    python scripts/skill_synthesizer.py extract --decision-id tick-20260501-abc123
    python scripts/skill_synthesizer.py synthesize --decision-id tick-20260501-abc123
    python scripts/skill_synthesizer.py validate --skill-path skills/auto-generated/my-skill
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"
AUTO_SKILLS_DIR = SKILLS_DIR / "auto-generated"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

# Force UTF-8 output on Windows to avoid cp1252 encoding errors.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ---- Env + Supabase ----------------------------------------------------------

def load_env() -> dict[str, str]:
    """Load .env.agents without exposing the file path to callers."""
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
    """Return an authenticated Supabase client. Fail-closed on missing creds."""
    e = env if env is not None else load_env()
    url = e.get("BRAVO_SUPABASE_URL") or e.get("SUPABASE_URL") or os.environ.get("BRAVO_SUPABASE_URL")
    key = (
        e.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
        or e.get("SUPABASE_SERVICE_KEY")
        or os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    )
    if not url or not key:
        raise RuntimeError(
            "Supabase credentials missing — set BRAVO_SUPABASE_URL and "
            "BRAVO_SUPABASE_SERVICE_ROLE_KEY in .env.agents"
        )
    from supabase import create_client  # type: ignore
    return create_client(url, key)


def get_anthropic_key(env: Optional[dict[str, str]] = None) -> str:
    """Return the Anthropic API key. Fail-closed."""
    e = env if env is not None else load_env()
    key = e.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY missing in .env.agents")
    return key


# ---- Destructive-op safety guard ---------------------------------------------

# Terms that indicate a skill step could cause irreversible side effects.
# Auto-generated skills are blocked if any step body contains these.
DESTRUCTIVE_TERMS = re.compile(
    r"\b(rm\b|drop\b|delete\b|truncate\b|force[\s_-]?push|force\b|"
    r"send\b|post\b|publish\b|pay\b|charge\b|deploy\b|migrate\b)\b",
    re.IGNORECASE,
)


def _has_destructive_ops(procedure: dict[str, Any]) -> list[str]:
    """Return list of flagged terms found in procedure steps or trigger phrases."""
    flagged: list[str] = []
    steps: list[str] = procedure.get("steps") or []
    for step in steps:
        for m in DESTRUCTIVE_TERMS.finditer(str(step)):
            flagged.append(m.group(0).lower())
    for t in procedure.get("triggers") or []:
        for m in DESTRUCTIVE_TERMS.finditer(str(t)):
            flagged.append(m.group(0).lower())
    return sorted(set(flagged))


# ---- Slug + path helpers -----------------------------------------------------

def _to_slug(name: str) -> str:
    """Normalize a skill name to a safe kebab-case slug."""
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:50] if slug else "unnamed-skill"


def _auto_skill_dir(slug: str) -> Path:
    return AUTO_SKILLS_DIR / slug


# ---- Phase: SCAN -------------------------------------------------------------

def _parse_since(since: str) -> datetime:
    """Parse a --since argument like '7d', '24h', '2026-04-01' into a UTC datetime."""
    since = since.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", since):
        return datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
    m = re.match(r"^(\d+)([dhm])$", since, re.IGNORECASE)
    if not m:
        raise ValueError(f"Cannot parse --since value: '{since}'. "
                         "Use '7d', '24h', '90m', or 'YYYY-MM-DD'.")
    amount = int(m.group(1))
    unit = m.group(2).lower()
    delta = {"d": timedelta(days=amount), "h": timedelta(hours=amount), "m": timedelta(minutes=amount)}[unit]
    return datetime.now(timezone.utc) - delta


def scan_decisions(
    since: str = "7d",
    confidence_threshold: float = 0.85,
    limit: int = 50,
    env: Optional[dict[str, str]] = None,
) -> list[dict[str, Any]]:
    """Query agent_decisions for successful patterns above confidence threshold.

    Returns a list of candidate dicts with id, decision_type, confidence,
    reasoning, and chosen_action.
    """
    cutoff = _parse_since(since)
    db = get_supabase(env)
    rows = (
        db.table("agent_decisions")
        .select(
            "id,tick_id,decision_type,confidence,chosen_action,"
            "reasoning,target_description,outcome_status,created_at"
        )
        .gte("confidence", confidence_threshold)
        .eq("executed", True)
        .gte("created_at", cutoff.isoformat())
        .in_("outcome_status", ["sent", "completed", "success"])
        .order("confidence", desc=True)
        .limit(limit)
        .execute()
        .data
    ) or []

    candidates = []
    for row in rows:
        candidates.append(
            {
                "decision_id": row.get("id"),
                "tick_id": row.get("tick_id"),
                "decision_type": row.get("decision_type"),
                "confidence": row.get("confidence"),
                "chosen_action": row.get("chosen_action"),
                "outcome_status": row.get("outcome_status"),
                "reasoning_preview": (row.get("reasoning") or "")[:200],
                "created_at": row.get("created_at"),
            }
        )
    return candidates


def cmd_scan(args: argparse.Namespace) -> int:
    env = load_env()
    try:
        candidates = scan_decisions(
            since=args.since,
            confidence_threshold=args.confidence,
            limit=args.limit,
            env=env,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: scan failed: {exc}", file=sys.stderr)
        return 1

    result: dict[str, Any] = {
        "since": args.since,
        "confidence_threshold": args.confidence,
        "candidates": candidates,
        "count": len(candidates),
    }
    if args.output_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if not candidates:
            print(f"No high-confidence decisions found since {args.since}.")
            return 0
        print(f"Found {len(candidates)} skill candidates (confidence >= {args.confidence}):\n")
        for c in candidates:
            print(
                f"  {c['decision_id']}  conf={c['confidence']:.2f}  "
                f"type={c['decision_type']}  action={c['chosen_action']}"
            )
            print(f"    {c['reasoning_preview'][:100]}")
    return 0


# ---- Phase: EXTRACT ----------------------------------------------------------

_EXTRACT_SYSTEM = """\
You are Bravo's skill extraction engine. Given a decision trace from an autonomous agent,
extract a reusable procedural pattern that could be encoded as a skill.

Return ONLY valid JSON matching this schema:
{
  "name": "<kebab-case skill name, 2-5 words>",
  "description": "<one sentence: what the skill does and when to use it>",
  "trigger": "<plain-English phrase CC might say to invoke this>",
  "triggers": ["<trigger 1>", "<trigger 2>", "<trigger 3>"],
  "steps": [
    "<step 1: imperative sentence>",
    "<step 2>",
    "..."
  ],
  "tools": ["<tool or script name>", "..."],
  "success_signals": ["<what a successful outcome looks like>"],
  "preconditions": ["<what must be true before running>"],
  "confidence": <float 0.0-1.0 reflecting how well this generalizes>
}

Rules:
- Steps must be concrete and imperative, not aspirational.
- Tools must name actual scripts or APIs (no invented names).
- Do not include any destructive operations (rm, delete, send, publish, pay, force-push).
- confidence should reflect how cleanly this generalizes from a single example.
- Return ONLY the JSON object. No markdown fences, no explanation.
"""


def extract_procedure(
    decision_id: str,
    env: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Read one decision trace from agent_decisions and call Claude Haiku to extract
    a structured procedure. Returns a procedure dict."""
    e = env or load_env()
    db = get_supabase(e)

    # Try to match by id (UUID) or by tick_id prefix.
    rows: list[dict] = []
    try:
        rows = (
            db.table("agent_decisions")
            .select("*")
            .eq("id", decision_id)
            .limit(1)
            .execute()
            .data
        ) or []
    except Exception:  # noqa: BLE001
        pass

    if not rows:
        # Fallback: search by tick_id or partial id.
        try:
            rows = (
                db.table("agent_decisions")
                .select("*")
                .ilike("tick_id", f"%{decision_id}%")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
                .data
            ) or []
        except Exception:  # noqa: BLE001
            pass

    if not rows:
        raise ValueError(f"No decision found for id/tick_id containing '{decision_id}'")

    row = rows[0]

    # Build a compact trace for Haiku to reason over.
    trace_text = (
        f"Decision type: {row.get('decision_type')}\n"
        f"Chosen action: {row.get('chosen_action')}\n"
        f"Confidence: {row.get('confidence')}\n"
        f"Outcome: {row.get('outcome_status')}\n"
        f"Target: {row.get('target_description')}\n"
        f"Reasoning: {row.get('reasoning') or '(none)'}\n"
    )

    api_key = get_anthropic_key(e)
    try:
        import anthropic  # type: ignore
    except ImportError:
        raise RuntimeError("anthropic SDK not installed — pip install anthropic")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        system=_EXTRACT_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract a reusable skill procedure from this agent decision trace:\n\n"
                    + trace_text
                ),
            }
        ],
    )
    raw = message.content[0].text.strip()

    # Strip any accidental markdown fences.
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)

    try:
        procedure = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Haiku returned invalid JSON: {exc}\n\nRaw:\n{raw}") from exc

    # Inject provenance.
    procedure["_source_decision_id"] = decision_id
    procedure["_extracted_at"] = datetime.now(timezone.utc).isoformat()
    return procedure


def cmd_extract(args: argparse.Namespace) -> int:
    env = load_env()
    try:
        procedure = extract_procedure(args.decision_id, env=env)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: extract failed: {exc}", file=sys.stderr)
        return 1

    if args.output_json:
        print(json.dumps(procedure, indent=2, default=str))
        return 0

    print(f"Extracted procedure: {procedure.get('name')}")
    print(f"  Description:  {procedure.get('description')}")
    print(f"  Steps:        {len(procedure.get('steps') or [])}")
    print(f"  Confidence:   {procedure.get('confidence')}")
    if args.out:
        out_path = Path(args.out)
        out_path.write_text(json.dumps(procedure, indent=2, default=str), encoding="utf-8")
        print(f"  Written to:   {out_path}")
    return 0


# ---- Phase: GENERATE ---------------------------------------------------------

_SKILL_MD_TEMPLATE = """\
---
name: {name}
description: {description}
tier: {tier}
owner: {owner}
risk: {risk}
triggers: {triggers_yaml}
status: '[NEW]'
generated_at: {generated_at}
confidence: {confidence}
source_decision_id: {source_decision_id}
---

# {title}

> {description}

## Why this skill exists

Auto-generated from a successful agent decision (confidence {confidence}).
The agent completed this workflow with high reliability — encoding it as a
skill makes it discoverable and reusable without re-discovering the pattern.

## Trigger phrases

{trigger_list}

## Steps

{steps_list}

## Tools used

{tools_list}

## Success signals

{success_signals_list}

## Preconditions

{preconditions_list}

## Safety note

This skill was auto-generated and carries status `[NEW]`. It has been
validated to contain no destructive operations. After 3 successful tracked
uses via `python scripts/skill_metrics.py track`, it will be promoted to
`[VALIDATED]` and moved to `skills/{name}/SKILL.md`.

To manually approve earlier: edit `skills/auto-generated/{name}/metrics.json`
and run `python scripts/skill_metrics.py promote --skill {name}`.

## Related files

- `skills/auto-generated/{name}/metrics.json` — usage tracking
- `scripts/skill_metrics.py` — promotion tool
- `scripts/skill_synthesizer.py` — generation pipeline

## Obsidian Links
- [[skills/auto-generated/README]]
"""


def generate_skill_md(
    procedure: dict[str, Any],
    output_dir: Optional[Path] = None,
) -> Path:
    """Render a SKILL.md from a procedure dict. Returns the path written."""
    raw_name = procedure.get("name") or "unnamed-skill"
    slug = _to_slug(raw_name)
    title = " ".join(w.capitalize() for w in slug.split("-"))
    description = (procedure.get("description") or "").strip()
    triggers: list[str] = procedure.get("triggers") or [procedure.get("trigger") or slug]
    steps: list[str] = procedure.get("steps") or []
    tools: list[str] = procedure.get("tools") or []
    success_signals: list[str] = procedure.get("success_signals") or []
    preconditions: list[str] = procedure.get("preconditions") or []
    confidence = float(procedure.get("confidence") or 0.0)
    source_id = procedure.get("_source_decision_id") or "unknown"
    generated_at = procedure.get("_extracted_at") or datetime.now(timezone.utc).isoformat()

    triggers_yaml = json.dumps(triggers[:8])
    trigger_list = "\n".join(f"- {t}" for t in triggers[:8]) or "- (none specified)"
    steps_list = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps)) or "1. (none extracted)"
    tools_list = "\n".join(f"- `{t}`" for t in tools) or "- (none identified)"
    success_signals_list = "\n".join(f"- {s}" for s in success_signals) or "- (none specified)"
    preconditions_list = "\n".join(f"- {p}" for p in preconditions) or "- (none specified)"

    content = _SKILL_MD_TEMPLATE.format(
        name=slug,
        title=title,
        description=description or f"Auto-generated skill: {title}",
        tier="specialized",
        owner="bravo",
        risk="low",
        triggers_yaml=triggers_yaml,
        generated_at=generated_at,
        confidence=round(confidence, 3),
        source_decision_id=source_id,
        trigger_list=trigger_list,
        steps_list=steps_list,
        tools_list=tools_list,
        success_signals_list=success_signals_list,
        preconditions_list=preconditions_list,
    )

    target_dir = output_dir or _auto_skill_dir(slug)
    target_dir.mkdir(parents=True, exist_ok=True)
    skill_path = target_dir / "SKILL.md"
    skill_path.write_text(content, encoding="utf-8")
    return skill_path


def cmd_generate(args: argparse.Namespace) -> int:
    proc_path = Path(args.procedure_file)
    if not proc_path.exists():
        print(f"ERROR: procedure file not found: {proc_path}", file=sys.stderr)
        return 1

    try:
        procedure = json.loads(proc_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: cannot read procedure file: {exc}", file=sys.stderr)
        return 1

    out_dir = Path(args.output_dir) if getattr(args, "output_dir", None) else None
    try:
        skill_path = generate_skill_md(procedure, output_dir=out_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: generate failed: {exc}", file=sys.stderr)
        return 1

    result = {"status": "generated", "skill_path": str(skill_path)}
    if args.output_json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"SKILL.md written to: {skill_path}")
    return 0


# ---- Phase: VALIDATE ---------------------------------------------------------

REQUIRED_FRONTMATTER_FIELDS = {"name", "description", "tier", "owner", "risk", "triggers", "status"}


def validate_skill(skill_path: Path) -> dict[str, Any]:
    """Structural + safety check on an auto-generated SKILL.md.

    Returns {"valid": bool, "issues": list[str], "name": str}.
    """
    result: dict[str, Any] = {
        "valid": True,
        "issues": [],
        "name": "",
        "path": str(skill_path),
    }

    skill_md = skill_path if skill_path.name == "SKILL.md" else skill_path / "SKILL.md"
    if not skill_md.exists():
        result["valid"] = False
        result["issues"].append(f"SKILL.md not found at {skill_md}")
        return result

    text = skill_md.read_text(encoding="utf-8")

    # Parse YAML frontmatter.
    fm_match = re.match(r"^\s*---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not fm_match:
        result["valid"] = False
        result["issues"].append("Missing YAML frontmatter block (expected --- delimiters)")
        return result

    try:
        import yaml  # type: ignore
        fm: dict[str, Any] = yaml.safe_load(fm_match.group(1)) or {}
    except Exception as exc:  # noqa: BLE001
        result["valid"] = False
        result["issues"].append(f"Frontmatter YAML parse error: {exc}")
        return result

    result["name"] = str(fm.get("name") or "")

    # Required fields check.
    for field in REQUIRED_FRONTMATTER_FIELDS:
        if not fm.get(field):
            result["valid"] = False
            result["issues"].append(f"Missing required frontmatter field: '{field}'")

    # Risk must be 'low' for auto-generated skills.
    if fm.get("risk") not in ("low", None, ""):
        result["issues"].append(
            f"Auto-generated skills must have risk='low', got '{fm.get('risk')}'"
        )
        # This is a warning, not a hard block — reviewer can override.

    # Destructive ops check: scan full file body.
    body = text[fm_match.end():]
    destructive = []
    for m in DESTRUCTIVE_TERMS.finditer(body):
        destructive.append(m.group(0).lower())
    destructive = sorted(set(destructive))
    if destructive:
        result["valid"] = False
        result["issues"].append(
            f"BLOCKED: auto-generated skill contains destructive operation keywords: "
            f"{destructive}. Remove these steps or register manually."
        )

    # Body substance check.
    if len(body.strip()) < 100:
        result["issues"].append("SKILL.md body is very short — may be empty template")

    return result


def cmd_validate(args: argparse.Namespace) -> int:
    skill_path = Path(args.skill_path)
    result = validate_skill(skill_path)

    if args.output_json:
        print(json.dumps(result, indent=2, default=str))
        return 0 if result["valid"] else 1

    status = "VALID" if result["valid"] else "INVALID"
    print(f"Validation: {status} — {skill_path}")
    if result["issues"]:
        for issue in result["issues"]:
            prefix = "[BLOCK]" if "BLOCKED" in issue else "[WARN]"
            print(f"  {prefix} {issue}")
    else:
        print("  No issues. Clean.")
    return 0 if result["valid"] else 1


# ---- Phase: REGISTER ---------------------------------------------------------

def register_skill(skill_path: Path) -> dict[str, Any]:
    """Call register_skill.py sync-one equivalent via subprocess.

    register_skill.py does not have a sync-one subcommand — it uses 'register <name>'.
    We derive the skill name from the path.
    """
    skill_dir = skill_path if skill_path.is_dir() else skill_path.parent
    skill_name_raw = skill_dir.name

    # register_skill.py operates relative to skills/ root — if it's under
    # auto-generated, pass the full relative path as the name arg.
    # The register command uses the skills/ folder structure, so we need
    # to resolve how register_skill.py finds the skill.
    # register_skill.py looks up skills/<name>/SKILL.md — for auto-generated
    # skills the path would be skills/auto-generated/<slug>/SKILL.md which
    # the register command won't find. We call validate from register directly
    # using the absolute path approach.

    register_script = SCRIPTS_DIR / "register_skill.py"
    if not register_script.exists():
        raise FileNotFoundError(f"register_skill.py not found at {register_script}")

    # For auto-generated skills, we pass the skill name as
    # "auto-generated/<slug>" — register_skill.py uses SKILLS_DIR / name,
    # so this resolves correctly.
    rel_to_skills = skill_dir.relative_to(SKILLS_DIR)
    skill_name_arg = str(rel_to_skills).replace("\\", "/")

    result = subprocess.run(
        [sys.executable, str(register_script), "register", skill_name_arg, "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    output: dict[str, Any] = {
        "returncode": result.returncode,
        "skill_name_arg": skill_name_arg,
    }
    if result.stdout.strip():
        try:
            output["register_result"] = json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            output["register_stdout"] = result.stdout.strip()
    if result.stderr.strip():
        output["register_stderr"] = result.stderr.strip()
    return output


def cmd_register(args: argparse.Namespace) -> int:
    skill_path = Path(args.skill_path)
    try:
        reg_result = register_skill(skill_path)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: register failed: {exc}", file=sys.stderr)
        return 1

    if args.output_json:
        print(json.dumps(reg_result, indent=2, default=str))
        return 0

    rc = reg_result.get("returncode", 1)
    if rc == 0:
        print(f"Registered: {reg_result.get('skill_name_arg')}")
        sub = reg_result.get("register_result") or {}
        print(f"  Status: {sub.get('status')}")
    else:
        print(f"Register returned code {rc}", file=sys.stderr)
        if reg_result.get("register_stderr"):
            print(reg_result["register_stderr"], file=sys.stderr)
        return 1
    return 0


# ---- Phase: SYNTHESIZE (full pipeline) ---------------------------------------

def synthesize(
    decision_id: str,
    env: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """End-to-end: extract -> generate -> validate -> register.

    Writes to skills/auto-generated/<slug>/SKILL.md.
    Returns a pipeline result dict with each phase outcome.
    """
    e = env or load_env()
    result: dict[str, Any] = {
        "decision_id": decision_id,
        "stages": {},
        "status": "pending",
        "skill_path": None,
    }

    # Stage 1: Extract.
    try:
        procedure = extract_procedure(decision_id, env=e)
        result["stages"]["extract"] = {"status": "ok", "name": procedure.get("name")}
    except Exception as exc:  # noqa: BLE001
        result["stages"]["extract"] = {"status": "error", "error": str(exc)}
        result["status"] = "failed:extract"
        return result

    # Safety check before generating file.
    destructive = _has_destructive_ops(procedure)
    if destructive:
        result["stages"]["safety_check"] = {
            "status": "blocked",
            "destructive_terms": destructive,
        }
        result["status"] = "failed:destructive_ops"
        return result
    result["stages"]["safety_check"] = {"status": "ok"}

    # Stage 2: Generate SKILL.md.
    try:
        skill_path = generate_skill_md(procedure)
        result["stages"]["generate"] = {"status": "ok", "path": str(skill_path)}
        result["skill_path"] = str(skill_path)
    except Exception as exc:  # noqa: BLE001
        result["stages"]["generate"] = {"status": "error", "error": str(exc)}
        result["status"] = "failed:generate"
        return result

    # Stage 3: Validate.
    validation = validate_skill(skill_path.parent)
    result["stages"]["validate"] = validation
    if not validation["valid"]:
        result["status"] = "failed:validate"
        return result

    # Stage 4: Register.
    try:
        reg = register_skill(skill_path.parent)
        result["stages"]["register"] = reg
        if reg.get("returncode", 1) != 0:
            result["status"] = "failed:register"
            return result
    except Exception as exc:  # noqa: BLE001
        result["stages"]["register"] = {"status": "error", "error": str(exc)}
        result["status"] = "failed:register"
        return result

    result["status"] = "ok"
    return result


def cmd_synthesize(args: argparse.Namespace) -> int:
    env = load_env()
    try:
        pipeline_result = synthesize(args.decision_id, env=env)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: synthesize pipeline failed: {exc}", file=sys.stderr)
        return 1

    if args.output_json:
        print(json.dumps(pipeline_result, indent=2, default=str))
        return 0

    status = pipeline_result["status"]
    print(f"Synthesize: {status}")
    for stage, outcome in pipeline_result.get("stages", {}).items():
        ok = outcome.get("status") == "ok" or outcome.get("valid") is True
        icon = "OK" if ok else "FAIL"
        print(f"  [{icon}] {stage}")
        if not ok and outcome.get("error"):
            print(f"        {outcome['error']}")
        if not ok and outcome.get("issues"):
            for iss in outcome["issues"]:
                print(f"        {iss}")
    if pipeline_result.get("skill_path"):
        print(f"\n  Skill written: {pipeline_result['skill_path']}")
    return 0 if status == "ok" else 1


# ---- Integration hook (for autonomous_agent.py Phase 7) ---------------------

def reflect_hook(
    tick_id: str,
    decisions: list[Any],
    env: Optional[dict[str, str]] = None,
) -> list[dict[str, Any]]:
    """Hook called from autonomous_agent.py Phase 7 REFLECT.

    For each decision with confidence > 0.90 and outcome 'completed'/'success',
    attempt background synthesis. Returns list of synthesis results (may be empty).

    This function is intentionally non-blocking: failures are caught and returned
    as error entries rather than propagated. autonomous_agent.py must NOT be
    modified — it calls this as an optional hook.
    """
    results: list[dict[str, Any]] = []
    for decision in decisions:
        # Support both Decision dataclass and plain dict rows.
        if hasattr(decision, "confidence"):
            conf = float(decision.confidence or 0)
            status = decision.outcome_status or ""
            d_id = getattr(decision, "id", None) or tick_id
        else:
            conf = float(decision.get("confidence") or 0)
            status = decision.get("outcome_status") or ""
            d_id = decision.get("id") or tick_id

        if conf < 0.90 or status not in ("completed", "success", "sent"):
            continue

        try:
            r = synthesize(d_id, env=env)
            results.append(r)
        except Exception as exc:  # noqa: BLE001
            results.append({"decision_id": d_id, "status": "hook_error", "error": str(exc)})
    return results


# ---- CLI entry ---------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        prog="skill_synthesizer.py",
        description="Autonomous skill extraction pipeline — decision trace -> SKILL.md.",
    )
    p.add_argument("--json", dest="output_json", action="store_true",
                   help="Emit JSON output")
    sub = p.add_subparsers(dest="command")

    # scan
    ps = sub.add_parser("scan", help="List high-confidence decision candidates")
    ps.add_argument("--since", default="7d", help="Time window: '7d', '24h', 'YYYY-MM-DD'")
    ps.add_argument("--confidence", type=float, default=0.85,
                    help="Minimum confidence threshold (default 0.85)")
    ps.add_argument("--limit", type=int, default=50)
    ps.add_argument("--json", dest="output_json", action="store_true",
                    default=argparse.SUPPRESS)

    # extract
    pe = sub.add_parser("extract", help="Extract procedure from one decision")
    pe.add_argument("--decision-id", required=True, help="Decision id or tick_id substring")
    pe.add_argument("--out", default=None, help="Write procedure JSON to this path")
    pe.add_argument("--json", dest="output_json", action="store_true",
                    default=argparse.SUPPRESS)

    # generate
    pg = sub.add_parser("generate", help="Render SKILL.md from a procedure JSON file")
    pg.add_argument("--procedure-file", required=True, help="Path to procedure JSON")
    pg.add_argument("--output-dir", default=None, help="Override output directory")
    pg.add_argument("--json", dest="output_json", action="store_true",
                    default=argparse.SUPPRESS)

    # register
    pr = sub.add_parser("register", help="Register an auto-generated skill")
    pr.add_argument("--skill-path", required=True, help="Path to skill dir or SKILL.md")
    pr.add_argument("--json", dest="output_json", action="store_true",
                    default=argparse.SUPPRESS)

    # validate
    pv = sub.add_parser("validate", help="Structural + safety check on a generated skill")
    pv.add_argument("--skill-path", required=True, help="Path to skill dir or SKILL.md")
    pv.add_argument("--json", dest="output_json", action="store_true",
                    default=argparse.SUPPRESS)

    # synthesize
    psy = sub.add_parser("synthesize", help="Full pipeline: extract -> generate -> validate -> register")
    psy.add_argument("--decision-id", required=True, help="Decision id or tick_id substring")
    psy.add_argument("--json", dest="output_json", action="store_true",
                     default=argparse.SUPPRESS)

    args = p.parse_args()
    # Ensure output_json is always present on the namespace regardless of
    # which subparser (or none) was invoked.
    if not hasattr(args, "output_json"):
        args.output_json = False

    dispatch = {
        "scan": cmd_scan,
        "extract": cmd_extract,
        "generate": cmd_generate,
        "register": cmd_register,
        "validate": cmd_validate,
        "synthesize": cmd_synthesize,
    }
    fn = dispatch.get(args.command)
    if fn is None:
        p.print_help()
        sys.exit(1)
    sys.exit(fn(args))


if __name__ == "__main__":
    main()
