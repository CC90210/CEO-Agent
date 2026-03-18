# Lesson 4: Production Patterns — Agency-Grade Cron Architecture

> **Level:** Integrator (L2)
> **XP Reward: +350 XP** | Running Total: 1,100 XP
> **Course:** Cron Jobs Masterclass
> **Goal:** Design, document, and operate cron infrastructure that scales from your first client to your fiftieth.

---

## The Three-Tier Cron Architecture

Not all cron jobs are equal. Running a weekly analytics rollup with the same monitoring rigor as a payment processor is over-engineering. Running a monthly invoice job with no alerting is negligent. The tier system gives you the right level of rigor for the right job.

### Tier 1: Critical (Must Never Fail)

**Characteristics:** Touches money, client contracts, or irreplaceable data. Failure has immediate business consequences.

| Job Type | Example | Alert Threshold |
|----------|---------|----------------|
| Payment processing | Monthly invoice generation | Any single failure |
| Client deliverables | Weekly client report | Any single failure |
| Data backups | Nightly database dump | Miss 1 run |
| Legal/compliance | Invoice archival | Any single failure |

**Requirements for Tier 1:**
- Heartbeat monitoring (Healthchecks.io or Cronitor)
- Failure alert within 5 minutes (Slack + email + SMS for highest stakes)
- Idempotency verified — safe to re-run manually
- Lock file or mutex to prevent overlapping
- Retry logic with exponential backoff (up to 3 attempts before alerting)
- Manual runbook documented: what to do when this job fails
- Last-run timestamp stored in database
- Tested monthly by triggering manually and verifying output

### Tier 2: Important (Acceptable Short Delay)

**Characteristics:** Affects quality of service but not immediately catastrophic. Failure discovered within hours is acceptable.

| Job Type | Example | Alert Threshold |
|----------|---------|----------------|
| Lead scoring | Daily lead quality update | Miss 2 consecutive runs |
| Social monitoring | Hourly mention check | Miss 3 runs |
| Content scheduling | Posting queue drainer | Miss 1 run (time-sensitive) |
| CRM sync | 30-min contact import | Miss 4 runs |

**Requirements for Tier 2:**
- Log output to file (with timestamps)
- Failure alert (Slack only, no SMS)
- Idempotency preferred but not mandatory
- Weekly review of execution history

### Tier 3: Nice-to-Have (Best Effort)

**Characteristics:** Convenience or optimization. Failure is not noticed by clients.

| Job Type | Example | Alert Threshold |
|----------|---------|----------------|
| Analytics aggregation | Nightly stats rollup | Weekly review |
| Cache warming | Pre-build report data | None |
| Log cleanup | Delete old log files | None |
| Memory compression | Bravo memory archiving | Weekly review |
| Database maintenance | VACUUM, ANALYZE | Monthly review |

**Requirements for Tier 3:**
- Log to file (no monitoring required)
- Run during off-peak hours
- Acceptable to skip entirely if system is under load

💡 **PRO TIP:** When onboarding a new client, categorize every automated job into tiers on Day 1. This prevents the scenario where you have 20 jobs, something breaks at 2am, and you cannot tell if it is Tier 1 (wake someone up) or Tier 3 (check in the morning).

---

## Client-Specific Cron Jobs: Namespace Isolation

When you run cron jobs for multiple clients on the same server, isolation prevents one client's failure from affecting another — and makes debugging dramatically faster.

### Directory Structure

```
/home/user/
├── clients/
│   ├── client-a/
│   │   ├── .env              # client A credentials (never committed)
│   │   ├── scripts/
│   │   │   ├── daily_report.py
│   │   │   └── weekly_digest.py
│   │   └── logs/
│   │       ├── daily_report.log
│   │       └── weekly_digest.log
│   ├── client-b/
│   │   ├── .env
│   │   ├── scripts/
│   │   └── logs/
│   └── client-c/
│       ├── .env
│       ├── scripts/
│       └── logs/
└── shared/
    └── lib/                  # shared Python utilities
```

### Crontab With Namespacing

```bash
# Client A — Daily report at 9am EST (14:00 UTC)
0 14 * * 1-5 /usr/bin/python3 /home/user/clients/client-a/scripts/daily_report.py >> /home/user/clients/client-a/logs/daily_report.log 2>&1

# Client B — Weekly digest, Monday 8am PST (16:00 UTC)
0 16 * * 1 /usr/bin/python3 /home/user/clients/client-b/scripts/weekly_digest.py >> /home/user/clients/client-b/logs/weekly_digest.log 2>&1

# Client C — Monthly invoice, 1st of month at 7am MST (14:00 UTC)
0 14 1 * * /usr/bin/python3 /home/user/clients/client-c/scripts/invoice.py >> /home/user/clients/client-c/logs/invoice.log 2>&1
```

### Templated Scripts

Avoid duplicating logic across client scripts. Create a base class, parameterize per client.

```python
# shared/lib/report_base.py
import os
import logging
from abc import ABC, abstractmethod

class DailyReportBase(ABC):
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.env_path = f'/home/user/clients/{client_id}/.env'
        self.load_env()
        self.setup_logging()

    def load_env(self):
        from dotenv import load_dotenv
        load_dotenv(self.env_path)
        self.supabase_url = os.environ['SUPABASE_URL']
        self.supabase_key = os.environ['SUPABASE_KEY']
        self.email_recipient = os.environ['CLIENT_EMAIL']

    def setup_logging(self):
        log_path = f'/home/user/clients/{self.client_id}/logs/daily_report.log'
        logging.basicConfig(filename=log_path, level=logging.INFO,
                            format='%(asctime)s — %(levelname)s — %(message)s')
        self.logger = logging.getLogger(__name__)

    @abstractmethod
    def fetch_data(self) -> list:
        pass

    def run(self):
        self.logger.info(f'Starting daily report for {self.client_id}')
        data = self.fetch_data()
        self.send_report(data)
        self.logger.info(f'Report sent — {len(data)} rows')
```

```python
# clients/client-a/scripts/daily_report.py
import sys
sys.path.insert(0, '/home/user/shared')
from lib.report_base import DailyReportBase

class ClientAReport(DailyReportBase):
    def fetch_data(self):
        # Client A specific query
        return self.supabase.table('client_a_activity').select('*').execute().data

if __name__ == '__main__':
    ClientAReport('client-a').run()
```

---

## Database Maintenance Crons

Databases need scheduled care. Neglecting these is how you end up with a 50GB database that runs at 10% of its potential speed.

### Supabase / PostgreSQL Maintenance

```sql
-- vacuum_analyze.sql — reclaim dead row space and update query planner stats
VACUUM ANALYZE;

-- Index health check — find bloated indexes
SELECT schemaname, tablename, indexname,
       pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 20;

-- Row count monitoring — detect unexpected table growth
SELECT schemaname, tablename,
       n_live_tup AS live_rows,
       n_dead_tup AS dead_rows,
       round(n_dead_tup::numeric / nullif(n_live_tup + n_dead_tup, 0) * 100, 2) AS dead_pct
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000
ORDER BY dead_pct DESC;
```

```bash
# Crontab: weekly VACUUM ANALYZE on Sunday at 2am
0 2 * * 0 psql $DATABASE_URL -f /scripts/vacuum_analyze.sql >> /logs/db_maintenance.log 2>&1
```

### Stale Data Cleanup

```python
# cleanup_stale_data.py
# Runs nightly at 3am — removes data past retention policy

import os
from datetime import datetime, timedelta, timezone
from supabase import create_client

supabase = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])

RETENTION_POLICIES = [
    ('session_logs', 90),     # keep 90 days
    ('raw_webhooks', 30),     # keep 30 days
    ('temp_exports', 7),      # keep 7 days
    ('error_logs', 60),       # keep 60 days
]

def run():
    for table, days in RETENTION_POLICIES:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result = supabase.table(table) \
            .delete() \
            .lt('created_at', cutoff) \
            .execute()
        print(f'{table}: deleted {len(result.data)} rows older than {days} days')
```

---

## Backup Strategy: The 3-2-1 Rule

**3** copies of data, on **2** different media types, with **1** offsite.

For agencies:
- Copy 1: Live Supabase database (primary)
- Copy 2: Daily dump on your VPS local disk (second medium)
- Copy 3: Weekly upload to S3 or Backblaze B2 (offsite)

### Automated Backup Script

```bash
#!/bin/bash
# backup.sh — runs via cron: 0 2 * * * /scripts/backup.sh >> /logs/backup.log 2>&1

set -euo pipefail  # exit on error, undefined vars, pipe failures

BACKUP_DIR="/home/user/backups"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_FILE="${BACKUP_DIR}/db_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=14

echo "$(date) — Starting backup"

# Create dump
pg_dump "$DATABASE_URL" | gzip > "$BACKUP_FILE"
echo "$(date) — Dump created: $(du -h "$BACKUP_FILE" | cut -f1)"

# Upload to S3 (requires aws CLI configured)
aws s3 cp "$BACKUP_FILE" "s3://${S3_BUCKET}/backups/$(basename "$BACKUP_FILE")"
echo "$(date) — Uploaded to S3"

# Delete local backups older than retention period
find "$BACKUP_DIR" -name "db_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
echo "$(date) — Pruned local backups older than ${RETENTION_DAYS} days"

echo "$(date) — Backup complete"
```

💀 **COMMON MISTAKE:** Building a backup cron job and never testing restore. A backup you have never restored is a backup you do not have. Schedule a quarterly restore test: pick a random backup file, restore it to a test database, verify the row counts match. Put it in your calendar now.

---

## Content Automation Crons

The Late API (connected via n8n) enables scheduled social content at scale.

### Scheduled Post Queue

The pattern: authors write posts → stored in a Supabase queue → cron drains the queue at optimal posting times.

```javascript
// n8n Code node: drain the posting queue
// Cron: 0 9,12,17,20 * * *  (post at 9am, 12pm, 5pm, 8pm)

const pending = await supabase
  .from('post_queue')
  .select('*')
  .eq('status', 'pending')
  .lte('scheduled_for', new Date().toISOString())
  .order('priority', { ascending: false })
  .limit(1)
  .single();

if (!pending.data) {
  return [{ json: { message: 'Queue empty, nothing to post' } }];
}

// Mark as processing before posting (prevents duplicate posts on retry)
await supabase
  .from('post_queue')
  .update({ status: 'processing', started_at: new Date().toISOString() })
  .eq('id', pending.data.id);

return [{ json: pending.data }];
```

### Drip Email Campaign Cron

```python
# drip_emails.py — runs every hour
# Sends the next email in a sequence to subscribers who are due

def run():
    # Find subscribers whose next email is due
    due = supabase.table('drip_subscriptions') \
        .select('*, contacts(email, name), drip_sequences(emails)') \
        .lte('next_send_at', datetime.now(timezone.utc).isoformat()) \
        .eq('status', 'active') \
        .execute()

    for sub in due.data:
        sequence = sub['drip_sequences']['emails']
        current_step = sub['current_step']

        if current_step >= len(sequence):
            # Sequence complete
            supabase.table('drip_subscriptions') \
                .update({'status': 'completed'}) \
                .eq('id', sub['id']) \
                .execute()
            continue

        # Send the email
        email = sequence[current_step]
        send_email(
            to=sub['contacts']['email'],
            subject=email['subject'],
            body=email['body'].replace('{{name}}', sub['contacts']['name'])
        )

        # Advance the sequence
        supabase.table('drip_subscriptions').update({
            'current_step': current_step + 1,
            'next_send_at': (datetime.now(timezone.utc) + timedelta(days=email['delay_days'])).isoformat(),
            'last_sent_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', sub['id']).execute()
```

---

## AI Agent Maintenance Crons

Bravo (and any AI agent system) needs scheduled maintenance to stay sharp and not bloat.

### Daily Self-Healing Run

```
Cron: 0 3 * * *  (3am daily)
What it does:
  1. Read memory/SESSION_LOG.md — compress entries older than 14 days to archives
  2. Read memory/ACTIVE_TASKS.md — mark completed tasks older than 7 days as archived
  3. Run confidence decay on LONG_TERM.md facts (C(t) = C₀ × e^(-λ × t))
  4. Scan for junk files in workspace
  5. Verify brain/STATE.md is not stale (last update within 48 hours)
  6. Log completion to Supabase agent_state table
```

### Weekly Retro Prompt

```
Cron: 0 9 * * 1  (Monday 9am)
What it does:
  Run /retro — analyze the past 7 days of commits, extract patterns,
  update PATTERNS.md and MISTAKES.md, generate the weekly report
```

### Memory Compression

```python
# compress_memory.py — runs monthly on 1st at 4am
# Archives session logs and daily logs older than 30 days

from pathlib import Path
import shutil
from datetime import datetime, timedelta

MEMORY_DIR = Path('/home/user/Business-Empire-Agent/memory')
ARCHIVE_DIR = MEMORY_DIR / 'ARCHIVES'

def compress_session_log():
    log_path = MEMORY_DIR / 'SESSION_LOG.md'
    lines = log_path.read_text().split('\n')

    # Keep last 10 session headers
    recent_start = None
    session_count = 0
    for i, line in enumerate(reversed(lines)):
        if line.startswith('### '):
            session_count += 1
            if session_count == 10:
                recent_start = len(lines) - i - 1
                break

    if recent_start is None:
        return  # Less than 10 sessions, nothing to archive

    archive_content = '\n'.join(lines[:recent_start])
    archive_path = ARCHIVE_DIR / f'sessions-{datetime.now().strftime("%Y-%m")}.md'

    with open(archive_path, 'a') as f:
        f.write(archive_content + '\n')

    log_path.write_text('\n'.join(lines[recent_start:]))
    print(f'Archived {recent_start} lines to {archive_path}')
```

---

## Cost Optimization: Batch Processing

Cron enables a powerful pattern: instead of triggering expensive operations in real-time, batch them and run during off-peak hours.

| Instead of... | Batch to... | Savings |
|---------------|------------|---------|
| Sending each email immediately on trigger | Queue emails, send in batches at 9am | API rate limits, retries simplified |
| Running Claude API per lead as they come in | Nightly lead scoring batch | 80-90% cost reduction via batching |
| Querying analytics on every page load | Pre-compute at midnight, cache results | Database load reduction |
| Real-time invoice calculation | Pre-calculate on 30th, send on 1st | Stripe API calls reduced |

### Claude API Batch Scoring (Cost Example)

```python
# lead_scoring.py — runs nightly at 2am
# Scores all unscored leads in one Claude API call (batched)

def score_leads_batch(leads: list) -> list:
    """Score up to 50 leads in a single API call."""

    prompt = f"""Score each lead on a scale of 1-10 for purchase likelihood.
Return JSON array with id and score fields only.

Leads:
{json.dumps([{'id': l['id'], 'company': l['company'], 'message': l['message']} for l in leads], indent=2)}"""

    response = claude.messages.create(
        model='claude-3-haiku-20240307',  # cheapest model for structured scoring
        max_tokens=500,
        messages=[{'role': 'user', 'content': prompt}]
    )

    return json.loads(response.content[0].text)

# Process in batches of 50
unscored = fetch_unscored_leads()
for batch in chunks(unscored, 50):
    scores = score_leads_batch(batch)
    update_lead_scores(scores)
```

---

## The Cron Registry

Once you have more than 10 cron jobs, you need a registry. Without one, you will duplicate jobs, create conflicting schedules, and have no idea what is running on which server.

### CRON_REGISTRY.md Template

```markdown
# Cron Registry

> Last updated: 2026-03-18
> Total active jobs: 12 | Tier 1: 4 | Tier 2: 5 | Tier 3: 3

## Tier 1 — Critical

| ID | Job Name | Schedule (UTC) | Platform | Script/Workflow | Client | Heartbeat | Runbook |
|----|----------|----------------|----------|----------------|--------|-----------|---------|
| C01 | Daily Client Report | `0 14 * * 1-5` | n8n | wf_daily_report | client-a | hc-uuid-1 | [link] |
| C02 | Monthly Invoice | `0 7 1 * *` | n8n | wf_invoice_gen | all | hc-uuid-2 | [link] |
| C03 | DB Backup | `0 2 * * *` | system | backup.sh | internal | hc-uuid-3 | [link] |
| C04 | Weekly Lead Digest | `0 8 * * 1` | n8n | wf_lead_digest | client-b | hc-uuid-4 | [link] |

## Tier 2 — Important

| ID | Job Name | Schedule (UTC) | Platform | Script/Workflow | Alert Channel |
|----|----------|----------------|----------|----------------|--------------|
| C05 | Hourly Mention Monitor | `0 * * * *` | n8n | wf_mentions | Slack #alerts |
| C06 | Post Queue Drainer | `0 9,12,17,20 * * *` | n8n | wf_post_queue | Slack #content |

## Tier 3 — Nice-to-Have

| ID | Job Name | Schedule (UTC) | Platform | Script/Workflow |
|----|----------|----------------|----------|----------------|
| C09 | Log Cleanup | `0 3 * * 0` | system | cleanup_logs.sh |
| C10 | Memory Compression | `0 4 1 * *` | system | compress_memory.py |
| C11 | DB VACUUM | `0 2 * * 0` | system | vacuum_analyze.sql |
```

---

## Lesson Exercise: Design a Complete Client Cron Architecture

Design a complete cron architecture for a hypothetical client: a local dental practice with a patient management system, social media presence, and monthly newsletter.

**Deliverable: your own CRON_REGISTRY.md**

Work through these steps:

**Step 1: Identify every repeated task (15 min)**
List every time-based task the practice needs: appointment reminders, review requests, social posts, monthly reports, database backup, etc. Aim for at least 10 jobs.

**Step 2: Categorize by tier (10 min)**
Assign each job to Tier 1, 2, or 3 using the criteria from this lesson.

**Step 3: Write the cron expressions (10 min)**
For each job, write the cron expression. Use crontab.guru to verify. Consider the practice's timezone (assume EST).

**Step 4: Assign platforms (5 min)**
Decide whether each job lives in n8n, system cron, Vercel, or GitHub Actions. Document the reason.

**Step 5: Define monitoring (5 min)**
For every Tier 1 job: define the heartbeat check interval and the alert channel. For Tier 2: define the alert channel. For Tier 3: no monitoring required.

**Step 6: Write the CRON_REGISTRY.md (10 min)**
Fill in the registry template using your decisions above.

🔥 **CHALLENGE:** Pick one Tier 1 job from your registry and write the full implementation: the n8n workflow or script, the heartbeat ping, the error notification, and the idempotency check. Make it production-ready enough that you could deploy it for a real client tomorrow.

---

## Summary

- Tier 1 (critical) jobs require heartbeat monitoring, retry logic, idempotency, and a runbook
- Tier 2 (important) jobs need logging and failure alerts; Tier 3 (nice-to-have) need logging only
- Namespace client cron jobs by directory — isolation makes debugging fast and failure blast radius small
- The 3-2-1 backup rule: 3 copies, 2 media types, 1 offsite — automate all three with cron
- Batch processing with cron slashes AI API costs by 80-90% compared to per-event triggering
- A Cron Registry is mandatory beyond 10 jobs — document tier, schedule, platform, heartbeat, and runbook per job

**Course Complete.** You have covered the full cron stack: syntax and theory (L1), implementation across platforms (L2), monitoring and reliability (L3), and agency-grade production patterns (L4).

**Total XP earned: 1,100 XP** — Level complete: Integrator (L2).
