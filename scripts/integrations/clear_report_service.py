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
  * Billing guards run BEFORE the vendor call and fail CLOSED: a successful
    report for the same subject within DEDUPE_DAYS is reused (no new charge),
    and pulls stop with a loud error once CLEAR_DAILY_PULL_CAP attempts have
    been made since UTC midnight. The tunnel gate (source-IP verification via
    the QuotaGuard proxy) lives in clear_client.clear_post and runs on every
    billable POST.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta, timezone
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

#: Billing guards — every CLEAR pull costs real money on Breeze's account.
#: A successful report for the same subject is reused for this many days.
DEDUPE_DAYS = 30

#: clair_reports.requested_by is uuid; anything else must degrade to NULL,
#: never to a failed insert (audit-every-attempt is the table's whole point).
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

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


def _recent_report(sb, tenant_id: str, lead_id: str, report_type: str,
                   entity_id: Optional[str]) -> Optional[dict[str, Any]]:
    """The newest successful report for this subject inside the dedupe window,
    or None. Same subject == same lead + report_type (+ entity_id for the
    entity-keyed report endpoints). Raises on a query failure — the caller
    fails CLOSED rather than billing for a pull it could not prove is new."""
    since = (datetime.now(timezone.utc) - timedelta(days=DEDUPE_DAYS)).isoformat()
    q = (
        sb.table(TABLE)
        .select("id,status,result_count,people,phones,report_type,completed_at,"
                "query_name,query_city,query_state,query_zip,entity_id")
        .eq("tenant_id", tenant_id)
        .eq("lead_id", lead_id)
        .eq("report_type", report_type)
        .in_("status", ["completed", "no_results"])
        .gte("completed_at", since)
        .order("completed_at", desc=True)
        .limit(1)
    )
    if entity_id:
        q = q.eq("entity_id", entity_id)
    data = getattr(q.execute(), "data", None) or []
    return data[0] if data else None


def _pulls_today(sb) -> int:
    """Vendor pulls attempted since UTC midnight, account-wide (the cap
    protects Breeze's CLEAR bill, not one tenant's). Every attempt — success
    or error — wrote a row, so the row count IS the billable-attempt count.
    Raises on failure; the caller fails CLOSED."""
    day_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0).isoformat()
    res = (sb.table(TABLE).select("id", count="exact")
           .gte("created_at", day_start).limit(1).execute())
    count = getattr(res, "count", None)
    if count is None:
        raise ClearError("cap_check_failed", "could not count today's CLEAR pulls")
    return int(count)


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

    # ── billing guards (each pull costs real money) ── fail CLOSED: if either
    # guard cannot be evaluated, refuse the pull rather than risk the bill.
    try:
        recent = _recent_report(sb, tenant_id, lead_id, report_type, entity_id)
        if recent is not None:
            return {
                "ok": True,
                "reused": True,
                "report_id": recent["id"],
                "report_type": report_type,
                "status": recent["status"],
                "result_count": recent.get("result_count"),
                "people": recent.get("people") or [],
                "phones": recent.get("phones") or [],
                "completed_at": recent.get("completed_at"),
                "message": (f"reused report from {recent.get('completed_at')} — same subject "
                            f"pulled within the last {DEDUPE_DAYS} days; no new CLEAR charge"),
                "query": query.as_columns() if query else {"entity_id": entity_id},
            }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "dedupe_check_failed",
                "message": f"could not verify 30-day dedupe — refusing to bill: {e}"}

    try:
        cap = int((env.get("CLEAR_DAILY_PULL_CAP") or "0").strip() or "0")
        if cap <= 0:
            return {"ok": False, "error": "daily_cap_unset",
                    "message": "CLEAR_DAILY_PULL_CAP is missing/zero — refusing to pull "
                               "without a hard daily billing cap"}
        used = _pulls_today(sb)
        if used >= cap:
            return {"ok": False, "error": "daily_cap_reached",
                    "message": f"DAILY CLEAR PULL CAP REACHED ({used}/{cap} since UTC "
                               "midnight) — refusing further billable pulls today"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "cap_check_failed",
                "message": f"could not evaluate the daily pull cap — refusing to bill: {e}"}

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
        # The column is uuid; a CLI-originated label like "operator" must not
        # kill the audit insert (it did once, 2026-07-22, and the 403 body was
        # lost with it). Non-uuid callers stay attributed via the email field.
        "requested_by": requested_by if _UUID_RE.match(requested_by or "") else None,
        "requested_by_email": requested_by_email,
    }

    try:
        result: ClearResult = run_endpoint(
            report_type, query=query, entity_id=entity_id, env=env,
        )
    except ClearError as e:
        headers = getattr(e, "headers", None) or {}
        report_id = _insert(sb, {
            **base_row,
            "status": "error",
            "error_message": f"{e.code}: {e.message}",
            "http_status": e.status,
            # Body AND headers: `server: cloudflare` + CF-RAY = edge block;
            # XML SubStatusCode = CLEAR app refusal. Never discard either.
            "raw_report": {"body": e.body, "headers": headers} if (e.body or headers) else None,
            "raw_format": "xml",
            "completed_at": _now(),
        })
        # Diagnostics also go back to the caller so a failed DB insert can
        # never lose the vendor's explanation again.
        return {"ok": False, "error": e.code, "message": e.message,
                "report_type": report_type, "report_id": report_id,
                "http_status": e.status, "body": e.body, "headers": headers}

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
