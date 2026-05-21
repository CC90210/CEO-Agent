---
title: SunBiz CRM — handoff after 2026-05-15 evening session
date: 2026-05-15
audience: CC (operator) · Jordan Colleson (SunBiz) · Adon Delpeche-Yess (partner) · Ezra (rep)
status: ACTIVE — Round 2 partial. Phases 11/12/13 still queued; rest of Round 2 shipped.
---

# What this doc is

A clean read-out of what shipped tonight, what's live in production (`agent-dashboard-cc90210.vercel.app`), and what's blocked on input from the SunBiz team before further work can proceed.

If you're reading this fresh: the plan it pairs with is at `C:\Users\User\.claude\plans\this-is-a-handover-giggly-reef.md`. Round 1 (Phases 1-8) shipped earlier today. Round 2 (Phases 9-15) is partially shipped — this doc lists which slices landed and which are still waiting.

---

## Tonight's commits (in order)

| Commit | Title | What it does for operators |
|---|---|---|
| `0cf3d01` | Phase 9 — operator polish | No more JSON chips / "Untitled" defaults on create forms; structured sequence step editor; Lead Follow-up Check cron unstuck (was crashing 25 days from a 12KB JSON dump truncated mid-string by a 8KB cap) |
| `911c7c6` | Phase 9 self-review fixes | JsonField Simple↔Advanced toggle bidirectional; FormBuilder framed honestly as "power-user editor, visual builder coming next" |
| `def41e4` | JSON-field array safety | Arrays default to Advanced mode so Simple-mode "Add field" can't clobber them |
| `fcec21d` | Delete-but-returns + Reasoning dev view | `router.refresh()` after every mutation invalidates Next.js RSC cache; DELETE handlers return 404 on zero rows; removed `?dev=1` developer view from /reasoning |
| `5886eb4` | Leads + Kanban UI rebuild | LeadsTableClient (stage tabs, search, sort, pagination for 500 leads); ManifestKanban cards 2× bigger with up to 5 labeled fields; ?view=table/kanban toggle |
| `6260efa` | Funded Deals renewal Kanban | Synthetic compute_group_by="renewal_window" buckets deals into upcoming / due / overdue / renewed / lost from `funded_at` + `term_months` |
| `e10cf76` | Bulk lead import + dev-tag cleanup | CSV paste/drop → preview → tenant-scoped dedup → bulk insert (5000/req cap); dropped "Phase 3" / "kanban" tags from operator UI |
| `4758b58` | Phase 10.2 Offer Accept/Decline | Inline buttons on offer Kanban cards. Accept = stage → "accepted" + creates draft funded_deal carrying lead_id / lender_id / amount / term / funded_at=today |
| `b9dfe36` | Phase 10.3 AI lender scoring | Per-application "Recommended lenders" expandable panel with rule-based fit score against lender requirements + per-lender "Shop out" button wired to existing endpoint |
| `0b10589` | Self-review fixes | Import reachable for SunBiz tenants via `kind: "import"`; extracted duplicated `humanize()` to lib/manifest/humanize.ts |
| (this commit) | Phase 14 + Phase 15.1 + Codex #3 | Cloak-browsing skill upgraded with TPS-specific routing; 3 new default drips (cold→sent_application 24h, signed→bank-stmt nag, default 60d soft check-in); migration 045 + runner update closes the sequence_state race |

---

## What's live & functional for operators today

**For Ezra (logged in as `submissions@sunbizfunding.com`):**
- `/t/sun/leads` — Kanban grouped by lead stage. Click any stage tab. Switch to table via the toggle pill.
- `/t/sun/import` — paste/drop CSV → preview → bulk insert. Dedups by email + phone (US-normalized).
- `/t/sun/applications` — Kanban grouped by status. Per-card "Recommended lenders" expandable panel hits `/api/applications/<id>/match-lenders` and ranks every tenant lender against the application's underwriting profile, with one-click Shop-out per lender.
- `/t/sun/offers` — Kanban grouped by offer stage. Cards in `offered` / `contracts_out` have inline Accept / Decline buttons. Accept flips the offer + creates a draft `funded_deal`. Decline is idempotent and doesn't create downstream records.
- `/t/sun/funded-deals` — Kanban with renewal-window buckets: upcoming (0-40%) / due (40-50%) / overdue (50%+) / renewed / lost.
- `/t/sun/renewals` — Kanban grouped by renewal status.
- `/t/sun/lenders` — Table view of the lender book.
- `/sequences` (drip editor) — structured per-step editor with channel dropdown, delay, optional subject, body, from-label. Advanced raw-JSON toggle for power moves.
- `/forms` — list + editor. Editor is marked "Power-user editor — visual builder next round" honestly.
- `/reasoning` — quick actions only. Developer view removed.
- `/automations` — empire cron jobs (Lead Follow-up Check now green again) + tenant cron jobs + Background Workers panel showing 9 PM2 daemons + standalone Skool engine.

**For CC (OASIS HQ via `/`):**
- Same surfaces. `/leads` uses the new LeadsTableClient at the bare path for CC's tenant.
- `/automations` shows the merged empire + tenant cron view that landed earlier today.

**Daemons running on CC's machine (PM2):**
- `bravo-scheduler` (empire cron, Windows only)
- `bravo-telegram` (Telegram bridge)
- `claude-bridge` + `claude-bridge-ping` (chat backbone + heartbeat + tenant cron poller)
- `event-router` (V6 event bus tail)
- `override-consumer` (exec-override approvals)
- `sequence-runner` — reloaded tonight to pick up the Codex #3 ON-CONFLICT-style dedup
- `lender-response-classifier` (Gmail thread classifier)
- Standalone Skool daemon (lockfile-based, not in PM2)

---

## What still needs SunBiz-owner input

This is the list that I can't progress without Jordan / Adon / Ezra. Each one is "ready to wire once we have the data."

### From Adon

| Item | What I need | Why |
|---|---|---|
| **Lender book** | Each lender's row populated with `min_monthly_revenue`, `max_funded_amount`, `min_time_in_business_months`, `fico_floor`, `product_types[]` (mca / term_loan / line_of_credit / equipment / invoice_factoring / sba). Plus contact email + lender domain. | Drives Phase 10.3's "Recommended lenders" scoring. Without the requirement fields, every lender scores 0/0 and the panel is useless. Today the seed has lender entity defined but no real rows. |
| **Mega-email account credentials** | Gmail address + app-password (or OAuth tokens) for the central lender-offers inbox (e.g. `offers@sunbizfunding.com`). | Phase 12 (Gmail domain labels). The lender_response_classifier will auto-label inbound threads `SunBiz/Lender/<domain>` once it can authenticate to the inbox. |
| **Constant Contact API key + refresh token** | From CC dashboard → Integrations. Set as `CONSTANT_CONTACT_API_KEY` and `CONSTANT_CONTACT_REFRESH_TOKEN` in Vercel env. | Phase 11 wrap. Without these the `cc_blast` channel in send_gateway just errors `unconfigured`. |
| **TextTorrent API key (separate from Twilio)** | TT's actual API key, not the Twilio-relabel we ran on temporarily. | TT-direct already shipped in Phase 5 but operator still needs the real key in `TEXTTORRENT_API_KEY` for blasts to route through TT's own API rather than the legacy Twilio path. |
| **Per-employee email accounts** | Adon creates real Google Workspace mailboxes for Ezra and any other reps. | Phase 13 per-employee model. Each rep's `user_profiles.email` should map to a real mailbox before we add the role / RLS layer. |
| **Existing TextTorrent campaign copy** | The actual blast copy SunBiz uses today (the "meeting-tested wording" from the transcript). | Replaces my placeholder drip copy with battle-tested language. Current seeds (cold→follow_up, viewed→nudge, etc.) all need an Adon review pass before turning on for real leads. |
| **Form-template variants** | Field shapes for "SunBiz Meta-Ads Lead Capture" and "SunBiz Google-Ads Lead Capture" templates. Meta usually wants `name / phone / business / amount`; Google often wants `email / company`. Confirm the actual fields. | Phase 13.4 form templates. The base "Application" form is built; Meta/Google variants need Adon's input to seed correctly. |

### From Jordan

| Item | What I need | Why |
|---|---|---|
| **Confirm the renewal window** | "40-50% of funded-deal term" was the meeting decision. Confirm it's *days from funded_at* and not e.g. *days from contract maturity*. | Phase 10.1 ships 40-50% of `funded_at + term_months * 30 days`. If the renewal-eligibility math is different (e.g. some MCA contracts use ACH-payment-count) the bucketing logic in `ManifestKanban.computeRowGroup("renewal_window", ...)` needs to switch to that source. |
| **Default-stage drip approval** | The default-lead 60-day soft check-in ships **disabled** by default (see Phase 15.1 §8). Review the copy + the timing with whoever does collections; flip enabled=true when ready. | Compliance: re-engaging a defaulted borrower needs collections-approved language. I shipped conservative copy; Jordan must approve before it fires. |
| **Commission split rules** | Per-deal % to Ezra, Adon, house, etc. | Phase 13.x commission tracking — manual entry per the meeting, but the system needs to know the *structure* (commission types: gross commission / split / bonus) before we can build the UI. |
| **STOP / TCPA language** | The exact opt-out language each commercial SMS must carry (varies by state). | Codex finding #4 (open) — first-touch commercial SMS must auto-append "Reply STOP to opt out." Jordan to confirm the exact phrase + any state-specific overlays before commercial SMS turns on. |

### From CC (operator action, not Bravo work)

| Item | What I need |
|---|---|
| Apply migration 045 to production (already done tonight via Management API, but confirm). | `python scripts/apply_migration.py database/045_sequence_state_one_per_lead.sql` — already ran, confirmed applied. |
| Optionally rotate `BRAVO_SUPABASE_SERVICE_ROLE_KEY` if you want — the delete bug fix means the dashboard never silently no-ops on deletes anymore. |
| Bridge daemon stays alive on the Windows box (`pm2 status` shows everything online; reloaded sequence-runner tonight). |

---

## Still in the queue (no blocker — just hasn't been built yet)

These are tracked in the plan file; none need external input but they're each meaningful work that I didn't get to this session.

| Phase | What | Estimate (CC+Bravo) |
|---|---|---|
| 9.6 | FormBuilderClient visual field-builder (today: still 3 raw-JSON textareas behind a "Power-user editor" warning) | ~1 day |
| 11.1 | `scripts/constant_contact_tool.py` CLI wrapper + `cc_blast` channel in send_gateway | ~half day |
| 12.1 | Extend `lender_response_classifier.py` to apply Gmail labels by lender domain | ~half day once mega-email creds land |
| 13.1-2 | `user_profiles.role` column + RLS on `tenant_records.owner_user_id` for per-rep visibility | ~half day after Adon creates rep emails |
| 13.3 | "Assign to rep" picker on Lead + Application detail pages | ~half day |
| 13.4 | Form templates seed + "Use template" clone button on /forms | ~half day after Adon confirms Meta/Google ad shapes |
| 15.3 | `scripts/snapshots/renewal_window_scan.py` daily cron — auto-enroll 40% deals into the renewal drip | ~half day. Until this ships, the renewal Kanban shows the windows correctly but no automated drip fires; operator must manually move leads into the renewal drip from `/sequences` |
| Codex #1 (open) | Atomic claim on sequence_state rows in `execution_tick` — add `claimed_at` / `claimed_by` columns + an atomic `UPDATE … RETURNING` so two daemon ticks can't both fire the same step | ~2 hours. **Gates commercial SMS** alongside #4. Today the race is hypothetical (single-machine deployment, single sequence-runner daemon) but if CC ever spawns a second runner — or if a PM2 restart overlaps a tick — the same step fires twice. The fix in `brain/SUNBIZ_CRM_KNOWN_GAPS.md` Finding #1 is exact: add migration 046 with the claim columns + an `rpc("claim_sequence_state_row")` SQL function, then route `_send_step` through it. |
| Codex #4 (open) | SMS opt-out webhook + phone-side DNC + first-touch STOP language enforcement | ~3 hours. **Gates commercial SMS** alongside #1. Don't blast real leads until this lands. |
| Setup Wizard 2.0 (Round 1 Phase 8) | Full repo scaffold + credentials questionnaire + auto-pair for new client tenants | ~2 weeks. Deferred until the SunBiz CRM is operational. |

---

## How to verify everything works (end-to-end smoke test for Ezra)

When Adon's data lands and you want to verify the pipeline:

1. **Import** — go to `/t/sun/import`, paste a 3-row CSV with `Name,Email,Phone,Company`. Confirm preview shows the right column mapping. Click Import. Confirm the result panel shows `Inserted: 3 / Skipped: 0`.
2. **Move a lead** — go to `/t/sun/leads`, find a lead. Click drill-down. Manually update stage to `follow_up` (via the manifest record edit flow). Watch `/feed` for a `BRAVO_RECORD_STATUS_CHANGED` event.
3. **Drip fires** — within ~10s the sequence-runner picks up the event, inserts a `sequence_state` row at step 0. Check `/sequences/<seq-id>/edit` — the In-flight state panel should show the new enrollment.
4. **Send fires** — when the step's delay elapses, send_gateway dispatches (Gmail for email, Twilio/TT for SMS). Real send happens; log shows in `state/sequence_runner.log`.
5. **Application** — operator pushes the lead through to `sent_application` via the application form. Watch the drips fire on each stage change.
6. **Underwriting** — when `application.status` flips to `submitted`, the Phase 7 underwriting chain populates `application.data.underwriting_jsonb` (bank-statement parse + debt detector + sales angle). Visible on application detail / kanban card.
7. **Recommended lenders** — open the application kanban card → expand "Recommended lenders". The top lender by fit score appears with check/X breakdown. Click "Shop out" → email goes to that lender + a `application_lender_threads` row appears.
8. **Offer arrives** — when the lender replies, `lender_response_classifier` daemon classifies the reply within 5 min. Operator manually logs an Offer (Phase 13 will auto-create from the classifier; today still manual).
9. **Offer accepted** — on the offer's Kanban card, click Accept. Offer flips to `accepted`. A draft funded_deal appears in `/t/sun/funded-deals` under the "Upcoming" bucket.
10. **Renewal window** — when the funded_deal hits 40% of its term, the card moves to the "Due" bucket. (Auto-enrollment into the renewal drip is queued — Phase 15.3.)

If any step breaks, the failure-mode docs are in `brain/SUNBIZ_CRM_KNOWN_GAPS.md`.

---

## Quick file map for future Bravo / Maven / contractor onboarding

| Where to look | What's there |
|---|---|
| `apps/command-center/lib/manifest/seeds.ts` SUN_SEED | The whole SunBiz shell definition — nav, pages, data_model entities (lead / application / offer / funded_deal / lender / renewal / commission), integrations |
| `apps/command-center/lib/sunbiz-default-sequences.ts` | The 8 default drip sequences seeded on tenant provision |
| `apps/command-center/app/api/leads/import` | Bulk CSV import endpoint |
| `apps/command-center/app/api/applications/[id]/match-lenders` | AI lender scoring endpoint |
| `apps/command-center/app/api/applications/[id]/shop-out` | Multi-lender email distributor (Phase 6) |
| `apps/command-center/app/api/applications/[id]/underwrite` | Bank-statement parse → sales-angle chain (Phase 7) |
| `apps/command-center/app/api/manifest/[slug]/offer/[id]/accept` | Offer accept + draft-funded_deal creation |
| `apps/command-center/components/manifest/` | All the kanban / table / form / record-form / accept-button / lender-recommend primitives |
| `apps/command-center/components/leads/` | LeadsTableClient + LeadsImportClient |
| `scripts/sequence_runner.py` | The daemon that enrolls + fires drips |
| `scripts/lender_response_classifier.py` | Gmail thread classifier |
| `scripts/integrations/send_gateway.py` | The single outbound send chokepoint — CASL / cooldown / multi-brand |
| `database/043_drip_sequences.sql` + `044_lender_shopout.sql` + `045_sequence_state_one_per_lead.sql` | Phase 4 + 6 + Codex #3 migrations |
| `brain/SUNBIZ_CRM_KNOWN_GAPS.md` | Codex review findings — fixed + still open |
| `C:\Users\User\.claude\plans\this-is-a-handover-giggly-reef.md` | The two-round plan doc (Round 1 Phases 1-8 + Round 2 Phases 9-15) |

---

## Finish line for this round

The infrastructure is end-to-end functional. Operators can:
- Onboard leads (manual entry, bulk import, or future JotForm webhook)
- Drive them through the stage pipeline with drips firing at each stage change
- Send the application form, track viewed / signed / submitted
- See AI-recommended lenders ranked by fit
- Shop the application out + track per-lender Gmail threads
- Accept offers → funded deals
- Watch funded deals walk toward the renewal window

What's blocking commercial use:
1. **Codex findings #1 + #4** — atomic sequence-state claim (no double-send under restart-overlap) and SMS opt-out enforcement (STOP language + phone-side DNC + inbound STOP webhook). Don't blast real commercial SMS until both land.
2. **Real lender data** (Adon to populate) — without it the recommended-lenders panel ranks nothing meaningfully.
3. **Constant Contact / mega-email credentials** — Phases 11 + 12 are wired but unconfigured.

Once those three close, the system is production-ready for SunBiz beta. Schedule the Sunday session per the meeting notes to walk Adon through what's live and triage what to fix first.
