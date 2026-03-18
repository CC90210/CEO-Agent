# Day 6: Automation & Workflows — n8n and Cron Jobs

> **Level:** Integrator (Level 2)
> **Duration:** ~2.5 hours
> **Prerequisites:** Day 5 complete
> **Goal:** Automate repetitive tasks with visual workflows and scheduled jobs.

---

## Module 1: The Automation Mindset (15 min)

### The Rule of Three

If you do something 3 times → automate it.

**Before automation:**
1. Check email → copy lead info → paste into spreadsheet → send welcome email → set reminder
2. Time: 10 minutes per lead × 5 leads/day = 50 minutes/day = 300+ hours/year

**After automation:**
1. Email arrives → n8n catches it → extracts info → adds to database → sends welcome email → creates follow-up task
2. Time: 0 minutes. It just happens.

### Two Types of Automation

| Type | Trigger | Example |
|------|---------|---------|
| **Event-driven** | Something happens | "When a form is submitted, send an email" |
| **Time-based** | Clock hits a time | "Every morning at 9am, send me a summary" |

**Best practice:** Prefer event-driven (webhooks) over time-based (cron/polling). Why? Events are instant; polling wastes resources checking "did anything change?"

---

## Module 2: n8n Setup (25 min)

### What Is n8n?

n8n is a visual workflow automation tool. Like Zapier or Make.com, but:
- Open source (free to self-host)
- More powerful (code nodes, complex logic)
- Self-hosted (your data stays on your server)

### Getting Started

**Option A: n8n Cloud (easiest for learning)**
1. Go to https://n8n.io
2. Sign up for free trial
3. You get a hosted instance immediately

**Option B: Local (free forever)**
```bash
npx n8n
```
Opens at http://localhost:5678

**Option C: Self-hosted VPS (production)**
For running 24/7, host on a VPS (DigitalOcean, Hostinger, etc.)

### Dashboard Tour

| Area | Purpose |
|------|---------|
| **Workflows** | Your automations (the main area) |
| **Credentials** | API keys stored securely |
| **Executions** | History of every workflow run |
| **Variables** | Shared values across workflows |

---

## Module 3: Your First Workflow (30 min)

### The Building Blocks

Every n8n workflow has:
1. **Trigger** — What starts it (webhook, schedule, email, etc.)
2. **Nodes** — Actions performed (API calls, data transforms, etc.)
3. **Connections** — Lines between nodes (data flows through them)

### Build: Webhook → Process → Respond

**Step 1:** Create new workflow

**Step 2:** Add a Webhook trigger
- Click "+" → Search "Webhook"
- Set method to POST
- Copy the webhook URL (you'll need it to test)

**Step 3:** Add a "Set" node (transform data)
- Connect it to the webhook
- Add fields:
  - `message`: `Received: {{ $json.name }}`
  - `timestamp`: `{{ $now }}`

**Step 4:** Add a "Respond to Webhook" node
- Connect it to the Set node
- Response body: `{{ $json }}`

**Step 5:** Activate the workflow

**Step 6:** Test it
```bash
curl -X POST https://your-n8n.com/webhook/xxxx \
  -H "Content-Type: application/json" \
  -d '{"name": "Test User", "email": "test@email.com"}'
```

You should get back the processed response.

---

## Module 4: Common Workflow Patterns (30 min)

### Pattern 1: Form → Database → Email

```
Webhook (form data) → Supabase (insert row) → Email (send confirmation)
```

**Use case:** Contact form on your website automatically saves the lead and sends a thank-you email.

### Pattern 2: Schedule → API → Notification

```
Cron (every morning 9am) → HTTP Request (get data) → Slack/Email (send summary)
```

**Use case:** Daily sales report, weather briefing, news digest.

### Pattern 3: Email → AI → Response

```
Email Trigger → OpenAI/Claude (analyze email) → IF (is urgent?) → Email (auto-reply) / Slack (alert team)
```

**Use case:** AI-powered email triage.

### Pattern 4: Webhook → Multiple Actions (Parallel)

```
Webhook → Branch:
  ├── Supabase (save data)
  ├── Email (notify owner)
  └── Slack (post to channel)
```

**Use case:** New customer sign-up triggers multiple actions simultaneously.

### Key Nodes to Know

| Node | Purpose |
|------|---------|
| **Webhook** | Receive HTTP requests (triggers workflow) |
| **Schedule** | Run at specific times (cron) |
| **HTTP Request** | Call any API |
| **Supabase** | Database operations |
| **Set** | Transform/reshape data |
| **IF** | Conditional branching |
| **Switch** | Multiple branches based on value |
| **Code** | Custom JavaScript/Python |
| **Email (SMTP)** | Send emails |
| **Slack** | Post to Slack channels |

---

## Module 5: Cron Jobs (20 min)

### What Is Cron?

Cron is a scheduler built into every Unix/Linux/Mac system. It runs commands at specific times.

### Cron Syntax

```
* * * * *
│ │ │ │ │
│ │ │ │ └── Day of week (0-7, Sun=0 or 7)
│ │ │ └──── Month (1-12)
│ │ └────── Day of month (1-31)
│ └──────── Hour (0-23)
└────────── Minute (0-59)
```

**Examples:**
| Cron Expression | Meaning |
|----------------|---------|
| `0 9 * * *` | Every day at 9:00 AM |
| `*/30 * * * *` | Every 30 minutes |
| `0 9 * * 1` | Every Monday at 9:00 AM |
| `0 0 1 * *` | First day of every month at midnight |
| `0 9,17 * * 1-5` | 9 AM and 5 PM, Monday through Friday |

### Cron in n8n

In n8n, the Schedule trigger node handles cron:
1. Add a Schedule Trigger node
2. Set the cron expression or use the visual scheduler
3. Connect it to your workflow

### Cron in Claude Code

Claude Code has a built-in `/loop` command:
```
/loop 30m check the deploy status and notify me if anything changed
```

This runs the prompt every 30 minutes within your session.

### System Cron (Advanced)

For scripts that need to run on your server independently:
```bash
# Edit crontab
crontab -e

# Add a job: run backup.py every day at 2 AM
0 2 * * * /usr/bin/python3 /home/user/scripts/backup.py >> /home/user/logs/backup.log 2>&1
```

---

## Module 6: n8n + Claude Code (20 min)

### Connecting via MCP

With the n8n MCP server configured, Claude Code can:
- List all your workflows
- Get workflow details
- Execute workflows

```
List my n8n workflows
```

```
Run workflow ID 123 with input: {"name": "Test"}
```

### Connecting via Webhooks

Any n8n workflow with a Webhook trigger can be called from Claude Code:

```
Use bash to send a POST request to my n8n webhook:
curl -X POST https://my-n8n.com/webhook/xxx -H "Content-Type: application/json" -d '{"message": "Hello from Claude Code"}'
```

### The Power Combo

```
You ask Claude Code something
    → Claude Code triggers an n8n workflow
        → n8n calls APIs, processes data, sends notifications
            → Returns result to Claude Code
                → Claude Code summarizes for you
```

---

## Module 7: Webhooks Deep Dive (20 min)

### What Is a Webhook?

A webhook is a URL that receives data when something happens.

**Normal API call:** You ask → Server responds (pull)
**Webhook:** Something happens → Server tells you (push)

### Common Webhook Sources

| Service | Event | What It Sends |
|---------|-------|--------------|
| Stripe | Payment received | Customer info, amount, product |
| GitHub | Code pushed | Commit info, author, files changed |
| Supabase | Row inserted | New row data |
| Typeform | Form submitted | Form responses |
| Shopify | Order placed | Order details |

### Building a Webhook Receiver in n8n

1. Create workflow with Webhook trigger
2. Copy the webhook URL
3. Paste it into the external service's webhook settings
4. When the event happens → your workflow runs automatically

### Testing Webhooks Locally

```bash
# Send test data to your webhook
curl -X POST http://localhost:5678/webhook/test \
  -H "Content-Type: application/json" \
  -d '{
    "event": "new_lead",
    "name": "Jane Doe",
    "email": "jane@company.com",
    "source": "website"
  }'
```

---

## Exercise: Build an Automation Pipeline

**Create a "Lead Capture" automation:**

**Step 1:** Create an n8n workflow:
```
Webhook (receives lead data)
  → Supabase (insert into contacts table from Day 5)
  → Set (format welcome message)
  → Respond to Webhook (confirm receipt)
```

**Step 2:** Test with curl:
```bash
curl -X POST YOUR_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Lead", "email": "lead@test.com", "city": "Toronto"}'
```

**Step 3:** Verify in Supabase that the contact was added.

**Step 4:** Add a Schedule trigger workflow:
```
Cron (daily at 9 AM)
  → Supabase (count new contacts from last 24 hours)
  → Set (format summary message)
  → Log output
```

**Step 5:** Document your workflows in your project:
```bash
cd ~/ai-bootcamp/day-06
claude
```

Ask Claude Code:
```
Create a document called AUTOMATIONS.md that describes:
1. My lead capture webhook workflow (URL, expected payload, what it does)
2. My daily summary cron job (schedule, what it reports)
Include example curl commands for testing.
```

Push to GitHub.

---

## Checklist Before Moving On

- [ ] Understand event-driven vs time-based automation
- [ ] n8n set up (cloud or local)
- [ ] Built a webhook-triggered workflow
- [ ] Understand cron syntax and scheduling
- [ ] Connected n8n to Supabase
- [ ] Understand webhooks (what they are, how to test)
- [ ] Built the lead capture exercise
- [ ] Documented automations and pushed to GitHub

**All boxes checked?** You've automated your first pipeline. You're no longer doing manual work — the system does it for you.

---

**Next:** [Day 7 — Deployment & Hosting](../day-07-deployment-and-hosting/LESSON.md)
