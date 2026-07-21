"""integrations/clear_report_service.py — run a CLEAR search and persist it.

The seam between clear_client (the vendor call) and Supabase (the clair_reports
table). Called ONLY from the bridge tool `clair_report`, which is reachable only
from the dashboard's authenticated API route behind an operator click.

Design rules that follow from CLEAR being a regulated, billable, manual tool:

  * A row is written for EVERY attempt, including failures. A CLEAR query that
    errored still consumed a permissible-use assertion against the account, so
    it belongs in the audit trail — not just the ones that happened to work.
  * `raw_report` is persisted verbatim even when parsing yields nothing, so a
    response whose schema differs from our expectation is never lost.
  * The permissible-use codes are copied onto the row from the config used for
    THAT call, never re-derived later from config that may have changed.
  * Nothing here touches tenant_records. The report is reference material an
    operator reads; it must not merge into the application data.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from integrations.clear_client import (  # noqa: E402
    ClearError,
    ClearQuery,
    ClearResult,
    clear_config,
    is_configured,
    person_search,
)
from integrations.clear_endpoints import (  # noqa: E402
    CAPABILITIES,
    BusinessQuery,
    list_capabilities,
    run_endpoint,
)

TABLE = "clair_reports"

#: report_type -> the *Query class that builds its criteria from a lead. Report
#: endpoints (needs_entity_id) take an entity_id instead of a lead-derived query.
_QUERY_BUILDERS = {
    "person_search": ClearQuery,
    "business_search": BusinessQuery,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_env() -> dict[str, str]:
    """Secrets via the shared loader, immune to sys.path shadowing."""
    try:
        sys.path.insert(0, "/srv/sunbiz/sunbiz-agent/scripts")
        from _bravo_bootstrap import load_bravo_env  # type: ignore

        return load_bravo_env()
    except Exception:  # noqa: BLE001
        try:
            from lib.secret_loader import load_env  # type: ignore

            return dict(load_env())
        except Exception:  # noqa: BLE001
            return dict(os.environ)


def _client(env: dict[str, str]):
    from supabase import create_client  # type: ignore

    url = (env.get("BRAVO_SUPABASE_URL") or "").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise ClearError("supabase_not_configured",
                         "BRAVO_SUPABASE_URL / SERVICE_ROLE_KEY missing")
    return create_client(url, key)


def _load_lead(sb, tenant_id: str, lead_id: str) -> dict[str, Any]:
    res = (
        sb.table("tenant_records")
        .select("id,tenant_id,entity_type,data")
        .eq("id", lead_id)
        .eq("tenant_id", tenant_id)
        .maybe_single()
        .execute()
    )
    row = getattr(res, "data", None)
    if not row:
        raise ClearError("lead_not_found", f"lead {lead_id} not found in this tenant")
    return row.get("data") or {}


def _insert(sb, row: dict[str, Any]) -> Optional[str]:
    try:
        res = sb.table(TABLE).insert(row).execute()
        data = getattr(res, "data", None) or []
        return data[0].get("id") if data else None
    except Exception as e:  # noqa: BLE001
        # Never let a persistence failure hide the vendor outcome from the
        # operator — surface it, but the call already happened and was billed.
        print(f"[clear] clair_reports insert failed: {e}", file=sys.stderr)
        return None


def run_clear_report(
    tenant_id: str,
    lead_id: str,
    report_type: str = "person_search",
    entity_id: Optional[str] = None,
    requested_by: Optional[str] = None,
    requested_by_email: Optional[str] = None,
    application_id: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Run a CLEAR endpoint for one lead and persist the report. UI-shaped dict.

    report_type selects the endpoint (see clear_endpoints.CAPABILITIES):
      * person_search  (default, VERIFIED) — locate the owner + phones
      * business_search — locate the merchant business + phones/principals
      * person_report / business_report — full detail for an entity_id
    A row is written for EVERY attempt, failures included, because each one
    consumes a permissible-use assertion on the account. Nothing here is ever
    called automatically — the only caller is an operator-initiated bridge tool.
    """
    env = env or _load_env()
    sb = _client(env)

    if not is_configured(env):
        return {"ok": False, "error": "not_configured",
                "message": "CLEAR credentials are not present on this host"}

    spec = CAPABILITIES.get(report_type)
    if spec is None:
        return {"ok": False, "error": "unknown_report_type",
                "message": f"unknown report_type '{report_type}'",
                "available": [c["key"] for c in list_capabilities()]}

    lead = _load_lead(sb, tenant_id, lead_id)
    cfg = clear_config(env)

    # Build the criteria for the audit row + the call.
    query = None
    if not spec.needs_entity_id:
        builder = _QUERY_BUILDERS.get(report_type)
        if builder is None:
            return {"ok": False, "error": "unsupported",
                    "message": f"no lead-query builder for '{report_type}'"}
        query = builder.from_lead(lead, reference=f"sunbiz-lead-{lead_id[:8]}")
        ok, why = query.is_searchable()
        if not ok:
            # Refuse BEFORE billing for a query that cannot identify anybody.
            return {"ok": False, "error": "insufficient_criteria", "message": why,
                    "report_type": report_type, "query": query.as_columns()}
    elif not entity_id:
        return {"ok": False, "error": "missing_entity_id",
                "message": f"report_type '{report_type}' requires an entity_id"}

    base_row: dict[str, Any] = {
        "tenant_id": tenant_id,
        "lead_id": lead_id,
        "application_id": application_id,
        "report_type": report_type,
        "entity_id": entity_id,
        **(query.as_columns() if query else {}),
        "permissible_dppa": cfg.get("dppa") or None,
        "permissible_glb": cfg.get("glb") or None,
        "permissible_voter": cfg.get("voter") or None,
        "clear_environment": cfg.get("environment"),
        "requested_by": requested_by,
        "requested_by_email": requested_by_email,
    }

    try:
        result: ClearResult = run_endpoint(
            report_type, query=query, entity_id=entity_id, env=env,
        )
    except ClearError as e:
        report_id = _insert(sb, {
            **base_row,
            "status": "error",
            "error_message": f"{e.code}: {e.message}",
            "http_status": e.status,
            "raw_report": {"body": e.body} if e.body else None,
            "raw_format": "xml",
            "completed_at": _now(),
        })
        return {"ok": False, "error": e.code, "message": e.message,
                "report_type": report_type, "report_id": report_id, "http_status": e.status}

    report_id = _insert(sb, {
        **base_row,
        "status": result.status,
        "http_status": result.http_status,
        "result_count": result.result_count,
        "people": result.people or None,
        "phones": result.phones or None,
        # Wrapped: the column is jsonb and the vendor payload is XML text.
        "raw_report": {"body": result.raw_report} if result.raw_report else None,
        "raw_format": result.raw_format,
        "completed_at": _now(),
    })

    return {
        "ok": True,
        "report_id": report_id,
        "report_type": report_type,
        "status": result.status,
        "result_count": result.result_count,
        "people": result.people,
        "phones": result.phones,
        "query": query.as_columns() if query else {"entity_id": entity_id},
    }
