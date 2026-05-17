---
title: SunBiz CRM — diagnostic report after Round 4 stage rework
date: 2026-05-17
audience: CC · Adon · Jordan
status: PASS with one production-data fix applied + one hardening landed
---

# What was tested

Deep diagnostic pass across the Round-4 changes (Salesforce-parity
Lead Pipeline + Opportunity Pipeline + chevron arrow bar + page-kind
swap on /leads and /applications). Goal: catch every place an
operator-visible regression or security hole could be hiding before
Adon's team starts driving the system.

# Live findings — fixed in this round

### F1. Production data drift on legacy enum values

Five SunBiz tenant_records rows were still on the pre-rework enum:

| id (prefix) | entity     | old value          | new value                |
|-------------|------------|--------------------|--------------------------|
| 62925d44    | application| status=submitted   | submitted_to_underwriting|
| 44805fb7    | offer      | stage=expired      | approved_never_funded    |
| e5b8bc0b    | offer      | stage=accepted     | funded                   |
| 75d3bcaf    | offer      | stage=accepted     | funded                   |
| f794ebe1    | offer      | stage=accepted     | funded                   |

In the chevron pipeline view these would have rendered as raw-string
fallbacks (no stage chip, no chevron filter match) — Adon would have
seen "0 in every column" and one orphan row floating in the table.

**Fix:** `scripts/backfill_sunbiz_stages.py` ships as an idempotent,
dry-runnable, audit-logged one-shot. Applied to production tonight;
re-run confirms 0 further changes needed. Log at
`state/backfill_sunbiz_stages.log` documents every mutation.

### F2. Pixel-tracking endpoint can be flooded with known reservation_ids

`/api/track/open/[id]` accepts unauthenticated GETs (it has to —
mail clients fetch the pixel without a session). Each successful hit
inserted a row in `email_open_events`. A malicious actor who scrapes
a real reservation_id from an outbound email's HTML could spam the
route to inflate the open-count for that message.

Cross-tenant leakage was already impossible (the route resolves
tenant_id from the interaction row, never trusts the URL parameter),
but row inflation was a real noise vector.

**Fix:** migration 050 adds partial unique index
`(outbound_message_id, ip_hash) WHERE ip_hash IS NOT NULL`. Same
recipient (by IP hash) only counts once per message, regardless of
re-opens. Anonymous opens — where corporate proxies strip
`x-forwarded-for` — skip the constraint so they still record (over-
counting anon beats silently dropping legit signal). Route now uses
upsert with `ignoreDuplicates: true` so the index doesn't turn into
a 500 source.

# Verified clean — no fix needed

| # | Check                                                | Result |
|---|------------------------------------------------------|--------|
| C1| Migration 049 tables (email_open_events / lead_documents / agent_alerts) exist with right shape + RLS | ✓ live, queryable, 0 rows |
| C2| Timeline API `/api/leads/[id]/timeline` tenant isolation | ✓ every feed filters by `tenant_id = resolveTenantId()` |
| C3| Tracking-pixel cross-tenant isolation                | ✓ tenant_id resolved from interaction row, never from URL |
| C4| Dashboard alerts panel tenant scoping                | ✓ `.eq("tenant_id", tenantId)` on every query |
| C5| Live drip_sequences row trigger filters              | ✓ only existing row triggers on `viewed_application` (still valid) |
| C6| Live forms config `on_complete_stage` values         | ✓ no forms exist for SunBiz tenant yet |
| C7| Live funded_deals stage values                       | ✓ no rows; enum unchanged anyway (renewal-window-derived) |
| C8| Codebase grep for stale stage string literals        | ✓ only OASIS-tenant sequences (correct, different enum) + doc comments |
| C9| Form-submission stage write path                     | ✓ fully data-driven from form.on_complete_stage; no hardcoded defaults |
| C10| AI lead-scoring path                                | ✓ doesn't touch stage |
| C11| Offer Accept route — flips application.status to funded | ✓ verified in route handler |
| C12| TypeScript `tsc --noEmit` across the workspace      | ✓ exits 0 |

# Known tech debt — NOT fixed (priority calls for CC)

These are real but none are regressions or production breakers.

1. **Triple source of truth for stage labels** —
   `lib/manifest/seeds.ts` (enum_values) + `lib/sunbiz-stage-meta.ts`
   (hex colors) + `lib/manifest/format.ts` (semantic tones) all carry
   the same stage list shape. Adding a stage requires three edits.
   Proper fix is encoding `{label, bg, fg, tone}` into the manifest
   entity schema itself. Effort ~3h.

2. **Pipeline table cells show short-hash UUIDs for lead_id / lender_id** —
   "Lead: 8f3a2e1c" instead of "Lead: Acme Roofing." Renders cleanly
   but requires the operator to click in. Fix is a server-side join
   against the referenced record's business_name / lender name.
   Effort ~2h.

3. **`pipeline_entity` page kind is hardcoded for SunBiz** —
   looks up stage list by entity name (lead / application / offer).
   SUGA / future client tenants can't reuse it without code edits.
   Generalize by reading `stage_meta` from the manifest. Effort ~3h.

4. **`offer.stage` and `application.status` share identical enum
   lists** — semantically correct (offer is a per-lender sub-detail of
   the application's Opportunity Pipeline) but mildly wasteful. No
   action item; flagging for future schema review.

5. **Application columns in pipeline list don't show Submitted At
   nicely for null values** — empty date column shows "—" via
   formatVal. Acceptable.

# Commit chain since the start of this work

```
8d5c8d5  Round 3 substrate (migration 049 + tracking pixel + classifier)
d25697e  AI editor advertises new pipeline page kind
9561430  Round 3.5 UI (Timeline panel + missing-info banner + alerts)
82d11de  Honest copy on missing-info banner + handoff gap doc
4a355c2  Round 4 (Salesforce-parity stages + arrow bar + cleaned nav)
6bcdba4  Sync LeadsTableClient stage tabs + import default
eecc076  Replace /leads with Lead Pipeline, /applications with Opp Pipeline
92cc8a7  Format pipeline table cells (UUID short-hash, currency, dates)
(this)   Backfill production stage drift + dedup index on pixel endpoint
```

All commits live on `main`. Vercel auto-deployed every push; latest
URL is `agent-dashboard-cc90210.vercel.app`.

# Sign-off

System is structurally secure (RLS on every new table, tenant-id
filters on every query, fail-closed semantics on unauthenticated
endpoints), integrity-driven (production data backfilled to match
the new enums, idempotent migration scripts, audit logs), and ready
for Adon's team to start driving real leads through.
