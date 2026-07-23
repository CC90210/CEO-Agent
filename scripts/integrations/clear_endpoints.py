"""integrations/clear_endpoints.py — the CLEAR S2S endpoint framework.

clear_client.py owns the VERIFIED transport (mutual TLS, auth, retry, errors)
and the reference endpoint, Person Search. This module turns that transport into
an extensible, enumerable catalog: each CLEAR capability is one EndpointSpec
(path + request builder + response parser + verified flag), so adding a new one
is a small, self-contained change and the system can list what it can do.

VERIFICATION HONESTY — read before enabling anything here.
Only `person_search` is confirmed against the live endpoint (its request shape
and transport were exercised against s2s.thomsonreuters.com). The other specs are
built from Thomson Reuters' published S2S documentation and general knowledge of
its two-phase Search→Report pattern, and their exact request/response XML is NOT
yet confirmed against a real response. They are therefore marked verified=False
and are GATED: run_endpoint refuses an unverified spec unless
CLEAR_ALLOW_UNVERIFIED=1 is set, so an untested endpoint can never silently bill
a regulated, production query. `raw_report` is always persisted verbatim, so the
first real call captures the true schema for reconciliation — which touches only
that spec's build/parse functions.

Everything a CLEAR query needs (permissible use, billing, audit) is identical
across endpoints; only the criteria and the payload shape differ. That is why
this file is small.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from integrations.clear_client import (
    ClearError,
    ClearResult,
    _build_search_xml,       # person search request (verified)
    _el,
    _find,
    _findall,
    _parse_search_xml,       # person search response (verified)
    _text,
    clear_config,
    clear_get,
    clear_post,
    results_uri,
)

# ── normalized model ────────────────────────────────────────────────────────


@dataclass
class ClearEntity:
    """One person or business from any CLEAR response, in a single shape the
    clair_reports table and the UI consume regardless of endpoint."""
    entity_type: str                                   # 'person' | 'business'
    name: Optional[str] = None
    entity_id: Optional[str] = None
    age: Optional[str] = None
    dob: Optional[str] = None
    addresses: list[str] = field(default_factory=list)
    phones: list[dict[str, Any]] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    associates: list[str] = field(default_factory=list)   # relatives / principals / agents
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d = {
            "entity_type": self.entity_type,
            "name": self.name,
            "entity_id": self.entity_id,
            "age": self.age,
            "dob": self.dob,
            "addresses": self.addresses,
            "phones": self.phones,
            "emails": self.emails,
            "associates": self.associates,
        }
        if self.extra:
            d["extra"] = self.extra
        return {k: v for k, v in d.items() if v not in (None, [], {})}


def _flatten_phones(entities: list[ClearEntity]) -> list[dict[str, Any]]:
    """Every distinct phone across all entities — the enrichment payoff."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for e in entities:
        for p in e.phones:
            num = p.get("number")
            if num and num not in seen:
                seen.add(num)
                out.append({**p, "person": e.name})
    return out


def _entities_to_result(entities: list[ClearEntity], body: str, status: int) -> ClearResult:
    return ClearResult(
        status="completed" if entities else "no_results",
        people=[e.as_dict() for e in entities],
        phones=_flatten_phones(entities),
        raw_report=body,
        raw_format="xml",
        http_status=status,
    )


# ── shared response parsing (person path reuses the verified parser) ────────


def _parse_person_entities(body: str) -> list[ClearEntity]:
    people, _phones = _parse_search_xml(body)   # verified parser
    return [
        ClearEntity(
            entity_type="person",
            name=p.get("name"),
            entity_id=p.get("entity_id"),
            age=p.get("age"),
            dob=p.get("dob"),
            addresses=p.get("addresses") or [],
            phones=p.get("phones") or [],
        )
        for p in people
    ]


def _digits10(raw: str) -> Optional[str]:
    d = re.sub(r"\D", "", raw or "")
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return d if len(d) == 10 else None


def _parse_business_entities(body: str) -> list[ClearEntity]:
    """UNVERIFIED. Namespace-/shape-tolerant parse of a BusinessSearchResponse.
    Confined here so reconciling against a real payload touches one function."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        raise ClearError("bad_response", f"CLEAR business response unparseable: {e}", body=body) from e

    out: list[ClearEntity] = []
    for rec in _findall(root, "BusinessResult", "Business", "BusinessRecord", "Record"):
        phones: list[dict[str, Any]] = []
        for pn in _findall(rec, "Phone", "PhoneNumber", "PhoneInfo"):
            num = _digits10(_text(_find(pn, "Number", "PhoneNumber")) or _text(pn))
            if num:
                phones.append({
                    "number": num,
                    "type": _text(_find(pn, "PhoneType", "Type")) or None,
                    "carrier": _text(_find(pn, "Carrier", "Provider")) or None,
                    "last_seen": _text(_find(pn, "LastSeen", "LastReportedDate")) or None,
                })
        addresses = []
        for ad in _findall(rec, "Address", "AddressInfo"):
            line = " ".join(x for x in (
                _text(_find(ad, "Street", "AddressLine1")),
                _text(_find(ad, "City")), _text(_find(ad, "State")),
                _text(_find(ad, "ZipCode", "Zip")),
            ) if x)
            if line:
                addresses.append(line)
        principals = [
            _text(p) for p in _findall(rec, "Principal", "Officer", "RegisteredAgent", "Contact")
            if _text(p)
        ]
        name = _text(_find(rec, "BusinessName", "CompanyName", "Name"))
        if name or phones or addresses:
            out.append(ClearEntity(
                entity_type="business",
                name=name or None,
                entity_id=_text(_find(rec, "BusinessEntityId", "EntityId")) or None,
                addresses=addresses,
                phones=phones,
                associates=principals,
                extra={
                    "ein": _text(_find(rec, "FEIN", "EIN", "TaxId")) or None,
                    "status": _text(_find(rec, "Status")) or None,
                },
            ))
    return out


# ── request builders ────────────────────────────────────────────────────────


def _build_business_search_xml(q: "BusinessQuery", cfg: dict[str, str]) -> bytes:
    """UNVERIFIED. BusinessSearchRequest, mirroring the person request layout."""
    root = ET.Element("BusinessSearchRequest")
    purpose = _el(root, "PermissiblePurpose")
    _el(purpose, "GLB", cfg.get("glb", ""))
    _el(purpose, "DPPA", cfg.get("dppa", ""))
    _el(purpose, "VOTER", cfg.get("voter", ""))
    _el(root, "Reference", q.reference)
    criteria = _el(root, "Criteria")
    biz = _el(criteria, "BusinessCriteria")
    if q.business_name:
        _el(biz, "BusinessName", q.business_name)
    if q.ein:
        _el(biz, "FEIN", q.ein)
    if q.street:
        _el(biz, "Street", q.street)
    if q.city:
        _el(biz, "City", q.city)
    if q.state:
        _el(biz, "State", q.state)
    if q.zip_code:
        _el(biz, "ZipCode", q.zip_code)
    return b'<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(root, encoding="utf-8")


def _build_report_xml(request_tag: str, entity_id: str, cfg: dict[str, str],
                      reference: str) -> bytes:
    """UNVERIFIED. The second phase of CLEAR's Search→Report pattern: given an
    entity id returned by a search, request the full detail report."""
    root = ET.Element(request_tag)
    purpose = _el(root, "PermissiblePurpose")
    _el(purpose, "GLB", cfg.get("glb", ""))
    _el(purpose, "DPPA", cfg.get("dppa", ""))
    _el(purpose, "VOTER", cfg.get("voter", ""))
    _el(root, "Reference", reference)
    _el(root, "EntityId", entity_id)
    return b'<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(root, encoding="utf-8")


# ── query models ────────────────────────────────────────────────────────────


@dataclass
class BusinessQuery:
    business_name: str = ""
    ein: str = ""
    street: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    reference: str = "sunbiz-manual-lookup"

    @classmethod
    def from_lead(cls, data: dict[str, Any], reference: str = "sunbiz-manual-lookup") -> "BusinessQuery":
        return cls(
            business_name=str(data.get("business_name") or data.get("company")
                              or data.get("legal_name") or "").strip(),
            ein=str(data.get("ein") or data.get("tax_id_ein") or "").strip(),
            street=str(data.get("business_address_line1") or data.get("business_address")
                       or data.get("address") or "").strip(),
            city=str(data.get("business_city") or data.get("city") or "").strip(),
            state=str(data.get("business_state_code") or data.get("state_code")
                      or data.get("state") or "").strip(),
            zip_code=str(data.get("business_zip") or data.get("zip") or "").strip(),
            reference=reference,
        )

    def is_searchable(self) -> tuple[bool, str]:
        if self.ein:
            return True, ""
        if self.business_name and (self.state or self.city or self.zip_code):
            return True, ""
        return False, "need an EIN, or a business name plus a city/state/ZIP"

    def as_columns(self) -> dict[str, Any]:
        return {
            "query_name": self.business_name or None,
            "query_address": self.street or None,
            "query_city": self.city or None,
            "query_state": self.state or None,
            "query_zip": self.zip_code or None,
        }


# ── the capability registry ─────────────────────────────────────────────────


@dataclass
class EndpointSpec:
    """One CLEAR capability: how to build its request, parse its response, and
    whether its wire format is confirmed against the live API."""
    key: str
    label: str
    path: str
    entity_type: str
    verified: bool
    description: str
    build: Callable[..., bytes]
    parse: Callable[[str], list[ClearEntity]]
    needs_entity_id: bool = False


CAPABILITIES: dict[str, EndpointSpec] = {
    "person_search": EndpointSpec(
        key="person_search",
        label="Person Search",
        # v3: the v2 resource is entitlement-blocked on this account (403/10001,
        # 2026-07-23) while v3 accepts the same criteria schema under a
        # PersonSearchRequestV3 root.
        path="/api/v3/person/searchResults",
        entity_type="person",
        # verified 2026-07-23 on a REAL round-trip (unlike the 2026-07-21
        # handshake-only overclaim): POST v3 search → 200 + <Uri> → GET results
        # → PersonResultsPageV3 parsed to 1 person / 5 phones for a live lead
        # (clair_reports bc101333, through the QuotaGuard tunnel).
        verified=True,
        description="Find individuals by name + address/DOB. Returns matches with "
                    "phones and addresses. The primary enrichment vector — this is "
                    "how a merchant's owner's phone number is located.",
        build=lambda q, cfg: _build_search_xml(q, cfg),
        parse=_parse_person_entities,
    ),
    "business_search": EndpointSpec(
        key="business_search",
        label="Business Search",
        path="/api/v2/business/searchResults",
        entity_type="business",
        verified=False,
        description="Find a business by name/EIN + address. Returns the entity, its "
                    "phones, addresses, and principals/registered agents. High value "
                    "here because the merchant IS a business.",
        build=lambda q, cfg: _build_business_search_xml(q, cfg),
        parse=_parse_business_entities,
    ),
    "person_report": EndpointSpec(
        key="person_report",
        label="Person Report",
        path="/api/v2/person/reports",
        entity_type="person",
        verified=False,
        description="Full detail report for a person entity id from a prior search: "
                    "complete phone/address history, relatives, and associated records.",
        build=lambda entity_id, cfg: _build_report_xml("PersonReportRequest", entity_id, cfg,
                                                       "sunbiz-manual-lookup"),
        parse=_parse_person_entities,
        needs_entity_id=True,
    ),
    "business_report": EndpointSpec(
        key="business_report",
        label="Business Report",
        path="/api/v2/business/reports",
        entity_type="business",
        verified=False,
        description="Full detail report for a business entity id: complete contact "
                    "history, filings, principals.",
        build=lambda entity_id, cfg: _build_report_xml("BusinessReportRequest", entity_id, cfg,
                                                       "sunbiz-manual-lookup"),
        parse=_parse_business_entities,
        needs_entity_id=True,
    ),
}


def list_capabilities() -> list[dict[str, Any]]:
    """Enumerate the catalog — key, label, entity type, verified flag,
    description — so the system (and other agents) can discover what CLEAR can do."""
    return [
        {"key": s.key, "label": s.label, "entity_type": s.entity_type,
         "verified": s.verified, "needs_entity_id": s.needs_entity_id,
         "description": s.description}
        for s in CAPABILITIES.values()
    ]


def _unverified_allowed(env: dict[str, str]) -> bool:
    return str(env.get("CLEAR_ALLOW_UNVERIFIED") or "0").strip() == "1"


def run_endpoint(
    key: str,
    *,
    query: Any = None,
    entity_id: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    timeout: Optional[tuple[int, int]] = None,
) -> ClearResult:
    """Execute any catalog endpoint through the shared verified transport.

    Args:
      key: a CAPABILITIES key (e.g. "person_search", "business_search").
      query: a *Query object (person/business) for search endpoints.
      entity_id: required for *_report endpoints.
      env: env dict; defaults to os.environ.

    Raises ClearError:
      unknown_endpoint / not_verified / insufficient_criteria / missing_entity_id,
      plus the transport taxonomy (unauthorized/http_error/network_error).

    An unverified endpoint runs ONLY when CLEAR_ALLOW_UNVERIFIED=1, so a spec
    whose wire format has not been confirmed cannot silently bill a prod query.
    """
    env = env if env is not None else dict(os.environ)
    spec = CAPABILITIES.get(key)
    if spec is None:
        raise ClearError("unknown_endpoint",
                         f"no CLEAR endpoint '{key}'. Available: {', '.join(CAPABILITIES)}")
    if not spec.verified and not _unverified_allowed(env):
        raise ClearError(
            "not_verified",
            f"endpoint '{key}' is built from documentation but its wire format is not "
            "confirmed against the live API. Set CLEAR_ALLOW_UNVERIFIED=1 to run it "
            "(the raw response is saved so the schema can be reconciled).",
        )

    cfg = clear_config(env)
    from integrations.clear_client import DEFAULT_TIMEOUT
    tmo = timeout or DEFAULT_TIMEOUT

    if spec.needs_entity_id:
        if not entity_id:
            raise ClearError("missing_entity_id", f"endpoint '{key}' requires an entity_id")
        payload = spec.build(entity_id, cfg)
    else:
        if query is None:
            raise ClearError("insufficient_criteria", f"endpoint '{key}' requires a query")
        ok, why = query.is_searchable()
        if not ok:
            raise ClearError("insufficient_criteria", why)
        payload = spec.build(query, cfg)

    status, body = clear_post(spec.path, payload, cfg, tmo)
    entities = spec.parse(body)
    if not entities:
        # v3 two-step searches acknowledge with a <Uri>; the entities are
        # behind a GET of it (same search — retrieval is not a new query).
        uri = results_uri(body)
        if uri:
            status, body = clear_get(uri, cfg, tmo)
            entities = spec.parse(body)
    return _entities_to_result(entities, body, status)
