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

# ── Config ────────────────────────────────────────────────────────────────────

CHECK_INTERVAL_SECONDS = 60  # How often to check for due jobs
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
PYTHON = sys.executable  # Use same Python that's running this script


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

def parse_cron_schedule(schedule: str) -> timedelta | None:
    """
    Convert a cron schedule string to a timedelta for the next run interval.
    Supports common patterns. Not a full cron parser - covers our 12 jobs.
    """
    parts = schedule.strip().split()
    if len(parts) != 5:
        return None

    minute, hour, dom, month, dow = parts

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
    """Calculate the next run time based on the cron schedule."""
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
        if action_type == "content_post":
            return run_content_post(config, env_vars)
        elif action_type == "lead_followup":
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
        elif action_type == "content_planning":
            return run_content_planning(env_vars)
        elif action_type == "ig_research":
            return run_ig_research(env_vars)
        else:
            return f"unknown_action_type: {action_type}"
    except Exception as exc:
        error_msg = f"ERROR: {exc}"
        log(error_msg)
        return error_msg


def run_script(script_name: str, args: list[str], timeout: int = 120) -> str:
    """Run a Python script from the scripts/ directory and return its output."""
    cmd = [PYTHON, str(SCRIPTS_DIR / script_name)] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(PROJECT_ROOT),
    )
    output = result.stdout.strip()
    if result.returncode != 0:
        error = result.stderr.strip()
        return f"FAILED (exit {result.returncode}): {error[:500]}"
    return output[:500] if output else "ok"


# ── Job handlers ──────────────────────────────────────────────────────────────

def run_content_post(config: dict, env_vars: dict) -> str:
    """Check for due content, post via Late MCP if body text exists."""
    result = run_script("content_engine.py", ["--json", "due"])
    try:
        due_items = json.loads(result)
        if not due_items:
            return "no content due"
        # Report what's due - actual posting requires Late MCP (agent session)
        count = len(due_items) if isinstance(due_items, list) else 0
        return f"{count} content item(s) due for posting"
    except json.JSONDecodeError:
        return result


def run_lead_followup(env_vars: dict) -> str:
    """Check for leads needing follow-up."""
    return run_script("lead_engine.py", ["--json", "followups"])


def run_booking_reminder(env_vars: dict) -> str:
    """Check tomorrow's bookings and flag reminders."""
    return run_script("booking_engine.py", ["--json", "remind"])


def run_stripe_sync(env_vars: dict) -> str:
    """Sync recent Stripe events into revenue_events table."""
    return run_script("revenue_engine.py", ["--json", "sync-stripe"])


def run_revenue_report(env_vars: dict) -> str:
    """Generate MRR dashboard summary."""
    return run_script("revenue_engine.py", ["--json", "dashboard"])


def run_pipeline_review(env_vars: dict) -> str:
    """Generate pipeline summary."""
    return run_script("lead_engine.py", ["--json", "pipeline"])


def run_nurture_check(env_vars: dict) -> str:
    """Check for leads in nurture sequences that need next email."""
    # For now, report sequence status - full auto-send requires Gmail confirmation
    return run_script("email_engine.py", ["--json", "sequence", "list"])


def run_monthly_snapshot(env_vars: dict) -> str:
    """Log monthly metrics snapshot."""
    return run_script("revenue_engine.py", ["--json", "mrr"])


def run_content_planning(env_vars: dict) -> str:
    """Generate next week's content plan."""
    return run_script("content_engine.py", ["--json", "week-plan"])


def run_ig_research(env_vars: dict) -> str:
    """Instagram research placeholder - requires Playwright (agent session)."""
    return "ig_research requires Playwright - flagged for next agent session"


# ── Main loop ─────────────────────────────────────────────────────────────────

def log(msg: str):
    """Print with timestamp for PM2 logs."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def check_and_run_due_jobs(client, env_vars: dict[str, str]):
    """Core loop iteration: find due jobs and execute them."""
    now_iso = datetime.now(timezone.utc).isoformat()

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

        # Update the job record
        new_count = (job.get("run_count") or 0) + 1
        next_run = calculate_next_run(job.get("schedule", ""))

        client.table("cron_jobs").update({
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "run_count": new_count,
            "next_run_at": next_run,
            "last_result": result_msg[:500],
        }).eq("id", job_id).execute()

        log(f"COMPLETED: {job_name} -> {result_msg[:200]}")

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

    log("Scheduler running. Checking for due jobs every 60 seconds...")
    log("")

    consecutive_errors = 0
    while True:
        try:
            jobs_run = check_and_run_due_jobs(client, env_vars)
            if jobs_run > 0:
                log(f"Cycle complete: {jobs_run} job(s) executed")
            consecutive_errors = 0
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
