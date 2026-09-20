"""
event_scope.py — which company an agent_events row belongs to, so each box
reads, logs and retires only its own company's events.

WHY THIS EXISTS (2026-09-11)
----------------------------
agent_events is ONE bus that both companies write to, and the same Python runs
on CC's machine (OASIS) and on SunBiz's VPS. The event router on each box logged
every row: the VPS stored CC's finance handoffs and Bravo session notes, CC's
machine stored SunBiz's Kixie calls and lead ids, and CC's weekly retention
sweep rewrote SunBiz's rows. The router and the sweep both ask this module, so
they cannot disagree about which rows are this box's.

WHERE THE TENANT RIDES ON A ROW
-------------------------------
agent_events has no tenant_id column (migration 006). Producers carry the
tenant in two places, checked against the live bus and the producers' code:

  payload.tenant_id  the TextTorrent RPC, Kixie compliance, the dashboard's
                     lead and email events.
  correlation_id     the Command Center calls it "the canonical tenant pointer"
                     (app/api/event-feed/route.ts), and its producers set it to
                     the tenant id. Bravo's own publishers use it for OTHER ids
                     (a session id, an interaction id, a shop-out round), so
                     only a value that IS a mapped tenant counts.

A row belongs to a box when every tenant it names is one of that box's
company's tenants. A row naming tenants of two companies belongs to neither:
picking one is the defect this module exists to stop.

TENANTLESS ROWS
---------------
A row that names no tenant says nothing about its company. The only such rows
a box may take are Bravo's own, and Bravo is OASIS's agent, so only the OASIS
box takes them. Other tenantless rows are left alone on both boxes; the fix
for those is the producer stamping its tenant.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from lib.tenant_brand import (
    TENANT_BRAND,
    company_for_mailbox,
    host_mailbox,
    tenants_for_mailbox,
)

# Bravo is OASIS's agent, so a row it published without a tenant is OASIS's.
BRAVO_PUBLISHER = "bravo"
BRAVO_COMPANY = "oasis"


@dataclass(frozen=True)
class BoxScope:
    """The company a box works for, and the tenants that company owns."""

    company: Optional[str]
    mailbox: str
    tenants: frozenset[str]


def box_scope(env: Mapping[str, str]) -> BoxScope:
    """This box's scope, from the mailbox it authenticates as — the same
    answer the dashboard consumer and the queue monitor act on. A mailbox that
    belongs to no company gives company None and no tenants: take nothing."""
    mailbox = host_mailbox(env)
    return BoxScope(company_for_mailbox(mailbox), mailbox,
                    frozenset(tenants_for_mailbox(mailbox)))


def _payload(row: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = row.get("payload")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, Mapping) else {}


def event_tenants(row: Mapping[str, Any],
                  payload: Optional[Mapping[str, Any]] = None) -> frozenset[str]:
    """Every tenant this row names (lower-cased), from payload.tenant_id and a
    correlation_id that is a mapped tenant."""
    if payload is None:
        payload = _payload(row)
    found: set[str] = set()
    ptid = payload.get("tenant_id")
    if isinstance(ptid, str) and ptid.strip():
        found.add(ptid.strip().lower())
    corr = row.get("correlation_id")
    if isinstance(corr, str) and corr.strip().lower() in TENANT_BRAND:
        found.add(corr.strip().lower())
    return frozenset(found)


def published_by_bravo(row: Mapping[str, Any]) -> bool:
    """True when every named publisher on the row is Bravo. 'unknown' is the
    column default for source_agent, so it names nobody."""
    names = {str(row.get(k) or "").strip().lower()
             for k in ("source_agent", "publisher_agent")}
    names -= {"", "unknown"}
    return names == {BRAVO_PUBLISHER}


def event_belongs_to(row: Mapping[str, Any], scope: BoxScope,
                     payload: Optional[Mapping[str, Any]] = None) -> bool:
    """May this box read, log or retire this agent_events row?"""
    if scope.company is None:
        return False
    tenants = event_tenants(row, payload)
    if tenants:
        return tenants <= scope.tenants
    return scope.company == BRAVO_COMPANY and published_by_bravo(row)
