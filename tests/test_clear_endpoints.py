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

def test_only_person_search_is_verified():
    """The honesty invariant: verified=True requires a REAL live round-trip.
    person_search earned it 2026-07-23 (v3 POST → 200 + Uri → GET →
    PersonResultsPageV3 parsed, clair_reports bc101333). Everything else is
    still doc-only and gated."""
    caps = {c["key"]: c for c in E.list_capabilities()}
    assert caps["person_search"]["verified"] is True
    for k in ("business_search", "person_report", "business_report"):
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
             CLEAR_GLB="Q", CLEAR_DPPA="3", CLEAR_VOTER="7",
             # required since 2026-07-23: no proxy env = not configured, never
             # a direct call. .invalid TLD guarantees the tunnel gate can only
             # fail if anything ever reaches the transport in these tests.
             QUOTAGUARD_SOCKS5_URL="socks5://u:p@relay.invalid:1080")
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


def test_person_search_aborts_at_tunnel_gate_not_direct():
    """person_search is verified, so with valid criteria it proceeds to the
    transport — where the tunnel gate must ABORT on an unreachable proxy
    instead of ever falling back to a direct (unproxied) CLEAR call."""
    q = ClearQuery(last_name="Doe", state="TX")
    with pytest.raises(ClearError) as ei:
        E.run_endpoint("person_search", query=q, env=_envcfg())
    assert ei.value.code == "tunnel_unverified"


def test_missing_proxy_env_means_not_configured():
    """No QUOTAGUARD_SOCKS5_URL: the account creds alone must NOT be enough —
    a direct call would come from a non-whitelisted IP and leak intent."""
    with pytest.raises(ClearError) as ei:
        clear_config(_envcfg(QUOTAGUARD_SOCKS5_URL=""))
    assert ei.value.code == "not_configured"


def test_insufficient_criteria_refused_before_any_call():
    """A query that can't identify anyone is rejected before the transport —
    so an unsearchable query never bills, even on a verified endpoint."""
    q = E.BusinessQuery(business_name="X")  # name only, not searchable
    with pytest.raises(ClearError) as ei:
        E.run_endpoint("business_search", query=q, env=_envcfg(CLEAR_ALLOW_UNVERIFIED="1"))
    assert ei.value.code == "insufficient_criteria"


# ── v3 wire format, locked against the LIVE responses of 2026-07-23 ─────────

from integrations.clear_client import (  # noqa: E402
    NS_CRITERIA,
    NS_SEARCH,
    _build_search_xml,
    _parse_search_xml,
    _socks5h,
    results_uri,
)


def test_person_search_xml_matches_live_v3_validator():
    """Every constraint here was dictated by CLEAR's own 400/40002 messages:
    namespaced PersonSearchRequestV3 root, schemas/search PersonCriteria,
    Datasources required, NameInfo with LastName BEFORE FirstName,
    AgeInfo/PersonBirthDate in MM/DD/YYYY."""
    q = ClearQuery(first_name="Richard", last_name="Rutledge", city="VACAVILLE",
                   state="CA", zip_code="95688", dob="1965-12-27")
    xml = _build_search_xml(q, CFG).decode()
    assert f'"{NS_SEARCH}"' in xml and "PersonSearchRequestV3" in xml
    assert f'"{NS_CRITERIA}"' in xml and "PersonCriteria" in xml
    assert "<Datasources><PublicRecordPeople>true</PublicRecordPeople></Datasources>" in xml
    assert xml.index("<LastName>Rutledge</LastName>") < xml.index("<FirstName>Richard</FirstName>")
    assert "<AgeInfo><PersonBirthDate>12/27/1965</PersonBirthDate></AgeInfo>" in xml
    assert "<GLB>Q</GLB>" in xml and "<DPPA>3</DPPA>" in xml


_V3_ACK = (
    '<?xml version="1.0"?><ns2:PersonResults '
    'xmlns:ns2="http://clear.thomsonreuters.com/api/search/2.0">'
    "<Status><StatusCode>200</StatusCode></Status>"
    "<Uri>https://s2s.thomsonreuters.com/api/v3/person/searchResults/abc123</Uri>"
    "<GroupCount>1</GroupCount></ns2:PersonResults>"
)

_V3_PAGE = (
    '<?xml version="1.0"?><ns4:PersonResultsPageV3 '
    'xmlns:ns3="com/thomsonreuters/schemas/search" '
    'xmlns:ns4="http://clear.thomsonreuters.com/api/search/2.0">'
    "<Status><StatusCode>200</StatusCode></Status>"
    "<ResultGroup><GroupId>g1</GroupId><RecordCount>1</RecordCount>"
    "<RecordDetails><ns3:PersonResponseDetail>"
    "<Name><FirstName>RICHARD</FirstName><LastName>RUTLEDGE</LastName></Name>"
    "<PersonProfile><PersonBirthDates><PersonBirthDate>12/XX/1965</PersonBirthDate>"
    "</PersonBirthDates></PersonProfile>"
    "<KnownAddresses><Address><Street>4570 CRAIG LN</Street><City>VACAVILLE</City>"
    "<State>CA</State><ZipCode>95688</ZipCode></Address>"
    "<Phones><PhoneNumber>(707) 689-6252</PhoneNumber>"
    "<PhoneNumberInfoList><PhoneNumber>(707) 689-6252</PhoneNumber></PhoneNumberInfoList>"
    "<PhoneNumberInfoList><PhoneNumber>(530) 867-2586</PhoneNumber></PhoneNumberInfoList>"
    "</Phones></KnownAddresses>"
    "<PersonEntityId>P1__MTg2OTk5Njk</PersonEntityId>"
    "</ns3:PersonResponseDetail></RecordDetails></ResultGroup>"
    "</ns4:PersonResultsPageV3>"
)


def test_results_uri_extracted_from_v3_ack():
    assert results_uri(_V3_ACK) == \
        "https://s2s.thomsonreuters.com/api/v3/person/searchResults/abc123"
    assert results_uri(_V3_PAGE) is None
    assert results_uri("<garbage") is None


def test_parse_v3_results_page():
    people, phones = _parse_search_xml(_V3_PAGE)
    assert len(people) == 1
    p = people[0]
    assert p["name"] == "RICHARD RUTLEDGE"
    assert p["dob"] == "12/XX/1965"
    assert p["entity_id"] == "P1__MTg2OTk5Njk"
    assert p["addresses"] == ["4570 CRAIG LN VACAVILLE CA 95688"]
    # deduped inside the person AND in the flat list
    assert [x["number"] for x in p["phones"]] == ["7076896252", "5308672586"]
    assert [x["number"] for x in phones] == ["7076896252", "5308672586"]


def test_socks5h_rewrite():
    assert _socks5h("socks5://u:p@h:1080") == "socks5h://u:p@h:1080"
    assert _socks5h("socks5h://u:p@h:1080") == "socks5h://u:p@h:1080"
