"""test_clear_endpoints.py — the CLEAR S2S endpoint framework.

Everything here is OFFLINE — request builders, response parsers, normalization,
the capability registry, and the unverified-endpoint gate. No CLEAR call is
made (they are billable and regulated), so these lock the framework's behaviour
without spending a query.
"""

from __future__ import annotations

import pytest

from integrations import clear_endpoints as E
from integrations.clear_client import ClearError, ClearQuery, clear_config

CFG = {"glb": "Q", "dppa": "3", "voter": "7", "base_url": "https://s2s.thomsonreuters.com",
       "username": "u", "password": "p", "pfx_b64": "x", "passphrase": "y", "environment": "prod"}


# ── capability registry ─────────────────────────────────────────────────────

def test_no_endpoint_is_verified_yet():
    """The honesty invariant, corrected 2026-07-22: NO endpoint has ever seen a
    2xx from CLEAR (the old person_search verified=True rested on a
    TLS-handshake-only check, which the Cloudflare edge passes for anyone).
    Every endpoint is doc-only and gated until a real round-trip reconciles it."""
    caps = {c["key"]: c for c in E.list_capabilities()}
    for k in ("person_search", "business_search", "person_report", "business_report"):
        assert caps[k]["verified"] is False, f"{k} must not claim verified"


def test_capabilities_enumerable():
    caps = E.list_capabilities()
    assert {c["key"] for c in caps} == set(E.CAPABILITIES)
    for c in caps:
        assert c["label"] and c["description"] and c["entity_type"] in ("person", "business")


# ── request builders ────────────────────────────────────────────────────────

def test_business_search_xml_has_permissible_purpose_and_criteria():
    q = E.BusinessQuery(business_name="NEXGEN NETWORKS CORP", city="New York", state="NY")
    xml = E._build_business_search_xml(q, CFG).decode()
    assert "<BusinessSearchRequest>" in xml
    assert "<GLB>Q</GLB>" in xml and "<DPPA>3</DPPA>" in xml and "<VOTER>7</VOTER>" in xml
    assert "<BusinessName>NEXGEN NETWORKS CORP</BusinessName>" in xml
    assert "<City>New York</City>" in xml and "<State>NY</State>" in xml


def test_report_xml_carries_entity_id_and_purpose():
    xml = E._build_report_xml("PersonReportRequest", "E123", CFG, "ref").decode()
    assert "<PersonReportRequest>" in xml
    assert "<EntityId>E123</EntityId>" in xml
    assert "<DPPA>3</DPPA>" in xml


# ── business query criteria guard ───────────────────────────────────────────

def test_business_query_needs_identifying_criteria():
    assert E.BusinessQuery(business_name="X").is_searchable()[0] is False
    assert E.BusinessQuery(ein="12-3456789").is_searchable()[0] is True
    assert E.BusinessQuery(business_name="X", state="TX").is_searchable()[0] is True


def test_business_query_from_lead_maps_business_fields():
    q = E.BusinessQuery.from_lead({
        "business_name": "Testco LLC", "business_state_code": "TX",
        "business_city": "Austin", "ein": "12-3456789",
    })
    assert q.business_name == "Testco LLC" and q.state == "TX" and q.ein == "12-3456789"


# ── response parsing + normalization ────────────────────────────────────────

BIZ_XML = """<BusinessSearchResponse>
  <BusinessResult>
    <BusinessEntityId>B99</BusinessEntityId>
    <BusinessName>NEXGEN NETWORKS CORP</BusinessName><FEIN>123456789</FEIN>
    <Address><Street>64 BEAVER ST</Street><City>NEW YORK</City><State>NY</State><ZipCode>10004</ZipCode></Address>
    <Phone><Number>(212) 555-0100</Number><PhoneType>Main</PhoneType></Phone>
    <Principal>EDWARD LAWSON</Principal>
  </BusinessResult>
</BusinessSearchResponse>"""


def test_business_parse_normalizes_to_entities():
    ents = E._parse_business_entities(BIZ_XML)
    assert len(ents) == 1
    e = ents[0]
    assert e.entity_type == "business"
    assert e.name == "NEXGEN NETWORKS CORP"
    assert e.entity_id == "B99"
    assert e.phones[0]["number"] == "2125550100"          # normalized to 10 digits
    assert "EDWARD LAWSON" in e.associates
    assert e.extra["ein"] == "123456789"


def test_namespaced_business_response_still_parses():
    ns = BIZ_XML.replace("<BusinessSearchResponse>", '<ns:BusinessSearchResponse xmlns:ns="urn:x">') \
                .replace("</BusinessSearchResponse>", "</ns:BusinessSearchResponse>") \
                .replace("<BusinessResult>", "<ns:BusinessResult>") \
                .replace("</BusinessResult>", "</ns:BusinessResult>")
    assert len(E._parse_business_entities(ns)) == 1


def test_result_flattens_distinct_phones():
    ents = E._parse_business_entities(BIZ_XML)
    res = E._entities_to_result(ents, BIZ_XML, 200)
    assert res.status == "completed"
    assert [p["number"] for p in res.phones] == ["2125550100"]
    assert res.phones[0]["person"] == "NEXGEN NETWORKS CORP"


def test_bad_xml_raises_bad_response():
    with pytest.raises(ClearError) as ei:
        E._parse_business_entities("<not-closed>")
    assert ei.value.code == "bad_response"


# ── the unverified-endpoint gate (billing safety) ───────────────────────────

def _envcfg(**over):
    e = dict(CLEAR_USERNAME="u", CLEAR_PASSWORD="p", CLEAR_PFX_CERTIFICATE="x",
             CLEAR_PASSPHRASE="passphrase12", CLEAR_ENVIRONMENT="prod",
             CLEAR_GLB="Q", CLEAR_DPPA="3", CLEAR_VOTER="7")
    e.update(over)
    return e


def test_unverified_endpoint_refused_without_override():
    q = E.BusinessQuery(ein="12-3456789")
    with pytest.raises(ClearError) as ei:
        E.run_endpoint("business_search", query=q, env=_envcfg())
    assert ei.value.code == "not_verified"


def test_unknown_endpoint_rejected():
    with pytest.raises(ClearError) as ei:
        E.run_endpoint("teleport", env=_envcfg())
    assert ei.value.code == "unknown_endpoint"


def test_report_endpoint_requires_entity_id():
    with pytest.raises(ClearError) as ei:
        E.run_endpoint("person_report", env=_envcfg(CLEAR_ALLOW_UNVERIFIED="1"))
    assert ei.value.code == "missing_entity_id"


def test_person_search_gated_until_real_roundtrip():
    """person_search gates like everything else until a live 2xx reconciles it."""
    q = ClearQuery(last_name="Doe", state="TX")
    with pytest.raises(ClearError) as ei:
        E.run_endpoint("person_search", query=q, env=_envcfg())
    assert ei.value.code == "not_verified"


def test_insufficient_criteria_refused_before_any_call():
    """A query that can't identify anyone is rejected before the transport —
    so an unsearchable query never bills, even on a verified endpoint."""
    q = E.BusinessQuery(business_name="X")  # name only, not searchable
    with pytest.raises(ClearError) as ei:
        E.run_endpoint("business_search", query=q, env=_envcfg(CLEAR_ALLOW_UNVERIFIED="1"))
    assert ei.value.code == "insufficient_criteria"
