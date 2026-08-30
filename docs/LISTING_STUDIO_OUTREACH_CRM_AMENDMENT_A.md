---
tags: [docs, vps, listing-studio, mandy-management, runbook, crm, sms]
last_updated: 2026-08-24
---

# Listing Studio — Amendment A: mass text, Sheet import, push channel (2026-08-24)

> **Paste this into the ALREADY-RUNNING VPS session** (the one that just posted its
> Phase 0 findings and started Mission 6). Do NOT start a new session — this amends
> `docs/LISTING_STUDIO_OUTREACH_CRM_SYSTEM_MESSAGE.md` in flight.
> Adds Mission 10 (bulk import + broadcast), fixes the auto-text gate that would have
> excluded every hand-entered lead, and resolves the push-channel decision.

---

```text
AMENDMENT A to the Outreach CRM brief. Your Phase 0 report is accepted in full —
all six code-over-brief corrections stand (no compat views; dormant_at as the dormancy
mechanism; reuse sms_stopped_at instead of a new opted_out; idx_leads_phone_unique
already exists; message_sent / message_received + channel='sms_manual' instead of new
lead_events.kind values, since the CHECK is locked and you correctly refused to
improvise a table rebuild; near-empty leads table). Keep going on Mission 6 with those
corrections. Six changes and one addition follow.

── CORRECTION 1: ROUTE PATH (verified live from outside) ──────────────────────────
The brief said /dashboard/leads. That path 404s. The real surface is the TOP-LEVEL
route /leads (307 → auth). /pipeline and /inbox are likewise top-level. Everything the
brief assigns to "the leads page" goes on /leads. Do not create a /dashboard/* route.

── CORRECTION 2: THE AUTO-TEXT GATE EXCLUDES THE ENTIRE FEATURE ───────────────────
You surfaced the SMS worker's live gate:
  sms_opt_in=1 AND sms_stopped_at IS NULL AND dormant_at IS NULL
  AND status IN ('new','contacted','viewing_scheduled') AND phone IS NOT NULL
  AND listing_id IS NOT NULL AND sms_touch_count < 6
  AND datetime(last_sms_at) <= datetime('now','-2 days')
`listing_id IS NOT NULL` means a hand-entered lead can never auto-text. That is the
whole point of this brief — the client is entering people he texted, most of whom have
no listing attached yet. This is a REQUIRED fix, not an option:
  - Drop `listing_id IS NOT NULL` from the gate.
  - Where listing_id IS NULL, render the generic no-listing template the brief already
    specifies. Never interpolate a missing listing, never skip the lead.
  - `datetime(last_sms_at) <= ...` with last_sms_at NULL evaluates NULL → the row is
    silently excluded. A never-texted lead must be immediately eligible: wrap it
    (COALESCE(last_sms_at,'1970-01-01') or an explicit `last_sms_at IS NULL OR ...`).
    Check the same NULL trap on sms_touch_count.
  - Add a test per clause proving a hand-entered, listing-less, never-texted lead with
    consent is ELIGIBLE, and that each suppression clause still excludes correctly.
  - Also apply your ISO-vs-datetime() finding here: you confirmed lib/leads/create.ts
    writes JS toISOString() into consent_at / sms_consent_at while the convention is
    'YYYY-MM-DD HH:MM:SS'. Wrap both sides in datetime() everywhere (you already
    committed to this) AND normalise the existing ISO values in your migration so the
    stored data matches the convention going forward.

── CORRECTION 3: PUSH CHANNEL — DECIDED, AND IT COSTS NOTHING ─────────────────────
You reported ladder rung (c): no channel reaches the client. Two facts change that:
  1. The app's Settings page ALREADY has a "Telegram chat id" field, populated with
     8627602216 — the client (Joe, owner) already receives listing approvals there.
     He uses Telegram. The destination exists.
  2. A Telegram bot token is FREE and takes two minutes (@BotFather → /newbot). CC is
     creating a dedicated Mandy Management bot and will hand you
     TELEGRAM_BOT_TOKEN_MANDY. A private chat id is the USER's id and is identical
     across bots, so 8627602216 stays valid — the only requirement is that Joe presses
     Start on the new bot once (CC will walk him through it).
So: build the digest against TELEGRAM_BOT_TOKEN_MANDY + the Settings chat id, keep it
fail-closed until the token lands, and DO NOT fall back to the generic
TELEGRAM_BOT_TOKEN. Read the chat id from the Brokerage settings record, not a new env
var, so the client can change it himself.
SEPARATE FINDING YOU RAISED — treat as a real defect, report it, do not fix it
uninvited: the client's existing APPROVAL gate routes Mandy client data through
@Sexyrapeezra_bot, the SunBiz/Ezra empire bot. That is cross-tenant leakage of a
client's data through another tenant's bot. Once the Mandy bot exists, repointing the
approval gate to it is a one-line env change — propose it to CC with the diff and get
a yes before touching it.

── CORRECTION 4: CONSENT SOURCE OF TRUTH ──────────────────────────────────────────
The live /enquire form posts smsOptIn, and the worker gates on sms_opt_in=1. So the
quick-add consent control must SET sms_opt_in=1 for the 'manual_inquiry' basis and
leave it 0 for 'manual_cold'. Cold contacts stay reminder-mode-only forever. Do not
invent a parallel consent flag the worker doesn't read.

── CORRECTION 5: EVENT VOCABULARY ─────────────────────────────────────────────────
Your message_sent / message_received + channel discriminator design is correct and
supersedes the brief's invented kinds. Extend it: channel='sms_manual' (he texted from
his own phone), 'sms_auto' (the follow-up worker), 'sms_broadcast' (Mission 10 below).
For lead_reactivated, use whatever the 0012 vocabulary already has for a status change
and put the detail in the payload — do not add a kind.

── CORRECTION 6: TEST DATA ────────────────────────────────────────────────────────
The leads table holds one row — an 08-19 Instagram self-test named "You", no phone, no
listing. Delete it as part of your migration (it is a self-test artifact, not client
data) so the client's first view of his CRM is empty and honest rather than showing a
fake person named "You". Note the deletion in your report.

═══════════════════════════════════════════════════════════════════════════════
MISSION 10 — BULK IMPORT + BROADCAST ("mass text")
═══════════════════════════════════════════════════════════════════════════════
New client requirement (2026-08-24): "we need something like mass text — a seamless
process where you can upload a Google Sheet or put them in one by one." Mission 6's
paste box is the one-by-one/paste path; this is the file path and the send path.

10A — SHEET / CSV IMPORT
  - On /leads, next to quick-add: "Import from spreadsheet". Accepts .csv and .xlsx
    (Google Sheets exports as either; also accept a pasted TSV block, which is what a
    copy out of Sheets actually produces).
  - COLUMN MAPPING UI: read the header row, show a mapping dropdown per column
    (name / phone / email / note / listing / skip) with a sensible auto-guess. Never
    assume column order — his sheet will not match your fixture.
  - Every row runs through the SAME validate → normalize → dedupe path as Mission 6.
    One import path, one code path; a second parallel path is how bad numbers and
    duplicates get in.
  - Preview-before-commit: show "42 ready · 3 duplicates (will open existing) ·
    2 rejected (bad phone)" with the rejected rows inline and editable, THEN a
    single Import button. Never write rows before he has seen this screen.
  - Batch-level consent choice + "last texted" quick-pick + the post-import triage
    screen, exactly as Mission 6 specifies. Jitter next_follow_up_at across 24–72h.
  - Cap a single import at a sane row count (e.g. 2000) and stream/chunk the writes;
    do not build a request that times out on a big paste.

10B — BROADCAST SEND (the "mass text")
  Surface: on /leads, multi-select (or "select all in this filter") → "Text selected".
  No new top-level nav tab yet; sent campaigns get a history panel on /leads.
  The composer:
  - Audience: the current filter/selection, with a LIVE eligibility breakdown shown
    before sending — "38 selected · 31 will send · 4 no consent · 2 opted out ·
    1 no phone" — each exclusion class clickable to see who and why. He must never
    wonder why a number didn't get it.
  - Message body with {{first_name}} and {{listing}} tokens; {{listing}} on a
    listing-less lead falls back to the generic phrasing, never to blank or 'undefined'.
    Live preview rendered against three real selected recipients.
  - HARD GATES, enforced server-side, not in the UI:
      sms_opt_in=1 AND sms_stopped_at IS NULL AND dormant_at IS NULL AND phone
      IS NOT NULL AND consent basis is not 'manual_cold'. Quiet hours 9am–8pm
      America/New_York. Daily cap shared with the follow-up worker's cap — a broadcast
      must not blow the day's budget and starve the drip.
  - First message to any given recipient carries sender identity + opt-out:
    "— Joe, Mandy Management. Reply STOP to opt out." STOP handling reuses the existing
    inbound webhook and sets sms_stopped_at.
  - THROTTLED QUEUE, not a for-loop: persist the campaign and its per-recipient rows
    first, then send at a conservative rate (≈1/sec) from the worker, resumable if the
    process restarts. A half-sent campaign must be able to finish, and must never
    double-send — key each recipient row idempotently.
  - "Send test to me" is MANDATORY before the real send button enables: fires the fully
    rendered message to the operator's own number.
  - Kill switch: pause / cancel a running campaign; already-sent rows stay logged.
  - Per-recipient outcome written to the lead timeline (message_sent,
    channel='sms_broadcast', provider SID + status), so replies thread onto the right
    lead and set hold_state='waiting_on_us' via the Mission 7 rule.
  - A broadcast send counts toward sms_touch_count and reschedules next_follow_up_at,
    so the drip worker doesn't text the same person hours later.

10C — ARMING (unchanged, and it applies to broadcast too)
  All of Mission 10B is built behind the same fail-closed cage: no Twilio creds → the
  composer renders, the eligibility maths runs, "send test" and "send" are disabled with
  an explicit "no SMS number connected yet" state. Never a silent no-op. When creds
  land: pm2 restart <worker> --update-env && pm2 save → dry-run to CC → CC's go →
  first-day cap 10.

PROOF FOR MISSION 10: import a 10-row spreadsheet with a shuffled header order, one
duplicate, one bad phone, one comma-laden note → preview screen screenshot → import →
triage → build a broadcast to the imported cohort → eligibility breakdown screenshot
showing a cold-consent lead excluded and an opted-out lead excluded → "send test"
disabled-state screenshot (no creds) → unit tests for eligibility, throttle,
idempotency, and resume-after-restart. All rows ZZTEST, deleted at close-out.

REPORT BACK: as before, plus explicitly — is the client's leads surface reachable by
his own login on a phone, and what exactly is still CC-gated.
```

## Notes for CC

- **Where it lives:** the `/leads` tab. Pipeline is the stage board, Inbox is
  conversations — neither is the right home for a contact roster and a worklist.
- **Your one free unblock today:** create a Mandy Telegram bot in @BotFather (`/newbot`,
  two minutes, no billing), send me the token, and have Joe press Start on it once. That
  turns on the 9 AM "who's waiting on you" digest with zero spend. His chat id
  (8627602216) is already in the app's Settings.
- **Cross-tenant finding:** Joe's listing approvals currently route through
  `@Sexyrapeezra_bot` — the SunBiz/Ezra empire bot. Client data on another tenant's bot.
  The new Mandy bot fixes it with a one-line env change; the agent will propose the diff
  rather than doing it uninvited.
- **The number (for real mass texting):** US application-to-person SMS requires carrier
  registration (10DLC) before traffic flows reliably — unregistered sends get filtered.
  Two routes, both needing Mandy Management's business details (we already have the
  address, site and email from Settings) plus their EIN from Joe:
  1. **Add SMS to the existing (203) 773-9710** via hosted SMS — texts come from the
     number renters already recognise, voice stays with their current carrier.
     Best-looking option; confirm the provider supports hosting that specific number.
  2. **New local CT number** — instant to buy, still needs 10DLC registration.
  Either way it's ~a few days of registration, so getting the EIN from Joe is the long
  pole. Everything else ships and waits behind the cage.

## Obsidian Links
- [[docs/LISTING_STUDIO_OUTREACH_CRM_SYSTEM_MESSAGE]] (the brief this amends)
- [[docs/LISTING_STUDIO_VPS_AGENT_SYSTEM_MESSAGE]] | [[brain/APP_REGISTRY]]
