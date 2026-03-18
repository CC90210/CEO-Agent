# Lesson 3: Monitoring & Reliability — Making Sure Cron Jobs Actually Run

> **Level:** Integrator (L2)
> **XP Reward: +300 XP** | Running Total: 750 XP
> **Course:** Cron Jobs Masterclass
> **Goal:** Build cron jobs that fail loudly, recover gracefully, and never silently corrupt data.

---

## The #1 Cron Problem: Silent Failures

Every beginner builds the same cron job: it works on the first run, they forget about it, six weeks later they discover it stopped working three weeks ago and nobody noticed.

Silent failures are the defining risk of cron architecture. Unlike a web server that 500s and your users scream at you, a failed cron job produces exactly nothing — no error, no alert, no visible symptom. The report just does not arrive. The backup just does not exist. The invoice just does not get sent.

**The categories of silent failure:**

| Failure Type | What Happens | How Long Until Noticed |
|--------------|-------------|----------------------|
| Script throws uncaught exception | Job stops mid-run | Days to weeks |
| API credential expired | Job runs, does nothing | Weeks |
| Database connection timeout | Job errors and exits | Hours to days |
| Disk full | Job cannot write output | Unknown |
| Script path changed | Job can't find the file | Next scheduled run |
| Environment variable missing | Job runs with wrong config | Unknown |
| Overlapping executions | Data corruption | Very hard to detect |

🧠 **KEY TAKEAWAY:** A cron job without monitoring is not a scheduled job — it is a scheduled hope. Monitoring transforms cron from "it probably ran" to "I know it ran."

---

## Logging Best Practices

The foundation of debuggable cron jobs is structured, persistent logs.

### Append, Never Overwrite

```bash
# WRONG — overwrites every run, you lose history
0 9 * * * /usr/bin/python3 report.py > /logs/report.log

# RIGHT — appends each run below the last
0 9 * * * /usr/bin/python3 report.py >> /logs/report.log 2>&1
```

### Timestamped Entries

Every log entry needs a timestamp. Without it you cannot tell which run produced which output.

```python
import logging
from datetime import datetime

logging.basicConfig(
    filename='/home/user/logs/daily_report.log',
    level=logging.INFO,
    format='%(asctime)s — %(levelname)s — %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)

def run():
    logger.info('Job started')
    try:
        # your logic here
        result = do_work()
        logger.info(f'Job completed successfully — {result["count"]} records processed')
    except Exception as e:
        logger.error(f'Job failed — {str(e)}', exc_info=True)
        raise  # re-raise so the exit code is non-zero

if __name__ == '__main__':
    run()
```

**Output in the log:**
```
2026-03-18 09:00:01 — INFO — Job started
2026-03-18 09:00:03 — INFO — Job completed successfully — 47 records processed
2026-03-18 09:00:01 — INFO — Job started
2026-03-18 09:00:02 — ERROR — Job failed — Connection timeout
Traceback (most recent call last): ...
```

### Structured JSON Logs

For logs you want to query or forward to a monitoring service:

```python
import json
import sys
from datetime import datetime, timezone

def log(level, message, **extra):
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'level': level,
        'message': message,
        'job': 'daily_report',
        **extra
    }
    print(json.dumps(entry), flush=True)

log('INFO', 'Job started', run_id='2026-03-18-0900')
log('INFO', 'Records processed', count=47, duration_ms=1823)
log('ERROR', 'API call failed', error='401 Unauthorized', endpoint='/v1/contacts')
```

💡 **PRO TIP:** Structured logs are queryable. If you forward JSON logs to a service like Logtail, Papertrail, or even just grep, you can ask "how many records did we process every Monday for the past 3 months?" Unstructured text logs cannot answer that.

---

## Log Rotation

Logs that grow without bounds eventually fill your disk. Add rotation from day one.

```bash
# /etc/logrotate.d/cron-jobs
/home/user/logs/*.log {
    weekly
    rotate 4
    compress
    delaycompress
    missingok
    notifempty
}
```

Or a manual cleanup cron:

```bash
# Every Sunday at 3am: delete logs older than 30 days
0 3 * * 0 find /home/user/logs -name "*.log" -mtime +30 -delete
# Every Sunday at 3:05am: compress logs older than 7 days
5 3 * * 0 find /home/user/logs -name "*.log" -mtime +7 -exec gzip {} \;
```

---

## Heartbeat Monitoring: The Dead Man's Switch

A **heartbeat** (also called a "dead man's switch") inverts the monitoring model. Instead of alerting when something goes wrong, you expect a check-in on every successful run. If the check-in does not arrive, you get an alert.

This catches failures that produce no error — the script just never ran.

### How It Works

1. Your cron job runs
2. On successful completion, it pings a URL: `https://hc-ping.com/your-uuid`
3. The monitoring service expects a ping every N minutes/hours
4. If the ping does not arrive within the expected window — alert fires

```python
import requests
import os

HEALTHCHECK_URL = os.environ['HEALTHCHECK_URL']  # from .env

def run():
    # Signal start (optional — some services support /start + /finish)
    requests.get(f'{HEALTHCHECK_URL}/start', timeout=5)

    try:
        # Your job logic
        result = do_work()

        # Signal success
        requests.get(HEALTHCHECK_URL, timeout=5)
        return result

    except Exception as e:
        # Signal failure
        requests.get(f'{HEALTHCHECK_URL}/fail', timeout=5, data=str(e))
        raise
```

### Monitoring Services

| Service | Free Tier | Paid | Best For |
|---------|-----------|------|---------|
| **Healthchecks.io** | 20 checks | $20/mo | Self-hosted option, excellent free tier |
| **Cronitor** | 5 monitors | $7/mo | Visual timeline, anomaly detection |
| **UptimeRobot** | 50 monitors | $7/mo | HTTP endpoint monitoring |
| **Better Uptime** | Unlimited | $20/mo | On-call alerting, status pages |

**Recommended for agencies starting out:** Healthchecks.io. The free tier covers 20 cron jobs — enough for a full client stack. Alerts via email, Slack, Telegram, or webhook.

💡 **PRO TIP:** Set up heartbeat monitoring before you deploy the cron job, not after. The worst time to discover monitoring is missing is when a client calls asking why they did not get their Monday report.

---

## n8n Execution History

n8n has built-in execution history for every workflow. This is one of its biggest advantages over system cron.

### Viewing Past Runs

1. Open any workflow
2. Click "Executions" in the left panel
3. Filter by: All / Success / Error / Waiting

Each execution shows:
- Start time and duration
- Success / Error status
- Full node-by-node output (click any node to see its input/output data)
- Error message with stack trace if it failed

### Filtering Failures

```
Executions panel → filter by "Error" → see every failed run chronologically
```

For production workflows, check this weekly at minimum. A pattern of failures at a specific time or node tells you where to investigate.

### Retry Patterns

n8n does not auto-retry failed cron executions by default. Add your own:

```javascript
// In a Function node at the start of critical workflows
// Check if this is a manual retry trigger
const isRetry = $input.first().json.is_retry || false;

if (isRetry) {
  // Log that we're retrying
  console.log(`Retry run at ${new Date().toISOString()}`);
}
```

For automatic retry: use the **n8n Error Workflow** feature. Set a dedicated error workflow in Settings → Workflows → Error Workflow. It fires whenever any other workflow fails.

---

## Error Handling in Cron Scripts

The difference between a cron job that alerts on failure and one that dies silently is error handling.

### Python: Full Error Handling Pattern

```python
import logging
import requests
import os
import sys
from datetime import datetime

logger = logging.getLogger(__name__)

def notify_failure(error_message: str) -> None:
    """Send alert when job fails."""
    webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
    if not webhook_url:
        return

    requests.post(webhook_url, json={
        'text': f':rotating_light: *Cron Job Failed*\n'
                f'Job: `daily_report`\n'
                f'Time: {datetime.now().isoformat()}\n'
                f'Error: ```{error_message}```'
    }, timeout=10)

def run() -> int:
    """Returns exit code: 0 = success, 1 = failure."""
    try:
        logger.info('Starting daily report job')
        result = generate_report()
        send_email(result)
        logger.info(f'Job completed — report sent to {result["recipient"]}')
        return 0
    except ConnectionError as e:
        msg = f'Database connection failed: {e}'
        logger.error(msg)
        notify_failure(msg)
        return 1
    except ValueError as e:
        msg = f'Invalid data encountered: {e}'
        logger.error(msg)
        notify_failure(msg)
        return 1
    except Exception as e:
        msg = f'Unexpected error: {e}'
        logger.exception(msg)
        notify_failure(msg)
        return 1

if __name__ == '__main__':
    sys.exit(run())
```

### Exit Codes Matter

Cron uses exit codes to determine success or failure. `sys.exit(0)` = success. `sys.exit(1)` = failure. Some monitoring tools read exit codes to trigger alerts.

```bash
# In crontab: alert if exit code is non-zero
0 9 * * * /usr/bin/python3 /scripts/report.py || echo "FAILED $(date)" | mail -s "Cron Alert" cc@yourdomain.com
```

💀 **COMMON MISTAKE:** Wrapping your entire script in a bare `try/except Exception: pass`. This is the worst possible pattern — it catches every error and swallows it silently. Every exception should be caught at the right level, logged with detail, and propagated up (or specifically handled if recovery is possible).

---

## Idempotency: Run-Twice Safety

**Idempotency** means running the same job twice produces the same result as running it once. This is non-negotiable for production cron jobs.

Why it matters:
- Network timeouts can cause n8n to retry an execution
- Clock skew can cause a job to fire at the edge of two intervals
- Manual re-runs after a failure should not double-charge customers or create duplicate records
- Server reboots can interrupt mid-run and resume from the start

### Making a Job Idempotent

```python
from datetime import date

def generate_daily_report(report_date: date) -> dict:
    """
    Idempotent: safe to run multiple times for the same date.
    If a report for this date already exists, return the existing one.
    """
    existing = supabase.table('reports') \
        .select('*') \
        .eq('report_date', report_date.isoformat()) \
        .execute()

    if existing.data:
        logger.info(f'Report for {report_date} already exists — returning existing')
        return existing.data[0]

    # Only here if no report exists for this date
    report_data = build_report(report_date)

    result = supabase.table('reports').insert({
        'report_date': report_date.isoformat(),
        'data': report_data,
        'created_at': 'now()'
    }).execute()

    return result.data[0]
```

**The idempotency checklist:**
- [ ] Does the job check if its output already exists before creating it?
- [ ] Does inserting the same record twice cause a duplicate or raise a unique constraint error?
- [ ] Is the job safe to run manually at any time?
- [ ] If the job is interrupted halfway, is the partial state recoverable?

---

## Lock Files and Mutex: Preventing Overlap

Some jobs must not run concurrently. If a daily report job takes 10 minutes and you have an hourly cron, you might get two instances running at the same time.

### File-Based Lock (Bash)

```bash
#!/bin/bash

LOCKFILE=/tmp/daily_report.lock

# If lock exists and process is still running — exit
if [ -f "$LOCKFILE" ]; then
    PID=$(cat "$LOCKFILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "$(date) — Job already running (PID $PID), exiting" >> /logs/report.log
        exit 0
    else
        echo "$(date) — Stale lock found, removing" >> /logs/report.log
        rm "$LOCKFILE"
    fi
fi

# Create lock with current PID
echo $$ > "$LOCKFILE"

# Run job (cleanup lock on exit regardless of success/failure)
trap "rm -f $LOCKFILE" EXIT

python3 /scripts/report.py
```

### Python File Lock

```python
import fcntl
import sys

LOCKFILE = '/tmp/daily_report.lock'

def acquire_lock(lockfile: str):
    lock = open(lockfile, 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock
    except BlockingIOError:
        print(f'Another instance is running. Exiting.')
        sys.exit(0)

lock = acquire_lock(LOCKFILE)
try:
    run_job()
finally:
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()
```

---

## Backfill Strategy: What to Do After Downtime

Your server was down for 3 days. You have 3 days of missed cron runs. What now?

### Option A: Skip Missed Runs

For jobs where the specific time does not matter — just run now and resume from here.

```python
# Example: hourly data sync
# If we missed 72 runs, we don't need 72 syncs — just sync the last 3 days in one run

def sync_since_last_run():
    last_run = get_last_successful_run_timestamp()
    records = fetch_records_since(last_run)
    process_records(records)
    update_last_run_timestamp()
```

### Option B: Replay Missed Runs

For jobs where each time window must be processed — financial records, sequential reports.

```python
from datetime import date, timedelta

def backfill_reports(from_date: date, to_date: date):
    current = from_date
    while current <= to_date:
        logger.info(f'Backfilling report for {current}')
        generate_daily_report(current)  # idempotent — safe to re-run
        current += timedelta(days=1)

# Run manually after downtime
backfill_reports(date(2026, 3, 15), date(2026, 3, 17))
```

### Option C: Mark as Skipped

For jobs where missed runs are acceptable and should be acknowledged, not replayed.

```python
# On startup, detect missed runs and mark them skipped
def handle_startup_gap():
    expected_runs = get_expected_runs_since_last_run()
    for run_time in expected_runs:
        if not run_already_logged(run_time):
            log_skipped_run(run_time, reason='server_downtime')
```

💡 **PRO TIP:** The right backfill strategy depends entirely on the job. Payment processing must replay. Analytics can skip. Client reports should replay if missed by less than 48 hours, skip if older. Document the strategy per job, not per system.

---

## Lesson Exercise

Add monitoring to the three cron jobs you built in Lesson 2.

**Step 1: Set up Healthchecks.io (10 min)**
- Go to [healthchecks.io](https://healthchecks.io) and create a free account
- Create a check for each of your three cron jobs
- Set the expected schedule to match your cron expression
- Note the ping URL for each check (looks like `https://hc-ping.com/uuid-here`)

**Step 2: Add heartbeat to the n8n workflow (10 min)**
- Add an HTTP Request node at the END of your workflow (after all other nodes)
- Method: GET, URL: your healthchecks.io ping URL
- Add an error workflow that pings the `/fail` endpoint if anything goes wrong

**Step 3: Add error notifications to the system cron script (10 min)**
- Wrap the script body in try/except
- On exception: send a Telegram message or email with the error details
- On success: ping the healthchecks.io URL
- Test by temporarily introducing a bug (invalid variable name) and verifying the alert fires

🔥 **CHALLENGE:** Simulate a failure. Introduce a deliberate bug in your system cron script, let it run, and verify that:
1. The error appears in the log with timestamp and stack trace
2. You receive a failure notification (Telegram/email/Slack)
3. The healthchecks.io dashboard shows the check as "down"
4. Fixing the bug and running again clears the alert

---

## Summary

- Silent failure is the defining risk of cron — monitoring turns "probably ran" into "I know it ran"
- Always append logs with `>>`, always include timestamps, always capture stderr with `2>&1`
- Heartbeat monitoring inverts the model: alert fires when a check-in does not arrive
- n8n execution history is your first debugging tool for workflow-based cron jobs
- Idempotent jobs produce the same result on re-run — non-negotiable for financial and data jobs
- Lock files prevent overlapping executions from corrupting shared state
- Have a backfill strategy per job before you need it — not after a 3-day outage

**Next:** Lesson 4 — Production Patterns. Agency-grade cron architecture — tiered jobs, client isolation, backup strategy, AI agent maintenance, and scaling from 5 cron jobs to 50.
