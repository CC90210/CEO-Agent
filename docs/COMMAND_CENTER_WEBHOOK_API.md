# OASIS Command Center — Public Webhook API

> Base URL: `https://agent-dashboard-cc90210.vercel.app` (production)

## Auth

Every webhook endpoint takes `Authorization: Bearer <secret>` headers, where the secret is issued per integration. Generate via:

```bash
python scripts/n8n_webhook_secret.py issue --profile-email <operator@email>
```

Multiple endpoints share the same secret-table model (`n8n_webhook_secrets`). Secrets are SHA-256 hashed at rest. Lose the secret → revoke + re-issue.

## Endpoints

### POST /api/inbound/n8n
Accepts a classified inbound email from n8n. Idempotent on `x-oasis-message-id` header.

**Headers:**
```
Authorization: Bearer <secret>
Content-Type: application/json
x-oasis-profile-id: <uuid>      # which operator this inbound belongs to
x-oasis-message-id: <string>    # optional, for dedup
```

**Body:**
```json
{
  "from_email": "lead@example.com",
  "from_name": "Some Lead",
  "subject": "Re: your pitch",
  "content": "interested in the pilot…",
  "received_at": "2026-04-30T17:00:00Z",
  "classification": {
    "intent": "info_request",
    "sentiment": "positive",
    "priority": "medium",
    "category": "business_opportunity"
  }
}
```

**Returns:** `{ ok: true, lead_id, interaction_id }`

### POST /api/webhook/lead-update *(planned)*
Update an existing lead (status change, score change, notes).

### POST /api/webhook/agent-event *(planned)*
Publish an event to the agent_events bus (lights up the Agents tab).

## Realtime updates on the dashboard

The Command Center subscribes to Supabase Realtime channels for:
- `lead_interactions` — new inbound/outbound shows in Pipeline within ~1s
- `agent_state_snapshot` — agent ticks update the Agents tab live
- `integrations_health` — service status dots flip in real time

Clients don't need to do anything to trigger these — write to the table via the webhook above and the dashboard updates itself.

## Rate limits

- 10 req/sec per secret (burst)
- 1000 req/hour per secret (sustained)

Exceeding either returns `429 too many requests`. Contact CC for higher limits.

## Errors

| Status | Meaning |
|---|---|
| 200 | OK |
| 400 | Body validation failed |
| 401 | Missing or invalid Bearer secret |
| 404 | Operator profile / secret not found |
| 409 | Duplicate (when `x-oasis-message-id` already seen) |
| 429 | Rate limit |
| 500 | Server error — contact CC |

## Smoke test

```bash
curl -X POST https://agent-dashboard-cc90210.vercel.app/api/inbound/n8n \
  -H "Authorization: Bearer YOUR_SECRET" \
  -H "x-oasis-profile-id: YOUR_PROFILE_UUID" \
  -H "Content-Type: application/json" \
  -d '{"from_email":"test@example.com","subject":"smoke test","content":"hi","classification":{"intent":"info_request"}}'
```

Expected: `{"ok":true,"lead_id":"...","interaction_id":"..."}`. Check the Pipeline page within ~1s — the row appears live via Supabase Realtime.
