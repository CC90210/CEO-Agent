"""db_snapshot.py — the runnable half of V9.0 Defense #5.

The tool's whole value is its exit code: `verify` must return 0 ONLY when a
usable restore point exists. Every test here attacks that promise — a partial
capture, a tampered file, a stale one, an empty schema — because a gate that
says PASS when it shouldn't is worse than no gate at all (the migration goes
ahead either way, but with false confidence).

No network: a fake Supabase client stands in for the SDK.
"""
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── fakes ────────────────────────────────────────────────────────────────────

class _FakeQuery:
    def __init__(self, table: str, store: dict, fail: set[str], seen_order: list):
        self.table, self.store, self.fail = table, store, fail
        self._range = None
        self._seen_order = seen_order

    def select(self, *_a, **kw):
        self._count_mode = kw.get("count")
        return self

    def limit(self, _n):
        return self

    def order(self, column):
        self._seen_order.append((self.table, column))
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        if self.table in self.fail:
            raise RuntimeError("permission denied for table")
        rows = self.store.get(self.table, [])
        if self._range is not None:
            s, e = self._range
            return type("R", (), {"data": rows[s:e + 1], "count": len(rows)})()
        return type("R", (), {"data": [], "count": len(rows)})()


class FakeClient:
    def __init__(self, store: dict, fail: set[str] | None = None):
        self.store, self.fail = store, fail or set()
        self.ordered_by: list = []          # (table, column) per .order() call

    def table(self, name):
        return _FakeQuery(name, self.store, self.fail, self.ordered_by)


@pytest.fixture()
def ds(tmp_path, monkeypatch):
    """db_snapshot with an isolated snapshot dir — never the real tmp/snapshots."""
    import db_snapshot as _ds
    importlib.reload(_ds)
    monkeypatch.setattr(_ds, "SNAPSHOT_DIR", tmp_path / "snapshots")
    return _ds


def wire(ds, monkeypatch, store, schema=None, fail=None) -> FakeClient:
    """Point the module at fakes instead of Supabase. Returns the fake client so
    a test can assert on how it was queried."""
    fake_env = {"BRAVO_SUPABASE_URL": "https://x.supabase.co",
                "BRAVO_SUPABASE_SERVICE_ROLE_KEY": "k",
                "OASIS_SUPABASE_URL": "https://o.supabase.co",
                "OASIS_SUPABASE_SERVICE_ROLE_KEY": "k"}
    client = FakeClient(store, fail)
    stub = type("S", (), {
        "load_env": staticmethod(lambda: fake_env),
        "PROJECTS": {"bravo": {"url_key": "BRAVO_SUPABASE_URL",
                               "key_key": "BRAVO_SUPABASE_SERVICE_ROLE_KEY"},
                     "oasis": {"url_key": "OASIS_SUPABASE_URL",
                               "key_key": "OASIS_SUPABASE_SERVICE_ROLE_KEY"}},
        "get_client": staticmethod(lambda *_a, **_k: client),
    })
    monkeypatch.setattr(ds, "_supabase", lambda: stub)
    monkeypatch.setattr(ds, "discover_schema",
                        lambda *_a, **_k: schema if schema is not None
                        else {t: {"columns": ["id"], "pk": ["id"]} for t in store})
    return client


class Args:
    def __init__(self, **kw):
        self.project = "bravo"
        self.output_json = False
        self.name = None
        self.rows = "0"
        self.file = None
        self.max_age_hours = 24.0
        self.no_live = False
        self.allow_missing_tables = False
        self.__dict__.update(kw)


# ── create ───────────────────────────────────────────────────────────────────

def test_create_writes_a_checksummed_snapshot(ds, monkeypatch):
    wire(ds, monkeypatch, {"leads": [{"id": 1}, {"id": 2}], "agent_events": [{"id": 9}]})
    assert ds.cmd_create(Args(name="pre-0061")) == 0

    files = list(ds.SNAPSHOT_DIR.glob("*_db_snapshot.json"))
    assert len(files) == 1, files
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["table_count"] == 2
    assert payload["total_rows"] == 3
    assert payload["tables"]["leads"]["row_count"] == 2
    assert payload["complete"] is True
    assert payload["content_sha256"] == ds._checksum(payload)


def test_create_exits_nonzero_when_a_table_fails(ds, monkeypatch):
    """A partial capture must not read as a restore point — this is the exact
    path by which a migration gets applied against a baseline nobody took."""
    wire(ds, monkeypatch, {"leads": [{"id": 1}], "locked": []}, fail={"locked"})
    assert ds.cmd_create(Args()) == 1
    payload = json.loads(next(ds.SNAPSHOT_DIR.glob("*.json")).read_text(encoding="utf-8"))
    assert payload["complete"] is False
    assert payload["errors"], "capture errors must be recorded, not swallowed"


def test_create_refuses_an_empty_schema(ds, monkeypatch):
    """Discovery returning nothing is a failure, not an empty backup: an empty
    snapshot would verify perfectly clean and protect nothing."""
    import requests

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"definitions": {}, "paths": {"/": {}}}

    monkeypatch.setattr(requests, "get", lambda *_a, **_k: _Resp())
    with pytest.raises(RuntimeError, match="no tables"):
        ds.discover_schema("https://x.supabase.co", "k")


def test_rows_export_is_opt_in(ds, monkeypatch):
    store = {"leads": [{"id": i} for i in range(5)]}
    wire(ds, monkeypatch, store)

    assert ds.cmd_create(Args()) == 0
    counts_only = json.loads(next(ds.SNAPSHOT_DIR.glob("*.json")).read_text(encoding="utf-8"))
    assert "rows" not in counts_only["tables"]["leads"]
    assert counts_only["rows_captured"] is False

    for f in ds.SNAPSHOT_DIR.glob("*.json"):
        f.unlink()
    assert ds.cmd_create(Args(rows="all")) == 0
    with_rows = json.loads(next(ds.SNAPSHOT_DIR.glob("*.json")).read_text(encoding="utf-8"))
    assert with_rows["tables"]["leads"]["rows_captured"] == 5
    assert with_rows["rows_captured"] is True


# ── verify: the gate ─────────────────────────────────────────────────────────

def test_negative_rows_is_rejected_not_treated_as_all(ds, monkeypatch):
    """Codex [P2] round 3. `--rows -1` used to map to MAX_ROWS_PER_TABLE, so a
    typo silently dumped 50k production rows per table to disk. Fail closed."""
    wire(ds, monkeypatch, {"leads": [{"id": 1}]})
    assert ds.cmd_create(Args(rows="-1")) == 2
    assert ds.cmd_create(Args(rows="banana")) == 2
    assert not list(ds.SNAPSHOT_DIR.glob("*.json")), "nothing may be written on a rejected run"


def test_two_creates_in_the_same_second_do_not_overwrite(ds, monkeypatch):
    """Codex [P2] round 3. A scripted gate can call create twice inside one
    second; the second write silently destroyed the first restore point."""
    wire(ds, monkeypatch, {"leads": [{"id": 1}]})
    fixed = datetime(2026, 8, 2, 22, 31, 16, tzinfo=timezone.utc)
    monkeypatch.setattr(ds, "_now", lambda: fixed)

    assert ds.cmd_create(Args(name="first")) == 0
    assert ds.cmd_create(Args(name="second")) == 0

    files = sorted(ds.SNAPSHOT_DIR.glob("*_db_snapshot.json"))
    assert len(files) == 2, [f.name for f in files]
    labels = {json.loads(f.read_text(encoding="utf-8"))["label"] for f in files}
    assert labels == {"first", "second"}, labels


def test_verify_passes_on_a_fresh_complete_snapshot(ds, monkeypatch):
    wire(ds, monkeypatch, {"leads": [{"id": 1}]})
    assert ds.cmd_create(Args()) == 0
    assert ds.cmd_verify(Args()) == 0


def test_verify_fails_when_no_snapshot_exists(ds, monkeypatch):
    assert ds.cmd_verify(Args(no_live=True)) == 1


def test_another_projects_snapshot_cannot_satisfy_this_gate(ds, monkeypatch):
    """Codex [P2] round 2. A fresh OASIS baseline must not green-light a Bravo
    pre-migration gate — that passes while no Bravo baseline exists at all."""
    wire(ds, monkeypatch, {"leads": [{"id": 1}]})
    assert ds.cmd_create(Args(project="oasis")) == 0
    assert list(ds.SNAPSHOT_DIR.glob("*_oasis_db_snapshot.json")), \
        "project must be in the filename so lookup can be scoped"

    assert ds.cmd_verify(Args(project="bravo", no_live=True)) == 1   # wrong project
    assert ds.cmd_verify(Args(project="oasis", no_live=True)) == 0   # its own


def test_explicit_project_must_match_an_explicit_file(ds, monkeypatch):
    """--file bypasses the newest-snapshot lookup, so the match is re-checked."""
    wire(ds, monkeypatch, {"leads": [{"id": 1}]})
    ds.cmd_create(Args(project="oasis"))
    other = next(ds.SNAPSHOT_DIR.glob("*_oasis_db_snapshot.json"))

    assert ds.cmd_verify(Args(project="bravo", file=str(other), no_live=True)) == 1
    assert ds.cmd_verify(Args(project=None, file=str(other), no_live=True)) == 0


def test_verify_fails_on_a_tampered_file(ds, monkeypatch):
    wire(ds, monkeypatch, {"leads": [{"id": 1}]})
    ds.cmd_create(Args())
    path = next(ds.SNAPSHOT_DIR.glob("*.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tables"]["leads"]["row_count"] = 999          # edited after capture
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert ds.cmd_verify(Args(no_live=True)) == 1


def test_verify_fails_on_a_stale_snapshot(ds, monkeypatch):
    wire(ds, monkeypatch, {"leads": [{"id": 1}]})
    ds.cmd_create(Args())
    path = next(ds.SNAPSHOT_DIR.glob("*.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["created_at"] = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    payload["content_sha256"] = ds._checksum(payload)      # re-sign: only age is wrong
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert ds.cmd_verify(Args(no_live=True, max_age_hours=24)) == 1
    assert ds.cmd_verify(Args(no_live=True, max_age_hours=72)) == 0


def test_verify_fails_when_the_capture_was_incomplete(ds, monkeypatch):
    wire(ds, monkeypatch, {"leads": [{"id": 1}], "locked": []}, fail={"locked"})
    ds.cmd_create(Args())
    assert ds.cmd_verify(Args(no_live=True)) == 1


def test_verify_reports_drift_without_failing(ds, monkeypatch, capsys):
    """Rows changing since capture is normal — it is information, not a gate
    failure. Only integrity, completeness and freshness block."""
    store = {"leads": [{"id": 1}]}
    wire(ds, monkeypatch, store)
    ds.cmd_create(Args())
    store["leads"].append({"id": 2})                       # live table moved on

    assert ds.cmd_verify(Args()) == 0
    out = capsys.readouterr().out
    assert "drift since capture" in out
    assert "1 -> 2" in out


def test_report_survives_a_cp1252_console(ds, monkeypatch, capsys):
    """The real Windows console is cp1252 and pytest captures in utf-8, so a
    non-ASCII diagnostic passes every test and crashes the live gate mid-report.
    That is exactly what U+2192 did on first contact. Assert the report is
    encodable by the console that will actually print it."""
    store = {"leads": [{"id": 1}]}
    wire(ds, monkeypatch, store)
    ds.cmd_create(Args())
    store["leads"].append({"id": 2})                       # force the drift branch
    ds.cmd_verify(Args())

    captured = capsys.readouterr()
    for stream_name, text in (("stdout", captured.out), ("stderr", captured.err)):
        try:
            text.encode("cp1252")
        except UnicodeEncodeError as exc:
            pytest.fail(f"{stream_name} is not cp1252-encodable: {exc}")


def test_a_vanished_table_blocks_the_gate_by_default(ds, monkeypatch):
    """Codex [P2]. A captured table that is now unreadable means the live schema
    no longer matches the baseline — the exact state this gate exists to catch.
    It must block WITHOUT the caller knowing to pass an extra flag; a gate that
    fails open is worse than no gate, because it prints VERIFIED."""
    store = {"leads": [{"id": 1}], "temp_thing": [{"id": 1}]}
    wire(ds, monkeypatch, store)
    ds.cmd_create(Args())
    wire(ds, monkeypatch, store, fail={"temp_thing"})      # table now unreadable

    assert ds.cmd_verify(Args()) == 1                      # blocks by default
    assert ds.cmd_verify(Args(allow_missing_tables=True)) == 0   # explicit waiver


# ── export integrity ─────────────────────────────────────────────────────────

def test_row_export_sorts_by_primary_key(ds, monkeypatch):
    """Paginated export without a stable sort can duplicate and skip rows, and
    the resulting file looks perfectly valid. Assert the sort is actually asked
    for rather than trusting that it is."""
    client = wire(ds, monkeypatch, {"leads": [{"id": i} for i in range(3)]},
                  schema={"leads": {"columns": ["id", "email"], "pk": ["id"]}})
    assert ds.cmd_create(Args(rows="all")) == 0
    assert ("leads", "id") in client.ordered_by, client.ordered_by

    payload = json.loads(next(ds.SNAPSHOT_DIR.glob("*.json")).read_text(encoding="utf-8"))
    assert payload["tables"]["leads"]["rows_ordered_by"] == "id"


def test_unsortable_multipage_export_is_reported_not_hidden(ds, monkeypatch):
    """A view with no primary key can't be paged deterministically. That must
    surface as a capture error (→ not a restore point), never as a clean file."""
    big = {"v_report": [{"n": i} for i in range(ds.ROW_PAGE + 5)]}
    wire(ds, monkeypatch, big,
         schema={"v_report": {"columns": ["n"], "pk": []}})
    assert ds.cmd_create(Args(rows="all")) == 1
    payload = json.loads(next(ds.SNAPSHOT_DIR.glob("*.json")).read_text(encoding="utf-8"))
    assert payload["complete"] is False
    assert any("no primary key" in e for e in payload["errors"]), payload["errors"]


def test_verify_never_claims_more_coverage_than_it_captured(ds, monkeypatch, capsys):
    """Honesty gate: a counts-only snapshot must say so and point at PITR,
    because 'VERIFIED' next to a logical snapshot is how someone drops a table
    believing they can roll it back."""
    wire(ds, monkeypatch, {"leads": [{"id": 1}]})
    ds.cmd_create(Args())
    ds.cmd_verify(Args(no_live=True))
    out = capsys.readouterr().out
    assert "counts only" in out
    assert "PITR" in out


def test_snapshots_are_protected_from_tmp_hygiene():
    """tmp/ is swept every week; a restore point the sweep deletes is worse than
    none, because the gate reports VERIFIED right up until the file is gone."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "utilities"))
    import tmp_hygiene
    assert tmp_hygiene._is_allowlisted("snapshots"), \
        "tmp/snapshots must be allowlisted in tmp_hygiene.ALLOWLIST_PATTERNS"
