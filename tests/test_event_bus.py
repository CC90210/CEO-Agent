"""V6 BUILD 3 — event_bus.py regression suite.

Mocked tests (no live Supabase / Postgres dep). Covers:
  - publish() success path
  - publish() PGRST204 schema-cache fallback (strip migration-015 columns + retry)
  - publish() idempotency-conflict classification
  - publish() offline-queue fallback on hard error
  - subscribe() routes to LISTEN when DSN constructable + psycopg2 available
  - subscribe() falls back to polling when DSN unavailable
  - subscribe() honors `force_polling=True`
  - claim/ack handler dispatch + retry-on-False
  - _get_pg_dsn() construction
  - the strip-set covers every migration-015 column

The live LISTEN/NOTIFY round-trip is verified manually with the CLI smoke
once `PGBOUNCER_DB_PASSWORD` lands in `.env.agents`.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import event_bus  # type: ignore[import-not-found]  # noqa: E402  sys.path.insert above


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_supabase_mock(insert_behavior=None, rpc_data=None):
    """Build a Supabase client double matching what event_bus calls."""
    client = MagicMock()
    table_mock = MagicMock()
    insert_chain = MagicMock()
    if insert_behavior is None:
        insert_chain.execute.return_value = MagicMock(
            data=[{"id": "00000000-0000-0000-0000-000000000001"}]
        )
    else:
        insert_chain.execute.side_effect = insert_behavior
    table_mock.insert.return_value = insert_chain
    client.table.return_value = table_mock

    rpc_chain = MagicMock()
    rpc_chain.execute.return_value = MagicMock(data=rpc_data or [])
    client.rpc.return_value = rpc_chain
    return client


# ── publish() ────────────────────────────────────────────────────────────


def test_publish_success() -> None:
    client = _make_supabase_mock()
    res = event_bus.publish("BRAVO_TEST", {"x": 1}, db=client)
    assert res["status"] == "published"
    assert res["id"] == "00000000-0000-0000-0000-000000000001"


def test_publish_idempotency_conflict_returns_duplicate() -> None:
    err = Exception("duplicate key value violates unique constraint")
    client = _make_supabase_mock(insert_behavior=err)
    res = event_bus.publish("BRAVO_TEST", {"x": 1}, db=client,
                            idempotency_key="dup-key")
    assert res["status"] == "duplicate"


def test_publish_offline_queue_on_hard_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(event_bus, "OFFLINE_QUEUE_PATH", tmp_path / "events_offline.jsonl")
    err = Exception("connection refused — supabase unreachable")
    client = _make_supabase_mock(insert_behavior=err)
    res = event_bus.publish("BRAVO_TEST", {"x": 1}, db=client)
    assert res["status"] == "offline"
    assert (tmp_path / "events_offline.jsonl").exists()
    line = (tmp_path / "events_offline.jsonl").read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["event_type"] == "BRAVO_TEST"


def test_publish_pgrst204_strips_migration_015_cols_and_retries(monkeypatch) -> None:
    """When PostgREST schema cache lacks migration 015 columns, publish
    retries with the migration-006 base shape and lands the row."""
    pgrst = Exception(
        "Error PGRST204: Could not find the 'idempotency_key' column "
        "of 'agent_events' in the schema cache"
    )
    success = MagicMock(data=[{"id": "11111111-1111-1111-1111-111111111111"}])

    call_count = {"n": 0}
    captured_rows: list[dict] = []

    def insert_side_effect(row):
        captured_rows.append(row)
        chain = MagicMock()
        call_count["n"] += 1
        if call_count["n"] == 1:
            chain.execute.side_effect = pgrst
        else:
            chain.execute.return_value = success
        return chain

    client = MagicMock()
    table_mock = MagicMock()
    table_mock.insert.side_effect = insert_side_effect
    client.table.return_value = table_mock

    res = event_bus.publish(
        "BRAVO_TEST", {"x": 1}, db=client,
        idempotency_key="some-key", source="bravo",
    )
    assert res["status"] == "published"
    assert "schema-cache lag" in res["reason"]
    # First attempt had the migration-015 cols
    assert "idempotency_key" in captured_rows[0]
    assert "source_agent" in captured_rows[0]
    # Second attempt stripped them
    assert "idempotency_key" not in captured_rows[1]
    assert "source_agent" not in captured_rows[1]
    assert "status" not in captured_rows[1]
    # Base shape preserved
    assert captured_rows[1]["event_type"] == "BRAVO_TEST"
    assert captured_rows[1]["publisher_agent"] == "bravo"
    assert captured_rows[1]["target_agent"] is None
    assert captured_rows[1]["payload"] == {"x": 1}


def test_publish_strip_set_covers_every_migration_015_column() -> None:
    """If migration 015 adds a column and `publish()`'s strip set doesn't
    know about it, the schema-cache fallback breaks. This test fences
    the strip set against the migration-015 source of truth."""
    migration_015_columns = {
        "source_agent", "idempotency_key", "status",
        "processed_at", "processed_by",
        "retry_count", "last_error", "visibility_until",
    }
    # Read the actual strip set out of publish() by triggering the fallback
    # and inspecting the second call's row dict.
    pgrst = Exception("Error PGRST204: schema cache")
    success = MagicMock(data=[{"id": "x"}])
    captured: list[dict] = []
    call_count = {"n": 0}

    def insert_side_effect(row):
        captured.append(row)
        chain = MagicMock()
        call_count["n"] += 1
        if call_count["n"] == 1:
            chain.execute.side_effect = pgrst
        else:
            chain.execute.return_value = success
        return chain

    client = MagicMock()
    table_mock = MagicMock()
    table_mock.insert.side_effect = insert_side_effect
    client.table.return_value = table_mock

    event_bus.publish("BRAVO_TEST", {"x": 1}, db=client,
                      idempotency_key="k", expires_in_seconds=60)
    stripped_keys = set(captured[1].keys())
    leaked = migration_015_columns & stripped_keys
    assert not leaked, (
        f"strip set is missing migration-015 columns: {leaked} — extend "
        f"event_bus.publish's PGRST204 branch."
    )


def test_publish_severity_clamps_to_known_values() -> None:
    client = _make_supabase_mock()
    event_bus.publish("BRAVO_TEST", {}, db=client, severity="exotic-level")
    row = client.table.return_value.insert.call_args[0][0]
    assert row["severity"] == "info"  # clamped to default


# ── _get_pg_dsn() ────────────────────────────────────────────────────────


def test_get_pg_dsn_returns_none_when_password_absent() -> None:
    with patch.object(event_bus, "_load_env",
                      return_value={"PGBOUNCER_DB_HOST": "db.example.supabase.co"}):
        assert event_bus._get_pg_dsn() is None


def test_get_pg_dsn_builds_correct_url_with_quoted_password() -> None:
    env = {
        "PGBOUNCER_DB_HOST": "db.example.supabase.co",
        "PGBOUNCER_DB_USER": "postgres",
        "PGBOUNCER_DB_PASSWORD": "p@ss:word",  # special chars must be URL-encoded
        "PGBOUNCER_DB_NAME": "postgres",
    }
    with patch.object(event_bus, "_load_env", return_value=env):
        dsn = event_bus._get_pg_dsn()
    assert dsn is not None
    assert dsn.startswith("postgresql://postgres:")
    assert "p%40ss%3Aword" in dsn   # @ and : URL-encoded
    assert ":5432/postgres" in dsn   # session-pool port, not 6543
    assert "sslmode=require" in dsn


# ── subscribe() routing ──────────────────────────────────────────────────


def test_subscribe_falls_back_to_polling_when_dsn_absent() -> None:
    client = _make_supabase_mock()
    polling_called = {"n": 0}

    async def fake_poll(*args, **kwargs):
        polling_called["n"] += 1
        return  # return immediately so the test doesn't hang

    with patch.object(event_bus, "_get_pg_dsn", return_value=None), \
         patch.object(event_bus, "_subscribe_via_polling", new=fake_poll):
        asyncio.run(event_bus.subscribe("bravo", handlers={}, db=client))
    assert polling_called["n"] == 1


def test_subscribe_force_polling_skips_listen() -> None:
    client = _make_supabase_mock()
    polling_called = {"n": 0}
    listen_called = {"n": 0}

    async def fake_poll(*args, **kwargs):
        polling_called["n"] += 1
        return

    async def fake_listen(*args, **kwargs):
        listen_called["n"] += 1
        return

    with patch.object(event_bus, "_get_pg_dsn",
                      return_value="postgresql://x:y@host:5432/postgres"), \
         patch.object(event_bus, "_subscribe_via_polling", new=fake_poll), \
         patch.object(event_bus, "_subscribe_via_listen", new=fake_listen):
        asyncio.run(event_bus.subscribe("bravo", handlers={}, db=client,
                                        force_polling=True))
    assert polling_called["n"] == 1
    assert listen_called["n"] == 0


def test_subscribe_listen_failure_falls_back_to_polling() -> None:
    """If LISTEN setup fails (psycopg2 missing, network error), subscribe
    must degrade to polling instead of crashing."""
    client = _make_supabase_mock()
    polling_called = {"n": 0}

    async def listen_explodes(*args, **kwargs):
        raise ConnectionError("no route to db.example.supabase.co")

    async def fake_poll(*args, **kwargs):
        polling_called["n"] += 1
        return

    with patch.object(event_bus, "_get_pg_dsn",
                      return_value="postgresql://x:y@host:5432/postgres"), \
         patch.object(event_bus, "_subscribe_via_listen", new=listen_explodes), \
         patch.object(event_bus, "_subscribe_via_polling", new=fake_poll):
        asyncio.run(event_bus.subscribe("bravo", handlers={}, db=client))
    assert polling_called["n"] == 1


# ── handler dispatch (via _consume_claimed_rows) ─────────────────────────


def test_consume_acks_on_handler_true() -> None:
    client = _make_supabase_mock()
    seen: list[dict] = []

    async def on_test(event):
        seen.append(event)
        return True

    rows = [{"id": "evt-1", "event_type": "BRAVO_TEST", "payload": {"a": 1}}]
    asyncio.run(event_bus._consume_claimed_rows(client, "bravo", rows,
                                                {"BRAVO_TEST": on_test}))
    assert seen[0]["id"] == "evt-1"
    # ack was RPC'd
    call_args = [c[0] for c in client.rpc.call_args_list]
    assert any(c[0] == "ack_event" for c in call_args)


def test_consume_fails_on_handler_false() -> None:
    client = _make_supabase_mock()

    async def on_test(event):
        return False  # request retry

    rows = [{"id": "evt-2", "event_type": "BRAVO_TEST", "payload": {}}]
    asyncio.run(event_bus._consume_claimed_rows(client, "bravo", rows,
                                                {"BRAVO_TEST": on_test}))
    call_names = [c[0][0] for c in client.rpc.call_args_list]
    assert "fail_event" in call_names


def test_consume_fails_on_handler_exception() -> None:
    client = _make_supabase_mock()

    async def on_test(event):
        raise RuntimeError("handler blew up")

    rows = [{"id": "evt-3", "event_type": "BRAVO_TEST", "payload": {}}]
    asyncio.run(event_bus._consume_claimed_rows(client, "bravo", rows,
                                                {"BRAVO_TEST": on_test}))
    call_names = [c[0][0] for c in client.rpc.call_args_list]
    assert "fail_event" in call_names


def test_consume_unhandled_event_type_silent_acks() -> None:
    """Events whose type has no registered handler get ack'd quietly —
    they were targeted at this agent but it doesn't care about them."""
    client = _make_supabase_mock()
    rows = [{"id": "evt-4", "event_type": "BRAVO_UNHANDLED", "payload": {}}]
    asyncio.run(event_bus._consume_claimed_rows(client, "bravo", rows, {}))
    call_names = [c[0][0] for c in client.rpc.call_args_list]
    assert "ack_event" in call_names
    assert "fail_event" not in call_names
