---
title: SunBiz CRM — known gaps blocking commercial SMS shipment
date: 2026-05-15
status: ACTIVE — close before any real commercial SMS send to a SunBiz lead
---

# Known gaps from Codex adversarial review (2026-05-15)

Codex caught 5 real bugs in the SunBiz CRM Phase 4-7 substrate. Three are
now fixed in the 2026-05-15/2026-05-16 commit chain. Two remain and still
block commercial SMS shipment to real leads.

## Fixed in this session

| # | Codex Finding | File | Fix commit |
|---|---|---|---|
| 2 | SMS dispatch skipped reservation idempotency pattern (concurrent send race) | `scripts/send_gateway.py` SMS branch | (this session) |
| 5 | `/api/forms/view` missing tenant slug cross-check | `apps/command-center/app/api/forms/view/route.ts` | (this session) |
| 4 | Commercial SMS had no opt-out / DNC / STOP enforcement | `scripts/casl_compliance.py`, `scripts/send_gateway.py`, `/api/webhooks/{twilio,texttorrent}/sms-inbound` | R3-6 (this commit; final SHA reported after commit) |
| 3 | `one_per_lead` enrollment had no unique constraint (DB-level race) | `database/045_sequence_state_one_per_lead.sql` + `scripts/sequence_runner.py:_enroll_step` | 2026-05-15 evening |

## Still open — DO NOT enable real-lead SMS until these close

### Finding #1 — sequence_state rows not atomically claimed (HIGH)

**File:** `scripts/sequence_runner.py:511-518` (the `execution_tick` select-then-send pattern)

**Bug:** `execution_tick` runs `select ... where status='scheduled' and scheduled_for <= now()`, then performs `_send_step` BEFORE any status update. Two workers (or a daemon that overlaps with a PM2 restart across a tick boundary) can both read the same scheduled row + both physically send. The send_gateway cooldown is downstream — by the time it fires, the row-level race has already escaped.

**Fix:** Atomic claim before `_send_step`:
```python
# Add to migration 043 (or 045):
ALTER TABLE sequence_state ADD COLUMN claimed_at timestamptz;
ALTER TABLE sequence_state ADD COLUMN claimed_by text;
-- Composite index supporting the claim:
CREATE INDEX idx_sequence_state_claimable
  ON sequence_state (scheduled_for) WHERE status='scheduled' AND claimed_at IS NULL;
```

Then in `execution_tick`:
```python
# Atomic lease — only the row whose UPDATE returns 1 row proceeds.
claimed = sb.rpc("claim_sequence_state_row", {"row_id": row["id"]}).execute()
if not claimed.data:
    continue  # another worker won
```

Plus an `rpc("claim_sequence_state_row")` SQL function:
```sql
CREATE OR REPLACE FUNCTION claim_sequence_state_row(row_id uuid)
RETURNS sequence_state LANGUAGE sql AS $$
  UPDATE sequence_state
     SET claimed_at = now(),
         claimed_by = current_setting('request.jwt.claims', true)
   WHERE id = row_id AND status = 'scheduled' AND claimed_at IS NULL
  RETURNING *;
$$;
```

**Why deferred:** Needs a new migration (045) + an RPC function + a daemon code change. ~2 hours of careful work + verification.

---

### Finding #3 — `one_per_lead` enrollment has no unique constraint (HIGH)

**File:** `scripts/sequence_runner.py:338-340` + `database/043_drip_sequences.sql` (no UNIQUE index)

**Bug:** `_has_active_state` SELECTs then INSERTs. Two concurrent agent_events for the same lead, or two daemon runs that overlap, both observe "no active state" and both insert. The duplicate state rows then both fire step 0.

**Fix:** Add to a new migration 045:
```sql
CREATE UNIQUE INDEX idx_sequence_state_one_active_per_lead
  ON sequence_state (sequence_id, lead_id)
  WHERE status IN ('scheduled', 'failed');
```

Then update `_enroll_step` to use `INSERT ... ON CONFLICT DO NOTHING`:
```python
sb.table("sequence_state").upsert(
    payload,
    on_conflict="sequence_id,lead_id",
    ignore_duplicates=True,
).execute()
```

**Why deferred:** Same migration that adds atomic claim from #1. Ship both together in migration 045.

---

## Cutover gate

Before SunBiz's first real commercial-SMS drip campaign fires:

- [ ] Ship migration 045: atomic-claim + one-per-lead unique index (closes #1 + #3)
- [x] Ship phone-side CASL suppression (closes #4 step 1)
- [x] Ship the two SMS-inbound webhook handlers (closes #4 step 2)
- [x] Ship first-touch STOP-language enforcement (closes #4 step 3)
- [ ] Verify a real STOP reply suppresses the next drip step on a test lead
- [ ] Verify a duplicate enrollment via two agent_events doesn't double-send

Estimated ~5 hours of focused work + verification. Schedule before SunBiz beta operators start blast cadences.
