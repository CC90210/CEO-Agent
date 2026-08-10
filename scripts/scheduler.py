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
import os
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional, List

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

# Scrub this process's own env, then hand a sanitized copy to every child.
#
# 2026-07-29: the scheduler is a long-lived PM2 daemon, so it inherits whatever
# AVG's TLS scanner exported into the PM2 daemon's environment — including
# SSLKEYLOGFILE=\\.\avgMonFltProxy\<kernel-handle>. Those handles go stale, and
# CPython opens the path inside ssl.create_default_context(), so every child
# that built an HTTPS client died at construction with PermissionError.
#
# ecosystem.config.js now sets SSLKEYLOGFILE="" and lib/tls_trust strips it
# in-process, but neither covers a child script that (a) doesn't import
# tls_trust and (b) is launched after a `pm2 restart` that skipped --update-env.
# This is the belt: every subprocess below gets CHILD_ENV, never the implicit
# inherited environment.
try:
    from lib.tls_trust import ensure_os_trust as _ensure_os_trust

    _ensure_os_trust()
except Exception:  # noqa: BLE001 — never block daemon startup on the TLS helper
    os.environ.pop("SSLKEYLOGFILE", None)

CHILD_ENV = os.environ.copy()
CHILD_ENV["SSLKEYLOGFILE"] = ""  # falsy -> ssl.py skips keylog_filename entirely

# Boot-blast suppression (2026-06-06): when CC's PC has been off, the
# scheduler comes back to a backlog of cron rows whose next_run_at is hours
# old. Without this guard, every due job fires in sequence — CC gets
# bombarded with Telegram briefs the moment he turns his computer on.
#
# Policy: if a job's next_run_at is more than this many minutes behind, skip
# the execution and just advance next_run_at to the next legitimate slot.
# The job picks back up on its normal schedule. 30 min = "we'll still catch
# a job whose previous tick was delayed by a real cause, but anything older
# is from a PC-off / hibernation window we don't want to replay."
STALE_FIRE_THRESHOLD_MINUTES = 30

# Action types that were retired but whose handlers are kept as no-op stubs
# (see execute_job dispatch). On startup, the orphan-cron self-check warns
# if any cron_jobs row still uses one of these — a 39-day silent-pings
# incident (MISTAKES.md 2026-05-16: Daily Outreach Batch) was caused by an
# orphan row hiding without ever surfacing in any audit. Append here when
# retiring a new action_type.
RETIRED_ACTIONS: frozenset[str] = frozenset({
    "lead_outreach_batch",  # retired 2026-05-16 — see feedback_no_cold_outreach_cron.md
})

# ── Who owns which cron ──────────────────────────────────────────────────────
#
# These two sets already existed as LOCALS inside execute_job, used only to emit
# a "moved_to_maven" marker. Hoisted to module scope 2026-07-30 so the alert
# router can reuse the same ownership map — one source of truth for "whose job
# is this", rather than a second copy that drifts.
MAVEN_DOMAIN_ACTIONS: frozenset[str] = frozenset({
    "content_post", "ig_research", "ig_dm_check", "ig_auto_reply",
    "content_generate", "content_repurpose", "content_planning",
    "maven_token_check",
})
ATLAS_DOMAIN_ACTIONS: frozenset[str] = frozenset({
    "atlas_wealth_refresh", "stripe_sync", "revenue_report", "monthly_snapshot",
})


def agent_for_action(action_type: str) -> str:
    """Which C-suite agent's Telegram bridge owns alerts for this cron."""
    if action_type in ATLAS_DOMAIN_ACTIONS:
        return "atlas"
    if action_type in MAVEN_DOMAIN_ACTIONS:
        return "maven"
    return "bravo"


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

# A job that runs at least this often gets another attempt before CC could
# realistically act on a page, so its FIRST failure is noise, not signal.
# Anything slower (hourly, daily) fails once and then stays broken for a long
# time — for those the first failure is the only useful moment to alert.
FAST_JOB_PERIOD = timedelta(minutes=15)


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
        # MAVEN_DOMAIN_ACTIONS / ATLAS_DOMAIN_ACTIONS now live at module scope
        # (shared with agent_for_action, which routes alerts by owner). Phase
        # 9.1: Maven Token Expiry Check ships from CMO-Agent — the row exists
        # empire-side but the handler does not, so it is marked moved rather
        # than showing red on the Health page.
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


FAILURE_DUMP_DIR = PROJECT_ROOT / "tmp" / "cron_failures"
FAILURE_DUMP_KEEP = 50

# script_run timeout policy. Most jobs are quick; a few (Review Harvest) spawn a
# model session plus a test suite and legitimately need longer. Per-job override
# lives in action_config["timeout"].
SCRIPT_RUN_DEFAULT_TIMEOUT = 300
SCRIPT_RUN_MAX_TIMEOUT = 3600


def _as_text(raw: Any) -> str:
    """Decode whatever subprocess handed back. TimeoutExpired.stdout/.stderr is
    str under text=True, bytes if the child died before the decoder ran, and
    None when nothing was captured — all three reach the dump writer."""
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace").strip()
    return str(raw).strip()


def _slug(label: str) -> str:
    """The dump-filename slug. Shared so the reader and the writer cannot drift."""
    return re.sub(r"[^a-z0-9]+", "-", (label or "").lower()).strip("-")[:48] or "job"


def failure_dump_hint(job_name: str, job: Optional[dict] = None) -> str:
    """Return the 'Full traceback: …' line ONLY when a dump actually exists.

    run_script_action() — the `script_run` path — never calls persist_failure()
    (only run_script() does, at its two failure exits). So for every script_run
    job this line pointed whoever was debugging at a directory that is never
    written for that job. An alert that cites evidence which does not exist costs
    a round-trip and quietly teaches people to distrust the alert. Name the file
    when there is one, say nothing when there isn't.
    """
    try:
        if not FAILURE_DUMP_DIR.exists():
            return ""
        script = ((job or {}).get("action_config") or {}).get("script") or ""
        candidates = {_slug(job_name)}
        if script:
            candidates.add(_slug(script))
        newest = None
        for path in FAILURE_DUMP_DIR.glob("*.log"):
            if any(path.name.startswith(f"{c}-") for c in candidates):
                if newest is None or path.stat().st_mtime > newest.stat().st_mtime:
                    newest = path
        return f"\nFull traceback: tmp/cron_failures/{newest.name}" if newest else ""
    except OSError:
        return ""


def persist_failure(label: str, cmd: List[str], returncode: "int | str",
                    stderr: str, stdout: str = "") -> Optional[str]:
    """Write a failed child's FULL stderr to tmp/cron_failures/ and return the path.

    Everything upstream truncates: run_script caps stderr at 2000 chars,
    cron_jobs.last_result at 500, the PM2 log line at 200. Diagnosing the
    2026-07-29 SSLKEYLOGFILE outage required the frame BELOW the 500-char cut —
    which existed nowhere on disk, so the root cause was invisible for 25h while
    the job dutifully logged "FAILED (exit 1): Traceback (most recent call
    last):" every five minutes.

    Secrets are stripped before writing (a child traceback can embed a
    connection string or a token-bearing URL). Ring-buffered so it can't grow
    without bound. Best-effort: a dump failure must never mask the job failure.
    """
    try:
        FAILURE_DUMP_DIR.mkdir(parents=True, exist_ok=True)
        slug = _slug(label)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = FAILURE_DUMP_DIR / f"{slug}-{ts}.log"

        try:
            from lib.redact import redact_secrets
            env_vars = load_env()
        except Exception:  # noqa: BLE001
            def redact_secrets(t, _e=None):  # type: ignore[misc]
                return t
            env_vars = {}

        body = (
            f"job       : {label}\n"
            f"when      : {datetime.now(timezone.utc).isoformat()}\n"
            f"exit code : {returncode}\n"
            f"command   : {' '.join(cmd)}\n"
            f"{'-' * 72}\nSTDERR\n{'-' * 72}\n{redact_secrets(stderr or '(empty)', env_vars)}\n"
            f"{'-' * 72}\nSTDOUT\n{'-' * 72}\n{redact_secrets((stdout or '(empty)')[:20000], env_vars)}\n"
        )
        path.write_text(body, encoding="utf-8")

        dumps = sorted(FAILURE_DUMP_DIR.glob("*.log"))
        for stale in dumps[:-FAILURE_DUMP_KEEP]:
            stale.unlink(missing_ok=True)
        return str(path)
    except Exception as exc:  # noqa: BLE001
        log(f"  [warn] could not persist failure dump for {label}: {exc}")
        return None


def run_script(script_name: str, args: List[str], timeout: int = 120) -> str:
    """Run a Python script from the scripts/ directory and return its output."""
    cmd = [PYTHON, str(SCRIPTS_DIR / script_name)] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
            env=CHILD_ENV,
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        # A TIMEOUT is the failure mode that most needs a dump and was the only
        # one that never produced one: subprocess.run raised straight past the
        # persist_failure call below, so CC's 2026-07-30 "timed out after 30s"
        # page pointed at tmp/cron_failures/ — which was empty. A hang leaves no
        # traceback of its own, so whatever the child managed to emit before the
        # wall is the ONLY evidence there will ever be. Capture it.
        partial_out = _as_text(exc.stdout)
        partial_err = _as_text(exc.stderr)
        dump = persist_failure(
            script_name, cmd, "TIMEOUT",
            f"No exception — killed after {timeout}s with no exit.\n"
            f"A hang produces no traceback; the partial output below is all\n"
            f"the child emitted before the wall.\n\n{partial_err}",
            partial_out,
        )
        hint = f" [full: {Path(dump).name}]" if dump else ""
        return f"FAILED (timeout after {timeout}s):{hint} {partial_err[:1000]}"
    output = result.stdout.strip()
    if result.returncode != 0:
        error = result.stderr.strip()
        dump = persist_failure(script_name, cmd, result.returncode, error, output)
        # Point at the full dump from inside the truncated string, so whoever
        # reads last_result or the PM2 log knows where the rest of it lives.
        hint = f" [full: {Path(dump).name}]" if dump else ""
        return f"FAILED (exit {result.returncode}):{hint} {error[:2000]}"
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
    """MRR reporting is ATLAS-OWNED (CFO) — Bravo does not send revenue digests.

    Handler-level enforcement (2026-07-09): the 'Weekly MRR Report' cron was
    disabled in both the DB and SEED_JOBS, but that's a toggle anyone could flip
    back on. This is the backstop — even if a revenue_report row fires, Bravo
    refuses to build/send an MRR figure to Telegram. Set BRAVO_ALLOW_REVENUE_REPORT=1
    ONLY for a deliberate one-off; the digest belongs to Atlas.
    """
    import os as _os
    if (env_vars.get("BRAVO_ALLOW_REVENUE_REPORT")
            or _os.environ.get("BRAVO_ALLOW_REVENUE_REPORT") or "").strip() != "1":
        return ("revenue-report skipped: MRR reporting is Atlas-owned (CFO). "
                "Re-home this job to Atlas or set BRAVO_ALLOW_REVENUE_REPORT=1 for a one-off.")
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

    # Days left to North Star deadline (September 30, 2026 — $5K achieved
    # 2026-06-20 via the BreezeAdvance deal; target reset to $10K. See CLAUDE.md WHY).
    import datetime as _dt
    deadline = _dt.date(2026, 9, 30)
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
    # 2026-07-28 — same reorg breakage already fixed once for the inbox sweep:
    # the script lives at scripts/core/, but this pointed at scripts/, so
    # run_script spawned a non-existent file and got "FAILED (exit 2)" on every
    # run since the move.
    #
    # It reported GREEN the whole time. The only guard was `if not out`, and
    # "FAILED (exit 2): ..." is non-empty — so the failure string sailed through
    # into _send_digest and the handler returned its success phrase. cron_jobs
    # showed "self-improvement-handled-by-digest", the dashboard showed green,
    # and the health-check watchdog had nothing to flag. A silent green failure
    # outlives a loud red one, so the FAILED check below is the real fix.
    out = run_script("core/agent_self_improvement.py", ["run"])
    if not out or not out.strip():
        return "ERROR: agent_self_improvement returned empty output"
    if out.startswith("FAILED"):
        return f"ERROR: agent_self_improvement failed: {out[:300]}"
    return _send_digest(out.strip(), "system", "self-improvement-handled-by-digest")


def run_daily_brief(_env_vars: dict) -> str:
    """Phase 5c — daily operational brief to CC's Telegram.

    scripts/daily_brief.py reads the latest briefing snapshot (regenerating
    if >5min stale), narrates a 5-bullet brief via the LOCAL claude CLI on
    CC's subscription (falling back to a deterministic brief on any failure),
    and ships it to Telegram via notify(force=True). Revenue/MRR is omitted —
    that's Atlas's brief. The script self-ships; this handler just invokes it
    and returns stdout so cron_jobs.last_result captures whether it landed.

    Timeout 150s > daily_brief's inner CLI-narration timeout (60s) + snapshot
    regen (60s) so the script always reaches its own graceful fallback before
    the scheduler force-kills it.
    """
    out = run_script("daily_brief.py", [], timeout=150)
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
            env=CHILD_ENV,
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

    # Optional per-job timeout (2026-07-29). 300s was hardcoded, which is fine
    # for a snapshot but fatal for a job that spawns work of its own: the Review
    # Harvest loop runs a Claude editing session plus the target repo's full test
    # suite, and being SIGKILLed halfway through can leave uncommitted edits in a
    # client repo. A job that knows it is long declares it; everything else keeps
    # the old default. Capped at an hour so a runaway can't occupy the scheduler.
    try:
        timeout_s = int(config.get("timeout") or SCRIPT_RUN_DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout_s = SCRIPT_RUN_DEFAULT_TIMEOUT
    timeout_s = max(10, min(timeout_s, SCRIPT_RUN_MAX_TIMEOUT))

    full_path = PROJECT_ROOT / script
    if not full_path.exists():
        return f"ERROR: script_run target not found: {script}"

    try:
        result = subprocess.run(
            [PYTHON, str(full_path), *[str(a) for a in args]],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_s,
            cwd=str(PROJECT_ROOT),
            env=CHILD_ENV,
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: script_run timed out ({timeout_s}s): {script}"
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
            env=CHILD_ENV,
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
    """Log monthly metrics snapshot.

    Previously returned the raw JSON dump from revenue_engine.py --json mrr,
    which the scheduler wrapper truncated to 200 chars and posted to
    Telegram on the 1st of each month — CC ended up with a mangled blob like
    `{"stripe_mrr": 180.0, "manual_mrr": 191.0, "total_mrr": 371.0,
    "stripe_subs": [{"subscription_id": "sub_1T7j6...` in his chat.
    Hideous and impossible to act on.

    New behavior (2026-06-06): still run the engine (so the snapshot is
    captured in last_result for auditing), but parse the JSON and return a
    one-line human-readable summary. CC sees "Monthly snapshot: $371 MRR
    (Stripe $180 + manual $191) · 2 active subs" instead of raw JSON.
    """
    raw = run_script("revenue_engine.py", ["--json", "mrr"])
    if not raw or not raw.strip().startswith("{"):
        return f"ERROR: monthly snapshot returned non-JSON: {raw[:200] if raw else 'empty'}"
    if raw.startswith("FAILED"):
        return f"ERROR: monthly snapshot {raw[:300]}"
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        return f"ERROR: monthly snapshot JSON parse failed: {exc}"

    # 2026-07-09 Atlas boundary: Bravo does NOT report MRR/revenue figures to
    # CC — that's Atlas's (CFO) brief. The engine still runs above so the
    # snapshot data lands in the revenue DB (plumbing Atlas reads) and a
    # broken engine still surfaces as ERROR — but the message CC sees (this
    # return string doubles as last_result AND the Telegram digest) carries
    # no dollar figures.
    subs = data.get("stripe_subs") or []
    active_subs = sum(1 for s in subs if isinstance(s, dict) and s.get("status") == "active")

    return (
        f"Monthly snapshot captured — revenue data logged for Atlas (CFO) · "
        f"{active_subs} active Stripe sub{'s' if active_subs != 1 else ''} · "
        f"details in the revenue DB, reporting via Atlas"
    )


def run_email_inbox_check(env_vars: dict) -> str:
    """Sweep the Gmail inbox: classify, route through the multi-brain email
    router (when EMAIL_BRAIN_ENABLED), draft/send/hand-off/archive, notify CC.

    2026-07-23 — two turnkey fixes:
      * PATH: email_engine.py moved to scripts/integrations/ in the 2026-05
        reorg but this handler still pointed at scripts/email_engine.py, so
        run_script resolved a non-existent file and every run returned
        "FAILED (exit 2)". The inbox sweep has been dead since the reorg.
      * TIMEOUT: 60s was sized for the old notify-and-mark-read path. With the
        brain enabled each email costs a Haiku classify plus (for replies) a
        Sonnet draft + critic pass, so a multi-email sweep needs real headroom.
    """
    return run_script("integrations/email_engine.py", ["--json", "check-inbox"], timeout=300)


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

    DORMANT, NOT DEAD (2026-07-30). Its cron row is is_active=False because
    funnel_leads has had no writer since cc-funnel was retired 2026-06-18 — see
    the note in cron_engine.py SEED_JOBS. The row still exists, so
    `cron_engine.py toggle <id>` re-enables it in one command; deleting this
    handler would turn that into a silent no-op at the worst possible moment.
    Keep it until either the table gets a writer again or the row is deleted.
    The same applies to run_nurture_check and run_funnel_sync.

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


# ── Cron result → something readable on a phone ────────────────────────────
# Until 2026-08-04 a job's raw stdout went straight to Telegram sliced at 200
# chars: CC got `Inbound Email Sweep: { "status": "checked", "unread_count": 1,
# "emails": [ { "from": "noreply-dmarc-...` — a JSON blob truncated mid-value,
# so the one field that mattered (the full Report-ID) was the part cut off.
# The scheduler already knows the shape; rendering it is cheap and the alert
# only has value if it can be read at a glance.

# Count keys worth putting in the headline, in the order they should appear.
_COUNT_LABELS = (
    ("unread_count", "unread"),
    ("sent", "sent"),
    ("published", "published"),
    ("synced", "synced"),
    ("inserted", "inserted"),
    ("updated", "updated"),
    ("processed", "processed"),
    ("skipped", "skipped"),
    ("failed", "failed"),
)

# Keys whose value is a list of things worth listing individually.
_ITEM_KEYS = ("emails", "leads", "items", "posts", "messages", "results", "rows")

# Fields that carry WHY something went wrong. These always render, even when a
# count headline exists — dropping them is how an alert becomes decoration.
_SIGNAL_KEYS = ("error", "errors", "failure", "failures", "reason",
                "detail", "details", "warning", "warnings")

# Status values that mean "nothing to report" and don't need their own line.
_BENIGN_STATUS = {"ok", "okay", "success", "succeeded", "done", "checked",
                  "complete", "completed", "clean", "healthy", "true"}

# Per-item label candidates: who it's from, then what it's about.
_WHO_KEYS = ("from", "email", "sender", "name", "to", "lead", "account")
_WHAT_KEYS = ("subject", "title", "summary", "message", "status", "reason")


def _clip(text: str, limit: int) -> str:
    """Truncate on a word boundary with an ellipsis — never mid-token.

    The old `[:200]` slice cut through a Report-ID and left CC a half-number.
    """
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return (cut or text[:limit]).rstrip(" ,;:-") + "…"


def _item_line(item) -> str:
    """One bullet for a single result item."""
    if not isinstance(item, dict):
        return f"• {_clip(item, 100)}"
    who = next((item[k] for k in _WHO_KEYS if item.get(k)), None)
    what = next((item[k] for k in _WHAT_KEYS if item.get(k)), None)
    if who and what:
        return f"• {_clip(who, 60)}\n   {_clip(what, 120)}"
    if who or what:
        return f"• {_clip(who or what, 120)}"
    # Unknown shape: show its fields as plain text rather than raw JSON.
    return "• " + _clip(" · ".join(f"{k}: {v}" for k, v in item.items()), 120)


# Status strings that mean the JOB itself failed.
_FAILURE_STATUS = {"error", "failed", "failure", "partial_failure", "exception",
                   "crashed", "timeout", "aborted"}

# Failure fields. Narrower than _SIGNAL_KEYS on purpose: a warning is worth
# printing, but it is not a job failure and must not feed the escalation ladder.
_FAILURE_KEYS = ("error", "errors", "failure", "failures")


def _looks_like_failure(result_msg: str) -> bool:
    """True when the JOB failed — not when its payload merely mentions failure.

    The old test was `"ERROR" in result_msg or "FAILED" in result_msg`, a
    substring scan of the ENTIRE payload. For the Inbound Email Sweep that
    payload contains inbound email subjects and senders, so a prospect writing
    "Re: your invoice FAILED to process" — or any of the endless "ERROR:
    action required" phishing subjects — flipped a perfectly healthy sweep to
    'failed', routed it to notify_error, and fed the consecutive-failure
    escalation ladder. CC gets paged about a broken job that isn't broken, and
    the real signal gets one notch harder to trust.

    Structured results are judged on their own status/error fields. Plain-text
    results keep the substring heuristic, because it is the only signal there.
    """
    raw = (result_msg or "").strip()
    if not raw:
        return False
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return "ERROR" in raw or "FAILED" in raw

    if isinstance(data, dict):
        if str(data.get("status", "")).strip().lower() in _FAILURE_STATUS:
            return True
        if data.get("ok") is False or data.get("success") is False:
            return True

    # Recursive scan. The first version returned False for any non-dict and
    # only looked at top-level scalars, so `["ERROR: database unavailable"]` and
    # {"result": {"error": "connection refused"}} — both failures under the old
    # substring check — became silence. Turning a broken job into silence is a
    # worse bug than the false alarm this replaced.
    return _scan_for_failure(data)


def _scan_for_failure(node, depth: int = 0, trusted: bool = True) -> bool:
    """Find failure evidence anywhere in a result, without trusting mail text.

    `trusted` is the whole trick. Inside an item list (emails/leads/rows) the
    free-text substring heuristic is OFF — that content is written by strangers,
    and "Re: your invoice FAILED" is their wording, not our job status. But an
    explicit `error` field on an item is OUR structure and still counts. So a
    per-row {"id": 7, "error": "rejected"} escalates while a subject line
    saying FAILED does not.
    """
    if depth > 6:  # depth guard; real job results are shallow
        return False
    if isinstance(node, str):
        return trusted and ("ERROR" in node.upper() or "FAILED" in node.upper())
    if isinstance(node, list):
        return any(_scan_for_failure(v, depth + 1, trusted) for v in node)
    if isinstance(node, dict):
        # Structured indicators are OUR schema wherever they appear, so they
        # count even inside an item list. Only the free-text substring heuristic
        # is suppressed there. Missing this made {"results":[{"status":"FAILED"}]}
        # — which the old substring check DID catch — return False, so a genuinely
        # failing job stopped retrying and reset its own fail_count.
        if str(node.get("status", "")).strip().lower() in _FAILURE_STATUS:
            return True
        if node.get("ok") is False or node.get("success") is False:
            return True
        for key, value in node.items():
            if key in _FAILURE_KEYS and value not in (None, "", [], {}, False, 0):
                return True
            if _scan_for_failure(value, depth + 1, trusted and key not in _ITEM_KEYS):
                return True
    return False


def _is_nothing_happened(result_msg: str) -> bool:
    """True when a structured result reports zero of everything it counts.

    Backstop for the literal `'"unread_count": 0' in result_lower` probes, which
    match exactly one spelling and miss the compact/reordered forms.
    """
    raw = (result_msg or "").strip()
    if not raw.startswith("{"):
        return False
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return False
    if not isinstance(data, dict) or _looks_like_failure(raw):
        return False
    counts = [v for k, v in data.items()
              if any(k == key for key, _ in _COUNT_LABELS)
              and isinstance(v, int) and not isinstance(v, bool)]
    if not counts or any(c != 0 for c in counts):
        return False
    # Zero counts is NOT enough. {"unread_count": 0, "status": "changed",
    # "message": "OAuth token refreshed"} counts nothing and still matters —
    # suppressing it here makes the notification disappear entirely rather than
    # merely get reformatted. Require the status to be explicitly benign and no
    # signal field populated before calling a tick a no-op.
    status = str(data.get("status") or data.get("message") or "").strip().lower()
    if status and status not in _BENIGN_STATUS:
        return False
    if any(data.get(k) not in (None, "", [], {}, False, 0) for k in _SIGNAL_KEYS):
        return False
    # Zero counts, benign status, nothing itemised — genuinely a no-op tick.
    return not any(isinstance(data.get(k), list) and data.get(k) for k in _ITEM_KEYS)


def humanize_job_result(job_name: str, result_msg: str, max_items: int = 3) -> str:
    """Render a cron job's result as plain text CC can read at a glance.

    Falls back to the (whitespace-collapsed, word-boundary-clipped) raw string
    for any shape it doesn't recognise — it never emits raw JSON punctuation,
    and it never returns something less informative than what it was given.
    """
    raw = (result_msg or "").strip()
    if not raw:
        return f"{job_name} — ran, no output"
    try:
        return _render_job_result(job_name, raw, max_items)
    except Exception as exc:  # noqa: BLE001
        # This runs inside check_and_run_due_jobs, AFTER the job's state update
        # and outside any per-job try. An unhandled error here would abort the
        # whole due-job loop: no notification, and every later due job skipped
        # for that tick. Deeply nested JSON raises RecursionError, which is not
        # a ValueError, so the narrow except below was not enough.
        # Fail loud in the log, degrade to the raw string CC used to get.
        print(f"[humanize_job_result] {job_name}: falling back to raw output "
              f"({type(exc).__name__}: {exc})", file=sys.stderr, flush=True)
        return f"{job_name} — {_clip(raw, 300)}"


def _render_job_result(job_name: str, raw: str, max_items: int) -> str:
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return f"{job_name} — {_clip(raw, 300)}"

    if not isinstance(data, dict):
        if isinstance(data, list):
            lines = [_item_line(i) for i in data[:max_items]]
            extra = len(data) - len(lines)
            head = f"{job_name} — {len(data)} item{'s' if len(data) != 1 else ''}"
            if extra > 0:
                lines.append(f"• …and {extra} more")
            return "\n".join([head, *lines])
        return f"{job_name} — {_clip(raw, 300)}"

    # `not isinstance(v, bool)` matters: bool subclasses int in Python, so
    # {"sent": true} rendered as "True sent" without it.
    counts = [f"{data[key]} {label}" for key, label in _COUNT_LABELS
              if isinstance(data.get(key), int) and not isinstance(data.get(key), bool)]
    headline = f"{job_name} — " + (" · ".join(counts) if counts
                                   else _clip(data.get("status") or data.get("message") or "done", 120))

    lines = [headline]

    # Failure detail survives REGARDLESS of counts. First version gated the
    # fallback on `not counts`, so {"processed":10,"failed":1,"error":"database
    # write rejected"} rendered as just "10 processed · 1 failed" — the error
    # text silently dropped, making the alert strictly LESS informative than the
    # raw prefix it replaced. That is the one thing this formatter must never do.
    for key in _SIGNAL_KEYS:
        value = data.get(key)
        if value in (None, "", [], {}, False):
            continue
        if isinstance(value, (list, tuple)):
            value = "; ".join(str(v) for v in list(value)[:3])
        elif isinstance(value, dict):
            value = " · ".join(f"{k}: {v}" for k, v in list(value.items())[:4])
        lines.append(f"{key}: {_clip(value, 160)}")

    # A status that isn't just "fine" is signal too, and the counts headline
    # hides it.
    status = data.get("status") or data.get("message")
    if counts and status and str(status).strip().lower() not in _BENIGN_STATUS:
        lines.insert(1, f"status: {_clip(status, 100)}")

    for key in _ITEM_KEYS:
        items = data.get(key)
        if isinstance(items, list) and items:
            for item in items[:max_items]:
                lines.append(_item_line(item))
            extra = len(items) - min(len(items), max_items)
            if extra > 0:
                lines.append(f"• …and {extra} more")
            break

    # Still nothing concrete beyond the headline: surface remaining scalars.
    if len(lines) == 1 and not counts:
        scalars = [f"{k}: {_clip(v, 60)}" for k, v in data.items()
                   if isinstance(v, (str, int, float, bool)) and k not in ("status", "message")]
        if scalars:
            lines.append(_clip(" · ".join(scalars), 200))

    return "\n".join(lines)


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

    now_dt = datetime.now(timezone.utc)
    stale_cutoff = now_dt - timedelta(minutes=STALE_FIRE_THRESHOLD_MINUTES)

    for job in due_jobs:
        job_id = job["id"]
        job_name = job.get("name", "unknown")

        # Boot-blast suppression. If this job's next_run_at is older than
        # the staleness threshold, the scheduler was almost certainly off
        # while this slot expired — don't replay it now (would spam CC's
        # Telegram on PC boot). Just advance to the next legitimate slot
        # and skip the execute. The job picks up normally on the next
        # real schedule.
        next_run_at_str = job.get("next_run_at")
        if next_run_at_str:
            try:
                # Tolerate both "...Z" and "...+00:00" trailers (older rows
                # written with isoformat() use the latter).
                next_run_at_dt = datetime.fromisoformat(
                    next_run_at_str.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                next_run_at_dt = None
            if next_run_at_dt and next_run_at_dt < stale_cutoff:
                # Stale: skip + reschedule. Don't touch run_count (no real
                # run happened) but advance next_run_at + log so the audit
                # tape shows the skip.
                skipped_next = calculate_next_run(job.get("schedule", ""))
                age_min = int((now_dt - next_run_at_dt).total_seconds() / 60)
                log(
                    f"  SKIPPED stale: {job_name} (next_run_at was "
                    f"{age_min} min behind, > {STALE_FIRE_THRESHOLD_MINUTES} min threshold) "
                    f"-> next run: {skipped_next[:19]}"
                )
                try:
                    client.table("cron_jobs").update({
                        "next_run_at": skipped_next,
                        "last_result": (
                            f"skipped-stale: next_run_at was {age_min} min behind threshold "
                            f"({STALE_FIRE_THRESHOLD_MINUTES} min) — PC was likely off when "
                            f"this slot expired"
                        )[:500],
                    }).eq("id", job_id).execute()
                except Exception as skip_exc:  # noqa: BLE001
                    log(f"  [warn] failed to advance next_run_at for stale skip: {skip_exc}")
                continue

        # Execute the job
        result_msg = execute_job(job, env_vars)

        # V2.1 2026-04-11: Retry-on-error logic.
        # Old: next_run_at always advances to the normal schedule, so a daily
        # 6am job that fails at 06:00:30 won't retry until 24h later.
        # New: if the result is an ERROR, schedule a retry in 5 minutes instead
        # of waiting for the full schedule. Max 5 consecutive retries before
        # giving up and waiting for the next scheduled slot.
        # Same classifier as the alerting path below (2026-08-04). This copy was
        # missed in the first pass and it is the more damaging of the two: it
        # does not just page CC, it increments fail_count, reschedules the job
        # to retry in 5 minutes, and "gives up" after 5 attempts. A raw
        # substring scan means an inbound email whose SUBJECT says "FAILED"
        # made a healthy Inbound Email Sweep burn its whole retry budget and
        # corrupt its own failure counter, every time such a mail arrived.
        result_is_error = _looks_like_failure(result_msg)
        new_count = (job.get("run_count") or 0) + 1
        fail_count = (job.get("fail_count") or 0) if hasattr(job, "get") else 0

        if result_is_error:
            fail_count += 1
            if fail_count < 5:
                # Retry sooner than the schedule — but NEVER later than it.
                # A flat 5-minute retry is a rescue for a daily job and a
                # PUNISHMENT for a */1 job: on 2026-07-30 one transient 30s
                # stall pushed the 60-second funnel poll out to 5 minutes,
                # stretching its cadence 5x at the exact moment it was already
                # degraded. Cap the delay at the job's own period.
                period = parse_cron_schedule(job.get("schedule", "") or "")
                delay = min(timedelta(minutes=5), period) if period else timedelta(minutes=5)
                retry_dt = datetime.now(timezone.utc) + delay
                next_run = retry_dt.isoformat()
                mins = delay.total_seconds() / 60
                log(f"  ERROR on {job_name}, retry scheduled in {mins:g} min "
                    f"(attempt {fail_count}/5)")
            else:
                # Give up, wait for next regular schedule
                next_run = calculate_next_run(job.get("schedule", ""))
                log(f"  ERROR on {job_name}, 5 retries exhausted, waiting for next schedule")
                fail_count = 0  # reset after giving up

            # Repeat-failure escalation (2026-07-29). One bad tick is noise —
            # a transient network blip resolves itself on the retry. TWO in a
            # row is a broken job, and until now that state was invisible:
            # fail_count never persisted (no column) so the counter reset every
            # tick, and notify_error() was muted by the category filter. The
            # Inbound Email Sweep failed 31 times over 25h without one alert.
            #
            # Fires at exactly 2 and at the give-up boundary, not on every tick;
            # notify.py's disk-persisted dedup then collapses repeats of the
            # same text to one per hour.
            if fail_count == 2 or fail_count == 0:
                stage = ("failing repeatedly" if fail_count == 2
                         else "gave up after 5 attempts")
                notify_error(
                    job_name,
                    f"{stage} — {result_msg[:220]}"
                    f"{failure_dump_hint(job_name, job)}",
                    # Distinct dedup identity from the per-tick page below.
                    # They shared one key until 2026-07-30, so the noisy
                    # first-failure alert consumed the slot and silenced THIS
                    # one — the alert that actually means "the job is broken".
                    stage="escalation",
                )
        else:
            next_run = calculate_next_run(job.get("schedule", ""))
            # Recovery ping: if this job had been failing, say so. A silent
            # recovery leaves CC unsure whether the earlier alert still stands.
            if fail_count >= 2:
                notify(f"{job_name}: recovered after {fail_count} failed run(s).",
                       category="system", silent=True, force=True)
            fail_count = 0  # successful run resets the counter

        update_payload = {
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "run_count": new_count,
            "next_run_at": next_run,
            "last_result": result_msg[:500],
        }
        # fail_count is a real column as of migration 105 (2026-07-29). It is
        # NOT optional any more: the previous try/except-and-retry-without-it
        # made a missing column indistinguishable from a successful write, so
        # the counter silently never persisted for ~3.5 months — every failure
        # logged "attempt 1/5", the give-up branch was unreachable, and no
        # repeat-failure alert could ever fire. A write failure here must be
        # loud, not quietly degraded.
        client.table("cron_jobs").update({
            **update_payload,
            "fail_count": fail_count,
        }).eq("id", job_id).execute()

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
            # 2026-06-06: Daily MRR Auto-Sync prints
            # "sync_mrr [no-op] ..." when MRR didn't change since
            # yesterday — that's the routine case (most days). CC only
            # cares when it CHANGES (the [CHANGED] prefix is not in the
            # routine list, so those notify normally).
            "sync_mrr [no-op]",
            "sync_mrr [DRY-RUN]",
            # 2026-06-06: Daily State DB Backup prints "[OK] {...}" on
            # success. Routine — only failures should notify CC.
            "  [OK]",
            # 2026-06-06: skipped-stale results from Phase 1.4 — the
            # scheduler's own boot-blast guard advances next_run_at but
            # doesn't fire the handler. No reason to notify CC about
            # the skip.
            "skipped-stale:",
            # 2026-06-06: Bravo Sleep Agent output is structured
            # "[bravo_sleep] wrote N, skipped M ..." — routine.
            "[bravo_sleep]",
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
            # Structured backstop for the four string probes above, which only
            # match one exact spelling of the JSON. Purely additive: it can make
            # a nothing-happened tick quieter, never noisier.
            or _is_nothing_happened(result_msg)
        )
        is_error = _looks_like_failure(result_msg)

        # Route the alert to the agent that OWNS the job, not to Bravo by
        # default (2026-07-30). A failed content_post is Maven's problem and a
        # failed stripe_sync is Atlas's; putting both on CC's executive channel
        # alongside real OS health is how that channel stops being read.
        owner = agent_for_action(action_type)

        if is_error:
            # Don't page CC for ONE bad tick of a fast job. A */1 or */5 cron
            # that fails once self-heals before he could act, and 130 lines
            # above there is already a deliberate "escalate at 2 consecutive
            # failures" policy — which this unconditional call silently
            # defeated, paging on attempt 1/5 every time (2026-07-30).
            #
            # Slow jobs are the opposite: a daily brief that fails at 06:00
            # will not retry for a day, so its first failure IS the signal.
            # The cutoff is "will it try again before CC could reasonably
            # act", not an arbitrary severity call.
            period = parse_cron_schedule(job.get("schedule", "") or "")
            self_healing = period is not None and period <= FAST_JOB_PERIOD
            if self_healing:
                log(f"  (transient failure on fast job {job_name} — "
                    f"escalation at 2 consecutive owns this alert)")
            else:
                # The failure path was the LAST place still shipping raw
                # `[:200]` JSON. It is also the path where detail matters most —
                # this is the message CC reads at 2am to decide whether to get
                # up. Same renderer, so the error field leads instead of being
                # the part the slice cut off. Job name is passed separately by
                # notify_error, so strip the headline the renderer prepends.
                # Strip the EXACT headline the renderer prepended — not "split
                # on the first em dash", which corrupts the detail when the job
                # name itself contains one and silently doubles the name when
                # the renderer returns no separator at all.
                detail = humanize_job_result(job_name, result_msg)
                headline = f"{job_name} — "
                if detail.startswith(headline):
                    detail = detail[len(headline):]
                notify_error(job_name, detail[:400], agent=owner)
        elif not is_routine:
            # Was: f"{job_name}: {result_msg[:200]}" — raw JSON, sliced
            # mid-value.
            #
            # NO dedup_key here, deliberately. Identity stays the rendered
            # text, which is what notify's design intends: "distinct alerts
            # (different sender/subject → different text) always pass, so this
            # only ever collapses genuine repeats." A result notification is
            # CONTENT, not a condition — pinning it to the job name would mean
            # the 06:30 sweep reporting a DMARC report suppresses the 06:35
            # sweep reporting a real prospect, for the full 1h window.
            # dedup_key belongs on condition alerts ("job failed again"),
            # never on a message whose whole value is what changed.
            notify(humanize_job_result(job_name, result_msg), category=cat,
                   silent=True, agent=owner)

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


def _scheduler_heartbeat(status: str, focus: str) -> None:
    """Best-effort agent_state heartbeat so `state_manager status` reflects a
    live scheduler.

    The scheduler is "the heartbeat of the business agent" (module docstring)
    but historically never wrote agent_state, so `agent_state.bravo` sat frozen
    and the fleet looked DEAD while it was actually running (root cause of the
    2026-07-07 Montreal turnkey-reset misdiagnosis). Observability only — a
    failure here must NEVER interrupt job execution, hence the blanket guard."""
    try:
        from state.state_manager import heartbeat as _hb
        _hb("bravo", status=status, focus=focus)
    except Exception:  # noqa: BLE001 — observability must not break the loop
        pass


def _parse_args() -> None:
    """Refuse to start on an unrecognised argument, and answer --help.

    This file had no argument handling at all, so `sys.argv` was ignored
    entirely and ANY invocation started the daemon. On 2026-08-08 an agent ran
    `scheduler.py --help` to read the usage text and instead started a second
    production scheduler, which ran for 33 hours executing every cron a second
    time -- against the database the fleet had already been migrated off. It was
    found by tracing an open socket, not by anything reporting it, because a
    scheduler that starts successfully looks exactly like one that was asked to.

    A daemon whose only argument-handling behaviour is "start anyway" cannot
    tell an operator apart from a typo. Same defect class as
    scripts/state/notify.py before it grew a parser.
    """
    argv = sys.argv[1:]
    if not argv:
        return
    if argv[0] in ("-h", "--help"):
        print(
            "usage: scheduler.py\n\n"
            "The Bravo scheduler daemon. Takes no arguments; it is started by\n"
            "PM2 (see ecosystem config) and polls cron_jobs every "
            f"{CHECK_INTERVAL_SECONDS}s.\n\n"
            "Running it by hand starts a SECOND scheduler alongside the PM2 one\n"
            "and every due job then runs twice. To inspect or trigger jobs use\n"
            "  python scripts/core/cron_engine.py --help\n"
        )
        raise SystemExit(0)
    print(f"scheduler.py: unrecognised argument {argv[0]!r} -- it takes none.",
          file=sys.stderr)
    print("Refusing to start rather than silently running a second scheduler. "
          "Try --help.", file=sys.stderr)
    raise SystemExit(2)


def main():
    _parse_args()
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
    _scheduler_heartbeat("working", "scheduler started — polling every 60s")

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
                # Refresh agent_state (~every 5 min) so `state_manager status`
                # tracks the live scheduler instead of sitting frozen.
                _scheduler_heartbeat(
                    "working",
                    f"live — {cycles} cycles, last ran {jobs_run} job(s)",
                )

            # Normal-path pacing. Historically the CHECK_INTERVAL sleep lived
            # ONLY in the error branch below, so the healthy loop busy-spun —
            # re-querying Supabase cron_jobs thousands of times/hour (CPU looked
            # ~0% only because each iteration blocked on the network round-trip).
            # Sleep here so the loop actually polls "every 60 seconds" as the
            # banner claims, and so the cycles%5 heartbeat lands ~every 5 min.
            # (Montreal turnkey reset, 2026-07-07.)
            time.sleep(CHECK_INTERVAL_SECONDS)
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
