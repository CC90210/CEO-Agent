# SunBiz Client Deployment Runbook

**Audience:** OASIS operator deploying a new SunBiz Funding tenant.
**Estimated time:** 45–60 minutes wall-clock; 25 minutes hands-on.
**Phases:** Pre-flight → Bootstrap → Personalize → Integrations → Handoff.

Run these phases in order. Each phase has a verification step — don't move on until the previous phase verifies green.

---

## Pre-flight (5 minutes)

Before you touch the client's machine, confirm the empire side is ready.

### Checklist
- [ ] The tenant exists in `tenants` table with `brand = "Sun Biz Funding"`.
- [ ] An `auth.users` row exists for the client's primary email.
- [ ] A `user_profiles` row links that auth_user_id to the tenant.
- [ ] `tenants.custom_fields.command_center_profile_slug` is unset OR equal to `"sun"` (the wizard's `applyClientProvisioningProfile` call fixes this if needed).
- [ ] You have the client's Mac Mini physical access (USB-C, Bluetooth keyboard, monitor) OR a Screen Sharing session approved by them.

### Verify
```bash
python scripts/supabase_tool.py select tenants \
  --eq '{"brand": "Sun Biz Funding"}' \
  --json | grep -E "id|brand|custom_fields"
```
Expected: one row, brand matches, custom_fields is either `{}` or contains the slug.

---

## Bootstrap (10 minutes)

Stand up the agent on the client's machine.

### Commands (run on the Mac Mini)
```bash
# 1. Install. The one-liner clones to ~/.bravo and adds the bravo shim to PATH.
curl -fsSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.sh | bash

# 2. Launch the wizard with the SunBiz profile preselected.
bravo setup --profile=sunbiz
```

### What to expect
The wizard walks through ~15 steps. Key ones for SunBiz:

| Step | What it asks | What to answer |
|---|---|---|
| Profile | Already pinned to `sunbiz` via `--profile`. | (skipped) |
| Identity | Operator's full name + email. | Their actual name + business email. |
| Business context | Brand + tagline. | "Sun Biz Funding" + their internal tagline. |
| AI keys | Anthropic / OpenAI. | OASIS can supply on shared tier; client supplies on dedicated. |
| Telegram (optional) | Skip unless they want chat-mode. | Usually skip in week one. |
| Stripe (server-side) | Stripe secret key. | From their Stripe dashboard → API keys → Restricted, scoped to read-only. |
| Twilio | Account SID + auth token + sender number. | Their existing Twilio account or one we provisioned for them. |
| n8n | URL + API key. | Skip if they don't run n8n; not required for V1. |
| Browser harness | y/n. | y for desktop installs (lets the agent control their browser for sponsor lookups, etc). |
| **Data sovereignty** | Local libSQL or Cloud Supabase. | **Local.** This is non-negotiable for funding ops (see customer script). |
| Dashboard pairing | Paste 9-char code from browser. | (See Personalize step below.) |

### Verify
```bash
bravo doctor
```
Exit code 0 + verdict `HEALTHY`. If `DEGRADED`, the doctor output names the missing piece — fix and re-run.

---

## Personalize (15 minutes)

This is the longest phase. Replace OASIS demo data with the client's real data.

### Bridge token + dashboard pairing
The wizard's "Dashboard pairing" step auto-opens the client's browser to `/settings/devices`. Click "Install Claude Code CLI bridge" → copy the 9-char code → paste into terminal. The wizard exchanges it via `/api/auth/pair-code/redeem` and saves `BRIDGE_PAIRING_TOKEN` to `.env.agents` + `~/.oasis/bridge_token`.

### Brand assets
- Logo: Place their company logo at `apps/command-center/public/sunbiz/<client-slug>-logo.png`. The dashboard reads this if present, otherwise falls back to the gold sun.
- Colors: SunBiz tenants get the existing amber palette by default. If the client wants a custom accent, edit `lib/client-profiles.ts:SUN_PROFILE.colorRgb` and rebuild (next session — too risky in the live deployment).

### Demo data → real data
Three sub-tasks:

1. **Leads import.** Their existing CRM export (JotForm / Excel / HubSpot) goes into `/import` page. The agent dedupes against existing leads on email/phone.
2. **Lenders.** Walk through `/lenders` page with them. Add their lender contacts (name, email, fee structure). Solara uses this to route applications.
3. **Templates.** Their existing SMS scripts and email templates go in `/templates`. The agent reads from this set when drafting follow-ups.

### Verify
```bash
# Confirm tenant_id-scoped data exists.
python scripts/supabase_tool.py select leads \
  --eq '{"tenant_id": "<their-tenant-id>"}' \
  --limit 5
```
Should return ≥1 row after import.

---

## Integrations (15 minutes)

Wire the third-party services that close the loop.

### Twilio (SMS)
- Buy or transfer a number into their Twilio account.
- Verify the number is A2P 10DLC registered (US clients) — un-registered numbers get throttled.
- Test send: from `/sms` page, type their cell number, send "Solara test ping — reply Y if received." Confirm verbally that the SMS arrives.

### Stripe (commissions)
- Their Stripe account links to commissions tracking. Webhook URL: `<dashboard>/api/stripe/webhook`.
- Add the webhook signing secret to `.env.agents` as `STRIPE_WEBHOOK_SECRET`.

### n8n workflows (optional, defer to week two)
If the client uses n8n for lead enrichment or lender callbacks, import the SunBiz starter workflows from `scripts/n8n_workflows/sunbiz/*.json` via the n8n MCP. Skip if they're not on n8n.

### JotForm (lead ingestion)
Their existing JotForm webhook URL needs to point to `<dashboard>/api/inbound/lead`. The HMAC secret is in their `n8n_webhook_secrets` row — give them the value to paste into JotForm's webhook config.

### Verify
- Send a test SMS from `/sms`. Confirm delivery on the client's phone.
- POST a fake lead to the JotForm endpoint. Confirm it appears in `/leads` within 10 seconds.

---

## Handoff (10 minutes)

Transfer ownership. From this point the client operates day-to-day.

### Verbal handoff (use the [customer onboarding script](/playbook/05-customer-onboarding-script) sections 5–7).

### What you leave them with
- Direct phone number to text for emergencies.
- Link to this runbook for self-service questions.
- A Day-7 check-in on your calendar.

### What you take with you
- Updated call notes in your CRM with their data-sovereignty choice + SMS consent attestation timestamped.
- A new quest in your `memory/ACTIVE_TASKS.md` for the Day-7 review.
- A first-pass eval: how long did each phase take vs. estimate? If you ran over by >30%, identify which phase is the blocker and add it to your [retrospective notes](/retro).

### Verify (final gate before you leave)
```bash
# 1. Heartbeat green
python scripts/agent_heartbeat.py --agent sunbiz --health healthy

# 2. Dashboard loads with SunBiz branding when they hit /
# (Visual check — should see "Sun Biz Funding · Operations Command" header)

# 3. /agent tab shows Solara with their primary_agent="sunbiz"

# 4. Their /team page shows them as owner with is_owner=true.
```

All four green → walk away. The agent is now live.

---

## Failure modes (read before you hit them)

| Symptom | Cause | Fix |
|---|---|---|
| `bravo doctor` says "no BRAVO_SUPABASE_URL" | Wizard skipped the credential prompt | Re-run wizard from the Supabase step: `bravo setup --resume` |
| Dashboard shows "OASIS AI" header instead of "Sun Biz Funding" | `applyClientProvisioningProfile` didn't fire (brand was empty during pair) | Manually update: `python scripts/supabase_tool.py update tenants '{"custom_fields": {"command_center_profile_slug": "sun"}}' --match '{"id": "<tenant-id>"}'` |
| Pair code "expired" | TTL is 15 minutes; client took too long | Generate a fresh code from `/settings/devices` |
| Solara chat returns "I don't have data on this tenant" | `agents_enabled` doesn't include `"sunbiz"` | Update via `/api/auth/pair` re-run or directly: `python scripts/supabase_tool.py update user_profiles '{"primary_agent": "sunbiz", "agents_enabled": ["sunbiz"]}' --match '{"tenant_id": "<id>"}'` |
| Turso reads return null silently | libSQL schema not bootstrapped | Run `bravo db init --backend=turso` (when shipped) OR manually replay migrations 001-037 against the libSQL file |

If you hit a failure not in this table, log it as a quest in `memory/ACTIVE_TASKS.md` for Bravo to add to the table.
