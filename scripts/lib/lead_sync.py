"""Lead-status dual-write: keep `leads.status` and `tenant_records.data.stage` in sync.

V6.8.3 — extracted from `lead_engine.cmd_update` (commit 4999d91) so every
writer of `leads.status` can mirror the change into `tenant_records` with
one call, not by copy-pasting 60 lines into each tool.

Two parallel lead systems coexist (per migrations 060 + 062):

  - `public.leads`    — pre-2026-05-15 OASIS canonical, 6 statuses
  - `tenant_records`  — manifest-era (entity_type='lead'), 11 stages

Mapping (migration 062 official):

    leads.status   → tenant_records.data->>'stage'
    new            → new_contact
    contacted      → outreach
    won            → active_client
    qualified / proposal / negotiation / lost → unchanged

Stages that exist only in `tenant_records` (discovery, onboarding,
churned, archived) are owned by the command-centre dashboard; this
helper never tries to set them.

Usage:

    from lib.lead_sync import sync_lead_status_to_tenant_records
    result = sync_lead_status_to_tenant_records(client, lead_id, "contacted")
    # result is "synced(N)" | "no_record" | "no_mapping" | "error:<type>"

Best-effort by design: never raises, returns a status string the caller
can log or surface. Match priority:
    1. `tenant_records.data->>'source_lead_id'`
    2. `tenant_records.data->>'lead_id'`
    3. `tenant_records.data->>'email'` (fallback — only if leads row has email)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Migration-062 mapping. Stable contract — any change must also update
# database/062_oasis_lead_lifecycle_v2.sql and the dashboard's
# lib/manifest/seeds.ts OASIS_SEED.data_model.lead.stage list.
LEADS_STATUS_TO_TENANT_STAGE: dict[str, str] = {
    "new":         "new_contact",
    "contacted":   "outreach",
    "qualified":   "qualified",
    "proposal":    "proposal",
    "negotiation": "negotiation",
    "won":         "active_client",
    "lost":        "lost",
}


def sync_lead_status_to_tenant_records(
    client: Any,
    lead_id: str,
    new_status: str,
) -> str:
    """Mirror `leads.status` → `tenant_records.data.stage`.

    Args:
        client: supabase-py Client (or anything quacking like it — table(),
                select(), update(), filter(), eq(), execute()).
        lead_id: UUID of the row in `public.leads`.
        new_status: New status value, must be one of the 7 canonical
                    `leads.status` values to be mapped.

    Returns:
        Short status string for logging:
          'synced(N)'   — N matching tenant_records row(s) updated
          'no_record'   — no matching tenant_records row found (legacy-only lead)
          'no_mapping'  — `new_status` has no tenant_records counterpart
          'error:<X>'   — exception of type X swallowed; primary write
                          path is unaffected
    """
    stage = LEADS_STATUS_TO_TENANT_STAGE.get(new_status)
    if not stage:
        return "no_mapping"

    # Pull the lead's email for the fallback match path.
    try:
        lead_row = (
            client.table("leads")
            .select("email")
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )
        lead_email = (lead_row.data[0].get("email") if lead_row.data else None) or None
    except Exception:  # noqa: BLE001
        lead_email = None

    candidates: list[dict] = []
    for key in ("source_lead_id", "lead_id"):
        try:
            r = (
                client.table("tenant_records")
                .select("id, data")
                .eq("entity_type", "lead")
                .filter(f"data->>{key}", "eq", lead_id)
                .limit(2)
                .execute()
            )
            if r.data:
                candidates.extend(r.data)
        except Exception as exc:  # noqa: BLE001
            return f"error:{type(exc).__name__}"

    if not candidates and lead_email:
        try:
            r = (
                client.table("tenant_records")
                .select("id, data")
                .eq("entity_type", "lead")
                .filter("data->>email", "eq", lead_email)
                .limit(2)
                .execute()
            )
            if r.data:
                candidates.extend(r.data)
        except Exception as exc:  # noqa: BLE001
            return f"error:{type(exc).__name__}"

    if not candidates:
        return "no_record"

    synced = 0
    for row in candidates:
        try:
            new_data = dict(row.get("data") or {})
            new_data["stage"] = stage
            client.table("tenant_records").update({
                "data": new_data,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", row["id"]).execute()
            synced += 1
        except Exception as exc:  # noqa: BLE001
            return f"error:{type(exc).__name__}"
    return f"synced({synced})"
