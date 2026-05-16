---
title: SunBiz CRM — known gaps blocking commercial SMS shipment
date: 2026-05-15
status: ACTIVE — close before any real commercial SMS send to a SunBiz lead
---

# Known gaps from Codex adversarial review (2026-05-15)

Codex caught 5 real bugs in the SunBiz CRM Phase 4-7 substrate. Two were
fixed in commit chain on 2026-05-15. Three remain — all block commercial
SMS shipment to real leads.

## Fixed in this session

| # | Codex Finding | File | Fix commit |
|---|---|---|---|
| 2 | SMS dispatch skipped reservation idempotency pattern (concurrent send race) | `scripts/send_gateway.py` SMS branch | (this session) |
| 5 | `/api/forms/view` missing tenant slug cross-check | `apps/command-center/app/api/forms/view/route.ts` | (this session) |
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

### Finding #4 — Commercial SMS has no opt-out / DNC enforcement (HIGH — CASL/TCPA risk)

**File:** `scripts/send_gateway.py:1622-1626` (`should_suppress` check is email-only)

**Bug:** The CASL suppression gate checks `should_suppress(to_email)` but NOT `should_suppress_phone(to_phone)`. A lead that replied STOP to a Twilio short code would still get the next drip step. Plus first-touch commercial SMS doesn't auto-append "Reply STOP to opt out." per the SUN_SEED compliance manifest.

**Fix:** Multi-step compliance work:

1. **Add phone-side suppression** (`scripts/casl_compliance.py`):
```python
PHONE_SUPPRESSIONS_CSV = DATA_DIR / "phone_suppressions.csv"

def should_suppress_phone(phone: str) -> bool:
    """Return True if the E.164 phone is on the DNC list."""
    normalized = (phone or "").strip()
    if not normalized: return True
    if not PHONE_SUPPRESSIONS_CSV.exists(): return False
    # CSV reader matching email path semantics
    ...
```

2. **SMS opt-out webhook handler** — Twilio + TT both fire webhooks on inbound STOP. Add `/api/webhooks/twilio/sms-inbound` + `/api/webhooks/texttorrent/sms-inbound` that parse the body for "STOP" / "UNSUBSCRIBE" / "QUIT" / "CANCEL" and call `add_phone_suppression()`.

3. **First-touch STOP-language enforcement** in `send_gateway` SMS branch:
```python
if intent == "commercial":
    # Check whether this is the first SMS to this lead
    prior_sms = db.table("lead_interactions").select("id", count="exact").eq("lead_id", lead_id).eq("channel", "sms").execute()
    if (prior_sms.count or 0) == 0 and "STOP" not in body_text.upper():
        body_text = body_text.rstrip() + "\n\nReply STOP to opt out."
```

4. **Gate the existing CASL suppression check** for SMS:
```python
if intent == "commercial":
    if to_email and should_suppress(to_email):
        return {"status": "suppressed", ...}
    if channel == "sms" and to_phone and should_suppress_phone(to_phone):
        return {"status": "suppressed", "reason": f"{to_phone} is on SMS DNC list", ...}
```

**Why deferred:** ~3 hours of work spanning send_gateway + casl_compliance + two new webhook routes. Operator needs to verify the webhooks land on Twilio/TT configuration BEFORE any commercial SMS goes out.

---

## Cutover gate

Before SunBiz's first real commercial-SMS drip campaign fires:

- [ ] Ship migration 045: atomic-claim + one-per-lead unique index (closes #1 + #3)
- [ ] Ship phone-side CASL suppression (closes #4 step 1)
- [ ] Ship the two SMS-inbound webhook handlers (closes #4 step 2)
- [ ] Ship first-touch STOP-language enforcement (closes #4 step 3)
- [ ] Verify a real STOP reply suppresses the next drip step on a test lead
- [ ] Verify a duplicate enrollment via two agent_events doesn't double-send

Estimated ~5 hours of focused work + verification. Schedule before SunBiz beta operators start blast cadences.
