---
name: outreach-send
description: Send OASIS cold/follow-up outreach emails with branded HTML, booking link, geo-rapport, and full deliverability protection. Use whenever CC says "send outreach", "email these leads", "follow up with X", or any first/second-touch sales email to a lead in the CRM. Works identically from Claude Code, OpenCode, Codex, Gemini, and Antigravity.
triggers: ["outreach send", "use outreach send", "run outreach send", "send oasis cold/follow-up outreach emails with branded html"]
---

# Outreach Send — Canonical Workflow

> Single source of truth for sending OASIS outreach emails. Every AI in CC's empire (Claude Code, OpenCode, Codex, Gemini, Antigravity) reads this file and uses the same command.
>
> **Do not draft and send raw text.** The system will refuse — see "Why this exists" at the bottom.
>
> Related: [[brain/CRM_STRATEGY]] · [[prompts/RUN_OUTREACH]] (full operator runbook)

---

## TL;DR — The one command you need

```bash
python scripts/email_engine.py --json send-template \
  --template-id <uuid> \
  --to <email> \
  --lead-id <lead-uuid> \
  --vars '{"first_name":"Matt","company":"Collingwood Charters"}'
```

That's it. The engine handles everything else: HTML rendering, geo-rapport line, booking-link button, OASIS website signature, CASL footer, suppression check, hourly cap, draft critic, lead ledger logging.

---

## The 3 OASIS templates

Run `python scripts/email_engine.py templates list` to get current UUIDs (don't memorize them — they may rotate).

| Name | Subject pattern | When to use |
|---|---|---|
| **OASIS Welcome** | `Quick thought for {{company}}` | First touch, never contacted before |
| **OASIS CTA** | `Worth a 15-minute AI audit for {{company}}?` | Direct ask after warm signal or 2nd touch |
| **OASIS Value Add** | `Where follow-up leaks at {{company}}` | Follow-up to a lead who didn't reply, 5+ days stale |

All three render with: `{{first_name}}`, `{{company}}`, `{{region}}`.

---

## Variables — what to pass

```json
{"first_name": "Matt", "company": "Collingwood Charters"}
```

That's the minimum. The engine **auto-injects `{{region}}`** from the lead row when you pass `--lead-id` (it reads `company`, `name`, `notes`, `phone` and runs region inference). You can override by passing `region` in `--vars` if you have better intel.

Region examples:
- Lead phone `(705) 443-1124` + company "Collingwood Charters" → `the Collingwood area`
- Lead phone `(416) 555-1212` → `the Toronto area`
- Lead phone `(905) 555-1212` → `the Greater Toronto area`
- Unknown → `your area` (still reads naturally: "fellow local business owner working with companies in your area")

This makes every email say "fellow local business owner working with companies in [their region]" — building rapport without lying. CC's actual address (Collingwood, ON) stays in the small grey CASL footer.

---

## What the system blocks (so you don't ship spam)

| Gate | What it catches | How to fix |
|---|---|---|
| **Gate 1b — HTML required** | Plain-text-only OASIS commercial sends | Use `send-template` (not raw `send --body`) |
| **Suppression** | Lead is on the unsubscribe list | Don't send. Period. |
| **Hourly cap** | More than 30 emails/hr | Wait, or batch over time |
| **Daily cap** | More than 60 emails/day | Wait until tomorrow |
| **Cooldown** | Same lead emailed in last 48h | Wait or pick a different lead |
| **Draft critic** | AI-slop, ungrounded claims, voice drift | Rewrite or skip |

If a send returns `status: "blocked"`, read the `reason` field. It tells you exactly which gate fired and what to do.

---

## Bulk / batch sends

For a list of leads, loop the single command. Pace at ~2-3 sec between sends to keep cooldown ledger writes serial:

```python
import json, subprocess, time
for lead in leads:
    cmd = ["python", "scripts/email_engine.py", "--json", "send-template",
           "--template-id", TEMPLATE_UUID,
           "--to", lead["email"],
           "--lead-id", lead["id"],
           "--vars", json.dumps({"first_name": lead["first_name"],
                                  "company": lead["company"]})]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    print(json.loads(r.stdout))
    time.sleep(2)
```

For Bravo's semi-auto draft-then-approve flow, use `python scripts/outreach_batch.py --limit 5`. That writes drafts to `tmp/outreach_drafts/`, posts to Telegram for CC's approval, and routes through the same gateway on `--send-draft <path>`.

---

## Required quality bar (non-negotiable)

Every outreach email that ships MUST:

1. **Be HTML** (the gateway refuses text-only OASIS commercial sends)
2. **Have the booking-link button** (built into all 3 templates)
3. **Have the website link** (`https://oasisai.work` in every template signature)
4. **Have a real first name** (no "Hi Contact" / "Hi Owner" / "Hi there" — sanitizer scrubs these)
5. **Reference the lead's region** (auto-injected from `--lead-id`)
6. **Pass the draft critic** (verdict = "ship", score ≥ 6.5)

If any of these fail, the gateway returns `status: "blocked"` BEFORE the email leaves SMTP.

---

## Picking leads from the CRM

```bash
python scripts/lead_engine.py --json list --status new --limit 30
python scripts/lead_engine.py --json list --status contacted --limit 30
```

Filter to leads with `email` set, `last_contacted_at` null or > 5 days old, and a real (non-placeholder) `name`. The 2026-04-25 incident: 9 emails went out as "Hi Contact" because the CSV import had `name="Contact"` for missing names. The sanitizer now blocks `Contact / Owner / Info / Team / There / Admin / Support / Customer / Service` as first names — but only if the caller actually passes the name; you still have to filter the lead list before sending.

---

## CLI tool reference

| Tool | Use for |
|---|---|
| `scripts/email_engine.py send-template` | The send command. Always this for outreach. |
| `scripts/email_engine.py templates list` | List the 3 OASIS template UUIDs |
| `scripts/email_engine.py templates view <uuid>` | Inspect a template's HTML/text/vars |
| `scripts/email_engine.py log` | View recent sends |
| `scripts/email_engine.py stats` | Aggregate stats |
| `scripts/email_engine.py check-inbox` | Process inbound replies (auto-suppress unsub) |
| `scripts/region_inference.py` | Self-test the region inferrer |
| `scripts/outreach_batch.py` | Semi-auto draft + Telegram-approve flow |
| `scripts/send_gateway.py status` | View gateway gate state |

All accept `--json` for machine-readable output. All accept `--dry-run` to validate without sending.

---

## Why this exists (incident history)

- **2026-04-20** outbound chokepoint was finalized (V5.6). All sends MUST route through `send_gateway.send()`.
- **2026-04-25** sanitizer added — 9 emails went out as "Hi Contact" because of bad CSV imports.
- **2026-04-27** Gate 1b (HTML required) added — opencode shipped 10 plain-text-only OASIS sends with no booking link, no website link, looked like spam. Same day: CASL footer trimmed (no more "reply STOP" line), draft critic loosened (ship threshold 7.5→6.5, "wanted to reach out" un-flagged), hourly cap raised 10→30.
- **2026-04-27** geo-rapport added — every email now references the lead's region ("the Collingwood area" / "the Toronto area" / etc.), auto-inferred from lead data so the AI caller doesn't have to think about it.

---

## Cross-AI consistency

This skill is referenced from:
- `CLAUDE.md` (Claude Code)
- `AGENTS.md` (OpenCode, Codex CLI, Cursor, Windsurf)
- `GEMINI.md` (Gemini CLI)
- `ANTIGRAVITY.md` (Antigravity IDE)

Whichever entry point an AI uses to enter this repo, this is the canonical outreach workflow. Don't reinvent.

## Obsidian Links
- [[brain/QUICK_REFERENCE]] | [[brain/CAPABILITIES]]
- [[memory/feedback_outreach_send_template]]
- [[skills/email-safety/SKILL]]
