---
adr: 0008
title: leads (tenant_id, lower(email)) unique constraint + atomic upsert
status: proposed
date: 2026-06-09
deciders: CC, Bravo
supersedes: —
superseded_by: —
related: ADR-0001 (skill dependency classification), Codex round-7 audit 2026-06-09
---

# ADR-0008 — leads (tenant_id, lower(email)) unique constraint + atomic upsert

## Context

`scripts/integrations/send_gateway.py:resolve_lead_id` does check-then-insert for first-touch sends:

```python
existing = db.table("leads").select("id").eq("email", norm).eq("tenant_id", tenant_id).limit(1).execute()
if existing.data:
    return existing.data[0]["id"]
# else INSERT new row
```

Codex audit 2026-06-09 round-7 [high] flagged the race: two concurrent first-touch sends to the same NEW address can both observe "no row," both INSERT distinct lead_ids, then both reserve via `reserve_send_slot` (keyed on lead_id) and both ship — duplicate outreach + corrupted CRM history.

Today's SunBiz volume makes this collision extremely rare in practice, but the surface exists. Multi-tenant onboarding (PropFlow, Adon's tenant, future client agents) will fan out concurrent sends and re-expose this.

## Decision

Add a partial unique index on `leads (tenant_id, lower(email))` and convert `resolve_lead_id` to an atomic upsert path.

The migration is additive and reversible:

```sql
-- database/0NN_leads_tenant_email_unique.sql
-- Partial unique: only enforce when both columns are non-null.
-- Tenantless legacy rows (OASIS personal tenant pre-multi-tenant)
-- keep the NULL tenant_id and are not constrained.
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS leads_tenant_email_lower_uq
  ON public.leads (tenant_id, lower(email))
  WHERE tenant_id IS NOT NULL;
```

Then `resolve_lead_id` becomes:

```python
created = db.table("leads").upsert(
    {
        "name": norm.split("@")[0],
        "email": norm,
        "tenant_id": tenant_id,
        "status": "new",
        "source": "gateway_autocreate",
        "created_at": now,
        "updated_at": now,
    },
    on_conflict="tenant_id,email",
    ignore_duplicates=True,
).execute()
# Re-select to capture the row id (the existing one OR the just-inserted one).
fetched = db.table("leads").select("id").eq("email", norm).eq("tenant_id", tenant_id).limit(1).execute()
return fetched.data[0]["id"] if fetched.data else None
```

The upsert + re-select pattern is atomic at the DB layer: two concurrent first-touches converge on the same row id.

## Why this is a separate ADR-tracked change instead of "just fix it now"

Three reasons:

1. **The migration touches a load-bearing table.** `leads` is referenced by `lead_interactions`, `lead_documents`, `lead_outreach_batch`, `cold_outreach_recipients`, and several Supabase functions. The CONCURRENT index build is online but the policy change (unique constraint where none existed) deserves an audit trail and a coordinated deploy with the operator awake.

2. **Existing duplicate rows must be reconciled first.** A pre-migration scan needs to find rows that would violate the new constraint. The reconciliation rule (keep oldest? Merge interaction history? Mark losers as superseded?) is a business decision, not a code decision. CC owns this call.

3. **The code-side `on_conflict` call needs Supabase Python client capability verification.** The current Supabase Python SDK version in `.env.agents` may or may not support the `on_conflict` parameter shape used above. A pre-check + targeted migration is safer than blanket replacement.

## Consequences

**Accepted today (this ADR):**

- The race is documented, surfaced in code comments, and tracked.
- Round-7's tenantless+tenant-bound ambiguity fix landed in the same commit so the lookup-side leak is closed even before the constraint exists.

**Deferred to a separate change (to be scheduled by CC):**

- Migration `database/0NN_leads_tenant_email_unique.sql`
- Pre-migration duplicate-row reconciliation script (read-only audit first; remediation only after CC's reconciliation decisions).
- `resolve_lead_id` upsert refactor + concurrency regression test (two simultaneous sends → one lead row, one reservation).

**Risk of deferring:** the race remains theoretically exploitable. Mitigations holding today:

- Current SunBiz volume makes the race extremely rare (~1 first-touch send per minute peak; concurrent first-touches to the SAME new address near-zero).
- The reservation RPC (`reserve_send_slot` via advisory lock) still prevents the SAME lead row from being double-sent — the duplicate-outreach failure mode requires the race to produce two DISTINCT lead rows for the same email.

## Next-step trigger

This ADR should move from `proposed` → `accepted` when ONE of:

1. PropFlow / Adon's tenant / a new client agent onboards (multi-tenant scale).
2. SunBiz volume rises past ~10 first-touch sends/minute.
3. A real duplicate-lead incident occurs in production.

Earliest pre-emptive scheduling: alongside the multi-tenant scaffolding work CC's currently planning.
