---
tags: [data]
last_updated: 2026-05-18
---

# Bravo ↔ Atlas Pulse Protocol (CEO side)

> Canonical handshake between Bravo (CEO agent, this project) and Atlas (CFO agent, `c:\Users\User\APPS\CFO-Agent`). One-way writes, no shared mutable state.

**Full contract:** `c:\Users\User\APPS\CFO-Agent\brain\AGENT_ORCHESTRATION.md`

---

## What Bravo publishes here

**File:** `ceo_pulse.json` (this folder)

**Schema:**

```json
{
  "updated_at": "ISO-8601 with tz offset",
  "mrr_usd": 2982,
  "mrr_growth_30d_pct": null,
  "clients_active": 3,
  "clients_top": [{"name": "Top retainer client", "share_pct": 94}],
  "pipeline_qualified_usd": 0,
  "committed_spend_next_30d_cad": 0,
  "next_launch_or_campaign": null,
  "blocker_cfo_needs_to_know": null,
  "v6": {
    "mode": "off | shadow | on",
    "hook_modes": {
      "secret_guard": "enforce | report | off",
      "exec_guard":   "enforce | report | off",
      "state_guard":  "enforce | report | off"
    },
    "state_db": {
      "session_log_count": 70,
      "transaction_count": 38,
      "size_kb": 112.0,
      "last_heartbeat": "ISO-8601"
    },
    "fts5": {
      "sources": 224,
      "chunks": 2828,
      "last_indexed": "ISO-8601",
      "size_kb": 7156.0
    }
  }
}
```

**Freshness:** Update on every significant revenue / pipeline / spend change. Atlas treats anything >7 days old as stale.

**V6.0 telemetry block (added 2026-05-10):** auto-populated by `scripts/pulse_publish.py refresh` on every publish. Sibling agents that don't recognize V6.0 fields ignore them (JSON additive contract). When Atlas / Maven / Aura / Hermes upgrade, they can use the `v6.mode` field to decide whether Bravo's `memory/SESSION_LOG.md` is canonical (V5.5 mode) or auto-generated (V6.0 mode), and the `state_db.last_heartbeat` for liveness checks instead of the markdown frontmatter.

---

## What Bravo reads

**File:** `c:\Users\User\APPS\CFO-Agent\data\pulse\cfo_pulse.json`

Read this BEFORE:
- Authorizing any spend >$500 CAD (check `spend_gate` field)
- Raising / dropping prices (check `tax_reserve_required_cad` — tax drag changes margin math)
- Committing to ad campaigns (check `liquid_cad` vs `montreal_floor_target_cad` — don't burn the Montreal floor)
- Scheduling a launch (check `open_tax_deadlines` — don't stack work during CRA windows)

If `spend_gate: "tight"` or `"frozen"`, defer discretionary spend and flag CC.

---

## Hard rules

1. **Bravo NEVER writes to `CFO-Agent/`.** Only reads `cfo_pulse.json`.
2. **Atlas NEVER writes to `Business-Empire-Agent/`.** Only reads `ceo_pulse.json`.
3. **All mutations to CC's actual business state** (new client, raise, launch) happen in Bravo's normal brain/memory files — then Bravo publishes a fresh `ceo_pulse.json`. The pulse file is a derived snapshot, not the source of truth.

---

## Boot-strapping

Bravo's first `ceo_pulse.json` has not been written yet. Until it exists, Atlas flags Bravo state as "unknown" and errs conservative. Template to start from:

```json
{
  "updated_at": "2026-04-17T00:00:00-04:00",
  "mrr_usd": 2982,
  "mrr_growth_30d_pct": null,
  "clients_active": 3,
  "clients_top": [
    {"name": "Top Client", "share_pct": 60},
    {"name": "Stripe Client A", "share_pct": 25},
    {"name": "Stripe Client B", "share_pct": 15}
  ],
  "pipeline_qualified_usd": 0,
  "committed_spend_next_30d_cad": 0,
  "next_launch_or_campaign": null,
  "blocker_cfo_needs_to_know": "Top-client concentration at 94% — need 2-3 additional retainer clients before Montreal move"
}
```

**When Bravo's CLI or agent ships a pulse command, this path is the target.**
