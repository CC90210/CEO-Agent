---
name: email-marketing
description: Send individual emails, run nurture sequences, and manage templates using email_engine.py and free Gmail SMTP. Zero paid ESP. All sends tracked in Supabase.
triggers: [email, nurture, sequence, campaign, gmail, smtp, template, drip]
tier: standard
dependencies: [lead-management]
---

# Email Marketing — Gmail SMTP + Supabase

## Overview

`email_engine.py` replaces Mailchimp, ConvertKit, and every other ESP CC doesn't need to pay for. Gmail SMTP handles delivery (500 emails/day — enough for OASIS at current scale). Supabase tracks every send, open, and failure. All templates live in the database, parameterized with `{{variable}}` syntax.

---

## Tool Routing

All operations go through `python scripts/email_engine.py`. Append `--json` to any command for machine-readable output.

| Operation | Command |
|-----------|---------|
| Send a plain email | `email_engine.py send --to email --subject "..." --body "..."` |
| Send with HTML + lead tracking | `email_engine.py send --to email --subject "..." --body "..." --html "<p>...</p>" --lead-id uuid` |
| Send a saved template | `email_engine.py send-template --template-id uuid --to email --vars '{"first_name":"John"}'` |
| List templates | `email_engine.py templates list` |
| Create a template | `email_engine.py templates create --name "..." --subject "..." --body-html "..." --category welcome --vars '["first_name"]'` |
| View a template | `email_engine.py templates view <template_id>` |
| List sequences | `email_engine.py sequence list` |
| Create a sequence | `email_engine.py sequence create --name "..." --trigger lead_created --steps '[...]'` |
| Run a sequence for a lead | `email_engine.py sequence run <sequence_id> --lead-id <lead_id>` |
| View send log | `email_engine.py log --status sent --limit 20` |
| Stats overview | `email_engine.py stats` |

---

## Template Design Principles

Templates that get replies are short, personal, and look hand-typed. The moment an email looks like a campaign, it gets ignored.

- **Subject lines:** Statement or question, under 8 words. No "RE:" tricks.
- **Opening line:** Reference something specific to their business or industry. Not "I hope this finds you well."
- **Body:** 3-5 sentences max. One idea per email.
- **CTA:** Single, specific ask. Not "let me know your thoughts."
- **No images, no logos, no unsubscribe footer** for cold outreach. Those are for newsletters.

Template variables use `{{double_braces}}`. Example: `{{first_name}}`, `{{company}}`, `{{pain_point}}`.

---

## CC's Voice in Email

Direct quotes from how CC writes. Use these as the reference tone.

- Talks like he's texting a founder he respects, not pitching at a conference
- Leads with the problem, never the product: "Most HVAC owners are manually dispatching jobs 6 hours a week..."
- Doesn't hedge: "I think maybe this could help" is dead on arrival. "This saves 6 hours a week" is not.
- Closes with one clear next step, never multiple options
- Signs as "Conaugh" for OASIS B2B outreach — not "CC"

---

## Nurture Sequence Structure

The default 3-email sequence structure for OASIS AI cold leads.

**Step 1 — Welcome / Intro (delay: 0 hours)**
- Trigger: `lead_created`
- Goal: establish credibility, name the problem they have
- Template category: `welcome`

**Step 2 — Value-Add (delay: 72 hours)**
- Goal: give something useful before asking for anything
- A result from a client, a stat, a 2-minute insight
- Template category: `nurture`

**Step 3 — CTA (delay: 168 hours / 7 days)**
- Goal: one ask — 20-min discovery call
- Include a direct booking link from `booking_engine.py available`
- Template category: `cta`

To build this as a sequence in the DB:
```
email_engine.py sequence create \
  --name "OASIS Cold Lead 3-Touch" \
  --trigger lead_created \
  --steps '[
    {"delay_hours": 0,   "template_name": "OASIS Welcome"},
    {"delay_hours": 72,  "template_name": "OASIS Value-Add"},
    {"delay_hours": 168, "template_name": "OASIS Discovery CTA"}
  ]'
```

Then enroll a lead: `email_engine.py sequence run <sequence_id> --lead-id <lead_id>`

---

## Send Limits and Hygiene

- **Gmail SMTP limit:** 500 emails/day. At OASIS scale (10-50 active leads), this is never a constraint.
- **Required in `.env.agents`:** `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` (Google App Password, not your account password).
- **Failed sends** are logged with `status=failed` — check `email_engine.py log --status failed` weekly.
- **Do not** send the same lead the same template twice. Check `email_engine.py log` before manual sends.

---

## Integration Points

- **lead_engine.py** — pass `--lead-id` on every send to link the email to the lead record and update interaction history
- **booking_engine.py** — pull `available` slot link to embed in CTA emails
- **revenue_engine.py** — no direct link, but won leads from email sequences should be logged there manually

## Obsidian Links
- [[skills/INDEX]] | [[brain/CAPABILITIES]]
