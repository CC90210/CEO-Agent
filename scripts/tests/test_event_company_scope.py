"""Each box reads, logs and retires only its own company's agent_events.

agent_events is one bus both companies write to, and the same router and
retention sweep run on CC's machine (OASIS) and on SunBiz's VPS. Before this,
the VPS router logged CC's finance handoffs and Bravo session notes, CC's router
logged SunBiz's Kixie calls and lead ids, and CC's weekly retention sweep marked
SunBiz's rows dead.

The bus below holds one row per producer shape seen live on 2026-09-11: the
tenant rides in payload.tenant_id, in correlation_id, in both, or nowhere.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from core import event_retention as ret  # noqa: E402
from core import event_router as er  # noqa: E402
from lib.event_scope import box_scope, event_belongs_to, event_tenants  # noqa: E402

SUNBIZ = "aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110"
OASIS_CC = "ef8d389e-3f15-43f2-ae00-3660f69a1452"
OASIS_WEBDEV = "42423fde-be8b-454f-932a-750e8c9b743d"
STRANGER = "5f63d7e6-0000-4000-8000-000000000000"  # a self-signup tenant: no company

SUNBIZ_BOX = box_scope({"GMAIL_USER": "submissions@sunbizfunding.com"})
OASIS_BOX = box_scope({"GMAIL_USER": "conaugh@oasisai.work"})
NO_COMPANY_BOX = box_scope({"GMAIL_USER": "someone@gmail.com"})


def _ev(rid, created, *, tenant=None, corr=None, publisher="unknown",
        source="unknown", event_type="X", **payload):
    if tenant:
        payload["tenant_id"] = tenant
    return {"id": rid, "event_type": event_type, "source_agent": source,
            "publisher_agent": publisher, "target_agent": None, "severity": "info",
            # Turso hands payload back as JSON text.
            "payload": json.dumps(payload), "correlation_id": corr,
            "published_at": created, "created_at": created, "status": "pending"}


NOW = "2026-09-11T10:00:00Z"
BUS = [
    # SunBiz — the TextTorrent RPC stamps both pointers.
    _ev("sun-tt", "2026-09-11T10:00:01Z", tenant=SUNBIZ, corr=SUNBIZ,
        publisher="texttorrent", event_type="TEXTTORRENT_UNMAPPED_DID",
        destination_last4="2557"),
    # SunBiz — a Kixie call with the tenant in the payload only.
    _ev("sun-kixie", "2026-09-11T10:00:02Z", tenant=SUNBIZ, publisher="kixie",
        event_type="KIXIE_CALL_ANSWERED", lead_id="sun-lead-42"),
    # OASIS — a dashboard event with both pointers.
    _ev("oas-dash", "2026-09-11T10:00:03Z", tenant=OASIS_CC, corr=OASIS_CC,
        publisher="dashboard", event_type="BRAVO_OUTBOUND_QUEUED_FROM_DASHBOARD",
        lead_id="oas-lead-7"),
    # OASIS — the record-outbound RPC puts the tenant in correlation_id only.
    _ev("oas-outbound", "2026-09-11T10:00:04Z", corr=OASIS_WEBDEV,
        publisher="email_engine", event_type="outbound.recorded", lead_id="oas-lead-8"),
    # Bravo, tenantless — correlation_id is a session id, not a tenant.
    _ev("bravo-session", "2026-09-11T10:00:05Z", corr="session-2026-09-11",
        publisher="bravo", source="bravo", event_type="BRAVO_SESSION_LOG_APPENDED",
        note="CC session note"),
    # Bravo, tenantless — source_agent left at its 'unknown' default.
    _ev("bravo-finance", "2026-09-11T10:00:06Z", publisher="bravo",
        event_type="email.financial_handoff", amount_cad="1200"),
    # Tenantless and not Bravo: nothing says whose it is.
    _ev("n8n-classified", "2026-09-11T10:00:07Z", corr="thread-99",
        publisher="n8n", event_type="inbound.classified"),
    # Tenant pointers from two companies: whose it is cannot be decided.
    _ev("split", "2026-09-11T10:00:08Z", tenant=OASIS_CC, corr=SUNBIZ,
        publisher="dashboard", event_type="Y"),
    # A tenant that belongs to no company.
    _ev("stranger", "2026-09-11T10:00:09Z", tenant=STRANGER, corr=STRANGER,
        publisher="dashboard", event_type="Z"),
]
OASIS_IDS = {"oas-dash", "oas-outbound", "bravo-session", "bravo-finance"}
SUNBIZ_IDS = {"sun-tt", "sun-kixie"}


# --------------------------------------------------------------------------- #
# Which rows are whose
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("scope,expected", [
    (OASIS_BOX, OASIS_IDS), (SUNBIZ_BOX, SUNBIZ_IDS), (NO_COMPANY_BOX, set())])
def test_each_box_owns_exactly_its_companys_rows(scope, expected):
    assert {r["id"] for r in BUS if event_belongs_to(r, scope)} == expected


def test_no_row_belongs_to_both_boxes():
    for r in BUS:
        assert not (event_belongs_to(r, OASIS_BOX) and event_belongs_to(r, SUNBIZ_BOX)), r


def test_a_correlation_id_counts_only_when_it_is_a_mapped_tenant():
    assert event_tenants({"correlation_id": "session-1", "payload": {}}) == frozenset()
    assert event_tenants({"correlation_id": SUNBIZ.upper(), "payload": "{}"}) == {SUNBIZ}


# --------------------------------------------------------------------------- #
# The router
# --------------------------------------------------------------------------- #

class _Table:
    def __init__(self, rows): self._rows = rows
    def select(self, *a, **k): return self
    def gt(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def execute(self): return type("Res", (), {"data": self._rows})()


class _Bus:
    def __init__(self, rows):
        self.rows, self.reads = rows, 0

    def table(self, name):
        assert name == "agent_events", name
        self.reads += 1
        return _Table(self.rows)


@pytest.fixture
def router(monkeypatch, tmp_path):
    monkeypatch.setattr(er, "STATE_DIR", tmp_path)
    monkeypatch.setattr(er, "LOG_PATH", tmp_path / "event_router.log")
    monkeypatch.setattr(er, "CURSOR_PATH", tmp_path / "event_router.cursor")
    monkeypatch.setattr(er, "SUPPRESS_STATE_PATH", tmp_path / "event_router.suppress.json")
    monkeypatch.setattr(er, "_SCOPE_WARNED", set())
    er.CURSOR_PATH.write_text(NOW, encoding="utf-8")

    def run(scope, rows):
        bus = _Bus(rows)
        monkeypatch.setattr(er, "_host_scope", lambda: scope)
        monkeypatch.setattr(er, "_client", lambda: bus)
        return er.tick(), bus
    return run


def _logged() -> list[dict]:
    if not er.LOG_PATH.exists():
        return []
    return [json.loads(ln) for ln in er.LOG_PATH.read_text(encoding="utf-8").splitlines() if ln]


def test_the_oasis_router_logs_only_oasis_rows(router):
    routed, _ = router(OASIS_BOX, BUS)
    assert routed == len(OASIS_IDS)
    assert {ln["id"] for ln in _logged()} == OASIS_IDS
    text = er.LOG_PATH.read_text(encoding="utf-8")
    assert "sun-lead-42" not in text and "2557" not in text


def test_the_sunbiz_router_logs_only_sunbiz_rows(router):
    routed, _ = router(SUNBIZ_BOX, BUS)
    assert routed == len(SUNBIZ_IDS)
    assert {ln["id"] for ln in _logged()} == SUNBIZ_IDS
    text = er.LOG_PATH.read_text(encoding="utf-8")
    for oasis_detail in ("oas-lead-7", "CC session note", "1200"):
        assert oasis_detail not in text


@pytest.mark.parametrize("scope,foreign", [(OASIS_BOX, SUNBIZ), (SUNBIZ_BOX, OASIS_CC)])
def test_the_cursor_passes_the_other_companys_rows(router, scope, foreign):
    last = _ev("last-foreign", "2026-09-11T11:00:00Z", tenant=foreign, corr=foreign)
    router(scope, BUS + [last])
    assert er.CURSOR_PATH.read_text(encoding="utf-8") == "2026-09-11T11:00:00Z"


def test_a_box_with_no_company_reads_nothing_and_says_so(router, capsys):
    routed, bus = router(NO_COMPANY_BOX, BUS)
    assert routed == 0
    assert bus.reads == 0, "a box with no company must not even read the bus"
    assert _logged() == []
    assert er.CURSOR_PATH.read_text(encoding="utf-8") == NOW
    assert "REFUSING TO ROUTE" in capsys.readouterr().err


def _seed_sunbiz_window() -> str:
    """A window opened before the router was scoped, now past its end."""
    opened = (datetime.now(timezone.utc)
              - timedelta(seconds=er.SUPPRESS_WINDOW_SEC + 60)).isoformat(timespec="seconds")
    key = f"TEXTTORRENT_UNMAPPED_DID|tenant_id={SUNBIZ}|destination_last4=2557"
    er._save_suppress_state({key: {"window_started_at": opened, "last_seen_at": opened,
                                   "logged": 1, "suppressed": 40}})
    return key


def test_an_old_sunbiz_window_closes_on_the_oasis_box_without_a_rollup(router):
    key = _seed_sunbiz_window()
    router(OASIS_BOX, [])
    assert _logged() == [], "a rollup naming SunBiz's tenant reached OASIS's log"
    assert key not in er._load_suppress_state()


def test_the_same_window_still_rolls_up_on_the_sunbiz_box(router):
    _seed_sunbiz_window()
    router(SUNBIZ_BOX, [])
    rollups = [ln for ln in _logged() if ln["event_type"] == er.ROLLUP_EVENT_TYPE]
    assert len(rollups) == 1 and rollups[0]["suppressed"] == 40


# --------------------------------------------------------------------------- #
# The retention sweep
# --------------------------------------------------------------------------- #

OLD = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
STALE_BUS = [dict(r, published_at=OLD, created_at=OLD) for r in BUS]


def _column(row: dict, col: str):
    if col == "payload->>tenant_id":
        payload = row.get("payload")
        payload = json.loads(payload) if isinstance(payload, str) else (payload or {})
        return payload.get("tenant_id")
    return row.get(col)


class _RetQuery:
    """Applies eq/in_/limit the way the database would; records reads and writes."""

    def __init__(self, db):
        self._db, self._filters, self._write, self._limit = db, [], None, None

    def select(self, *_a):
        return self

    def eq(self, col, val):
        self._filters.append((col, [val]))
        return self

    def in_(self, col, vals):
        self._filters.append((col, list(vals)))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def update(self, patch):
        self._write = patch
        return self

    def execute(self):
        if self._write is not None:
            self._db.updates.append({c: v[0] for c, v in self._filters})
            return type("R", (), {"data": []})()
        self._db.reads.append(list(self._filters))
        rows = [r for r in self._db.rows
                if all(_column(r, c) in vals for c, vals in self._filters)]
        return type("R", (), {"data": rows[: self._limit]})()


class _RetDB:
    def __init__(self, rows):
        self.rows, self.reads, self.updates = rows, [], []

    def table(self, name):
        assert name == "agent_events", name
        return _RetQuery(self)


@pytest.fixture
def retention(monkeypatch):
    def run(scope, rows, **kw):
        db = _RetDB(rows)
        monkeypatch.setattr(ret, "_host_scope", lambda: scope)
        monkeypatch.setattr(ret, "_client", lambda: db)
        return ret.sweep(days=30, apply=True, **kw), db
    return run


def test_the_oasis_box_retires_only_oasis_rows(retention):
    res, db = retention(OASIS_BOX, STALE_BUS)
    assert {w["id"] for w in db.updates} == OASIS_IDS
    assert res["company"] == "oasis" and res["marked"] == len(OASIS_IDS)


def test_the_sunbiz_box_retires_only_sunbiz_rows(retention):
    res, db = retention(SUNBIZ_BOX, STALE_BUS)
    assert {w["id"] for w in db.updates} == SUNBIZ_IDS
    assert res["company"] == "sunbiz"


def test_every_read_is_scoped_in_the_query(retention):
    for scope in (OASIS_BOX, SUNBIZ_BOX):
        _, db = retention(scope, STALE_BUS)
        assert db.reads
        for filters in db.reads:
            cols = {c for c, _ in filters}
            assert cols & {"correlation_id", "payload->>tenant_id", "publisher_agent"}, filters


def test_the_other_companys_backlog_cannot_starve_this_one(retention):
    flood = [_ev(f"sun-{i}", OLD, tenant=SUNBIZ, corr=SUNBIZ, publisher="texttorrent")
             for i in range(50)]
    mine = _ev("oas-late", OLD, tenant=OASIS_CC, corr=OASIS_CC, publisher="dashboard")
    _, db = retention(OASIS_BOX, flood + [mine], limit=10)
    assert {w["id"] for w in db.updates} == {"oas-late"}


def test_a_box_with_no_company_refuses_and_reads_nothing(retention, capsys):
    res, db = retention(NO_COMPANY_BOX, STALE_BUS)
    assert res["refused"] and res["marked"] == 0
    assert db.reads == [] and db.updates == []
    assert "REFUSED" in capsys.readouterr().err


def test_the_cli_exits_nonzero_when_it_refuses(monkeypatch, capsys):
    monkeypatch.setattr(ret, "_host_scope", lambda: NO_COMPANY_BOX)
    monkeypatch.setattr(sys, "argv", ["event_retention.py", "--json"])
    assert ret.main() == 1
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["refused"]
