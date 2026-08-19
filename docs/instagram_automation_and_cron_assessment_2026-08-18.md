# Instagram Automation and Cron Assessment — 2026-08-18

## Executive status

- Zernio now supports the required Instagram surface: DMs, comment replies, comment-to-DM, story-reply automation, webhooks, interactive buttons/quick replies, and per-post or account-wide keyword rules.
- The existing `LATE_API_KEY` is present. Do not create a second key until the existing key is tested and its scope is confirmed.
- Command Centre contains 29 empire jobs: 20 enabled and 9 disabled. Nineteen enabled jobs show current successful/no-op results; the Sleep Agent is failing.
- The Automations page failure has two confirmed causes: empty API bodies and Turso-decoded object values in `cron_jobs.last_result`. The local repair covers both and exits the stuck loading state with an in-place retry.
- The repair is not yet permanent because the two commits are not on GitHub `main`; a later main deployment overwrote them again. Local push is blocked by invalid/non-interactive GitHub credentials.

## Recommended Zernio architecture

Use Zernio as the Meta transport and OASIS as the decision/audit layer.

1. Zernio receives `comment.received`, `message.received`, story-reply, delivery/read/failure, and account-disconnected events.
2. A signed OASIS webhook validates authenticity before parsing, stores the provider event id, and rejects duplicates.
3. The router resolves `account_id + platform_post_id + normalized keyword` against a versioned campaign registry.
4. The policy engine checks consent, suppression, cooldown, prior private reply, business hours, confidence, and human-escalation rules.
5. Zernio sends the approved public reply/private reply/DM using an idempotency key.
6. The result and full funnel state are written to `lead_interactions`; qualified contacts are upserted into `leads` with source post and keyword attribution.
7. Delivery/read/reply/booking events advance the state machine and feed conversion analytics.

Do not let an LLM freely choose recipients or offers. Deterministic rules select the workflow; AI may classify intent or personalize inside an approved template.

## Per-video campaign registry

Every Reel/video needs one record before publishing:

| Field | Purpose |
|---|---|
| `campaign_key` | Stable internal identifier |
| `platform_post_id` | Exact Instagram media id after publish |
| `offer_key` / `offer_version` | The approved lead magnet or offer |
| `keywords` | Exact phrases plus deliberate aliases/typos |
| `match_mode` | Exact by default; contains only when collision-tested |
| `public_reply_template` | Optional visible acknowledgement |
| `private_reply_template` | First DM; use 1–3 buttons for cold comment traffic |
| `qualification_flow` | Questions, valid answers, scoring, and next state |
| `booking_url` | Offer-specific calendar destination |
| `owner` / `escalation_sla` | Human handoff target and deadline |
| `daily_cap` / `cooldown` | Demand and spam controls |
| `active_from` / `active_to` | Safe activation window |
| `success_event` | Booked call, form completed, purchase, etc. |

Per-post rules must win over account-wide catch-alls. Use account-wide automation only for evergreen help keywords. Zernio supports `exact` and `contains`, and can also match the same keyword in inbound DMs with `alsoMatchInDms`.

## Conversion workflows

### 1. Comment keyword to DM

`comment.received` → deduplicate → match post + keyword → optional public acknowledgement → one private reply within seven days → offer buttons → inbound reply → qualification → booking → human handoff.

Zernio permits one private reply per comment. Buttons are preferred for users in Message Requests because quick-reply chips may not render there.

### 2. Direct inbound DM keyword

`message.received` → identify campaign keyword/source → send approved first response → ask one question at a time → score intent → book, nurture, support-route, or human-escalate.

### 3. Story reply

Story reply/mention metadata → identify story/campaign → contextual response → same qualification state machine. Never infer an offer if the story is not mapped.

### 4. Non-keyword comment moderation

Classify into sales question, support, praise, objection, spam/abuse, or high-risk. Auto-reply only to high-confidence low-risk classes. Hide/delete requires explicit policy; legal, refund, harassment, and sensitive complaints go to a human.

### 5. Capacity and demand control

Queue events; cap sends per account and campaign; apply exponential backoff for 429/5xx; use a dead-letter queue; pause a campaign automatically on auth disconnect, elevated failure rate, or booking-capacity exhaustion. Never silently drop an event.

## Automation inventory recommendation

### Keep enabled (current evidence healthy)

Daily Briefing Snapshot, Daily Client Alerts Snapshot, OASIS Auto-Score Leads, Daily Bravo Brief, Hourly Cron Health Check, Daily State DB Backup, Nightly Harness Eval, Daily Log Rotation Audit, LanceDB Compaction, Event Bus Offline Drain, Inbound Email Sweep, Weekly tmp Hygiene, Marketing Publish Drain, Training Corpus Ingest, Post Analytics Sync, Daily Pulse Mechanical Refresh, and Library Post Linker.

### Keep, but recalibrate/verify

- Booking Reminders: latest result is an empty array; add a result schema that distinguishes “zero bookings” from an execution defect.
- Weekly Pipeline Review and Cross-Agent Self-Improvement Sweep: results say “handled-by-digest”; prove the digest performs the intended work or retire the redundant rows.
- Daily MRR Auto-Sync: currently successful but finance is Atlas-owned; verify there is no duplicate Atlas job, then move ownership or disable this copy.
- Loud Failures Weekly Probe, LanceDB Compaction, and Weekly tmp Hygiene: results collapse to `}`; preserve structured summaries so the dashboard can prove what occurred.
- Monthly Inventory Sync: enabled but has never run; execute a dry-run verification before its first scheduled date.

### Disable until repaired

- Bravo Sleep Agent: fails because Claude subscription access is disabled. Keep off until the approved local model-call path works; do not switch to a paid API key contrary to repo policy.

### Disabled legacy candidates for archive/removal after CC review

Weekly MRR Report, Monthly Metrics Snapshot, Nurture Sequence Check, Stripe Revenue Sync, Funnel Fast-Poll, Weekly Qualified-Leads Snapshot, Morning Pow Wow Call, Break-Glass Drill, and Review Harvest. Several were explicitly moved, superseded, or intentionally paused. Archive first; delete only after a retention/export check.

## Permanent dashboard fix gate

The source-of-truth fix is complete only when:

1. Commits `1de5c540` and `76642593` (or their final merged SHAs) are on GitHub `main`.
2. CI/typecheck/focused tests pass on that exact SHA.
3. Vercel deploys that SHA and `/api/cron-jobs` returns structured JSON.
4. An authenticated production session loads all 29 rows.
5. One safe test job is toggled off, observed inactive after the scheduler poll, toggled on, and observed active again.
6. A synthetic empty-body response and object-valued `last_result` remain covered by regression tests.

“Smart self-healing” should mean bounded retry, circuit breaking, last-known-good read-only display, correlation ids, monitoring, and alerts. It should not silently mutate data or mask repeated failures.
