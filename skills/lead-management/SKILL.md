---
name: lead-management
description: Manage OASIS AI leads through the full sales pipeline using lead_engine.py. Covers adding, scoring, updating, follow-up cadence, and pipeline reporting — all backed by Supabase, zero paid CRM.
triggers: [lead, pipeline, follow-up, CRM, prospect, outreach, qualified, proposal]
tier: standard
dependencies: [email-marketing, booking-management]
---

# Lead Management — OASIS AI CRM

## Overview

Every OASIS AI prospect lives in the Supabase `leads` table and is managed through `lead_engine.py`. No HubSpot, no ManyChat — owned infrastructure. The pipeline runs from first contact through closed-won. This skill covers every operation in that lifecycle.

---

## Tool Routing

All operations go through `python scripts/lead_engine.py`. Append `--json` to any command for machine-readable output.

| Operation | Command |
|-----------|---------|
| View pipeline summary | `lead_engine.py pipeline` |
| List leads by status | `lead_engine.py list --status qualified --limit 20` |
| Add a new lead | `lead_engine.py add "Name" --email x@y.com --company "Acme" --source cold_outreach` |
| View a lead | `lead_engine.py view <lead_id>` |
| Update status/score | `lead_engine.py update <lead_id> --status proposal --notes "Sent deck"` |
| Recalculate score | `lead_engine.py score <lead_id>` |
| Log an interaction | `lead_engine.py interact <lead_id> --type email_sent --channel email --subject "Follow-up"` |
| Get follow-up list | `lead_engine.py followups` |
| Search leads | `lead_engine.py search "HVAC"` |
| Assign to funnel | `lead_engine.py funnel <lead_id> <funnel_slug> --stage consideration` |

---

## Pipeline Stages

Move leads forward deliberately. Every stage transition gets logged via `update`.

| Stage | What It Means | Next Action |
|-------|--------------|-------------|
| `new` | Just added, no contact yet | Send Day 0 intro email |
| `contacted` | First message sent | Wait for reply; Day 3 value-add if silent |
| `qualified` | Confirmed budget + need + authority | Book a discovery call |
| `proposal` | Proposal or pricing sent | Follow up in 48 hours |
| `negotiating` | Active back-and-forth on terms | Close within the week |
| `won` | Client signed and paying | Onboard, log in revenue_engine |
| `lost` | Dead end | Log reason, add to re-engage list for 60 days |

---

## Lead Scoring Criteria

Scores are auto-calculated by `lead_engine.py score <lead_id>`. Understand the weights to know which leads to prioritize.

| Signal | Points |
|--------|--------|
| Email on file | +10 |
| Phone on file | +10 |
| Company on file | +5 |
| Each logged interaction | +5 (base), capped at +30 total |
| `email_opened` interaction | +10 |
| `email_clicked` interaction | +15 |
| `meeting` interaction | +20 |
| `dm_reply` interaction | +15 |
| Active in last 7 days | Recency bonus applied |

Scores 70+ = hot lead. Prioritize for calls. Scores below 30 after 14 days = candidate for `lost` or re-engage sequence.

---

## Outreach Cadence

Run `lead_engine.py followups` daily to see who is due. The cadence below is the default for cold-sourced OASIS leads.

| Day | Action | Tool |
|-----|--------|------|
| 0 | Intro email — CC's voice, lead with their problem | `email_engine.py send-template` |
| 3 | Value-add — share a relevant result or insight, no ask | `email_engine.py send-template` |
| 7 | CTA — offer a specific 20-min discovery call | `booking_engine.py available` + `email_engine.py send` |
| 14 | Re-engage — brief, direct, "still open to a quick chat?" | `email_engine.py send` |
| 21+ | Move to `lost` or add to long-term nurture sequence | `lead_engine.py update --status lost` |

After every send, log the interaction: `lead_engine.py interact <lead_id> --type email_sent --channel email --subject "..."`.

---

## Integration Points

- **email_engine.py** — send sequences, templates, and one-off messages tied to a `--lead-id`
- **booking_engine.py** — when a lead hits `qualified`, open a slot and send the booking link
- **revenue_engine.py** — when a lead hits `won`, log revenue manually: `revenue_engine.py log-revenue`
- **Supabase** — raw queries via `supabase_tool.py select leads --project bravo` if bulk reporting is needed

---

## Rules

- Never move a lead to `proposal` without a confirmed need — waste of a deck.
- Log every touchpoint as an interaction. Unlogged touches mean inaccurate scores and missed follow-ups.
- `followups` surfaces leads based on last interaction date. Run it every morning during outreach blocks.
- `lost` is not permanent. Re-engage at 60 days with a fresh angle if the business is still relevant.

## Obsidian Links
- [[skills/INDEX]] | [[brain/CAPABILITIES]]
