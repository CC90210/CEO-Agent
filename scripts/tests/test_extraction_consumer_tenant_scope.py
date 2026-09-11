"""extraction_consumer claims only its own company's document jobs.

Both claim queries (queued, and stale-recovery) filtered by status only, so the
consumer on SunBiz's VPS would have downloaded and read the first OASIS document
anyone queued for extraction, and reported its failures to SunBiz's channel.
No OASIS jobs exist yet (all 82 live jobs belong to SunBiz), so scoping the
claim changes nothing SunBiz does today.

The scope is the one dashboard_email_consumer uses: the tenants of the company
the box's host mailbox belongs to (lib/tenant_brand), in the query itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from integrations import extraction_consumer as ec  # noqa: E402

SUNBIZ = "aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110"
OASIS_CC = "ef8d389e-3f15-43f2-ae00-3660f69a1452"
OASIS_WEBDEV = "42423fde-be8b-454f-932a-750e8c9b743d"

SUNBIZ_BOX = {"GMAIL_USER": "submissions@sunbizfunding.com"}
OASIS_BOX = {"GMAIL_USER": "conaugh@oasisai.work"}

LONG_AGO = "2020-01-01T00:00:00Z"  # far past the stale window


def _job(jid: str, tenant: str, status: str) -> dict:
    return {"id": jid, "tenant_id": tenant, "status": status, "updated_at": LONG_AGO}


JOBS = [
    _job("sun-queued-000", SUNBIZ, "queued"),
    _job("oas-queued-000", OASIS_CC, "queued"),
    _job("sun-stale-0000", SUNBIZ, "processing"),
    _job("oas-stale-0000", OASIS_WEBDEV, "extracted"),
]


class _Query:
    """Applies eq/in_ to the rows, the way the database would, and records
    every filter so a test can see what the query itself asked for."""

    def __init__(self, rows, log):
        self._rows, self._log, self._filters = rows, log, []

    def select(self, *_a):
        return self

    def eq(self, col, val):
        self._filters.append((col, [val]))
        return self

    def in_(self, col, vals):
        self._filters.append((col, list(vals)))
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a):
        return self

    def execute(self):
        self._log.append(self._filters)
        rows = [r for r in self._rows
                if all(r.get(col) in vals for col, vals in self._filters)]
        return type("R", (), {"data": rows})()


class _Client:
    def __init__(self, rows):
        self.rows, self.queries = rows, []

    def table(self, name):
        assert name == "document_extraction_jobs", name
        return _Query(self.rows, self.queries)


def _claimed(env: dict) -> list[str]:
    client = _Client(JOBS)
    return sorted(j["id"] for j in ec._fetch_jobs(client, tenant_ids=ec._job_scope(env)))


def test_the_sunbiz_box_claims_only_sunbiz_jobs():
    assert _claimed(SUNBIZ_BOX) == ["sun-queued-000", "sun-stale-0000"]


def test_the_oasis_box_claims_only_oasis_jobs():
    assert _claimed(OASIS_BOX) == ["oas-queued-000", "oas-stale-0000"]


def test_both_claim_queries_carry_the_tenant_filter():
    client = _Client(JOBS)
    scope = ec._job_scope(SUNBIZ_BOX)
    ec._fetch_jobs(client, tenant_ids=scope)
    assert len(client.queries) == 2
    for filters in client.queries:
        assert ("tenant_id", [SUNBIZ]) in filters, filters


@pytest.mark.parametrize("env", [{}, {"GMAIL_USER": "someone@gmail.com"}])
def test_a_box_whose_mailbox_belongs_to_no_company_reads_nothing(monkeypatch, capsys, env):
    client = _Client(JOBS)
    processed: list[str] = []
    monkeypatch.setattr(ec, "process_job", lambda sb, e, job: processed.append(job["id"]))
    monkeypatch.setattr(ec, "_SCOPE_WARNED", set())
    assert ec.tick(client, env) == 0
    assert client.queries == [], "a box with no company must not even read the queue"
    assert processed == []
    assert "REFUSING TO CLAIM" in capsys.readouterr().err


def test_tick_processes_only_its_own_companys_jobs(monkeypatch):
    client = _Client(JOBS)
    processed: list[str] = []
    monkeypatch.setattr(ec, "process_job",
                        lambda sb, e, job: processed.append(job["id"]) or "applied")
    assert ec.tick(client, SUNBIZ_BOX) == 2
    assert sorted(processed) == ["sun-queued-000", "sun-stale-0000"]
