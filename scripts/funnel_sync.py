"""
Funnel Lead Sync — CRM Bridge
Reads funnel_leads and syncs any that don't already exist in the leads table.
Idempotent: keyed on email address.

Two modes:
  - `run`        — scan last 24h (the daily backstop, safe for retries)
  - `fast-poll`  — scan last 2 minutes only (for ~60s cron → immediate notifications)

For each new lead:
  1. Check if email already exists in leads table (skip if so)
  2. Insert into leads with source="cc_funnel"
  3. Send Welcome email template (graceful fallback if template missing)
  4. Notify CC via Telegram with a HIGH-PRIORITY digest
     (in fast-poll mode only; run mode uses lower-key per-lead notify)

Usage:
    python scripts/funnel_sync.py run              # Sync last 24h (daily cron)
    python scripts/funnel_sync.py fast-poll        # Sync last 2 minutes (fast cron)
    python scripts/funnel_sync.py stats            # Show sync stats
    python scripts/funnel_sync.py run --json       # JSON output for agents
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


# ── Credential loading ────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
PYTHON = sys.executable

sys.path.insert(0, str(SCRIPTS_DIR))
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

# Windows CA-bundle fix (2026-07-28) — see lib/tls_trust.py. Without this the
# AV TLS-scanner root is untrusted and every Supabase call raises
# CERTIFICATE_VERIFY_FAILED, which this tool then reported as "non-JSON".
from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

# Operator tenant (CC's funnel is OASIS inbound) — mirrors lead_engine.py.
# Stamped on every leads insert so tenant-scoped pipeline reads see the row.
OASIS_TENANT_ID = "ef8d389e-3f15-43f2-ae00-3660f69a1452"


def load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env.agents"
    if not env_path.exists():
        print(f"ERROR: {env_path} not found", file=sys.stderr)
        sys.exit(1)
    env_vars: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


def get_client(env_vars: dict[str, str]):
    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: supabase package not installed. Run: pip install supabase", file=sys.stderr)
        sys.exit(1)
    url = env_vars.get("BRAVO_SUPABASE_URL") or "https://bravo.turso.compat"
    key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "turso-compat-key"
    if not url or not key:
        print("ERROR: Missing BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        sys.exit(1)
    return create_client(url, key)


# ── Notification (graceful fallback) ─────────────────────────────────────────

try:
    from notify import notify
except ImportError:
    def notify(message: str, category: str = "system", **kwargs) -> bool:  # type: ignore[misc]
        return False


# ── Welcome email ─────────────────────────────────────────────────────────────

def send_welcome_email(client, env_vars: dict[str, str], lead_email: str, lead_name: str) -> str:
    """
    Look up the Welcome template by name and dispatch via email_engine.py.
    Returns a short status string.
    """
    # Look up template UUID by name
    try:
        result = client.table("email_templates").select("id, name").ilike("name", "Welcome").execute()
        templates = result.data or []
    except Exception as exc:
        return f"template_lookup_failed: {exc}"

    if not templates:
        return "welcome_template_not_found"

    template_id = templates[0]["id"]
    first_name = lead_name.split()[0] if lead_name else lead_email

    vars_json = json.dumps({"first_name": first_name, "name": lead_name, "email": lead_email})

    # scripts/email_engine.py moved to scripts/integrations/ on 2026-05-21
    # (commit 7f47d0f8). scheduler.py's copy of this path was updated; this one
    # was missed, so every welcome email since has died with "can't open file"
    # — latent only because no real lead has arrived to trigger it.
    engine = SCRIPTS_DIR / "integrations" / "email_engine.py"
    if not engine.exists():                       # fail at the call, not silently
        return f"email_engine_missing: {engine}"
    cmd = [
        PYTHON,
        str(engine),
        "--json",
        "send-template",
        "--template-id", template_id,
        "--to", lead_email,
        "--vars", vars_json,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            cwd=str(PROJECT_ROOT),
            creationflags=WINDOWLESS_FLAGS,
        )
        if proc.returncode != 0:
            return f"email_failed: {proc.stderr.strip()[:200]}"
        return "email_sent"
    except subprocess.TimeoutExpired:
        return "email_timeout"
    except Exception as exc:
        return f"email_error: {exc}"


# ── Core sync logic ───────────────────────────────────────────────────────────

def build_notes(lead: dict) -> str:
    """Assemble a notes string from funnel_lead fields."""
    parts: list[str] = []

    interests = lead.get("interests") or []
    if interests:
        parts.append(f"Interests: {', '.join(interests)}")

    if lead.get("event_type"):
        parts.append(f"Event type: {lead['event_type']}")
    if lead.get("event_date"):
        parts.append(f"Event date: {lead['event_date']}")
    if lead.get("music_vibe"):
        parts.append(f"Music vibe: {lead['music_vibe']}")
    if lead.get("brand_goal"):
        parts.append(f"Brand goal: {lead['brand_goal']}")
    if lead.get("audience"):
        parts.append(f"Audience: {lead['audience']}")
    if lead.get("instagram_handle"):
        parts.append(f"Instagram: @{lead['instagram_handle']}")

    return " | ".join(parts) if parts else ""


def run_sync(env_vars: dict[str, str], as_json: bool = False, window_seconds: int = 86400, priority: bool = False) -> None:
    """
    Sync funnel_leads created in the last `window_seconds` seconds into the CRM.

    `priority=True` fires a single consolidated high-priority Telegram digest
    at the end of a multi-lead batch (used by fast-poll mode for realtime alerts).
    `priority=False` uses the per-lead notify() path (used by the daily backstop).
    """
    client = get_client(env_vars)

    since = (datetime.now(timezone.utc) - timedelta(seconds=window_seconds)).isoformat()

    # Fetch funnel leads created in the last 24 hours
    try:
        result = (
            client.table("funnel_leads")
            .select("*")
            .gte("created_at", since)
            .order("created_at", desc=False)
            .execute()
        )
        funnel_leads = result.data or []
    except Exception as exc:
        output = {"error": f"funnel_leads query failed: {exc}", "synced": [], "skipped": [], "errors": []}
        print(json.dumps(output) if as_json else f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    synced: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for lead in funnel_leads:
        email = (lead.get("email") or "").strip().lower()
        name = (lead.get("name") or "").strip()
        lead_id_str = str(lead.get("id", ""))

        if not email:
            skipped.append(f"id={lead_id_str} (no email)")
            continue

        # RACE-SAFE INSERT: use idempotent upsert on email.
        # Two overlapping fast-poll runs could both see "not in CRM yet" and
        # both try to insert. Supabase .upsert(on_conflict="email") is atomic
        # at the DB layer — one wins, the other is a no-op. We still need to
        # distinguish "I inserted this one" vs "someone else already did" to
        # avoid sending duplicate welcome emails / duplicate notifications.
        notes = build_notes(lead)
        payload: dict = {
            "name": name,
            "email": email,
            "source": "cc_funnel",
            "status": "new",
            "tenant_id": OASIS_TENANT_ID,
        }
        if lead.get("phone"):
            payload["phone"] = lead["phone"]
        if lead.get("business_name"):
            payload["company"] = lead["business_name"]
        if notes:
            payload["notes"] = notes

        # Lead contract gate (scripts/lib/lead_contract.py) — drops rows
        # without email/source (cc_funnel always supplies both, but the
        # check guards against contract drift if upstream payload changes).
        # The funnel_fast_poll path runs every few minutes against CC's
        # public funnel, so the operator sees missing_info on the
        # dashboard within one poll cycle of any new submission.
        from lib.lead_contract import has_hard_required  # noqa: E402
        if not has_hard_required(payload):
            errors.append(f"{email}: lead_contract rejected (missing email/source)")
            continue

        # Two-phase race-safe insert:
        #   1. SELECT existing row by email
        #   2. If exists -> skip. If not -> INSERT and handle duplicate-key error gracefully.
        # This is NOT fully atomic in the "two clients race" sense, but the
        # duplicate-key error path below catches it. A true upsert on email
        # would require the leads table to have UNIQUE(email), which we don't
        # control from here. The duplicate-key catch is the backstop.
        try:
            existing = (
                client.table("leads")
                .select("id")
                .ilike("email", email)
                .limit(1)
                .execute()
            )
            if existing.data:
                skipped.append(f"{email} (already in CRM)")
                continue
        except Exception as exc:
            errors.append(f"{email}: leads lookup failed — {exc}")
            continue

        try:
            client.table("leads").insert(payload).execute()
        except Exception as exc:
            # If the insert failed because another parallel run won the race,
            # treat it as "already synced" rather than an error. Match any
            # duplicate-key / unique-violation error string.
            err_lower = str(exc).lower()
            if (
                "duplicate" in err_lower
                or "unique" in err_lower
                or "23505" in err_lower  # PG duplicate key code
            ):
                skipped.append(f"{email} (race: won by parallel run)")
                continue
            errors.append(f"{email}: insert failed — {exc}")
            continue

        # Send welcome email — errors are non-fatal
        email_status = send_welcome_email(client, env_vars, email, name)

        # In priority (fast-poll) mode, defer notification to the end digest.
        # In daily-sync mode, DO NOT notify per-lead here — scheduler's
        # run_funnel_sync wrapper returns a routine skip-phrase so scheduler
        # does not double-notify. Instead, log it to synced and let the
        # daily cron notify CC once per lead via its own single-lead path.
        synced.append({"name": name, "email": email, "email_status": email_status, "notes": notes})

    # Notification strategy:
    #   priority=True (fast-poll)  -> ONE consolidated high-priority digest
    #   priority=False (daily)     -> ONE consolidated digest, but lower-priority phrasing
    # Both emit a single notify() call total per run, regardless of lead count.
    # scheduler.run_funnel_sync returns a routine skip-phrase to prevent the
    # scheduler layer from double-notifying.
    if synced:
        if priority:
            header = f"🔥 <b>NEW FUNNEL LEAD{'S' if len(synced) > 1 else ''} ({len(synced)})</b>\n"
        else:
            header = f"<b>Funnel leads synced ({len(synced)})</b>\n"
        lines = [header]
        for lead in synced:
            lines.append(f"• <b>{lead['name']}</b>")
            lines.append(f"  📧 {lead['email']}")
            if lead.get("notes"):
                lines.append(f"  📝 {lead['notes'][:160]}")
            lines.append(f"  ✉️ Welcome email: {lead['email_status']}")
            lines.append("")
        notify("\n".join(lines), category="lead")

    result_data = {
        "synced": synced,
        "skipped": skipped,
        "errors": errors,
        "total_checked": len(funnel_leads),
        "window_seconds": window_seconds,
        "priority": priority,
    }

    if as_json:
        print(json.dumps(result_data, indent=2))
    else:
        window_label = f"{window_seconds}s" if window_seconds < 3600 else f"{window_seconds // 3600}h"
        print(
            f"Funnel sync: {len(synced)} synced, "
            f"{len(skipped)} skipped, "
            f"{len(errors)} errors "
            f"(checked {len(funnel_leads)} leads from last {window_label})"
        )
        if errors:
            for err in errors:
                print(f"  ERROR: {err}")


def run_stats(env_vars: dict[str, str], as_json: bool = False) -> None:
    client = get_client(env_vars)

    try:
        funnel_result = client.table("funnel_leads").select("id, email, created_at").order("created_at", desc=True).execute()
        funnel_leads = funnel_result.data or []

        crm_result = client.table("leads").select("id, email, source").eq("source", "cc_funnel").execute()
        crm_leads = crm_result.data or []
    except Exception as exc:
        output = {"error": str(exc)}
        print(json.dumps(output) if as_json else f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    stats = {
        "total_funnel_leads": len(funnel_leads),
        "synced_to_crm": len(crm_leads),
        "crm_emails": [r["email"] for r in crm_leads],
    }

    if as_json:
        print(json.dumps(stats, indent=2))
    else:
        print(f"Funnel leads total:  {stats['total_funnel_leads']}")
        print(f"Synced to CRM:       {stats['synced_to_crm']}")
        if crm_leads:
            print("CRM entries (cc_funnel source):")
            for r in crm_leads:
                print(f"  {r['email']}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="funnel_sync.py",
        description="Funnel Lead Sync — syncs recent cc-funnel leads into the CRM",
    )
    parser.add_argument(
        "command",
        choices=["run", "fast-poll", "stats"],
        help="Command to execute (run=24h daily backstop, fast-poll=2min realtime, stats=show state)",
    )
    parser.add_argument("--json", dest="output_json", action="store_true", help="JSON output for agents")
    parser.add_argument("--window", type=int, default=None, help="Override window in seconds (advanced)")
    args = parser.parse_args()

    env_vars = load_env()

    if args.command == "run":
        window = args.window if args.window else 86400  # 24h default
        run_sync(env_vars, as_json=args.output_json, window_seconds=window, priority=False)
    elif args.command == "fast-poll":
        window = args.window if args.window else 120  # 2 min default — overlap with 60s cron
        run_sync(env_vars, as_json=args.output_json, window_seconds=window, priority=True)
    elif args.command == "stats":
        run_stats(env_vars, as_json=args.output_json)


if __name__ == "__main__":
    main()
