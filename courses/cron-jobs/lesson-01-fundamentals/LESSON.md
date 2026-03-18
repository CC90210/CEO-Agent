# Lesson 1: Cron Job Fundamentals — Scheduling That Runs Your Business While You Sleep

> **Level:** Integrator (L2)
> **XP Reward: +200 XP** | Running Total: 200 XP
> **Course:** Cron Jobs Masterclass
> **Goal:** Understand cron from first principles — syntax, patterns, platforms, and when to use it.

---

## What Is Cron?

**Cron** is a time-based job scheduler. It originated in Unix in 1975 and has become the backbone of automated computing worldwide. The name comes from "chronos" (Greek for time).

Simple definition: you tell it *when* to run something, and it runs it. Every time. Without you.

Your server, your cloud functions, your n8n instance — they all have a cron engine underneath. Understanding cron is not optional for agency operators. It is the difference between a business that runs while you sleep and one that requires you to be awake.

**What cron replaces:**
- You manually sending client reports every Monday
- You remembering to run database backups
- You checking whether the overnight data sync finished
- You posting content at a specific time

🧠 **KEY TAKEAWAY:** Cron is not a tool. It is a mindset. Once you see a repeated manual task, the next thought should always be "what cron expression do I need?"

---

## Why Cron Matters for Agencies

Most agency operators automate *reactions* (webhooks, form submissions) and forget about *time*. Time-based automation is where the real leverage lives.

**Agency use cases by category:**

| Category | Example Jobs |
|----------|-------------|
| **Client Reporting** | Daily activity digest, weekly KPI report, monthly invoice |
| **Data Management** | Nightly database backup, stale lead cleanup, log rotation |
| **External Syncs** | Hourly CRM sync, daily contact import, weekly analytics pull |
| **Monitoring** | Every-5-min uptime check, hourly error log scan, daily disk usage alert |
| **Content Operations** | Scheduled social posts, drip email sequences, blog publishing queue |
| **AI Agent Maintenance** | Daily self-healing run, weekly retro, memory compression |
| **Financial** | Monthly invoice generation, weekly revenue summary, quarterly tax export |

💡 **PRO TIP:** The highest-leverage cron jobs are client-facing ones. A client who gets an automated weekly report every Monday at 9am feels like they have a team behind them. It takes 2 hours to build. It runs forever.

---

## Cron Syntax Deep Dive

Every cron expression has exactly five fields, separated by spaces:

```
* * * * *
│ │ │ │ │
│ │ │ │ └── Day of week  (0-7, Sun=0 or 7, Mon=1, Sat=6)
│ │ │ └──── Month        (1-12)
│ │ └────── Day of month (1-31)
│ └──────── Hour         (0-23, 24-hour clock)
└────────── Minute       (0-59)
```

### Special Characters

| Character | Name | Meaning | Example |
|-----------|------|---------|---------|
| `*` | Wildcard | Every possible value | `* * * * *` = every minute |
| `/` | Step | Every N units | `*/15 * * * *` = every 15 minutes |
| `-` | Range | From X to Y (inclusive) | `9-17` in hour field = 9am through 5pm |
| `,` | List | Multiple specific values | `1,15` in day field = 1st and 15th |
| `L` | Last | Last day of month/week | `0 0 L * *` = midnight on last day of month |
| `W` | Weekday | Nearest weekday to a date | `0 9 15W * *` = 9am on weekday nearest to 15th |

### Reading Expressions Left to Right

The order of fields trips up beginners. Always read: **minute, hour, day-of-month, month, day-of-week**.

```
0 9 * * 1
│ │ │ │ │
│ │ │ │ └── Monday (1)
│ │ │ └──── Every month
│ │ └────── Every day of month
│ └──────── 9am (hour 9)
└────────── 0 minutes (on the hour)

Translation: "At 9:00am every Monday, every month."
```

### Advanced Expressions

These are the patterns you will actually use in production:

```bash
# Every 15 minutes during business hours on weekdays
*/15 9-17 * * 1-5

# Every day at 9am AND 5pm
0 9,17 * * *

# Every weekday at 8:30am
30 8 * * 1-5

# First day of every month at midnight
0 0 1 * *

# Last day of every month at 11:59pm
59 23 L * *

# Every 6 hours
0 */6 * * *

# Quarterly: Jan, Apr, Jul, Oct on the 1st at 9am
0 9 1 1,4,7,10 *

# Every Sunday at 2am (low-traffic maintenance window)
0 2 * * 0
```

💡 **PRO TIP:** Use [crontab.guru](https://crontab.guru) to verify expressions before deploying them. Paste any expression and it shows you exactly when it will fire. Bookmark this. You will use it weekly.

---

## Common Patterns Reference Table

| Schedule | Cron Expression | Use Case |
|----------|----------------|----------|
| Every minute | `* * * * *` | Real-time monitoring (use sparingly) |
| Every 5 minutes | `*/5 * * * *` | Uptime checks, queue polling |
| Every 15 minutes | `*/15 * * * *` | Social media monitoring, webhook fallbacks |
| Every 30 minutes | `*/30 * * * *` | Data sync polling |
| Hourly | `0 * * * *` | Hourly digests, rate-limited API calls |
| Daily 9am | `0 9 * * *` | Client morning reports |
| Daily 2am | `0 2 * * *` | Database backups, maintenance |
| Weekdays 8:30am | `30 8 * * 1-5` | Business day briefings |
| Business hours every 15 min | `*/15 9-17 * * 1-5` | Active monitoring during client hours |
| Monday 8am | `0 8 * * 1` | Weekly lead digest |
| Friday 5pm | `0 17 * * 5` | End-of-week client summary |
| 1st of month midnight | `0 0 1 * *` | Monthly invoice generation |
| Quarterly | `0 9 1 1,4,7,10 *` | Quarterly business review |

---

## Cron vs Event-Driven: When to Use Each

This distinction matters. Using the wrong trigger pattern leads to wasted compute, stale data, or missed events.

| Factor | Cron (Time-Based) | Event-Driven (Webhook) |
|--------|-------------------|------------------------|
| **Latency** | Up to interval length | Near-instant |
| **Resource use** | Runs whether needed or not | Runs only when triggered |
| **Reliability** | Consistent, predictable | Depends on trigger firing |
| **Best for** | Batch jobs, reports, scheduled posts | Form submissions, payments, real-time alerts |
| **Failure mode** | Misses window if down | Misses event if not listening |

**Use cron when:**
- You need something to happen at a specific time (client reports, invoices)
- You are polling an external system that does not support webhooks
- You are doing batch processing (combining 100 small actions into one scheduled bulk run)
- You need cleanup jobs (delete records older than 90 days, compress logs)

**Use event-driven when:**
- Something happening immediately triggers a response (new lead → send welcome email)
- Latency matters (payment confirmation should not wait an hour)
- The source system supports webhooks (Stripe, Typeform, GitHub all do)

💀 **COMMON MISTAKE:** Using cron to poll a webhook-capable API every 5 minutes. If Stripe, Typeform, or GitHub can push to you, use their webhooks. Cron polling wastes API rate limits, adds latency, and misses events between intervals.

---

## Platform Differences

Cron syntax is the same everywhere, but execution environments differ significantly.

### Unix/Linux Crontab (System Level)
- Built into every Linux/Mac server
- Runs as the system user who owns the crontab
- Controlled with `crontab -e` (edit) and `crontab -l` (list)
- No built-in monitoring or retry — script must handle its own errors

### Windows Task Scheduler
- GUI-based and PowerShell-controllable
- Supports more complex triggers (on login, on idle, on event)
- Does not use cron syntax — uses a different scheduling format
- PowerShell: `Register-ScheduledTask` for automation

### n8n Schedule Trigger
- Visual cron builder with expression mode
- Timezone-aware (set per-workflow)
- Built-in execution history and error handling
- Best choice for agency workflows — visible, maintainable, no server access needed

### Vercel Cron Jobs
- Defined in `vercel.json`
- Calls a serverless function URL on schedule
- Free tier: once per day maximum
- Pro tier: up to once per minute
- Excellent for Next.js apps needing scheduled API calls

### GitHub Actions Scheduled Workflows
- Defined in `.github/workflows/*.yml` with `on: schedule:`
- Uses UTC timezone (non-negotiable)
- Free tier: generous for public repos, limited for private
- Best for code-related tasks: dependency updates, test runs, deployments

### Cloud Schedulers
- **AWS EventBridge Scheduler**: Enterprise-grade, millisecond precision, retries
- **Google Cloud Scheduler**: HTTP/Pub-Sub targets, timezone support
- **Railway Cron**: Simple, integrated with Railway deployments

💡 **PRO TIP:** For agency client work, use n8n for 90% of cron jobs. It gives you a visual history, easy editing, error notifications, and no server access required. Reserve system cron for scripts that run on your VPS and need OS-level access (file operations, system commands, database dumps).

---

## Time Zones: The Silent Killer

Cron fires based on the time zone of the system running it. This causes bugs that are nearly impossible to debug unless you know to look for them.

**The classic failure:**
- Your n8n instance runs in UTC
- Your client is in Toronto (EST, UTC-5)
- You set a cron job to `0 9 * * *` expecting 9am client time
- It fires at 4am local time for the client

**The rules:**
1. System crontab uses the server's local timezone — check with `date` before assuming
2. n8n Schedule nodes have a timezone field — always set it explicitly, never leave it on server default
3. Vercel cron runs in UTC — always
4. GitHub Actions runs in UTC — always
5. Cloud schedulers (AWS, GCP) are configurable — set to client timezone or UTC and document which

**Converting common timezone offsets:**
| Client Timezone | UTC Offset | "9am local" in UTC |
|-----------------|------------|-------------------|
| EST (Toronto/NYC) | -5 (winter), -4 (summer) | `0 14 * * *` (winter) |
| CST (Chicago) | -6 (winter), -5 (summer) | `0 15 * * *` (winter) |
| PST (Vancouver/LA) | -8 (winter), -7 (summer) | `0 17 * * *` (winter) |
| GMT (London) | 0 (winter), +1 (summer) | `0 9 * * *` (winter) |
| CET (Berlin/Paris) | +1 (winter), +2 (summer) | `0 8 * * *` (winter) |

💀 **COMMON MISTAKE:** Daylight Saving Time (DST) shifts timezone offsets twice a year. A cron job set to fire at 9am in winter will fire at 10am after clocks spring forward — or miss an entire hour entirely when clocks fall back. Solution: use a timezone-aware scheduler (n8n, cloud scheduler) rather than hardcoded UTC offsets in system cron.

---

## Lesson Exercise

Write cron expressions for these 10 business scenarios. Do not look at the answer until you have written all 10.

| # | Scenario | Your Expression |
|---|----------|----------------|
| 1 | Send a client report every weekday at 8am | |
| 2 | Run a database backup every night at 3am | |
| 3 | Post to social media at 9am and 6pm, every day | |
| 4 | Check for new leads every 10 minutes during business hours (9-5) on weekdays | |
| 5 | Generate monthly invoices on the 1st of each month at 7am | |
| 6 | Send a weekly summary every Friday at 4pm | |
| 7 | Run a cleanup job every 6 hours | |
| 8 | Send a quarterly business review on the first of Jan, Apr, Jul, Oct at 9am | |
| 9 | Monitor a competitor's website every 30 minutes | |
| 10 | Archive log files every Sunday at 1am | |

**Answers:**
1. `0 8 * * 1-5`
2. `0 3 * * *`
3. `0 9,18 * * *`
4. `*/10 9-17 * * 1-5`
5. `0 7 1 * *`
6. `0 16 * * 5`
7. `0 */6 * * *`
8. `0 9 1 1,4,7,10 *`
9. `*/30 * * * *`
10. `0 1 * * 0`

🔥 **CHALLENGE:** Open [crontab.guru](https://crontab.guru) and verify each expression you wrote. For any you got wrong, read the explanation until the syntax clicks — not until it "makes sense", until you can write the next one from memory.

---

## Summary

- Cron is a five-field time expression: minute, hour, day-of-month, month, day-of-week
- Special characters `*`, `/`, `-`, `,` unlock every scheduling pattern you will ever need
- Use cron for time-based batch work; use webhooks for event-driven real-time responses
- Platform matters: n8n for agency workflows, system cron for server scripts, Vercel/GitHub for cloud functions
- Always set timezone explicitly — never assume the server's local time matches the client's

**Next:** Lesson 2 — Implementation. You will build actual cron jobs in n8n, system cron, and Claude Code's `/loop` command.
