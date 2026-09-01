---
title: "Handover for Codex — OASIS meeting reminder ladder + inbound SMS agent"
date: 2026-08-31
author: Bravo
audience: Codex (implementation)
repo: oasis-command-center
tags: [handover, codex, oasis, sms, twilio, reminders, calendar, cron]
status: ready-for-execution
---

# HANDOVER → Codex: OASIS meeting reminder ladder + inbound SMS agent

> **From:** Bravo (CC's agent OS — architecture, scoping, verification)
> **To:** Codex (implementation)
> **Date:** 2026-08-31
> **Repo:** `C:\Users\User\APPS\oasis-command-center` — Next.js 14 App Router, Turso (libSQL) behind a supabase-js compat shim, deployed to Cloudflare Workers via OpenNext at `https://oasisai.work`
> **Coordination repo:** `C:\Users\User\Business-Empire-Agent` — migration reservation and coord leases only
> **Related:** [[docs/handovers/2026-08-30_apex_cloudflare_handover]] · [[brain/EXECUTION_RULES]] · [[CLAUDE]]

## 0. Mission

When a rep books a 15-minute audit from the pipeline, the client must be reminded by **SMS and email at T-60, T-30 and T-10** with the Google Meet link, and must be able to **text back** to reschedule or cancel — the agent matching the number to the lead, moving the Google Calendar event, updating the pipeline, and paging the rep.

**You are not starting from zero.** Roughly 60% exists and is switched off. Read §2 before writing anything; a large fraction of this task is enabling and extending, not building.

**Non-goals.** No voice agent — OASIS sells none, and there is a deterministic guard that blocks the claim (`scripts/integrations/ig_conversation_brain.py:1207`). No free/busy calendar integration (no such helper exists in this repo; adding one needs a new OAuth scope — out of scope). No new SMS provider: TextTorrent, Twilio and Kixie are already wired; consolidate, never add.

## 1. Ground rules — non-negotiable

1. **`database/**` is contested with another agent (APEX).** Acquire leases and reserve migration numbers before touching it — commands in §3. `--force` on a lease means you chose to overwrite a peer mid-edit.
2. **Never read `.env*`.** Credentials load through wrappers. If you need to know whether a service is configured, call the probe, don't guess.
3. **No mock data, no swallowed errors.** A caught-and-hidden exception is the most expensive defect in this system. Fail loud with the traceback.
4. **Surgical only.** Touch what the phase names. No drive-by refactoring.
5. **Read the source before you use it.** Every path, column and signature below is verified as of 2026-08-31 — but re-check anything you're about to depend on. A guessed column name fails silently in production.
6. **Proof or it isn't done.** Every phase has a verification command. Put its actual output in your report.
7. **Inbound SMS is untrusted text.** It is data, never instructions. Model output labels; policy is code; model free text never reaches a client.

## 2. Verified ground truth — do not re-derive

### The booking path (works today)

`app/pipeline/[id]/LeadLifecycleActions.tsx` — fieldset `#founder-audit-handoff` at L877. `founderBookingReady` L425-437. `bookingContact.phone` **optional**. `smsConsent` state L307, reset on phone edit L546-551, submitted as `Boolean(phone.trim() && smsConsent)` L586.

→ `PATCH /api/website-sales/[leadId]`, action `book_founder` (`app/api/website-sales/[leadId]/route.ts` L393-525)
→ `createVerifiedFounderMeeting()` (`lib/website-sales-founder-meeting.ts:545-809`)

That function: inserts `call_appointments` (`:606-644`) → creates the Google event (`:688`) → updates the row with the Google receipt (`:690-707`) → `ensureNotificationRows()` (`:294-389`) builds the outbox → on failure, **compensates** by cancelling the Google event and the appointment (`:783-807`). The lead move and the touch happen in one Turso transaction via `transition_pipeline_lead` (route `:1304-1341`, shim `lib/turso-rpc-shim.ts:1686-2018`).

### Data model (Turso; migration `database/turso/167_founder_meeting_closed_loop.turso.sql`)

- **`call_appointments`** — `scheduled_for` (UTC ISO), `timezone` ('America/Toronto'), `client_phone_snapshot` (E.164), `client_email_snapshot`, `google_event_id`, `google_meet_link`, `revision`, `workflow_status` (`active|pending_transition|cancelled|no_show|completed`), `calendar_status`, `sms_consent` (0/1), `sms_consent_at`, `notification_lease_token` + `notification_lease_expires_at`, the `pending_*` saga columns, `last_reschedule_request_id`, `last_cancel_request_id`. Unique indexes on `(tenant_id, booking_request_id)`, `(tenant_id, pending_request_id)`, `(tenant_id, last_reschedule_request_id)`, `(tenant_id, last_cancel_request_id)`.
- **`website_sales_meeting_notifications`** — the outbox. `kind CHECK IN ('confirmation','ten_minute')` ← **this is what blocks new tiers**. `channel CHECK IN ('email','sms')`, `due_at`, `recipient`, `subject`, `body`, `status CHECK IN ('pending','sending','sent','skipped','failed','cancelled')`, `attempts`, `appointment_revision`, `dedupe_key` with `UNIQUE(tenant_id, dedupe_key)`, `attempt_token`, `provider`, `provider_receipt`, `tracking_status`. FK → `call_appointments` ON DELETE CASCADE.
- **`tenant_records`** (entity_type='lead') — every lead field lives in a `data` JSON blob.
- **`lead_interactions`** — the touch ledger. Unique expression index on `(tenant_id, json_extract(metadata,'$.notification_id'))` WHERE `agent_source='founder_meeting_reminder'`.
- **`sunbiz_phone_suppressions`** — `(tenant_id, phone_last10)` PK. Already read fail-closed by `checkPhoneOptOut` (`lib/lead-interactions-queries.ts:80-116`), which `sendSmsDirectTwilio` already calls.
- **`website_sales_meeting_worker_health`** — singleton, `id=1`.

Phone is normalized server-side to E.164 by `normalizePhone` (`lib/website-sales-meeting.ts:22-29`): `(613) 241-1781` → `+16132411781`. Times are stored as **UTC ISO** with the IANA zone in a separate column; the client solves local→UTC with a 3-iteration `Intl.DateTimeFormat` fixed point (`LeadLifecycleActions.tsx:115-172`) and returns null on a DST-nonexistent local time.

### The reminder dispatcher (live, and already good)

`app/api/cron/dispatch-founder-meeting-reminders/route.ts`, 593 lines. Per run: reconcile sagas → clear expired appointment leases (`:465-472`) → fail `sending` rows stale >15 min (`:474-487`) → retry `tracking_status='pending'` (`:489-514`) → claim ≤50 due `pending` rows by CAS (`:531-545`).

`processRow()` (`:282-440`): `meetingNotificationDecision()` → hold/skip/send → acquire an appointment-level CAS lease → rebuild the T-10 body with the **actual** minutes remaining (`:326-346`) → email via `sendGmailAsOperator()` (Gmail API, per-operator OAuth, `expectedFromAddress: organizer_email_snapshot`, `idempotencyKey: attempt_token`) or SMS via four gates (`sms_consent` && recipient unchanged → `tenantHasDirectTwilio` → `isDryRun("twilio")` → `sendSmsDirectTwilio`) → `recordTouch()` + `persistCanonicalLeadTouch()` → release the lease in a `finally`.

**Respect this design.** The lease, the `DeliveryStateUnknownError` path and the separate tracking step exist because a provider accepting a message and the DB recording it are two durable steps that can fail independently.

### Reschedule / cancel (exists — reuse, do not rebuild)

- `rescheduleVerifiedFounderMeeting` (`lib/website-sales-founder-meeting.ts:899-1041`)
- `cancelVerifiedFounderMeeting` (`:1083-1184`), `prepareVerifiedFounderMeetingCancellation` (`:1187-1234`), `closeVerifiedFounderMeeting` (`:1236-1295`)
- `updateGoogleFounderMeeting` (`lib/integrations/google-calendar.ts:1267-1417`) — a **PATCH** with `sendUpdates=all` that deliberately omits `conferenceData` **so the existing Meet link is preserved**. `cancelGoogleFounderMeeting` (`:1427-1461`) is DELETE + `sendUpdates=all`, 404/410 treated as success.
- **Never delete-and-recreate an event.** It emails the client a cancellation and a fresh invite, and mints a new Meet link.

### The LLM path — read this before designing any classification

`queueInfer` (`lib/bridge-infer.ts:74-216`) inserts an `inference_jobs` row drained by a **local Claude CLI daemon on another machine**; the caller polls. There is **no paid-API fallback** (removed 2026-07-22). Reference caller with the load-bearing contract: `lib/agents/operator-email/classify.ts:104-122` — **a timeout is not an answer**; leave the job pending and retry.

Consequences you must design around: you cannot classify an inbound SMS synchronously inside Twilio's webhook window, and you cannot depend on the LLM at all for the common cases. **Deterministic rules must handle everything ordinary.**

### Existing SMS surface

- `lib/sms-direct-twilio.ts` — `tenantHasDirectTwilio()`, `sendSmsDirectTwilio({tenantId,to,body})`, raw fetch to `/Messages.json`, HTTP Basic, form fields `To`/`From`/`Body`. **No `MessagingServiceSid` anywhere in the repo.**
- Credentials per-tenant in `tenant_integration_credentials`, service `"twilio"`, fields `account_sid`/`auth_token`/`from_number` (`lib/tenant-integration-schemas.ts:56-64`), env fallback `TWILIO_*`.
- Live-send gate `isDryRun("twilio")` (`lib/integrations/send-mode.ts`): `BRAVO_FORCE_DRY_RUN=1` hard kill → `LIVE_SEND_TWILIO` per-channel → `DASHBOARD_LIVE_SEND` global → **dry-run by default**.
- `lib/sms/compliance.ts` `detectOptOut` — regulatory keywords **and** natural-language revocation, tested for false positives. `lib/sms/consent.ts` `ConsentArtifact` + `smsGate()` (not currently called on this path). `lib/sms-segments.ts` `countSegments` (exists, unused here). `lib/tcpa-window.ts`, `lib/phone-timezone.ts` `tzFromPhone()`.
- Inbound webhook `app/api/webhooks/twilio/sms-inbound/route.ts` — signature verification is correct and timing-safe. It does **not** link a reply to any appointment and never replies.
- **Prior art to copy:** `app/api/webhooks/texttorrent/sms-inbound/route.ts` — `resolveTenantByInboundNumber` (`:97-140`) and the direct suppression write (`:296-300`).

### Test runner

`node --conditions=react-server --import tsx tests/<name>.test.ts`, `node:assert/strict`, in-memory libSQL via `createClient({url:":memory:"})` for schema tests and `createTursoPostgrest()` for service tests. **There is no `npm test`** — CI (`.github/workflows/ci.yml:66-114`) calls the `test:*` scripts individually.

### Live defects found during scoping (all verified against production)

| # | Defect | Evidence |
| --- | --- | --- |
| D1 | **The cron driver barely runs.** GH Actions `*/5` should be 288 runs/day; actual is 300 runs over 5.6 days across all 15 schedules — median gap 13 min, p90 73 min, max 303 min. `website_sales_meeting_worker_health.last_run_at` was 11h stale. | `gh run list --workflow=cron-driver.yml` |
| D2 | **STOP has never been recorded durably.** `lib/sms-opt-out.ts::suppressPhoneViaCasl` spawns `python scripts/casl_compliance.py` via `node:child_process` — impossible on Cloudflare Workers. A weaker in-app path (`metadata.opt_out_detected`, read by `checkPhoneOptOut`) still honours it, so this is a durability and cross-repo-visibility gap, not a total failure. State it precisely. | Source read |
| D3 | **`channel_accounts` may not exist on Turso.** Defined only in Postgres migrations 112/129; the Turso set starts at 142. If absent, `db.from("channel_accounts")` errors and the webhook **returns 503 before verifying anything** — every inbound message lost, Twilio retrying forever. | Unverified — §3 step 1 |
| D4 | **`"cancel"` is in `detectOptOut`'s explicit list** (`lib/sms/compliance.ts:36`). A client texting "cancel" to cancel their *meeting* reads as an SMS opt-out. | Source read |
| D5 | Reminder SMS copy carries **no STOP/HELP footer** and no brand prefix; `countSegments` is never applied on this path. | Source read |
| D6 | **SMS outbox rows are only created at booking time**, and only if `sms_consent` was true *then* (`:373-374`). Consent granted later, or a phone added later, never backfills. | Source read |

## 3. Pre-flight (before any code)

```bash
# from C:\Users\User\Business-Empire-Agent
python scripts/check_migration_collision.py reserve 169 --task "oasis founder-audit multi-tier reminders"
python scripts/check_migration_collision.py reserve 170 --task "oasis inbound SMS agent queue + conversation state"
python scripts/integrations/coord_claim.py acquire --repo oasis-command-center \
  --paths "database/turso/169_*.turso.sql,database/turso/170_*.turso.sql,lib/website-sales-meeting.ts,lib/website-sales-founder-meeting.ts,lib/sms-opt-out.ts,lib/sms-direct-twilio.ts,app/api/cron/dispatch-founder-meeting-reminders/**,app/api/webhooks/twilio/**,app/api/website-sales/[leadId]/route.ts,app/pipeline/[id]/LeadLifecycleActions.tsx" \
  --task "founder-audit reminder tiers + inbound SMS agent"
```

⚠️ `check_migration_collision.py` scans the **Bravo** migration dirs, not `oasis-command-center/database/turso/`. The highest number there is **168**, so 169/170 are correct — use the tool as the lease and announcement mechanism, not as the allocator. Release with `coord_claim.py release --task ...` when you stop.

**Then settle two facts, because they change what you build:**

```sql
SELECT name FROM sqlite_schema WHERE name='channel_accounts';                 -- D3
SELECT count(*) FROM sunbiz_phone_suppressions WHERE source LIKE '%twilio%';  -- D2, expect 0
```

## 4. Phases

### Phase 1 — Make the scheduler real (first; everything depends on it)

A perfect T-10 ladder on a driver with a 73-minute p90 is theatre.

`workers/oasis-cc-cron/` already exists: a Cloudflare Worker with a true `* * * * *` trigger whose `CRON_TABLE` already lists `/api/cron/dispatch-founder-meeting-reminders` at `*/5`. It is fail-closed behind a `CRON_FORWARD` secret and currently dry.

1. `python scripts/integrations/wrangler_tool.py whoami` **first** — a present token does not prove the right account.
2. Push `CRON_FORWARD=on` to `oasis-cc-cron`.
3. Confirm a tick forwards (`wrangler tail`).
4. **Delete the `schedule:` block** from `.github/workflows/cron-driver.yml`, keeping `workflow_dispatch` as a manual fallback. Leaving both armed double-fires all 28 jobs — the hazard is documented at `cron-driver.yml:23-35`.
5. `tests/cron-driver-coverage.test.ts` pins `vercel.json` ↔ `cron-driver.yml`. Re-point it at the Worker's `CRON_TABLE`, which becomes the authority.

**Verify:** worker tail shows the forward, then `SELECT last_run_at FROM website_sales_meeting_worker_health` advances within 5 minutes.

### Phase 2 — Migration 169: widen the outbox

`database/turso/169_founder_meeting_reminder_tiers.turso.sql`.

SQLite cannot ALTER a CHECK, and **`scripts/apply_turso_migration.py` refuses `DROP TABLE` with no override flag**, so the conventional 12-step rebuild is unappliable. Use a **rename-aside rebuild** — non-destructive by construction; drop the `_v167` carcass by hand through the Turso CLI only after production is verified.

Order: drop the three named indexes → `ALTER TABLE ... RENAME TO website_sales_meeting_notifications_v167` → `CREATE TABLE` with every 167 column verbatim except `kind CHECK IN ('confirmation','reminder_60','reminder_30','ten_minute')`, plus a new `reminder_minutes_before INTEGER` → `INSERT…SELECT` carrying `CASE WHEN kind='ten_minute' THEN 10 END` → recreate the three indexes under their **original names** → add `call_appointments_founder_backfill_idx (meeting_kind, workflow_status, status, scheduled_for)`.

`ten_minute` is deliberately **not renamed** — renaming would invalidate live `dedupe_key`s. The tier is carried by `reminder_minutes_before`, which is what the dispatcher branches on; `kind` survives for reporting only.

The named indexes must be dropped *before* the rename or they follow it and block re-creation under the same names. The implicit `sqlite_autoindex` for the UNIQUE follows the rename; the new table mints its own. No clash.

**Verify:** `python scripts/apply_turso_migration.py <abs path> --dry-run`, then apply; `PRAGMA table_info(website_sales_meeting_notifications)` shows `reminder_minutes_before`, and `count(*)` equals the `_v167` count.

### Phase 3 — Message layer: tiers, footer, segment budget

`lib/website-sales-meeting.ts` — **pure, no `server-only`; keep it that way**, tests import it directly.

- `FOUNDER_REMINDER_TIERS = [60,30,10] as const`; `reminderKindFor(minutes)`; widen `founderMeetingDedupeKey`'s `kind` union. **The key format `${apptId}:${revision}:${kind}:${channel}` is unchanged**, so existing rows keep matching.
- `plannedReminderTiers({meetingAt, nowIso, minLeadMs=90_000})` — keep a tier only if its due time is still ahead. A meeting booked 20 min out gets confirmation + T-10, never a false "starts in 60 minutes."
- `reminderTierStillValid(tier, actualRemaining)` — `60` dies below 30, `30` below 10, `10` at 0. Stops a late-claimed T-60 row going out as a duplicate T-10.
- `SMS_STOP_FOOTER`, `withSmsFooter(body,{firstInConversation})`, `clampSmsBody(body, maxSegments=2)` using `countSegments` from `lib/sms-segments.ts`. Standardise on an `OASIS AI:` prefix. **The Meet link and the STOP footer are never droppable** — drop the agenda clause first.
- `buildFounderMeetingMessages` renders each tier naturally ("in 1 hour" / "in 30 minutes" / "in 10 minutes").

`tests/founder-meeting-closed-loop.test.ts` asserts current copy. Re-point it in the same commit; do not weaken it.

### Phase 4 — Outbox creation + backfill reconciler

`lib/website-sales-founder-meeting.ts`:

- `ensureNotificationRows` (`:294-389`) — loop `plannedReminderTiers` instead of one hardcoded `reminderAt`; one email + one SMS row per tier, each carrying `reminder_minutes_before` and `kind: reminderKindFor(m)`. Leave the `sms_consent` re-read (`:360-374`), the dedupe probe and the unique-violation tolerance alone — that is precisely what makes re-running it safe.
- New export `backfillFounderMeetingNotifications({tenantId?, now?, horizonMs=48h, limit=25})` — scan `call_appointments` where `meeting_kind='founder_audit'`, `workflow_status='active'`, `status='scheduled'`, `calendar_status='verified'`, `pending_request_id IS NULL`, `scheduled_for` between now and now+horizon; rebuild via the existing `meetingFromAppointment(appointment, appointment.booking_request_id)` and re-run `ensureNotificationRows`. Follow the tenant-enumeration shape of `reconcileFounderMeetingSagas` (`:1727-1763`).
  **One mechanism closes D6 three ways:** already-booked meetings get the new tiers, consent-granted-later produces SMS rows, phone-added-later is picked up from the snapshot.
- `cancelOutstandingNotifications` (`:273-292`) needs **no change** — it cancels by `appointment_revision <=`, tier-agnostic. `compensateReschedule` (`:1445-1562`) inherits tiering for free.

`app/api/cron/dispatch-founder-meeting-reminders/route.ts`:

- Call the backfill after saga reconciliation, degrading the same way (`:449-463`) — a backfill failure must never stop deliveries.
- Add `reminder_minutes_before` to `NotificationRow` **and to both select column lists** (`:490`, `:538`). Miss either and the tier is silently lost.
- `processRow`: branch on `row.reminder_minutes_before != null`, not `kind === "ten_minute"`. Insert **before** the rebuild: if `actual <= 0` skip `meeting_already_started`; if `!reminderTierStillValid(...)` skip `reminder_tier_superseded`.
- Apply `withSmsFooter` / `clampSmsBody`. `firstInConversation` = no prior `sent` SMS row for that recipient in that tenant.
- Quiet-hours check on the SMS branch only, ahead of the send, via `tzFromPhone()` (`lib/phone-timezone.ts:60`). **Skip, don't fail.**

**Known interaction, must be tested:** `acquireAppointmentLease` (`:144-178`) serialises delivery per appointment. With three tiers two rows can be due on one tick; the loser is re-marked `pending` and retries next tick, where `reminderTierStillValid` decides. Ordering is already `due_at ASC` (`:520`) and the lease releases in a `finally` (`:431-439`), so consecutive rows in one pass do succeed. Note also that `MAX_ATTEMPTS=3` at a 5-minute cadence gives a T-10 SMS ~15 min of retry against a 10-minute deadline — correct behaviour (it skips), but it must page.

### Phase 5 — Phone required + consent as a separate affirmative act

**Read this trap before writing code.** `normalizeFounderMeetingContact` is called from two places: the booking path, *and* `contactFromAppointment` (`:391-399`), which re-normalises historical rows on every reschedule, cancel and saga compensation. Making phone required inside it makes every already-booked phone-less meeting un-reschedulable and starts `compensateReschedule` throwing inside the cron.

- **Leave `normalizeFounderMeetingContact` permissive.**
- Enforce `client_phone_required` **inside the new-booking arm only** — the `else` at `createVerifiedFounderMeeting:603-664`, before the insert. Idempotency replays return through the `if (appointment)` arm at `:580-602` and never reach the guard. `assertSameRequest` (`:208-238`) already compares `client_phone_snapshot`, so a same-payload replay still matches.
- Add `client_phone_required` to the 400 list in the route (`:465-478`).
- `LeadLifecycleActions.tsx`: phone gets `required`; add `founderPhoneValid` (10–15 digits) to `founderBookingReady` (`:425-437`) and a `bookingBlockedReason` arm right after the email arm.
- **Consent is NOT a booking gate.** Making the box a gate manufactures coerced consent. Phone + no consent is a valid booking with email-only reminders. Keep the reset-on-phone-edit at `:549` — editing the number correctly invalidates consent.
- Replace the consent label with a **versioned disclosure exported from a new `lib/sms/auto-responses.ts`**, so the copy submitted to Toll-Free Verification and the copy shown to the rep cannot drift. Submit a **consent artifact** (`disclosure_text`, `disclosure_version`, `seller_named`, `captured_at`, `method:"verbal"`, `source_url`) in the shape `readConsentArtifact` (`lib/sms/consent.ts:64-105`) already parses; persist as `founder_meeting_sms_consent_artifact`.
- New PATCH action `founder_meeting_sms_consent` for consent captured after booking: same role gate, sets `sms_consent`/`sms_consent_at` on the current revision, then re-runs `ensureNotificationRows`. **Without this the backfill can only ever produce email rows.**

Note: `tenant_records.data.founder_meeting_sms_consent` is written and never read anywhere. `call_appointments.sms_consent` is the only source of truth.

### Phase 6 — Fix the Twilio front door

**Delete the `node:child_process` spawn from `lib/sms-opt-out.ts` (D2).** Replace with `suppressPhoneNumber(db, {tenantId, phone, reason, source})` and `releasePhoneSuppression(db, …)` against **`sunbiz_phone_suppressions`** (exists; upsert on `tenant_id,phone_last10`; release is a targeted DELETE plus a `lead_interactions` row with `metadata.opt_in_restored:true`). The TextTorrent webhook (`:296-300`) already does exactly this — copy that shape and drop its now-dead `suppressPhoneViaCasl` call. Keep `isStopCommand`/`classifyOptOut` unchanged; they are pure and correct.

**Create `lib/sms/auto-responses.ts`** — one source of truth for the TFV submission, the webhook replies and the consent disclosure. Assert each ≤ 1 segment:

- `STOP_CONFIRMATION` · `HELP_RESPONSE` · `START_CONFIRMATION` · `SMS_CONSENT_DISCLOSURE` + `_VERSION`
- Each must name the business, state message frequency and that rates may apply, and carry the opt-out instruction.

**Rewrite `app/api/webhooks/twilio/sms-inbound/route.ts` as the agent front door.** Budget **p99 < 2s**; no provider calls, no LLM.

1. **Tenant resolution must not fail closed on a missing table (D3).** Today a `channel_accounts` read error returns 503 and Twilio retries forever. Fall through instead: `channel_accounts` → credential match on the decrypted `from_number` (port `resolveTenantByInboundNumber`, texttorrent `:97-140`) → `TWILIO_TENANT_ID` → only then 422.
2. Signature verification unchanged.
3. **Idempotency on `MessageSid`** via `UNIQUE(tenant_id, provider, provider_message_id)` on the new `sms_agent_jobs`. A unique violation is a Twilio retry → return `<Response/>`, do nothing. Stronger than the current `lead_interactions` upsert because it also prevents double-enqueuing agent work.
4. **Deterministic keywords answered inline via TwiML.** There is no Messaging Service yet, so carrier Advanced Opt-Out does not apply — the app must answer. STOP → suppress **and cancel every `pending`/`sending` SMS outbox row for that recipient** and set `metadata.opt_out_detected` (keeps the defence-in-depth path) → reply. HELP/INFO → reply. START/UNSTOP → release → reply.
   **D4 is decided, implement it exactly:** honour the opt-out (legally mandatory) **and** additionally enqueue a `cancel_meeting` job; reply only the STOP confirmation; page the rep. Cancelling the meeting is the safe reading of both interpretations. Document it in the file header — it is the most likely surprise in the system.
5. Everything else: write the `lead_interactions` row (shape unchanged, `:101-127`), `persistCanonicalLeadTouch`, `nudgeConversations`, enqueue `sms_agent_jobs` as `pending`, return **empty** `<Response/>` — no auto-reply until the agent has decided.

**Sender flexibility.** In `lib/sms-direct-twilio.ts` (`:107-112`), `lib/tenant-integration-schemas.ts` (`:56-64`) and `lib/tenant-integration-store.ts` (`ENV_FALLBACKS.twilio`): add a `messaging_service_sid` field (`alphanum_uppercase`, env fallback `TWILIO_MESSAGING_SERVICE_SID`). Send `MessagingServiceSid` when present, **else** `From` — **never both** (Twilio 21606-class error). `tenantHasDirectTwilio` accepts either. The column name `twilio_messaging_service_sid` already exists in `112_conversations_spine.sql:169` — reuse it.

**Why:** CC's leads are Canadian, and Canadian carriers forbid A2P over local long codes. The compliant sender is a toll-free number with Toll-Free Verification. This change makes that swap a settings change with zero deploy.

### Phase 7 — Migration 170 + the SMS reply agent

`database/turso/170_sms_reply_agent.turso.sql` — three `CREATE TABLE IF NOT EXISTS`, nothing destructive:

- **`sms_agent_jobs`** — `id`, `tenant_id`, `provider`, `provider_message_id`, `from_phone`, `to_phone`, `phone_last10`, `body`, `lead_id`, `appointment_id`, `interaction_id`, `status CHECK IN ('pending','running','done','escalated','dead_letter')`, `intent`, `intent_confidence CHECK IN ('high','low')`, `intent_source CHECK IN ('rules','llm','none')`, `proposed_action`, `executed_action`, `attempts`, `lease_token`, `lease_expires_at`, `last_error`, `received_at`, `completed_at`, `UNIQUE(tenant_id, provider, provider_message_id)`. Indexes on `(status, received_at)` and `(tenant_id, phone_last10, received_at)`.
- **`sms_agent_conversations`** — `PK(tenant_id, phone_last10)`, `lead_id`, `appointment_id`, `state CHECK IN ('idle','awaiting_slot_choice','awaiting_rep','closed')`, `proposed_slots` (JSON), `state_expires_at`, `last_inbound_sid`, `last_outbound_at`, `agent_turns_24h`, `turn_window_started_at`, `automation_paused`, `paused_reason`.
- **`sms_agent_worker_health`** — singleton mirroring 167's.

`sunbiz_phone_suppressions` needs no change.

**`lib/sms/meeting-intent.ts` — pure, no I/O, no `server-only`**, exactly like `lib/sms/compliance.ts`, so the rules with money attached are directly testable:

```ts
export type MeetingIntent = "confirm"|"reschedule"|"cancel"|"running_late"|"question"|"opt_out"|"unknown";
export function classifyMeetingReply(body: string): { intent: MeetingIntent; confidence: "high"|"low"; proposedTime: {isoLocal:string; source:string}|null };
export function parseProposedTime(body: string, nowIso: string, tz: string): string | null; // null on ANY ambiguity
```

Test against a **false-positive corpus** the way `detectOptOut` is: "stop by at 3" is not an opt-out; "can you cancel the second item" is not a meeting cancel; a bare "2" is a slot choice only in state `awaiting_slot_choice`.

**`app/api/cron/sms-reply-agent/route.ts`** — `runtime="nodejs"`, `dynamic="force-dynamic"`, `maxDuration=60`, exports **both GET and POST**, `checkCronAuth(req)` first. Every 5 min:

1. Clear expired leases; fail `running` rows stale past 15 min; claim ≤20 `pending` by CAS — copy `:465-545` of the reminder dispatcher.
2. **Appointment matching**, tenant-scoped throughout, in this order:
   a. The appointment whose SMS reminder we most recently sent to this number (newest `website_sales_meeting_notifications` with `status='sent' AND channel='sms' AND recipient` matching) — **strongest signal: they are replying to what we sent.**
   b. Else soonest active `founder_audit` with `client_phone_snapshot` last-10 matching and `scheduled_for > now-2h`.
   c. Else widen to `now-24h` (catches "sorry I missed it").
   d. **More than one candidate within 2h of each other → `escalated`, page the rep, never guess.**
   e. Zero → lead-level match only; permitted intents `opt_out`/`question` → escalate.
   Match on `client_phone_snapshot`, **not** the lead's `data->>phone` — the snapshot is the number we actually texted.
3. **Classification: rules first.** Only when `confidence === "low"` **and** `SMS_AGENT_LLM === "1"`, call `queueInfer` — with `wrapUntrusted` + `redactAll` applied **before** queueing (`queueInfer` persists the prompt in `inference_jobs`), the `INJECTION_GUARD` from `lib/llm-input-boundary.ts:60` in the system prompt, `dedupeKey` from the `MessageSid`, `modelTier:"fast"`, `maxTokens:200`, `timeoutMs:20_000`. **`timedOut` → leave the job `pending` and return** (retry next tick). A non-timeout failure → escalate: that means the daemon is dead, and waiting forever is the failure this contract exists to prevent. Validate output against the enum; re-check any datetime in deterministic code.
4. **`SMS_AGENT_AUTONOMY` — CC has chosen to ship at `propose`.** `BRAVO_FORCE_DRY_RUN=1` clamps to `off` regardless.

| Intent | `off` | **`propose` (launch)** | `execute` |
| --- | --- | --- | --- |
| `opt_out` | handled inline in the webhook — always live | " | " |
| `confirm` | record | + "See you then" | same |
| `running_late` | record + page | + ack, page | same |
| `cancel` | record + page | + "I've asked {rep} to confirm" + page | `cancelVerifiedFounderMeeting` + lead patch + reply + page |
| `reschedule` **with** a valid time | record + page | + ack + page | `rescheduleVerifiedFounderMeeting` + lead patch + reply with new time & Meet link + page |
| `reschedule` **without** a time | record + page | reply with 3 slots, state → `awaiting_slot_choice` | same |
| `question`/`unknown` | record + page | "{rep} will reply shortly" + page | same — **never answered autonomously** |

5. **Reschedule guardrails** (all must pass or degrade to `propose`): ≥2h out, ≤21 days, Mon–Fri 09:00–18:00 America/Toronto, on a 15-minute boundary, and no other `call_appointments` row for the same `assigned_to` overlaps (a Turso query — **there is no Google free/busy helper in this repo and adding one needs a new scope**). Execute with `requestId = "sms:" + messageSid` — the existing unique index gives idempotency for free, and the saga does the Google PATCH, the revision bump, the old-tier cancellation and the new-tier `ensureNotificationRows` for you.
6. **Cancel must patch the lead, and there is a real constraint.** `leadConfirmsAppointment` (`:1329-1347`) treats a cancel saga as confirmed only when the lead is `lost`. An SMS cancel should **return the lead to the rep, not lose the deal**. Extend `leadConfirmsAppointment` to also accept `lead.founder_meeting_status === 'cancelled_by_client'` for `operation === 'cancel'`, and patch `stage:'qualified'`, `founder_meeting_status:'cancelled_by_client'`, `next_action_at: now+1h`, `founder_meeting_at: null`, `calendar_event_status:'cancelled'`. This only bites if the process dies mid-saga, but leaving it inconsistent makes the reconciler *release* the reservation instead of completing the cancel.
7. **Loop breaker:** max 3 agent outbound messages per conversation per 24h; set `automation_paused=1` the moment an outbound `lead_interactions` row exists for that lead with an `agent_source` other than `sms_reply_agent` (a human took over — the `lib/drips/reply-handoff.ts` doctrine: mark first, then page). 24h expiry on `awaiting_slot_choice`.
8. Every agent outbound goes through `sendSmsDirectTwilio` (inherits the fail-closed opt-out gate), is gated by `isDryRun("twilio")`, is footered and clamped, and is recorded with `agent_source:'sms_reply_agent'` + `persistCanonicalLeadTouch`.
9. `setHealth()` writes `sms_agent_worker_health` in the shape of `:80-92`.

**Register the cron in `workers/oasis-cc-cron/src/index.ts` `CRON_TABLE` AND `vercel.json`** (kept as the diffable source of truth), plus `cron-driver.yml`'s `workflow_dispatch` arm. `tests/cron-driver-coverage.test.ts` fails CI otherwise.

### Phase 8 — Observability + rep notification

- `writeAgentAlert` (`lib/notify/agent-alert.ts`) on lane **`operator`** always — never `sunbiz-ops`, that is another operator's lane and there is a recorded 2026-08-02 misroute. `subjectId` = appointment id so a repeatedly-failing meeting collapses to one card. Alert types: `founder_reminder_failed` (warn, once-per-open), `founder_reminder_tier_missed` (warn, once-per-open), `sms_agent_ambiguous_match` (warn), `sms_agent_dead_letter` (urgent), `sms_agent_meeting_moved` (info, telegram).
- **The rep learns their meeting moved on three surfaces:** Google's own update mail (host and opener are both attendees and the PATCH uses `sendUpdates=all`) — the *what*; the Telegram page — the *alarm*; and `sendGmailAsOperator` to `organizer_email_snapshot` with the client's verbatim message plus old and new times — the *why*, which Google's invite never says. Plus the `lead_interactions` row in the drawer timeline.
- `lib/health/runner.ts`: alert when any notification row is `pending` more than 15 min past `due_at`, or any `sms_agent_jobs` row is `pending`/`running` older than 30 min.

## 5. Rollout — nothing sends live until step 7

Rollback at every step is unsetting one flag. `BRAVO_FORCE_DRY_RUN=1` is the hard kill for all outbound.

| # | Step | Flags | Gate |
| --- | --- | --- | --- |
| 1 | Scheduler cutover (Phase 1) | — | Worker tail shows the forward; `last_run_at` advances within 5 min |
| 2 | Migrations 169 + 170 | — | `--dry-run`, then `PRAGMA table_info` + row count matches `_v167` |
| 3 | Phases 3–4, dispatcher still dry | `LIVE_SEND_TWILIO` unset | `npm run typecheck && npm run lint && npm run test:website-sales` |
| 4 | Deploy, drive the cron by hand | " | `curl -sS -m 120 "https://oasisai.work/api/cron/dispatch-founder-meeting-reminders" -H "Authorization: Bearer $OASIS_CRON_SECRET"` → SMS rows `skipped:"twilio_live_send_disabled"`, **email genuinely sent at all three tiers** |
| 5 | Phases 5 + 6 (still no outbound SMS) | " | Book a test meeting 75 min out → **6 outbox rows** (3 email + 3 SMS) with `reminder_minutes_before` 60/30/10. Text STOP to the number → a `sunbiz_phone_suppressions` row appears **and** the confirmation TwiML returns; START removes it |
| 6 | **Toll-Free Verification — external, blocking, CC's action** | — | TFV `VERIFIED`; `messaging_service_sid` set in Settings → Integrations |
| 7 | Go live on outbound SMS | `LIVE_SEND_TWILIO=1` | Canary meeting 75 min out to CC's own mobile: T-60/T-30/T-10 SMS **and** email; first SMS carries the STOP footer; every body ≤ 2 segments |
| 8 | Agent at `propose` | `SMS_AGENT_AUTONOMY=propose` | Reply "can we move to tomorrow at 2?" → client acknowledged, rep paged, **calendar unchanged**, job row shows intent `reschedule` + `proposed_action` |
| 9 | Promote to `execute` — **CC's call, after a week of real replies** | `SMS_AGENT_AUTONOMY=execute` | Same reply → event PATCHed to the new time with the **same Meet link**, revision incremented, old rows cancelled, new tiers created, client and host both told |

**Steps 6 and 9 are CC's, not yours.** Stop at step 5 and report; stop again at step 8 and report.

### What CC must do in the Twilio console (context, not your task)

The account is new, funded, and its **Primary Compliance Profile (Business)** is `Pending Review` — that is the correct profile and must not be dismissed; toll-free purchase requires a compliance profile and TFV requires business identity. `oasisai.work/privacy` and `/terms` must render (routes exist at `app/(marketing)/privacy` and `app/(marketing)/terms` — **confirm they actually render, and flag it if not**, because from 2026-09-15 a TFV submission without separate Privacy and Terms URLs is auto-rejected with error 30493). The TFV submission must quote the STOP/HELP strings from `lib/sms/auto-responses.ts` **byte-for-byte**.

## 6. Tests to add

Run each as `node --conditions=react-server --import tsx tests/<file>` from the repo root.

| File | Covers |
| --- | --- |
| `tests/founder-meeting-reminder-tiers.test.ts` | 169 loaded into `:memory:` after 167 (`PRAGMA table_info`, all three original index names present, CHECK admits the new kinds, legacy rows land with `reminder_minutes_before=10`); tier collapse (booked 20 min out ⇒ no T-60/T-30); `reminderTierStillValid`; dedupe-key stability; footer + `countSegments ≤ 2`; **source assertion that the dispatcher branches on `reminder_minutes_before`, not `kind`** |
| `tests/founder-booking-phone-required.test.ts` | New booking without phone throws `client_phone_required`; **replay of a legacy phone-less `booking_request_id` still returns the meeting**; `contactFromAppointment` still tolerates a null snapshot; UI source assertions for `required`, `founderPhoneValid`, the blocked reason, and that consent is *not* a term of `founderBookingReady` |
| `tests/sms-meeting-intent.test.ts` | Intent classification + false-positive corpus; `parseProposedTime` null on ambiguity; **the D4 collision produces both outcomes** |
| `tests/sms-inbound-agent.test.ts` | Signature verification; tenant fallback chain (a `channel_accounts` read error must **not** 503); `MessageSid` idempotency; STOP writes `sunbiz_phone_suppressions` **and** cancels pending SMS outbox rows; TwiML matches `auto-responses.ts` byte-for-byte; `assert(!readFileSync("lib/sms-opt-out.ts","utf8").includes("child_process"))` |
| `tests/sms-agent-autonomy-gate.test.ts` | Default is `off`; `execute` required for any calendar mutation; every reschedule guardrail rejects (past, weekend, out-of-hours, >21d, non-15-min, host conflict); `BRAVO_FORCE_DRY_RUN` clamps; a `queueInfer` timeout leaves the job pending; `wrapUntrusted` **and** `redactAll` both applied |
| `tests/sms-sender-messaging-service.test.ts` | `MessagingServiceSid` when present, `From` otherwise, **never both**; `tenantHasDirectTwilio` accepts either |

Wire the first two into the existing `test:website-sales` chain in `package.json` (zero `ci.yml` change); add a `test:sms-agent` script for the rest plus the existing `test:sms-*` suites, and one `npm run test:sms-agent` line to `.github/workflows/ci.yml` after `test:website-sales`.

## 7. Open — verify before relying on

1. **Does `channel_accounts` exist on Turso?** (D3.) One query, step one. If absent, Phase 6 goes from hardening to "the inbound path has never worked," and that changes the report.
2. **How were `database/turso/142–168` actually applied?** `apply_turso_migration.py` defaults to the *Bravo* migration directory. It accepts an explicit path, but confirm that is the real process before assuming 169/170 apply the same way.
3. **Is the remote infer daemon running?** The entire LLM fallback is worthless if not — which is exactly why the deterministic classifier must cover every common case and `SMS_AGENT_LLM` defaults off.
4. **`record_lead_touch` under the agent's write pattern** — a hand-ported RPC (`lib/turso-rpc-shim.ts:2299-2396`) with a retry loop and an `owner_conflict` path. The agent writes touches for leads it does not own; verify `expectedOwnerId` is left undefined so the conflict branch is not entered.
5. **Real webhook latency from workerd.** Designed to a 2s p99 against Twilio's ~15s limit, but the 4–6 Turso round trips are unmeasured. Measure before trusting it.
6. Whether `PRAGMA writable_schema` works on Turso Cloud — if it does, an in-place CHECK rewrite is tidier than the rename-aside. **Do not ship it untested.**

## 8. Report back

Four lines, per phase and at the end:

- **Changed:** paths.
- **Why:** one plain sentence each.
- **Proof:** the verification command and its **actual output**.
- **Needs from CC:** specific asks, or "nothing."

Flag anything in §2 you found to be wrong — that section is verified but not infallible, and a stale claim acted on is worse than an open question.
