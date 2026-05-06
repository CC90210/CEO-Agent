"""
Personalize — render operator-specific files from the wizard's answers.

This is the scaffolding step that turns a fresh clone into THIS operator's
agent. Reads either `brain/operator.profile.json` (preferred) or env vars
written by the setup wizard, then renders:

  brain/USER.md                 from brain/USER.template.md
  memory/ACTIVE_TASKS.md        from memory/ACTIVE_TASKS.template.md
  memory/SESSION_LOG.md         from memory/SESSION_LOG.template.md

All target files are gitignored — local-only, never pushed. Re-running
personalize is idempotent: it overwrites the targets in place.

USAGE
-----
    # After wizard completes:
    python scripts/personalize.py apply

    # Inspect what would change without writing:
    python scripts/personalize.py apply --dry-run --json

    # Show the resolved profile:
    python scripts/personalize.py show --json

    # Check whether the system has been personalized yet (first-run guard):
    python scripts/personalize.py check --json
    # Exit 0 if profile present, 1 if missing.

PROFILE SCHEMA
--------------
The canonical profile lives at `brain/operator.profile.json`:

    {
      "full_name":       "Conaugh McKenna",
      "preferred_name":  "CC",
      "personal_brand":  "Conaugh McKenna",
      "primary_brand":   "OASIS AI Solutions",
      "role":            "Founder",
      "location":        "Collingwood, Ontario",
      "primary_email":   "conaugh@oasisai.work",
      "website":         "https://oasisai.work",
      "booking_link":    "https://calendar.app.google/...",
      "north_star":      "$5,000 USD Net MRR by 2026-05-15",
      "industry":        "agency",
      "primary_metric":  "MRR",
      "daily_work":      "Sales calls, content, partner ops.",
      "off_limits":      "Don't send anything without approval",
      "voice":           "direct, warm, no AI slop"
    }
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = PROJECT_ROOT / "brain" / "operator.profile.json"

TEMPLATE_TARGETS: list[tuple[Path, Path]] = [
    (PROJECT_ROOT / "brain" / "USER.template.md",
     PROJECT_ROOT / "brain" / "USER.md"),
    (PROJECT_ROOT / "memory" / "ACTIVE_TASKS.template.md",
     PROJECT_ROOT / "memory" / "ACTIVE_TASKS.md"),
    (PROJECT_ROOT / "memory" / "SESSION_LOG.template.md",
     PROJECT_ROOT / "memory" / "SESSION_LOG.md"),
]

# Profile fields that are required for personalization to proceed.
REQUIRED_FIELDS = ["full_name", "preferred_name", "primary_brand", "north_star"]

# Mapping from setup-wizard env keys to profile fields. Used when no
# `operator.profile.json` exists but the wizard already wrote to .env.agents.
ENV_TO_PROFILE: dict[str, str] = {
    "USER_FULL_NAME": "full_name",
    "USER_PREFERRED_NAME": "preferred_name",
    "USER_BUSINESS_NAME": "primary_brand",
    "USER_ROLE": "role",
    "USER_INDUSTRY": "industry",
    "USER_PRIMARY_METRIC": "primary_metric",
    "USER_DAILY_WORK": "daily_work",
    "USER_OFF_LIMITS": "off_limits",
    "BRAVO_TARGET": "north_star",
    "BRAVO_PRIMARY_BRAND": "primary_brand",
    "BRAVO_TIMEZONE": "timezone",
    "BRAVO_WORKING_HOURS": "working_hours",
    "AURA_RESIDENCE_CITY": "location",
}


def _load_dotenv() -> dict[str, str]:
    env_file = PROJECT_ROOT / ".env.agents"
    try:
        from dotenv import dotenv_values  # type: ignore
    except ImportError:
        return {}
    if not env_file.exists():
        return {}
    return {k: str(v) for k, v in dotenv_values(env_file).items() if v is not None}


def load_profile() -> Optional[dict[str, Any]]:
    """Resolve the operator profile from disk OR env vars OR return None."""
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
    env = _load_dotenv()
    if not env:
        return None
    profile: dict[str, Any] = {}
    for env_key, field in ENV_TO_PROFILE.items():
        val = env.get(env_key)
        if val:
            profile[field] = val
    if not profile:
        return None
    profile.setdefault("preferred_name", profile.get("full_name", "").split()[0] if profile.get("full_name") else "")
    return profile


def save_profile(profile: dict[str, Any]) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(profile, indent=2), encoding="utf-8")


def validate_profile(profile: dict[str, Any]) -> list[str]:
    """Return a list of missing required fields."""
    missing = [f for f in REQUIRED_FIELDS if not profile.get(f)]
    return missing


def render_template(template_text: str, profile: dict[str, Any]) -> str:
    """Substitute {{ field }} placeholders with profile values."""
    out = template_text
    for key, val in profile.items():
        out = out.replace(f"{{{{ {key} }}}}", str(val))
        out = out.replace(f"{{{{{key}}}}}", str(val))
    return out


def apply(profile: dict[str, Any], dry_run: bool = False, force: bool = False) -> dict[str, Any]:
    """Render every (template, target) pair using the profile.

    By default, never clobber an existing target — preserves the operator's
    edits. Pass `force=True` to overwrite (the wizard's first-run path).
    """
    results: list[dict[str, Any]] = []
    for tpl, target in TEMPLATE_TARGETS:
        rel_target = str(target.relative_to(PROJECT_ROOT))
        rel_tpl = str(tpl.relative_to(PROJECT_ROOT))
        if not tpl.exists():
            results.append({"template": rel_tpl, "target": rel_target, "status": "skip:no-template"})
            continue
        if target.exists() and not force:
            results.append({"template": rel_tpl, "target": rel_target, "status": "skip:exists"})
            continue
        rendered = render_template(tpl.read_text(encoding="utf-8"), profile)
        if dry_run:
            results.append({"template": rel_tpl, "target": rel_target, "status": "would-write", "bytes": len(rendered)})
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8")
            results.append({"template": rel_tpl, "target": rel_target, "status": "written", "bytes": len(rendered)})
    return {"dry_run": dry_run, "force": force, "profile_path": str(PROFILE_PATH.relative_to(PROJECT_ROOT)),
            "results": results, "missing_fields": validate_profile(profile)}


def cmd_apply(args: argparse.Namespace) -> int:
    profile = load_profile()
    if profile is None:
        msg = {"ok": False, "error": "No profile found. Run setup wizard first or create brain/operator.profile.json."}
        print(json.dumps(msg, indent=2)) if args.output_json else print(msg["error"], file=sys.stderr)
        return 1
    missing = validate_profile(profile)
    if missing:
        msg = {"ok": False, "error": f"Profile missing required fields: {missing}"}
        print(json.dumps(msg, indent=2)) if args.output_json else print(msg["error"], file=sys.stderr)
        return 1
    # Persist the profile JSON if it came from env vars only.
    if not PROFILE_PATH.exists():
        save_profile(profile)
    result = apply(profile, dry_run=args.dry_run, force=getattr(args, "force", False))
    result["ok"] = True
    if args.output_json:
        print(json.dumps(result, indent=2))
    else:
        for r in result["results"]:
            print(f"  [{r['status']}] {r['target']}")
        print(f"Done. Profile at {result['profile_path']}.")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    profile = load_profile()
    if profile is None:
        msg = {"ok": False, "error": "No profile found."}
        print(json.dumps(msg, indent=2)) if args.output_json else print(msg["error"], file=sys.stderr)
        return 1
    payload = {"ok": True, "profile_path": str(PROFILE_PATH.relative_to(PROJECT_ROOT)),
               "profile": profile, "missing_fields": validate_profile(profile)}
    if args.output_json:
        print(json.dumps(payload, indent=2))
    else:
        for k, v in profile.items():
            print(f"  {k:18}  {v}")
        if payload["missing_fields"]:
            print(f"\n  WARN: missing fields: {payload['missing_fields']}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """First-run guard: exit 0 if personalized, 1 if not."""
    profile = load_profile()
    personalized = profile is not None and not validate_profile(profile)
    target_user_md = TEMPLATE_TARGETS[0][1]
    user_md_exists = target_user_md.exists()
    payload = {
        "personalized": personalized,
        "profile_present": profile is not None,
        "user_md_present": user_md_exists,
        "missing_fields": validate_profile(profile) if profile else REQUIRED_FIELDS,
        "next_step": ("python scripts/setup_wizard.py" if not personalized else "ready"),
    }
    if args.output_json:
        print(json.dumps(payload, indent=2))
    else:
        status = "PERSONALIZED" if personalized else "NOT PERSONALIZED"
        print(f"  {status}")
        print(f"  next: {payload['next_step']}")
    return 0 if personalized else 1


def cmd_seed(args: argparse.Namespace) -> int:
    """Write a minimal example profile JSON for first-time scaffolding."""
    if PROFILE_PATH.exists() and not args.force:
        msg = {"ok": False, "error": f"{PROFILE_PATH} already exists. Pass --force to overwrite."}
        print(json.dumps(msg, indent=2)) if args.output_json else print(msg["error"], file=sys.stderr)
        return 1
    example = {
        "full_name": "Your Full Name",
        "preferred_name": "You",
        "personal_brand": "Your Personal Brand",
        "primary_brand": "Your Business Name",
        "role": "Founder",
        "location": "City, Country",
        "primary_email": "you@yourdomain.com",
        "website": "https://yourdomain.com",
        "booking_link": "https://calendly.com/you",
        "north_star": "$10,000 MRR by 2027-01-01",
        "industry": "services",
        "primary_metric": "MRR",
        "daily_work": "Sales, content, ops",
        "off_limits": "No autonomous sends without approval",
        "voice": "direct, warm",
    }
    save_profile(example)
    msg = {"ok": True, "path": str(PROFILE_PATH.relative_to(PROJECT_ROOT)), "next": "edit then run apply"}
    if args.output_json:
        print(json.dumps(msg, indent=2))
    else:
        print(f"  Seeded {msg['path']}. Edit it, then run: python scripts/personalize.py apply")
    return 0


def main() -> None:
    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument("--json", dest="output_json", action="store_true")

    p = argparse.ArgumentParser(description="Render operator-specific files from operator.profile.json.")
    sub = p.add_subparsers(dest="command")

    pa = sub.add_parser("apply", parents=[json_parent], help="Render templates with the operator profile")
    pa.add_argument("--dry-run", action="store_true")
    pa.add_argument("--force", action="store_true", help="Overwrite existing targets (default: preserve)")

    sub.add_parser("show", parents=[json_parent], help="Print the resolved operator profile")
    sub.add_parser("check", parents=[json_parent], help="First-run guard: exit 0 if personalized, 1 otherwise")

    ps = sub.add_parser("seed", parents=[json_parent], help="Write an example profile JSON")
    ps.add_argument("--force", action="store_true")

    args = p.parse_args()
    dispatch = {"apply": cmd_apply, "show": cmd_show, "check": cmd_check, "seed": cmd_seed}
    fn = dispatch.get(args.command)
    if fn is None:
        p.print_help()
        sys.exit(1)
    sys.exit(fn(args))


if __name__ == "__main__":
    main()
