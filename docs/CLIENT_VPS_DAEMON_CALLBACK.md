---
title: Client VPS daemon → dashboard HTTP callback pattern
date: 2026-05-16
status: ACTIVE — required reading before any client agent moves off CC's machine
tags: [docs]
last_updated: 2026-05-22
---

# Why this exists

Today (2026-05-16) every Python automation daemon runs on **CC's Windows box** via PM2:
`sequence_runner`, `lender_response_classifier`, `event-router`,
`bravo-scheduler`, `claude-bridge`, `claude-bridge-ping`, etc. They all read `.env.agents`
locally to get the Supabase service-role key + dashboard URL + per-service credentials.
That works because CC is the operator AND the host.

**It does not work when SunBiz gets deployed to its own VPS.** A SunBiz daemon running
in DigitalOcean (or wherever Adon hosts it) shouldn't carry the central Supabase service-
role key — that key has cross-tenant write access and one VPS compromise leaks every
tenant's data. Each client deployment needs **per-tenant credentials** and a clean way
to push updates back to the central dashboard.

The closed-loop pattern this doc covers: **daemons HTTP POST to the dashboard with their
own bridge bearer token. The dashboard validates the token, scopes the write to the
token's tenant, and applies the change to `tenant_records`.**

# The endpoint

`POST /api/bridge/records/[entity]` — create a row
`PATCH /api/bridge/records/[entity]?id=<uuid>` — update a row

**Auth:** Bearer bridge token, hashed in `bridge_pairings.bridge_token_hash`. Minted
during onboarding by `/api/auth/pair` (already exists). One token per tenant + machine;
revocable via `bridge_pairings.revoked_at`.

**Tenant scoping:** The endpoint reads the pairing row's `tenant_id` and writes there.
The request body's tenant_id (if present) is **ignored**. A SunBiz daemon literally
cannot write into OASIS HQ's records even if it tried.

**Events:** Mutations route through `createRecord` / `updateRecord` in
`lib/manifest/data.ts`, which auto-publishes `BRAVO_RECORD_STATUS_CHANGED` on stage/
status transitions. So a daemon callback fires the same drips a dashboard-driven update
would. Closed loop intact.

# What daemons should call it for

| Daemon | What it writes |
|---|---|
| `lender_response_classifier` (Gmail thread classifier) | PATCH `application_lender_threads/<id>` with `{status: 'approved'\|'declined'\|...}` |
| `inbox_monitor` (future — generic inbound email) | POST `lead` or PATCH `lead/<id>` with new touch timestamps |
| `sequence_runner` (drip step results) | PATCH `lead/<id>` with `last_contacted_at` after a send |
| `bank_statement_parser` (Phase 7) | PATCH `application/<id>` with `underwriting_jsonb` populated |
| `funnel_fast_poll` (CC's existing job) | POST `lead` for fresh funnel submissions |

Today these all write through the Turso switch (`sitecustomize` patch / `turso_supabase_compat`
— direct Supabase pre-2026-08). As we deploy to client VPSes one by one, each
daemon's writes get re-routed through this endpoint instead.

# Daemon-side Python pattern

```python
import os
import requests

DASHBOARD_URL = os.environ["AGENT_DASHBOARD_URL"]  # e.g. https://agent-dashboard-cc90210.vercel.app
BRIDGE_TOKEN = os.environ["BRIDGE_TOKEN"]          # minted per-tenant during onboarding

def upsert_lead(data: dict) -> dict:
    """Create a lead — closed-loop callback to the dashboard."""
    r = requests.post(
        f"{DASHBOARD_URL}/api/bridge/records/lead",
        headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"},
        json={"data": data},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["record"]

def update_thread_status(thread_id: str, status: str, last_summary: str) -> dict:
    """Classifier callback — flip lender thread status after Claude classifies."""
    r = requests.patch(
        f"{DASHBOARD_URL}/api/bridge/records/lender_thread",
        params={"id": thread_id},
        headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"},
        json={"patch": {"status": status, "last_response_summary": last_summary}},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["record"]
```

That's it — no Supabase client on the daemon side. The daemon's `.env.agents` carries
only the bridge token + dashboard URL + the service-specific credentials (Gmail OAuth,
Anthropic key, etc.) it needs to do its actual job.

# Onboarding flow change for VPS deployments

When provisioning a new client tenant on a VPS:

1. Operator runs the dashboard onboarding wizard (already exists at `/onboarding`).
2. Wizard mints a bridge pair code via `/api/auth/pair`. That endpoint writes a row to
   `bridge_pairings` with `bridge_token_hash = sha256(plaintext_token)`.
3. Plaintext token is shown ONCE to the operator. They copy it into the VPS's
   `.env.agents` as `BRIDGE_TOKEN=...`.
4. VPS daemons read `BRIDGE_TOKEN` + `AGENT_DASHBOARD_URL` from `.env.agents` and POST
   to the callback endpoint.
5. To revoke: dashboard admin sets `bridge_pairings.revoked_at` — every subsequent
   daemon request returns 403 within one bridge_pairings cache TTL.

The pair-code flow already works for CC's machine. The VPS extension is: the daemons
swap their direct DB calls (Turso via the compat switch; Supabase pre-2026-08) for HTTP callbacks.

# What's NOT in scope for this pattern

- **Reading data from the dashboard.** Daemons that need to read tenant_records still
  go through the regular service-role Supabase client (when on CC's host) or — for
  VPS deployments — a future `GET /api/bridge/records/[entity]` endpoint that mirrors
  this one. For now the callback channel is write-only.
- **Cross-tenant lookups** (e.g., a SunBiz daemon wanting to read OASIS HQ data).
  Architecturally we never want that.
- **The bridge daemon itself.** `claude-bridge` is the chat-routing HTTP server that
  the dashboard talks to. This callback channel is the opposite direction.

# Migration path

We don't need to migrate today's daemons. They keep their direct DB access (Turso via
the compat switch) on
CC's host. The callback endpoint is **infrastructure for future deployments**.

When SunBiz goes on a VPS:

1. Generate a SunBiz-specific bridge token.
2. Deploy daemons + `.env.agents` (with the bridge token + Anthropic / Gmail creds,
   NO Supabase service-role key).
3. Daemons hit `/api/bridge/records/[entity]` for every mutation.
4. The dashboard's existing event-bus (V6 Apex Phase 3) carries the BRAVO_RECORD_STATUS_
   CHANGED events to anyone subscribed — so drips, the lender-response classifier, and
   the renewal-window cron all keep working unchanged.

# Acceptance / smoke test

```bash
# From any machine that has a valid bridge token in .env.agents:
curl -X POST \
  -H "Authorization: Bearer $BRIDGE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"data": {"name": "Smoke Test", "email": "smoke@example.com", "phone": "5551234567", "stage": "cold"}}' \
  https://agent-dashboard-cc90210.vercel.app/api/bridge/records/lead

# → { "ok": true, "record": { "id": "...", "entity_type": "lead", "data": {...} } }
# The lead immediately appears on /t/sun/leads if the token is for the SunBiz tenant.
```

If the curl returns 401: token is wrong or the bridge_pairings row is revoked.
If 400 with `data_object_required`: body shape is bad.
If 200 with a record but no event downstream: check `state/event_router.log` — the
event bus might be paused.

# Reading order for any future Bravo / Maven / contractor onboarding

1. `brain/EVENT_BUS_CONTRACT.md` (V6 Apex Phase 3 event bus — the substrate this builds on)
2. `apps/command-center/app/api/bridge/ping/route.ts` (the prior-art bridge bearer-token flow)
3. `apps/command-center/app/api/bridge/records/[entity]/route.ts` (this endpoint)
4. `apps/command-center/lib/manifest/data.ts` (`createRecord` / `updateRecord` — what
   the endpoint dispatches to)

## Obsidian Links
- [[docs/INDEX]]
- [[brain/STATE]]
