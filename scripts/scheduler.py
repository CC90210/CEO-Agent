"""
Bravo Scheduler - Autonomous Business Operations Daemon

This is the heartbeat of the business agent. It runs 24/7 via PM2 and
executes cron jobs defined in Supabase on schedule.

What it does every 60 seconds:
  1. Checks which cron jobs are due (next_run_at <= now)
  2. Executes the action for each due job
  3. Updates last_run_at and schedules the next run

Start: pm2 start scripts/scheduler.py --name bravo-scheduler --interpreter python
Stop:  pm2 stop bravo-scheduler

All credentials loaded from .env.agents (never hardcoded).
"""

import json
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List

# Shared Windows console-suppression flag — see scripts/_subprocess_helpers.
# The constant lived in this file (and 5 others) before consolidation;
# re-exported under the old name so existing imports keep working.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _subprocess_helpers import WINDOWLESS_FLAGS as CREATE_NO_WINDOW  # noqa: E402

# Notification system
try:
    from notify import notify, notify_error
except ImportError:
    def notify(*a, **kw): return False
    def notify_error(*a, **kw): return False

# Local-time cron parser + quiet-day awareness (2026-05-17).
# Replaces the UTC-naive calculate_next_run that fired the 8am Pow Wow
# at 04:00 ET on Victoria Day weekend. See schedule_helpers.py header.
from schedule_helpers import (
    next_local_cron_run_iso,
    is_quiet_day,
    today_local,
)

# ── Config ────────────────────────────────────────────────────────────────────

CHECK_INTERVAL_SECONDS = 60  # How often to check for due jobs
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
PYTHON = sys.executable  # Use same Python that's running this script

# Action types that were retired but whose handlers are kept as no-op stubs
# (see execute_job dispatch). On startup, the orphan-cron self-check warns
# if any cron_jobs row still uses one of these — a 39-day silent-pings
# incident (MISTAKES.md 2026-05-16: Daily Outreach Batch) was caused by an
# orphan row hiding without ever surfacing in any audit. Append here when
# retiring a new action_type.
RETIRED_ACTIONS: frozenset[str] = frozenset({
    "lead_outreach_batch",  # retired 2026-05-16 — see feedback_no_cold_outreach_cron.md
})


# ── Credential loading ────────────────────────────────────────────────────────

def load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env.agents"
    if not env_path.exists():
        print(f"FATAL: {env_path} not found", flush=True)
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
    from supabase import create_client
    url = env_vars.get("BRAVO_SUPABASE_URL")
    key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("FATAL: BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY missing", flush=True)
        sys.exit(1)
    return create_client(url, key)


# ── Cron schedule parsing ─────────────────────────────────────────────────────

def parse_cron_schedule(schedule: str) -> Optional[timedelta]:
    """
    Convert a cron schedule string to a timedelta for the next run interval.
    Supports common patterns. Not a full cron parser - covers our 12 jobs.
    """
    parts = schedule.strip().split()
    if len(parts) != 5:
        return None

    minute, hour, dom, month, dow = parts

    # Every N minutes: */N * * * *
    if minute.startswith("*/") and hour == "*" and dom == "*" and month == "*" and dow == "*":
        try:
            interval_min = int(minute[2:])
            return timedelta(minutes=interval_min)
        except ValueError:
            pass

    # Daily jobs: specific hour, * * *
    if dom == "*" and month == "*" and dow == "*":
        return timedelta(hours=24)

    # Weekday jobs: * * MON-FRI or MON,WED,FRI
    if dom == "*" and month == "*" and dow != "*":
        dow_lower = dow.lower()
        if "-" in dow_lower:
            # MON-FRI = 5 days, so average interval ~24h (run daily on weekdays)
            return timedelta(hours=24)
        elif "," in dow_lower:
            # MON,WED,FRI = 3 days per week, average ~56h
            day_count = len(dow_lower.split(","))
            return timedelta(hours=int(168 / day_count))
        else:
            # Single day per week (e.g., MON)
            return timedelta(days=7)

    # Monthly jobs: specific day of month
    if dom != "*" and month == "*":
        return timedelta(days=30)

    return timedelta(hours=24)  # Fallback: daily


def calculate_next_run(schedule: str) -> str:
    """Calculate the next run time based on the cron schedule.

    Prefers the local-time cron parser (schedule_helpers.next_local_cron_run_iso)
    so "0 8 * * *" means 08:00 in CC's timezone, not 08:00 UTC. Falls back to
    the legacy interval-add path only when the schedule isn't parseable by
    the local helper (kept so unusual expressions still get a next_run_at and
    a row never goes dead).
    """
    next_iso = next_local_cron_run_iso(schedule)
    if next_iso:
        return next_iso
    interval = parse_cron_schedule(schedule)
    if not interval:
        interval = timedelta(hours=24)
    next_time = datetime.now(timezone.utc) + interval
    return next_time.isoformat()


# ── Job execution ─────────────────────────────────────────────────────────────

def execute_job(job: dict, env_vars: dict[str, str]) -> str:
    """
    Execute a cron job based on its action_type.
    Returns a result string for logging.
    """
    action_type = job.get("action_type", "")
    config = job.get("action_config") or {}
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except json.JSONDecodeError:
            config = {}

    job_name = job.get("name", "unknown")
    log(f"EXECUTING: {job_name} (type={action_type})")

    try:
        # Marketing-domain action types (content_post, ig_*, content_generate,
        # content_repurpose, content_planning) were moved to Maven on 2026-04-26.
        # If a legacy DB row still has one of those types, route it to a
        # human-readable "moved" marker rather than failing silently.
        MAVEN_DOMAIN_ACTIONS = {
            "content_post", "ig_research", "ig_dm_check", "ig_auto_reply",
            "content_generate", "content_repurpose", "content_planning",
            # Phase 9.1 — Maven Token Expiry Check ships from CMO-Agent.
            # Was emitting "unknown_action_type" on this dashboard's
            # bravo-scheduler because the row exists empire-side but the
            # handler doesn't. Mark as moved so the Health page shows a
            # clean "moved_to_maven" instead of red.
            "maven_token_check",
        }
        # Atlas-domain actions ship from APPS/CFO-Agent. Same rationale
        # as MAVEN_DOMAIN_ACTIONS — bridge rows that have no local handler.
        ATLAS_DOMAIN_ACTIONS = {
            "atlas_wealth_refresh",
        }
        if action_type in ATLAS_DOMAIN_ACTIONS:
            return f"moved_to_atlas: {action_type} is now owned by CFO-Agent"
        if action_type in MAVEN_DOMAIN_ACTIONS:
            return f"moved_to_maven: {action_type} is now owned by CMO-Agent"
        if action_type in RETIRED_ACTIONS:
            # Single source of truth: RETIRED_ACTIONS (defined at module
            # top). Adding a new retirement only requires appending to the
            # set — no second elif branch to keep in sync. See MISTAKES.md
            # 2026-05-16 for the incident that motivated this pattern.
            return (
                f"retired: {action_type} — see RETIRED_ACTIONS in scheduler.py "
                f"and memory/feedback_no_cold_outreach_cron.md (if applicable). "
                f"Delete the orphan cron_jobs row."
            )
        if action_type == "lead_followup":
            return run_lead_followup(env_vars)
        elif action_type == "booking_reminder":
            return run_booking_reminder(env_vars)
        elif action_type == "stripe_sync":
            return run_stripe_sync(env_vars)
        elif action_type == "revenue_report":
            return run_revenue_report(env_vars)
        elif action_type == "pipeline_review":
            return run_pipeline_review(env_vars)
        elif action_type == "nurture_check":
            return run_nurture_check(env_vars)
        elif action_type == "monthly_snapshot":
            return run_monthly_snapshot(env_vars)
        elif action_type == "email_inbox_check":
            return run_email_inbox_check(env_vars)
        elif action_type == "funnel_sync":
            return run_funnel_sync(env_vars)
        elif action_type == "funnel_fast_poll":
            return run_funnel_fast_poll(env_vars)
        elif action_type == "agent_self_improvement":
            return run_agent_self_improvement(env_vars)
        elif action_type == "daily_brief":
            return run_daily_brief(env_vars)
        elif action_type == "auto_score_leads":
            return run_auto_score_leads(env_vars)
        elif action_type == "snapshot_run":
            return run_snapshot(config)
        elif action_type == "script_run":
            return run_script_action(config)
        elif action_type == "morning_powwow":
            return run_morning_powwow(env_vars)
        else:
            # Round 3 R3-12: previously this returned a plain string
            # which scheduler.py's caller treats as success and stamps
            # into last_result. Operators couldn't distinguish "handler
            # ran and reported unknown" from "handler doesn't exist"
            # — failed crons hid in the green column. ERROR: prefix
            # routes through the same status-detection path that
            # genuine failures use, so the Automations panel surfaces
            # it in red and Telegram alerting (R3-11) can pick it up.
            return f"ERROR: unknown_action_type:{action_type} — add a handler in scheduler.py or remove the cron job"
    except Exception as exc:
        error_msg = f"ERROR: {exc}"
        log(error_msg)
        return error_msg


def run_script(script_name: str, args: List[str], timeout: int = 120) -> str:
    """Run a Python script from the scripts/ directory and return its output."""
    cmd = [PYTHON, str(SCRIPTS_DIR / script_name)] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        cwd=str(PROJECT_ROOT),
        creationflags=CREATE_NO_WINDOW,
    )
    output = result.stdout.strip()
    if result.returncode != 0:
        error = result.stderr.strip()
        return f"FAILED (exit {result.returncode}): {error[:2000]}"
    if not output:
        return "ok"
    # 2026-04-11: capped at 8000 chars to prevent runaway stdout. 2026-05-15:
    # found that cap was breaking `lead_followup` because the 20-row JSON
    # dump from `lead_engine.py --json list` is ~12,500 chars — truncating
    # mid-string left an unterminated JSON value that crashed json.loads()
    # downstream. Behavior the cron exhibited for 25 days straight before
    # the catch: log "ERROR: lead_followup list JSON parse failed:
    # Unterminated string starting at: line 247 column 14 (char 7906)".
    #
    # New policy: JSON output (starts with `[` or `{`) is NOT truncated —
    # the downstream parser needs the whole thing intact. We cap at 200KB
    # as a fork-bomb guard but report-don't-truncate. Plain text output is
    # still capped at 8KB.
    if output[:1] in ("[", "{"):
        if len(output) > 200_000:
            return f"FAILED (exit 0): json output exceeds 200KB ({len(output)} bytes) — refusing to truncate JSON"
        return output
    return output[:8000]


# ── Job handlers ──────────────────────────────────────────────────────────────
#
# Marketing-domain handlers (run_content_post, run_ig_dm_check,
# run_content_generate, run_content_repurpose, run_content_planning)
# were removed on 2026-04-26 when content + social ownership transferred
# to Maven (CMO-Agent). Maven owns its own scheduler for those jobs.
# The dispatch above routes legacy DB rows with those action_types to a
# "moved_to_maven" marker so they don't fail loudly during the cutover.


def run_lead_followup(env_vars: dict) -> str:
    """Check for leads needing follow-up and auto-score unscored leads.

    V2.1 2026-04-11: Fail-closed. Removed blanket exception swallow.
    Subprocess errors, non-JSON output, and parse failures all surface as
    ERROR instead of being silenced. Matches the pattern of run_stripe_sync,
    run_nurture_check, run_funnel_sync, run_funnel_fast_poll.
    """
    # Phase 1: fetch leads list. Cap to the most recent 50 since this job
    # is checking for overdue follow-ups, not auditing the whole CRM. The
    # 50 cap also keeps the JSON dump well under the 200KB ceiling
    # run_script enforces.
    leads_result = run_script("lead_engine.py", ["--json", "list", "--limit", "50"])
    if not leads_result or leads_result.startswith("FAILED"):
        return f"ERROR: lead_followup list failed: {leads_result[:200] if leads_result else 'empty'}"

    # JSON parse is required in --json mode. Non-JSON output means something broke.
    stripped = leads_result.strip()
    if not stripped.startswith(("[", "{")):
        return f"ERROR: lead_followup list returned non-JSON: {stripped[:200]}"
    try:
        leads = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return f"ERROR: lead_followup list JSON parse failed: {exc}"

    # Phase 2: auto-score any unscored leads
    scored = 0
    score_errors = 0
    for lead in (leads if isinstance(leads, list) else []):
        if isinstance(lead, dict) and (lead.get("score") or 0) == 0 and lead.get("id"):
            score_result = run_script("lead_engine.py", ["--json", "score", lead["id"]])
            if not score_result or score_result.startswith("FAILED"):
                score_errors += 1
            else:
                scored += 1

    score_msg = f", scored {scored} lead(s)" if scored else ""
    err_msg = f", {score_errors} score error(s)" if score_errors else ""

    # Phase 3: fetch the followups list
    followups = run_script("lead_engine.py", ["--json", "followups"])
    if not followups or followups.startswith("FAILED"):
        return f"ERROR: lead_followup followups failed: {followups[:200] if followups else 'empty'}{err_msg}"

    # Non-JSON and non-routine output is still allowed (lead_engine followups
    # emits a human-friendly string when there are no follow-ups to report).
    # But we bubble up any score_errors as an ERROR so CC sees them.
    if score_errors:
        return f"ERROR: lead_followup: {followups[:150]}{score_msg}{err_msg}"

    return followups + score_msg


def run_booking_reminder(env_vars: dict) -> str:
    """Check tomorrow's bookings and flag reminders."""
    return run_script("booking_engine.py", ["--json", "remind"])


def run_stripe_sync(env_vars: dict) -> str:
    """Sync recent Stripe events into revenue_events table.

    Fail-closed parsing: any parse failure, exit-code error, or top-level
    `error` field is reported as ERROR so the alerting layer surfaces it.
    Only a CLEAN JSON result with `inserted == 0 && errors == 0` is
    classified as routine-silent.
    """
    result = run_script("revenue_engine.py", ["--json", "sync-stripe"])

    # Fail-closed: non-JSON output or FAILED prefix means something broke
    if not result or not result.strip().startswith("{"):
        return f"ERROR: stripe sync returned non-JSON: {result[:200]}"
    if result.startswith("FAILED"):
        return f"ERROR: stripe sync {result[:300]}"

    try:
        data = json.loads(result)
    except (json.JSONDecodeError, TypeError) as exc:
        return f"ERROR: stripe sync JSON parse failed: {exc}"

    # Top-level error field is a hard failure, not a routine result
    if data.get("error"):
        return f"ERROR: stripe sync {data['error']}"

    inserted = int(data.get("inserted", 0) or 0)
    errors = int(data.get("errors", 0) or 0)

    if inserted == 0 and errors == 0:
        return "stripe sync ok: 0 new events"  # routine -> silent

    parts = []
    if inserted:
        parts.append(f"{inserted} new Stripe event(s)")
    if errors:
        parts.append(f"{errors} errors")
    return "Stripe: " + ", ".join(parts)


def _send_digest(msg: str, category: str, skip_phrase: str) -> str:
    """Send a multi-line digest via notify() and return a skip-phrase.

    The scheduler wrapper at the bottom of run_due_jobs() truncates
    result_msg to 200 chars. Multi-line digests have to bypass it by
    notifying directly, then returning a routine-prefix string registered
    in routine_prefixes so the wrapper stays quiet.
    """
    notify(msg, category=category, silent=False)
    return skip_phrase


def run_revenue_report(env_vars: dict) -> str:
    """Generate MRR dashboard summary as a clean Telegram message."""
    raw = run_script("revenue_engine.py", ["--json", "dashboard"])
    if not raw or not raw.strip().startswith("{"):
        return f"ERROR: revenue dashboard returned non-JSON: {raw[:200]}"
    try:
        d = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        return f"ERROR: revenue dashboard JSON parse failed: {exc}"

    mrr = d.get("mrr", 0)
    goal = d.get("mrr_goal", 5000)
    pct = d.get("mrr_pct", 0)
    gap = d.get("gap", 0)
    clients_needed = d.get("clients_needed", 0)
    pipeline = d.get("pipeline", 0)
    leads = d.get("leads", 0)
    conv = d.get("conversion_rate", 0)
    last = d.get("last_payment") or {}

    # Days left to North Star deadline (May 30 per CLAUDE.md WHY section).
    import datetime as _dt
    deadline = _dt.date(2026, 5, 30)
    days_left = max((deadline - _dt.date.today()).days, 0)

    # 12-wide progress bar with three glyphs (▓ for the rough fill edge so
    # the bar looks intentional rather than blocky at boundaries).
    bar_len = 12
    pct_clamped = max(0.0, min(pct, 100.0))
    filled_f = pct_clamped / 100 * bar_len
    full = int(filled_f)
    partial = 1 if (filled_f - full) >= 0.5 and full < bar_len else 0
    empty = bar_len - full - partial
    bar = "█" * full + ("▓" if partial else "") + "░" * empty

    # Days since last payment — surfaces "going stale" risk implicitly.
    last_days = ""
    if last and last.get("date"):
        try:
            last_date = _dt.date.fromisoformat(str(last["date"])[:10])
            last_days = f"  ·  {(_dt.date.today() - last_date).days}d ago"
        except Exception:
            pass

    lines = [
        f"📊 *MRR*  ${mrr:,.0f} / ${goal:,.0f}  ·  {pct:.1f}%",
        f"`{bar}`  ${gap:,.0f} to go  ·  {days_left}d left",
        "",
        f"Pipeline   ${pipeline:,.0f}  ·  {leads} active  ·  {conv:.1f}% conv",
    ]
    if last:
        lines.append(
            f"Last paid  ${last.get('amount', 0):,.0f} · {last.get('client', '?')[:30]}{last_days}"
        )
    if clients_needed > 0:
        clients_word = "client" if clients_needed == 1 else "clients"
        lines.append("")
        lines.append(f"→ {clients_needed} {clients_word} closes the gap")
    return _send_digest("\n".join(lines), "revenue", "revenue-report-handled-by-digest")


def run_agent_self_improvement(env_vars: dict) -> str:
    """Run cross-agent self-improvement sweep (Bravo + Atlas + Maven).

    Delegates to scripts/core/agent_self_improvement.py for the full digest, then
    sends it via notify() directly (wrapper truncates at 200 chars).
    """
    out = run_script("agent_self_improvement.py", ["run"])
    if not out or not out.strip():
        return "ERROR: agent_self_improvement returned empty output"
    return _send_digest(out.strip(), "system", "self-improvement-handled-by-digest")


def run_daily_brief(_env_vars: dict) -> str:
    """Phase 5c — daily AI-narrated brief to CC's Telegram.

    scripts/daily_brief.py reads the latest briefing snapshot (regenerating
    if >24h stale), hands the JSON to Claude Sonnet for a 5-bullet
    narration, and ships it to Telegram via notify(force=True). The brief
    self-ships — this handler just invokes the script and returns the
    stdout so cron_jobs.last_result captures whether it landed.
    """
    out = run_script("daily_brief.py", [], timeout=90)
    if not out or not out.strip():
        return "ERROR: daily_brief returned empty output"
    first_line = out.strip().splitlines()[0]
    return f"sent: {first_line[:120]}"


def run_snapshot(config: dict) -> str:
    """Generic snapshot_run handler — invokes the Python script named in
    action_config['script'] with action_config['args'] as argv.

    Used by three SEED_JOBS today (Daily Briefing, Weekly Qualified-Leads,
    Daily Client Alerts) — all of which produce state/snapshots/latest_*.json
    files for the Prep Table layer. Before this handler existed they were
    landing in the dashboard's Automations panel as
    "ERROR: unknown_action_type:snapshot_run".

    action_config shape:
      {"script": "scripts/snapshots/briefing_snapshot.py", "args": ["--min-score", "60"]}

    Returns the script's stdout (first line) on success, or "ERROR: ..." on
    failure so cron_jobs.last_result drives the red/green badge.
    """
    script = config.get("script", "")
    args = config.get("args") or []
    if not script or not isinstance(script, str):
        return "ERROR: snapshot_run config missing 'script' path"
    if not isinstance(args, list):
        return "ERROR: snapshot_run config 'args' must be a list"

    # Resolve script path. SEED_JOBS use the repo-relative path
    # "scripts/snapshots/briefing_snapshot.py"; run_script() expects just
    # the filename + directory under SCRIPTS_DIR. Build the full command
    # inline so subdirectory scripts work without overloading run_script.
    full_path = PROJECT_ROOT / script
    if not full_path.exists():
        return f"ERROR: snapshot_run script not found: {script}"

    try:
        result = subprocess.run(
            [PYTHON, str(full_path), *[str(a) for a in args]],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
            cwd=str(PROJECT_ROOT),
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: snapshot_run timed out (300s): {script}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: snapshot_run failed: {exc}"

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "non-zero exit").strip()[:300]
        return f"ERROR: snapshot_run exit {result.returncode}: {err}"
    out = (result.stdout or "").strip().splitlines()
    return out[-1][:200] if out else "ok"


def run_script_action(config: dict) -> str:
    """Generic script_run handler — invokes the Python script named in
    action_payload['script'] with action_payload['args'] as argv.

    This is the handler the CronJobsManager UI declares (ActionType union
    in components/automations/CronJobsManager.tsx) and the Phase 10.3
    "Describe an automation" flow targets. Mirror of run_snapshot above
    but for arbitrary tenant scripts.

    action_payload / action_config shape (the dispatcher accepts either
    key — config is what the empire-side cron_jobs row stores, payload
    is what tenant_cron_jobs uses):
      {"script": "scripts/foo.py", "args": ["--limit", "10"]}

    Returns the script's last stdout line on success, or "ERROR: ..." on
    failure so cron_jobs.last_result drives the red/green badge.
    """
    script = config.get("script", "")
    args = config.get("args") or []
    if not script or not isinstance(script, str):
        return "ERROR: script_run config missing 'script' path"
    if not isinstance(args, list):
        return "ERROR: script_run config 'args' must be a list"

    full_path = PROJECT_ROOT / script
    if not full_path.exists():
        return f"ERROR: script_run target not found: {script}"

    try:
        result = subprocess.run(
            [PYTHON, str(full_path), *[str(a) for a in args]],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
            cwd=str(PROJECT_ROOT),
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: script_run timed out (300s): {script}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: script_run failed: {exc}"

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "non-zero exit").strip()[:300]
        return f"ERROR: script_run exit {result.returncode}: {err}"
    out = (result.stdout or "").strip().splitlines()
    return out[-1][:200] if out else "ok"


def run_morning_powwow(_env_vars: dict) -> str:
    """Phase 10.2 — Morning Pow Wow Call (Aura).

    Daily 08:00 voice-note to CC's Telegram. Aura drafts a ~120-word
    monologue (scripts/aura/brain.py), renders it in her voice
    (scripts/aura/voice.py), Telegram sendVoice ships it as an inline
    voicemail via notify_voice. Self-contained in scripts/aura/; this
    handler is a thin shell so the Health page surfaces it as a real
    cron row.

    Relocated 2026-05-17 from scripts/morning_powwow.py into the Aura
    home directory — the brain + voice primitives are reusable across
    every future Aura cron job.

    Quiet-day guard (added 2026-05-17 after a 04:00 ET Sunday-of-the-
    Victoria-Day-long-weekend voice ping): if today is a Saturday,
    Sunday, or Ontario stat holiday, the pow wow doesn't fire. CC isn't
    cold-calling on those days, doesn't need a "let's go, baby" voicemail
    on them either. Returns a "quiet-day:" routine-silent phrase so the
    scheduler advances next_run_at without notifying CC.
    """
    today = today_local()
    quiet, reason = is_quiet_day(today)
    if quiet:
        return f"quiet-day:{reason} — pow wow skipped for {today.isoformat()}"

    full_path = PROJECT_ROOT / "scripts" / "aura" / "morning_powwow.py"
    try:
        result = subprocess.run(
            [PYTHON, str(full_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            cwd=str(PROJECT_ROOT),
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return "ERROR: morning_powwow timed out (120s)"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: morning_powwow failed: {exc}"
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "non-zero exit").strip()[:300]
        return f"ERROR: morning_powwow exit {result.returncode}: {err}"
    out = (result.stdout or "").strip().splitlines()
    return out[-1][:200] if out else "ok"


def run_auto_score_leads(_env_vars: dict) -> str:
    """Phase 6a — score unscored OASIS leads in a daily batch.

    Each new lead would otherwise sit unscored until CC clicked the
    "Score with AI" button on its detail page. This handler delegates
    to scripts/auto_score_leads.py which scans tenant_records, scores
    leads in scorable stages (new / contacted / qualified / proposal /
    negotiation), and writes ai_score + ai_reasoning + ai_scored_at
    back into the data jsonb.
    """
    out = run_script("auto_score_leads.py", ["--limit", "25"], timeout=600)
    if not out or not out.strip():
        return "ERROR: auto_score_leads returned empty output"
    # The script prints "Done. N scored, M failed." on its last line.
    last_line = out.strip().splitlines()[-1]
    return last_line[:200]


def run_pipeline_review(env_vars: dict) -> str:
    """Generate pipeline summary as a clean Telegram message."""
    raw = run_script("lead_engine.py", ["--json", "pipeline"])
    if not raw or not raw.strip().startswith("{"):
        return f"ERROR: pipeline review returned non-JSON: {raw[:200]}"
    try:
        d = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        return f"ERROR: pipeline review JSON parse failed: {exc}"

    stage_order = ["new", "contacted", "qualified", "proposal", "won", "lost"]
    stage_emoji = {
        "new": "🆕",
        "contacted": "📨",
        "qualified": "🎯",
        "proposal": "📝",
        "won": "✅",
        "lost": "❌",
    }
    total = sum((d.get(s, {}) or {}).get("count", 0) for s in stage_order)
    qualified_info = d.get("qualified", {}) or {}
    qualified_count = qualified_info.get("count", 0)
    qualified_score = qualified_info.get("avg_score")

    # Headline: top-of-message TL;DR so CC scans the action first.
    headline_action = ""
    if qualified_count > 0:
        score_part = f" (avg score {qualified_score:.0f})" if qualified_score is not None else ""
        plural = "lead" if qualified_count == 1 else "leads"
        headline_action = f"  ·  {qualified_count} qualified {plural} ready{score_part}"

    lines = [
        f"🎯 *Pipeline*  {total} total{headline_action}",
        "",
    ]
    # Right-aligned numbers + drop zero-count stages so the eye lands on the
    # rows that matter. The old layout printed all 6 stages even when 4 were
    # empty, which made the actionable stage hard to spot.
    for stage in stage_order:
        info = d.get(stage, {}) or {}
        count = info.get("count", 0)
        if count == 0 and stage in ("proposal", "lost"):
            continue  # noise — skip empty pre-proposal stages
        score = info.get("avg_score")
        score_txt = f"   avg {score:.0f}" if score is not None and count > 0 else ""
        marker = "  ← ready" if stage == "qualified" and count > 0 else ""
        lines.append(f"  {count:>3}  {stage_emoji[stage]} {stage.capitalize():<10}{score_txt}{marker}")

    if qualified_count > 0:
        lines.append("")
        plural = "lead" if qualified_count == 1 else "leads"
        lines.append(f"→ Surface the qualified {plural} today")
    return _send_digest("\n".join(lines), "lead", "pipeline-review-handled-by-digest")


def run_nurture_check(env_vars: dict) -> str:
    """Run funnel lead nurture sequence (Day 2 + Day 5 follow-ups).

    Fail-closed parsing: funnel_nurture.py fires its OWN rich Telegram digest
    via notify() when day2_sent or day5_sent > 0, so this handler returns a
    routine skip-phrase to prevent scheduler double-notify. Parse failures,
    stderr output, or any errors field break the filter and surface ERROR.
    """
    funnel_result = run_script("funnel_nurture.py", ["--json", "run"])

    # Fail-closed: non-JSON output means noise leaked to stdout or runtime error
    if not funnel_result or not funnel_result.strip().startswith("{"):
        # funnel_nurture prints human-readable status when not in --json mode,
        # but in --json mode stdout should be pure JSON. Non-{ prefix = broken.
        return f"ERROR: nurture returned non-JSON: {funnel_result[:200]}"
    if funnel_result.startswith("FAILED"):
        return f"ERROR: nurture {funnel_result[:300]}"

    try:
        data = json.loads(funnel_result)
    except (json.JSONDecodeError, TypeError) as exc:
        return f"ERROR: nurture JSON parse failed: {exc}"

    day2 = len(data.get("day2_sent", []) or [])
    day5 = len(data.get("day5_sent", []) or [])
    errors_list = data.get("errors", []) or []
    errors = len(errors_list)

    # Zero-action runs = routine-silent. funnel_nurture's own digest handles
    # the actionable case, so the scheduler wrap intentionally stays quiet
    # here via the skip_phrases filter.
    if day2 == 0 and day5 == 0 and errors == 0:
        return "nurture run complete: no follow-ups due"  # routine -> silent

    parts = []
    if day2:
        parts.append(f"{day2} Day-2 sent")
    if day5:
        parts.append(f"{day5} Day-5 sent")
    if errors:
        parts.append(f"{errors} errors: {errors_list[0][:100] if errors_list else ''}")
    # Return "nurture-handled-by-digest" phrase so the scheduler wrap stays
    # silent (funnel_nurture already sent the rich HTML digest). If errors
    # exist, we DO want scheduler to surface them — ERROR breaks the filter.
    if errors:
        return "ERROR: nurture had failures: " + ", ".join(parts)
    return "nurture-handled-by-digest: " + ", ".join(parts)  # routine -> silent


def run_monthly_snapshot(env_vars: dict) -> str:
    """Log monthly metrics snapshot."""
    return run_script("revenue_engine.py", ["--json", "mrr"])


def run_email_inbox_check(env_vars: dict) -> str:
    """Check Gmail inbox for unread emails, notify CC, mark as read."""
    return run_script("email_engine.py", ["--json", "check-inbox"], timeout=60)


def run_funnel_sync(_env_vars: dict) -> str:
    """Sync new funnel_leads from the last 24h into the CRM leads table.

    Fail-closed: non-JSON output or top-level error becomes ERROR. In priority
    (fast-poll) mode, funnel_sync.py fires its own consolidated Telegram digest,
    so this handler returns a routine-silent phrase to prevent scheduler
    double-notify. In daily mode, scheduler does the notification.
    """
    result = run_script("funnel_sync.py", ["run", "--json"], timeout=60)

    if not result or not result.strip().startswith("{"):
        return f"ERROR: funnel sync returned non-JSON: {result[:200]}"
    if result.startswith("FAILED"):
        return f"ERROR: funnel sync {result[:300]}"

    try:
        data = json.loads(result)
    except (json.JSONDecodeError, TypeError) as exc:
        return f"ERROR: funnel sync JSON parse failed: {exc}"

    if data.get("error"):
        return f"ERROR: funnel sync {data['error']}"

    synced = data.get("synced", []) or []
    errors = data.get("errors", []) or []

    if not synced and not errors:
        return "funnel sync: 0 new leads"  # routine -> silent

    if errors:
        return f"ERROR: funnel sync had {len(errors)} errors: {errors[0] if errors else ''}"

    # synced > 0 and no errors: funnel_sync already fired per-lead notify()
    # in non-priority mode (or consolidated digest in priority mode), so tell
    # scheduler to stay silent via the skip-phrase filter.
    return f"funnel-sync-handled: {len(synced)} new lead(s) synced"


def run_funnel_fast_poll(_env_vars: dict) -> str:
    """Fast-poll funnel_leads (last 2 minutes) for near-realtime CC alerts.

    funnel_sync.py fast-poll mode fires a consolidated high-priority Telegram
    digest when new leads land. This handler returns a routine-silent phrase
    on empty runs so the scheduler doesn't spam CC every 60 seconds.
    """
    result = run_script("funnel_sync.py", ["fast-poll", "--json"], timeout=30)

    if not result or not result.strip().startswith("{"):
        return f"ERROR: fast-poll returned non-JSON: {result[:200]}"
    if result.startswith("FAILED"):
        return f"ERROR: fast-poll {result[:300]}"

    try:
        data = json.loads(result)
    except (json.JSONDecodeError, TypeError) as exc:
        return f"ERROR: fast-poll JSON parse failed: {exc}"

    if data.get("error"):
        return f"ERROR: fast-poll {data['error']}"

    synced = data.get("synced", []) or []
    errors = data.get("errors", []) or []

    if not synced and not errors:
        return "fast-poll: 0 new leads"  # routine -> silent

    if errors:
        return f"ERROR: fast-poll had {len(errors)} errors: {errors[0] if errors else ''}"

    # funnel_sync fast-poll already sent the consolidated digest — stay silent.
    return f"fast-poll-handled: {len(synced)} new lead(s) alerted"


# ── Main loop ─────────────────────────────────────────────────────────────────

def log(msg: str):
    """Print with timestamp for PM2 logs."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def check_and_run_due_jobs(client, env_vars: dict[str, str]):
    """Core loop iteration: find due jobs and execute them."""
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Get all active jobs that are due
    result = (
        client.table("cron_jobs")
        .select("*")
        .eq("is_active", True)
        .lte("next_run_at", now_iso)
        .not_.is_("next_run_at", "null")
        .order("next_run_at", desc=False)
        .execute()
    )
    due_jobs = result.data or []

    if not due_jobs:
        return 0

    log(f"Found {len(due_jobs)} due job(s)")

    for job in due_jobs:
        job_id = job["id"]
        job_name = job.get("name", "unknown")

        # Execute the job
        result_msg = execute_job(job, env_vars)

        # V2.1 2026-04-11: Retry-on-error logic.
        # Old: next_run_at always advances to the normal schedule, so a daily
        # 6am job that fails at 06:00:30 won't retry until 24h later.
        # New: if the result is an ERROR, schedule a retry in 5 minutes instead
        # of waiting for the full schedule. Max 5 consecutive retries before
        # giving up and waiting for the next scheduled slot.
        result_is_error = "ERROR" in result_msg or "FAILED" in result_msg
        new_count = (job.get("run_count") or 0) + 1
        fail_count = (job.get("fail_count") or 0) if hasattr(job, "get") else 0

        if result_is_error:
            fail_count += 1
            if fail_count < 5:
                # Retry in 5 minutes
                retry_dt = datetime.now(timezone.utc) + timedelta(minutes=5)
                next_run = retry_dt.isoformat()
                log(f"  ERROR on {job_name}, retry scheduled in 5 min (attempt {fail_count}/5)")
            else:
                # Give up, wait for next regular schedule
                next_run = calculate_next_run(job.get("schedule", ""))
                log(f"  ERROR on {job_name}, 5 retries exhausted, waiting for next schedule")
                fail_count = 0  # reset after giving up
        else:
            next_run = calculate_next_run(job.get("schedule", ""))
            fail_count = 0  # successful run resets the counter

        update_payload = {
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "run_count": new_count,
            "next_run_at": next_run,
            "last_result": result_msg[:500],
        }
        # Only set fail_count if the column exists (graceful — some deployments
        # may not have the migration yet). Catch the error if column missing.
        try:
            client.table("cron_jobs").update({
                **update_payload,
                "fail_count": fail_count,
            }).eq("id", job_id).execute()
        except Exception:
            # Fall back to update without fail_count (column doesn't exist)
            client.table("cron_jobs").update(update_payload).eq("id", job_id).execute()

        log(f"COMPLETED: {job_name} -> {result_msg[:200]}")

        # Notify CC via Telegram (skip empty/routine results)
        action_type = job.get("action_type", "")
        category_map = {
            "content_post": "content",
            "lead_followup": "lead",
            "booking_reminder": "booking",
            "stripe_sync": "revenue",
            "revenue_report": "revenue",
            "pipeline_review": "lead",
            "nurture_check": "email",
            "monthly_snapshot": "revenue",
            "content_planning": "content",
            "ig_research": "instagram",
            "ig_dm_check": "instagram",
            "ig_auto_reply": "instagram",
            "email_inbox_check": "email",
            "funnel_sync": "lead",
            "funnel_fast_poll": "lead",
            "content_generate": "content",
            "content_repurpose": "content",
            "agent_self_improvement": "system",
        }
        cat = category_map.get(action_type, "system")

        # ONLY notify CC when something ACTIONABLE happened.
        # Zero-result checks (no new DMs, no new emails, no content due) = silence.
        # CC said: "I don't need Telegram messages every 5 minutes saying there was nothing."
        # V2.1 2026-04-11: Routine detection uses PREFIX matching, not substring.
        # The old substring approach had a critical bug: 'ok' was matching inside
        # 'booking', 'no new' matching 'no newsletter', etc. Every handler that
        # returns its own routine-silent phrase now uses a canonical prefix.
        # Error detection stays as substring match (intentional — ERROR/FAILED
        # can appear inside a longer message and we still want to surface it).
        routine_prefixes = (
            # Engine-handled digests (engine already fired its own notify)
            "stripe sync ok:",
            "nurture run complete: no",
            "nurture-handled-by-digest",
            "funnel sync: 0 new",
            "funnel-sync-handled",
            "fast-poll: 0 new",
            "fast-poll-handled",
            "revenue-report-handled-by-digest",
            "pipeline-review-handled-by-digest",
            "self-improvement-handled-by-digest",
            # 2026-05-17: quiet-day guard skips (weekends, stat holidays).
            # The handler intentionally returns this prefix so CC isn't
            # poked every Saturday/Sunday with a "powwow skipped" note.
            "quiet-day:",
            # Generic empty-result signals
            "no content due",
            "no leads",
            "no active",
            "0 need nurture",
            "no unread",
            "0 unread",
            "no drafts found",
            "no posts to repurpose",
            "no replies sent",
            "0 auto-replies",
            # run_script's default "ok" fallback for empty-stdout successful runs
            # (guarded: must be EXACTLY "ok", not just contain it)
        )
        result_lower = result_msg.lower().strip()
        is_routine = (
            result_lower == "ok"
            or result_lower == "[]"
            or result_lower.startswith(routine_prefixes)
            or '"unread_count": 0' in result_lower
            or '"unread_count":0' in result_lower
            or '"published": 0' in result_lower
            or '"message": "no unread' in result_lower
        )
        is_error = "ERROR" in result_msg or "FAILED" in result_msg

        if is_error:
            notify_error(job_name, result_msg[:200])
        elif not is_routine:
            notify(f"{job_name}: {result_msg[:200]}", category=cat, silent=True)

    return len(due_jobs)


def initialize_next_run_times(client):
    """Set next_run_at for any active jobs that don't have one yet."""
    result = (
        client.table("cron_jobs")
        .select("*")
        .eq("is_active", True)
        .is_("next_run_at", "null")
        .execute()
    )
    jobs = result.data or []
    if not jobs:
        return

    log(f"Initializing next_run_at for {len(jobs)} job(s)")
    for job in jobs:
        next_run = calculate_next_run(job.get("schedule", ""))
        client.table("cron_jobs").update({
            "next_run_at": next_run,
        }).eq("id", job["id"]).execute()
        log(f"  {job['name']} -> next run: {next_run[:19]}")


def main():
    log("=" * 60)
    log("BRAVO SCHEDULER v1.0 - Business Operations Daemon")
    log("=" * 60)
    log(f"Check interval: {CHECK_INTERVAL_SECONDS}s")
    log(f"Python: {PYTHON}")
    log(f"Project: {PROJECT_ROOT}")

    env_vars = load_env()
    client = get_client(env_vars)

    # Initialize any jobs missing next_run_at
    initialize_next_run_times(client)

    # Orphan-cron self-check (added 2026-05-16 after the Daily Outreach
    # Batch silent-pings incident). Surfaces any cron_jobs row using a
    # retired action_type so a future agent can clean it up — instead of
    # the row hiding for weeks while the stub silently returns "retired:".
    try:
        check = client.table("cron_jobs").select("id,name,action_type,is_active").in_(
            "action_type", list(RETIRED_ACTIONS)
        ).execute()
        for row in check.data or []:
            log(
                f"  [ORPHAN-CRON] cron_jobs row '{row.get('name')}' "
                f"(id={row.get('id')}, active={row.get('is_active')}) "
                f"uses retired action_type='{row.get('action_type')}' — "
                f"delete this row or re-add a handler. See MISTAKES.md "
                f"2026-05-16."
            )
    except Exception as orphan_exc:  # noqa: BLE001
        log(f"  [warn] orphan-cron check failed: {orphan_exc}")

    log("Scheduler running. Checking for due jobs every 60 seconds...")
    log("")

    consecutive_errors = 0
    cycles = 0
    while True:
        try:
            jobs_run = check_and_run_due_jobs(client, env_vars)
            if jobs_run > 0:
                log(f"Cycle complete: {jobs_run} job(s) executed")
            consecutive_errors = 0

            # V2.1 2026-04-11: Every 5 cycles (~5 min), re-run next_run_at
            # initialization to catch any jobs that were added dynamically
            # via `cron_engine.py seed` or manual Supabase inserts while the
            # scheduler was already running. This fixes the latent bug where
            # new jobs with null next_run_at would be dead until next restart.
            cycles += 1
            if cycles % 5 == 0:
                try:
                    initialize_next_run_times(client)
                except Exception as init_exc:
                    log(f"  [warn] periodic init failed: {init_exc}")
        except KeyboardInterrupt:
            log("Shutdown requested. Goodbye.")
            break
        except Exception as exc:
            consecutive_errors += 1
            log(f"ERROR in check cycle: {exc}")
            if consecutive_errors >= 5:
                log("5 consecutive errors - sleeping 5 minutes before retry")
                time.sleep(300)
                consecutive_errors = 0
            time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
