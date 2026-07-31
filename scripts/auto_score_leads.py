"""Auto-score OASIS leads — daily cron.

Phase 6a of the OASIS HQ redesign. Companion to the operator-triggered
POST /api/leads/[id]/score (Phase 5a): instead of CC clicking "Score
with AI" on every lead, this script scans tenant_records for OASIS
leads with no ai_score and scores them in batches.

Why a Python script + cron instead of a Vercel route:
  - Long-running batches don't fit in Vercel's request budget. 50 leads
    × 2s/Anthropic call = ~100s; cron jobs are unbounded.
  - The empire briefing snapshot already runs from this script tree;
    keeping AI batches in the same place means one stack to monitor.
  - send_gateway.py + CASL_compliance.py + all the rest of the Python
    machinery is right here.

Behaviour:
  - Find unscored OASIS leads (entity_type=lead, data->>ai_score IS NULL)
  - Skip leads with stage in {won, lost} — scoring a closed lead is wasted
  - Cap at MAX_PER_RUN per invocation so a backlog doesn't burn through
    the Anthropic quota in one shot
  - For each: call the same prompt the TS lib uses (mirrored here so
    one prompt change in lib/ai-lead-scoring.ts triggers a follow-on
    in this script — both paths are intentionally identical)
  - Write {ai_score, ai_reasoning, ai_scored_at} back into data jsonb

CLI:
  python scripts/auto_score_leads.py              # run with default cap
  python scripts/auto_score_leads.py --limit 20   # smaller batch
  python scripts/auto_score_leads.py --dry-run    # show what would score, no API calls
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# Windows CA-bundle fix (2026-07-28) — see lib/tls_trust.py. Found by auditing
# every cron-wired script rather than only the ones that happened to be failing
# loudly: this one had the same latent AV-MITM break and died on its first
# Supabase call with CERTIFICATE_VERIFY_FAILED.
from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from lib.claude_cli import run_claude_cli  # noqa: E402

# Model calls run through the LOCAL claude CLI on CC's subscription OAuth
# (lib.claude_cli) — the metered ANTHROPIC_API_KEY is out of credits and
# banned for automations (2026-07-09 migration; same fix as daily_brief.py).
MODEL_CLI = "sonnet"       # CLI alias — matches the dashboard path's tier
CLI_TIMEOUT_SEC = 60
MAX_PER_RUN_DEFAULT = 25
THROTTLE_SEC = 1.0  # gap between model calls so we don't burst the CLI

# Default OASIS tenant slug. CC's empire tenant lives at slug "oasis-ai-cc"
# (auto-generated when the auth profile was created). Override with
# --tenant-slug or the EMPIRE_TENANT_SLUG env var if the operator moves.
DEFAULT_OASIS_SLUG = "oasis-ai-cc"

# Single source of truth for both the prompt + allowlist. The TypeScript
# dashboard reads the same files via lib/prompts/index.ts so the manual
# "Score with AI" button and this cron path produce identical scores.
#
# Path resolution delegates to scripts/sibling_repos.py — Windows defaults
# to C:\Users\User\APPS\oasis-command-center, Mac to ~/oasis-command-center,
# COMMAND_CENTER_REPO env var overrides on either. Keeps the dashboard's
# canonical location aligned with every other script that needs it.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sibling_repos import SIBLING_REPOS  # noqa: E402

_CC_REPO = SIBLING_REPOS["oasis-command-center"]
PROMPTS_DIR = _CC_REPO / "lib" / "prompts"
if not PROMPTS_DIR.exists():
    sys.stderr.write(
        f"auto_score_leads: prompt files not found at {PROMPTS_DIR}\n"
        "Either clone https://github.com/CC90210/oasis-command-center to "
        f"{_CC_REPO}, or set COMMAND_CENTER_REPO=<path>.\n"
    )
    sys.exit(2)
SYSTEM_PROMPT = (PROMPTS_DIR / "oasis-lead-scoring.txt").read_text(encoding="utf-8").strip()
INCLUDED_FIELDS = json.loads(
    (PROMPTS_DIR / "included-fields.json").read_text(encoding="utf-8")
)["lead_scoring"]

# Stages worth scoring. Closed-out leads stay frozen at their last score.
SCORABLE_STAGES = {"new", "contacted", "qualified", "proposal", "negotiation"}


def _client():
    from lib.secret_loader import load_env  # noqa: E402
    env = load_env()
    url = (env.get("BRAVO_SUPABASE_URL") or "").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        sys.stderr.write("ERROR: missing Supabase credentials\n")
        sys.exit(2)
    from supabase import create_client
    return create_client(url, key)


def _score_one(lead_data: dict) -> tuple[int, str] | None:
    """Returns (score, reasoning) or None on any failure. Never raises.

    2026-06-06 prompt update: the shared SYSTEM_PROMPT now references an
    'interactions' array Claude should weight. The dashboard path fetches
    lead_interactions and includes them; this auto-score cron runs only
    on UNSCORED leads (typically brand-new with no interactions), so we
    explicitly signal the absence rather than fetch + send an empty
    array. Keeps the lite cron lite without confusing Claude about a
    missing field.
    """
    relevant = {k: v for k, v in lead_data.items()
                if k in INCLUDED_FIELDS and v not in (None, "", [], {})}
    user_prompt = (
        "Score this lead.\n\n"
        f"Lead data:\n{json.dumps(relevant, indent=2, default=str)}\n\n"
        "Interactions (most recent first, 0 of 0 shown):\n"
        "[none recorded — score from lead data only, note 'limited signal' in reasoning if so]"
    )

    text = run_claude_cli(
        user_prompt, system=SYSTEM_PROMPT,
        model=MODEL_CLI, timeout=CLI_TIMEOUT_SEC,
    )
    if not text:
        sys.stderr.write("  claude CLI call failed (see [claude_cli] stderr)\n")
        return None
    cleaned = text
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        sys.stderr.write(f"  parse fail: {text[:200]}\n")
        return None

    score = parsed.get("score")
    reasoning = parsed.get("reasoning")
    if not isinstance(score, (int, float)) or not isinstance(reasoning, str):
        return None
    score_int = int(round(score))
    if score_int < 0 or score_int > 100 or not reasoning.strip():
        return None
    return score_int, reasoning.strip()


def _unscored_oasis_leads(client, limit: int, tenant_slug: str) -> list[dict]:
    """Pull leads on the OASIS tenant with no ai_score and a scorable
    stage. Filtering happens client-side because Postgres jsonb
    "->>" lookups for missing keys are awkward through the supabase-py
    builder — we pull a wider net and filter in Python."""
    # Resolve tenant id from slug. The OASIS empire tenant defaults to
    # 'oasis-ai-cc'; --tenant-slug overrides if the operator moved.
    # limit(1) + array shape instead of maybe_single() — newer supabase-py
    # raises on 0 rows from maybe_single().
    t = (client.table("tenants").select("id").eq("slug", tenant_slug).limit(1).execute())
    tenant_rows = t.data or []
    if not tenant_rows:
        sys.stderr.write(f"Tenant slug '{tenant_slug}' not found in tenants table — nothing to score\n")
        return []
    tenant_id = tenant_rows[0]["id"]

    r = (client.table("tenant_records")
         .select("id, data")
         .eq("tenant_id", tenant_id)
         .eq("entity_type", "lead")
         .order("updated_at", desc=True)
         .limit(max(limit * 4, 100))
         .execute())

    unscored: list[dict] = []
    for row in r.data or []:
        data = row.get("data") or {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, ValueError):
                continue
        stage = (data.get("stage") or data.get("status") or "").strip().lower()
        if stage and stage not in SCORABLE_STAGES:
            continue
        if data.get("ai_score") is not None:
            continue
        unscored.append({"id": row["id"], "data": data, "tenant_id": tenant_id})
        if len(unscored) >= limit:
            break
    return unscored


def _write_score(client, tenant_id: str, lead_id: str, lead_data: dict, score: int, reasoning: str) -> bool:
    merged = {
        **lead_data,
        "ai_score": score,
        "ai_reasoning": reasoning,
        "ai_scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        client.table("tenant_records").update({"data": merged}).eq("tenant_id", tenant_id).eq("entity_type", "lead").eq("id", lead_id).execute()
        return True
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"  write failed lead={lead_id[:8]}: {e}\n")
        return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--limit", type=int, default=MAX_PER_RUN_DEFAULT,
                   help=f"max leads to score per run (default {MAX_PER_RUN_DEFAULT})")
    p.add_argument("--tenant-slug", type=str,
                   default=os.environ.get("EMPIRE_TENANT_SLUG", DEFAULT_OASIS_SLUG),
                   help=f"target tenant slug (default {DEFAULT_OASIS_SLUG}; override via EMPIRE_TENANT_SLUG env)")
    p.add_argument("--dry-run", action="store_true",
                   help="print what would be scored, no Anthropic calls or writes")
    args = p.parse_args(argv)

    client = _client()
    leads = _unscored_oasis_leads(client, args.limit, args.tenant_slug)

    if not leads:
        print("No unscored OASIS leads in scorable stages.")
        return 0

    print(f"Found {len(leads)} unscored leads. Scoring...")
    if args.dry_run:
        for lead in leads:
            d = lead["data"]
            print(f"  [DRY] {lead['id'][:8]} {d.get('name', '?')[:30]} stage={d.get('stage', '?')}")
        return 0

    scored = 0
    failed = 0
    for i, lead in enumerate(leads, 1):
        d = lead["data"]
        name_preview = (d.get("name") or "?")[:30]
        print(f"  [{i}/{len(leads)}] {lead['id'][:8]} {name_preview}...", end="", flush=True)
        result = _score_one(d)
        if not result:
            print(" FAIL")
            failed += 1
            continue
        score, reasoning = result
        if _write_score(client, lead["tenant_id"], lead["id"], d, score, reasoning):
            print(f" {score}")
            scored += 1
        else:
            print(" WRITE FAIL")
            failed += 1
        if i < len(leads):
            time.sleep(THROTTLE_SEC)

    print(f"\nDone. {scored} scored, {failed} failed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
