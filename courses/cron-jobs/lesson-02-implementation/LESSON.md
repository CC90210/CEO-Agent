# Lesson 2: Implementation — n8n, System Cron & Claude Code Scheduling

> **Level:** Integrator (L2)
> **XP Reward: +250 XP** | Running Total: 450 XP
> **Course:** Cron Jobs Masterclass
> **Goal:** Build working cron jobs across three platforms — n8n, system cron, and Claude Code.

---

## n8n Schedule Trigger

The **Schedule Trigger** is n8n's cron node. It starts a workflow automatically at your defined interval. No webhook, no manual trigger — just time.

### Adding a Schedule Trigger

1. Open your n8n workflow editor
2. Click the "+" button to add the first node
3. Search "Schedule Trigger" and select it
4. Choose your mode:

| Mode | When to Use |
|------|------------|
| **Every X minutes/hours** | Simple intervals — "every 30 minutes" |
| **Every Day** | Fixed daily time with timezone selector |
| **Every Week** | Day of week + time |
| **Every Month** | Day of month + time |
| **Custom (Cron)** | Any expression from Lesson 1 |

### Expression Mode

Click "Custom (Cron)" to use raw cron syntax. This unlocks everything from Lesson 1.

```
Cron Expression field: */15 9-17 * * 1-5
Timezone: America/Toronto
```

n8n shows a human-readable preview: "Every 15 minutes, between 9:00 AM and 5:00 PM, Monday through Friday."

### Testing a Scheduled Workflow

You cannot wait for the schedule to fire to test. Use the "Execute Workflow" button (play icon) in the top toolbar to trigger an immediate single run. This executes the full workflow as if the cron fired — no waiting.

💡 **PRO TIP:** Build and test your workflow logic first with the manual trigger. Once the logic is confirmed working, swap the trigger node to Schedule Trigger. Never develop against a live cron schedule — you will wait forever between test runs.

---

## Agency Cron Patterns in n8n

These are the four workflows every agency should have running by default. They print money while you sleep.

### Pattern 1: Daily Client Report (9am)

**Cron:** `0 9 * * 1-5`
**What it does:** Pulls activity data from the past 24 hours, formats it, emails the client.

```
[Schedule: 0 9 * * 1-5]
    → [Supabase: SELECT activity WHERE created_at > NOW() - INTERVAL '24 hours']
    → [Code Node: format data into readable HTML table]
    → [Gmail/SMTP: send to client email]
    → [Supabase: INSERT into report_log (client_id, sent_at, row_count)]
```

**Code node template (JavaScript):**
```javascript
const rows = $input.all();
const tableRows = rows.map(r => `
  <tr>
    <td>${r.json.timestamp}</td>
    <td>${r.json.action}</td>
    <td>${r.json.value}</td>
  </tr>
`).join('');

return [{
  json: {
    subject: `Daily Report — ${new Date().toLocaleDateString()}`,
    html: `
      <h2>Yesterday's Activity</h2>
      <table border="1" cellpadding="8">
        <tr><th>Time</th><th>Action</th><th>Value</th></tr>
        ${tableRows}
      </table>
      <p>Total events: ${rows.length}</p>
    `
  }
}];
```

### Pattern 2: Weekly Lead Digest (Monday 8am)

**Cron:** `0 8 * * 1`
**What it does:** Aggregates leads from the past 7 days, scores them, emails a prioritized list.

```
[Schedule: 0 8 * * 1]
    → [Supabase: SELECT leads WHERE created_at > NOW() - INTERVAL '7 days']
    → [Code Node: score leads by recency + engagement]
    → [Sort: by score DESC]
    → [HTTP Request: POST to Claude API for lead qualification summary]
    → [Gmail: send prioritized lead digest]
```

**Scoring logic:**
```javascript
const leads = $input.all();
const scored = leads.map(lead => {
  let score = 0;
  if (lead.json.replied) score += 30;
  if (lead.json.opened_count > 2) score += 20;
  if (lead.json.source === 'referral') score += 25;
  if (lead.json.company_size > 10) score += 15;
  return { ...lead.json, score };
});
return scored
  .sort((a, b) => b.score - a.score)
  .map(l => ({ json: l }));
```

### Pattern 3: Monthly Invoice Generation (1st of Month)

**Cron:** `0 7 1 * *`
**What it does:** Pulls active subscriptions, creates Stripe invoices, logs them.

```
[Schedule: 0 7 1 * *]
    → [Supabase: SELECT clients WHERE status = 'active']
    → [Loop: for each client]
        → [Stripe: create invoice for client.stripe_customer_id]
        → [Stripe: finalize and send invoice]
        → [Supabase: INSERT invoice_log (client_id, invoice_id, amount, sent_at)]
    → [Gmail: send CC a summary "X invoices sent, $Y total"]
```

💀 **COMMON MISTAKE:** Running the invoice cron with `0 0 1 * *` (midnight) means you get woken up by errors at 12am. Push critical financial jobs to 7-9am so you are awake to handle failures. Never schedule money-touching crons at midnight.

### Pattern 4: Hourly Social Mention Monitor

**Cron:** `0 * * * *`
**What it does:** Checks brand mentions, alerts immediately if sentiment is negative.

```
[Schedule: 0 * * * *]
    → [HTTP Request: GET mentions from monitoring API]
    → [Code Node: filter for negative sentiment or competitor mentions]
    → [IF: any negative results?]
        → YES: [Slack/Telegram: alert with mention details]
        → NO:  [do nothing — no spam on clean hours]
```

💡 **PRO TIP:** For the hourly monitor, add a deduplication check before alerting. Store seen mention IDs in Supabase and `SELECT WHERE id NOT IN (seen_ids)` to avoid re-alerting on the same mention every hour.

---

## System Crontab (Linux/Mac)

System cron runs independently of n8n, Vercel, or any platform. It runs directly on your server as long as the server is on.

### Editing the Crontab

```bash
# Open the crontab editor for the current user
crontab -e

# View current crontab (list only)
crontab -l

# Remove all crontab entries (be careful)
crontab -r
```

The default editor is `vi`. To use nano instead:
```bash
EDITOR=nano crontab -e
```

### Crontab Format with Logging

Every production cron job should capture its output. Silent jobs are undebuggable jobs.

```bash
# Format: cron_expression command >> logfile 2>&1

# Daily backup at 2am — stdout and stderr to same log
0 2 * * * /usr/bin/python3 /home/user/scripts/backup.py >> /home/user/logs/backup.log 2>&1

# Hourly sync — append stdout to log, discard stderr (if you trust it)
0 * * * * /home/user/scripts/sync.sh >> /home/user/logs/sync.log

# Every 5 min health check — only log failures
*/5 * * * * /home/user/scripts/health.sh || echo "FAILED $(date)" >> /home/user/logs/health_failures.log
```

**Breaking down `>> /path/to/log 2>&1`:**
- `>>` — append to file (not overwrite)
- `/path/to/log` — the log file path
- `2>&1` — redirect stderr (file descriptor 2) to stdout (file descriptor 1), so both go to the same log

### Using Full Paths

System cron runs with a minimal environment. Your `$PATH` is not set. Always use full paths.

```bash
# WRONG — cron does not know where 'python3' is
0 2 * * * python3 /home/user/scripts/backup.py

# RIGHT — full path to python3
0 2 * * * /usr/bin/python3 /home/user/scripts/backup.py

# Find full paths with 'which'
which python3    # → /usr/bin/python3
which node       # → /usr/local/bin/node
which npm        # → /usr/local/bin/npm
```

### Environment Variables in Crontab

```bash
# Set variables at the top of the crontab file
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
MAILTO=cc@yourdomain.com

# Load from .env file in the script itself (recommended)
0 9 * * * /usr/bin/python3 /home/user/scripts/report.py

# Or source it inline (bash only)
0 9 * * * /bin/bash -c 'source /home/user/.env && python3 /home/user/scripts/report.py'
```

💡 **PRO TIP:** Never put credentials directly in the crontab. Load them from a `.env` file inside the script using `os.environ` (Python) or `dotenv` (Node.js). The crontab is readable by any process running as that user.

### Log Rotation

Cron logs grow indefinitely without rotation. Add a weekly log cleanup:

```bash
# Every Sunday at 3am: rotate logs older than 7 days
0 3 * * 0 find /home/user/logs -name "*.log" -mtime +7 -delete

# Or compress them instead of deleting
0 3 * * 0 find /home/user/logs -name "*.log" -mtime +7 -exec gzip {} \;
```

---

## Windows Task Scheduler via PowerShell

On Windows servers (or CC's local machine), system-level scheduled tasks use Task Scheduler. PowerShell gives you full control without touching the GUI.

### Create a Scheduled Task

```powershell
# Run a Python script every day at 9am
$action = New-ScheduledTaskAction `
    -Execute "C:\Python312\python.exe" `
    -Argument "C:\scripts\daily_report.py" `
    -WorkingDirectory "C:\scripts"

$trigger = New-ScheduledTaskTrigger `
    -Daily `
    -At "09:00AM"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName "DailyClientReport" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force
```

### Common Trigger Types

```powershell
# Every 15 minutes
$trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 15) -Once -At "00:00"

# Weekly on Monday at 8am
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "08:00AM"

# Monthly on the 1st at 7am
$trigger = New-ScheduledTaskTrigger -Monthly -DaysOfMonth 1 -At "07:00AM"
```

### Manage Existing Tasks

```powershell
# List all your scheduled tasks
Get-ScheduledTask | Where-Object { $_.TaskPath -eq "\" }

# Run a task manually right now
Start-ScheduledTask -TaskName "DailyClientReport"

# Disable without deleting
Disable-ScheduledTask -TaskName "DailyClientReport"

# Remove completely
Unregister-ScheduledTask -TaskName "DailyClientReport" -Confirm:$false
```

---

## Claude Code `/loop` Command

Claude Code's `/loop` command is a session-scoped recurring prompt. It does not use cron expressions — it takes a natural language interval.

### Syntax

```
/loop <interval> <prompt>
```

**Examples:**
```
/loop 30m check the deploy status and notify me if anything changed
/loop 5m scan the error logs and summarize any new failures
/loop 1h check if the n8n workflows are still healthy and report back
/loop 15m watch the Stripe dashboard and alert me if any payment fails
```

### Valid Intervals

| Format | Example |
|--------|---------|
| Minutes | `5m`, `15m`, `30m` |
| Hours | `1h`, `2h`, `4h` |

### When to Use `/loop` vs n8n Cron

| Scenario | Use |
|----------|-----|
| You are actively in a session and want updates | `/loop` |
| You need something to run while you are away | n8n / system cron |
| Checking build status during a deployment | `/loop 2m` |
| Permanent recurring business process | n8n Schedule Trigger |
| Monitoring a script that is currently running | `/loop` |
| Sending weekly client reports forever | n8n |

💡 **PRO TIP:** `/loop` is powerful during incident response. When something breaks, use `/loop 2m check the error logs and tell me if the issue is resolved` to get automatic updates without manually re-running checks.

---

## Vercel Cron Jobs

Vercel cron executes a serverless function at a schedule. Defined in `vercel.json`.

### Configuration

```json
{
  "crons": [
    {
      "path": "/api/cron/daily-report",
      "schedule": "0 9 * * 1-5"
    },
    {
      "path": "/api/cron/hourly-sync",
      "schedule": "0 * * * *"
    }
  ]
}
```

### The Handler Function

```typescript
// app/api/cron/daily-report/route.ts
import { NextRequest, NextResponse } from 'next/server';

export async function GET(req: NextRequest) {
  // Verify the request comes from Vercel (production only)
  const authHeader = req.headers.get('authorization');
  if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  // Your cron logic here
  const result = await runDailyReport();

  return NextResponse.json({ success: true, result });
}
```

```bash
# .env.local — generate a random secret
CRON_SECRET=your-random-secret-here
```

**Tier limits:**
- Free (Hobby): 1 run per day maximum
- Pro: 1 run per minute maximum
- Enterprise: 1 run per second maximum

💀 **COMMON MISTAKE:** Forgetting to verify the `Authorization` header on Vercel cron handlers. Without the check, anyone who knows your endpoint URL can trigger your cron job manually. Always verify `Bearer ${process.env.CRON_SECRET}`.

---

## GitHub Actions Scheduled Workflows

For code-adjacent cron jobs — dependency updates, automated tests, data exports from GitHub repos.

```yaml
# .github/workflows/weekly-report.yml
name: Weekly Report

on:
  schedule:
    - cron: '0 9 * * 1'  # Monday 9am UTC
  workflow_dispatch:       # Allow manual trigger

jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run report
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
        run: python scripts/weekly_report.py
```

**Key rules for GitHub Actions cron:**
- Always runs in UTC — factor the offset for your timezone
- Add `workflow_dispatch` alongside `schedule` — gives you a manual trigger button in the GitHub UI
- Secrets go in the repo's Settings → Secrets and Variables → Actions
- Free tier: 2,000 minutes/month for private repos (public repos are unlimited)

---

## Lesson Exercise

Build three cron jobs — one on each platform.

**Job 1: n8n — Daily Morning Brief (15 min)**
- Cron: `0 8 * * 1-5` with your local timezone
- Query Supabase for any records created in the last 24 hours from a table of your choice
- Send yourself a Telegram or email message with the count and a timestamp
- Verify it runs by using "Execute Workflow" manually

**Job 2: System Cron or Windows Task Scheduler (15 min)**
- Write a Python or Bash script that appends the current timestamp and a short message to a log file
- Schedule it to run every 5 minutes
- Wait 10-15 minutes and verify the log file has 2-3 entries

**Job 3: Claude Code `/loop` (5 min)**
- Start a 10-minute loop: `/loop 10m read the last 5 lines of [your log file from Job 2] and tell me what you see`
- Watch it report back at least once
- Cancel the loop when done: `/loop cancel` or close the session

🔥 **CHALLENGE:** Combine all three. Use the system cron to write data to a file every 5 minutes. Use the n8n workflow to read that file (via HTTP request to a small endpoint) every hour and email a digest. Use `/loop` to watch the n8n execution history while you are building it.

---

## Summary

- n8n Schedule Trigger: best for agency workflows — visual, timezone-aware, built-in history
- System crontab: best for server scripts — always use full paths, always log output
- Windows Task Scheduler: PowerShell-controlled, `Register-ScheduledTask` for automation
- Claude Code `/loop`: session-scoped, use for active monitoring during development or incidents
- Vercel cron: embedded in Next.js apps, verify the `CRON_SECRET` header on every handler
- GitHub Actions: UTC only, use `workflow_dispatch` alongside schedule for manual control

**Next:** Lesson 3 — Monitoring. The cron job that runs and fails silently is worse than no cron job at all.
