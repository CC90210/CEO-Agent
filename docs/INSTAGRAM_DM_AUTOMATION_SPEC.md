---
tags: [instagram, dm, zernio, automation, oasis, leads]
last_updated: 2026-08-20
---

# OASIS Instagram DM automation — verified API map + build spec

Every endpoint below was probed live against the real Zernio API with the empire
`LATE_API_KEY` on 2026-08-20. Nothing here is inferred from documentation alone.

## Verification method (use it before trusting any new path)

Zernio returns **HTTP 200 with its web-app HTML** for any unknown path. A naive
probe therefore reports every guess as "exists". Always probe a deliberate
control path alongside real candidates and compare bodies:

```
/v1/accounts               200  JSON   -> REAL
/v1/dms                    200  HTML   -> ABSENT
/v1/CONTROL-FAKE-PATH      200  HTML   -> ABSENT   (the control)
```

This cost a wrong conclusion once already ("Zernio has no DM API" — false).

## Confirmed live facts

- Base URL: `https://zernio.com/api`
- Auth: `Authorization: Bearer $LATE_API_KEY`
- Connected account: **`[instagram] oasisaisolutions`**, `platform: "instagram"`,
  `accountId` begins `699c92828ab8ae478b3e…`
- **The inbox is already populated: 50 real conversations.**

### Endpoints that exist

| Endpoint | Status |
|---|---|
| `GET /v1/accounts` | REAL — lists connected accounts |
| `GET /v1/inbox/conversations` | REAL — `{data[], pagination, meta}` |
| `GET /v1/inbox/conversations/{id}/messages?accountId={accountId}` | REAL — `accountId` is **required**; omitting it returns a precise 400 |

Conversation object fields:
`id, accountId, accountUsername, platform, participantId, participantName,
participantUsername, participantPicture, lastMessage, updatedTime, status,
unreadCount, instagramProfile, url`

### Webhook transport (documented, path not yet located)

Zernio supports inbound webhooks; the **`message.received`** event is the one to
subscribe to. Other inbox events: `message.sent`, `conversation.started`,
`message.edited`, `message.deleted`, `message.delivered`, `message.read`,
`message.failed`.

Delivery semantics from the docs: signed with an **`X-Zernio-Signature`** header
when a webhook secret is configured; **7 retry attempts** then a dead-letter
queue; **dedupe on the webhook event ID**; acknowledge fast and do heavy work
asynchronously, or retries will double-message a prospect.

`/v1/webhooks`, `/v1/webhook-endpoints`, `/v1/inbox/webhooks`,
`/v1/user/webhooks` and `/v1/settings/webhooks` are all ABSENT. The create-webhook
path still needs locating — likely via the Zernio dashboard UI rather than the API.

## Recommended architecture: POLL FIRST

Poll on a cron rather than waiting on webhook registration, because:

1. Every endpoint it needs is **already verified working**.
2. It requires no public URL, no secret exchange, no dashboard step.
3. **It appears natively in the Automations tab** — the operator's explicit
   requirement — because it *is* a cron job, not a passive endpoint.

Add the webhook later as a latency optimisation; the classify/reply/upsert core
is identical either way, so nothing is wasted.

## Build

Poller (`scripts/integrations/instagram_dm_poller.py`, run from `cron_engine.py SEED_JOBS`):

1. `GET /v1/inbox/conversations`, keep `platform == "instagram"` **and**
   `accountUsername == "oasisaisolutions"`. Every other connected profile is out
   of scope — New Haven pinned to its own profile for the same reason.
2. For each conversation with `unreadCount > 0`, fetch messages with the required
   `accountId`.
3. Keyword classifier, case-insensitive, OASIS intent:
   `audit, automation, automate, website, site, pricing, price, cost, help,
   interested, book, call, demo, ai`. **Non-matching DMs are logged only, never
   auto-replied.**
4. On match, reply with the AI-audit form:
   `https://oasisai.work/f/oasis-ai-cc/ai-audit`
   (that form now requires a phone number on step 1, so DM leads arrive reachable).
5. Upsert the sender as a lead in `tenant_records`: `source = "instagram_dm"`,
   handle from `participantUsername`, `stage = "researched"`, unassigned.
   Reuse `scripts/lib/lead_contract.py` for the field contract.
6. **24-hour per-sender cooldown**, keyed on `participantId`, so a second DM does
   not re-trigger. Store the last-sent stamp on the lead.

### Safety rules (carried from the New Haven brief — non-negotiable)

- **Test to CC's own handle first, never a real lead.** With marketing about to
  drive real DMs this matters more here than it did there.
- Dry-run mode by default; live sending behind an explicit env flag.
- Outbound goes through the existing gateway discipline — killswitch, caps, audit.

## Open item

Locate the create-webhook path (dashboard or API). Not a blocker: the poller
delivers the full outcome without it.
