"""Compat-shim tests — the harness's Turso switch must be behavior-identical.

The RPC ports guard production semantics: reserve_send_slot's dedupe prevents
double-sends to leads, claim_events' single-winner prevents two agents
processing one event. Tests run on real libsql with the real column shapes.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lib.db_turso import TursoDB  # noqa: E402
from lib.turso_supabase_compat import (  # noqa: E402
    CompatError,
    TursoSupabaseCompat,
)


@pytest.fixture()
def client(tmp_path) -> TursoSupabaseCompat:
    db = TursoDB(str(tmp_path / "compat.db"), None, "local(test)")
    db.execute("""
        CREATE TABLE "agent_events" (
          "id" TEXT PRIMARY KEY,
          "event_type" TEXT, "publisher_agent" TEXT, "target_agent" TEXT,
          "severity" TEXT, "correlation_id" TEXT, "status" TEXT DEFAULT 'pending',
          "published_at" TEXT, "visibility_until" TEXT, "processed_at" TEXT,
          "processed_by" TEXT, "retry_count" INTEGER DEFAULT 0, "last_error" TEXT,
          "consumed_by" TEXT DEFAULT '[]', "payload" TEXT
        )""", allow_unscoped=True, reason="test setup")
    db.execute("""
        CREATE TABLE "lead_interactions" (
          "id" TEXT PRIMARY KEY, "lead_id" TEXT, "type" TEXT, "channel" TEXT,
          "created_at" TEXT, "subject" TEXT, "content" TEXT, "agent_source" TEXT,
          "cooldown_until" TEXT, "metadata" TEXT, "actor_user_id" TEXT
        )""", allow_unscoped=True, reason="test setup")
    db.execute("""
        CREATE TABLE "leads" (
          "id" TEXT PRIMARY KEY, "tenant_id" TEXT, "name" TEXT, "email" TEXT,
          "status" TEXT, "source" TEXT, "score" INTEGER, "meta" TEXT,
          "created_at" TEXT, "updated_at" TEXT, "last_contacted_at" TEXT
        )""", allow_unscoped=True, reason="test setup")
    db.commit()
    db._tenant_tables = db._discover_tenant_tables()
    return TursoSupabaseCompat(db)


# ------------------------------------------------------------------- builder

def test_insert_select_roundtrip_with_data_attribute(client):
    res = client.table("leads").insert(
        {"id": "l1", "tenant_id": "t1", "email": "a@x.com", "status": "warm",
         "score": 80, "meta": {"src": "form"}}).execute()
    assert res.data[0]["email"] == "a@x.com"
    got = client.table("leads").select("*").eq("id", "l1").single().execute()
    assert got.data["meta"] == {"src": "form"}, "jsonb round-trip must parse"


def test_filters_order_limit(client):
    for i, s in enumerate(["cold", "warm", "hot"]):
        client.table("leads").insert(
            {"id": f"f{i}", "tenant_id": "t1", "email": f"{i}@x.com",
             "status": s, "score": i * 10}).execute()
    res = client.table("leads").select("id").gte("score", 10).order(
        "score", desc=True).limit(1).execute()
    assert res.data[0]["id"] == "f2"
    ors = client.table("leads").select("id").or_("status.eq.cold,status.eq.hot").execute()
    assert {r["id"] for r in ors.data} == {"f0", "f2"}


def test_count_head_and_maybe_single(client):
    res = client.table("leads").select("id", count="exact", head=True).execute()
    assert res.data is None and res.count == 0
    assert client.table("leads").select("*").eq("id", "nope").maybe_single().execute().data is None


def test_update_delete_require_filters(client):
    with pytest.raises(CompatError, match="refused"):
        client.table("leads").update({"status": "x"}).execute()
    with pytest.raises(CompatError, match="refused"):
        client.table("leads").delete().execute()


def test_upsert_on_conflict(client):
    client.table("leads").insert(
        {"id": "u1", "tenant_id": "t1", "email": "u@x.com", "status": "cold", "score": 1}).execute()
    client.table("leads").upsert(
        {"id": "u1", "tenant_id": "t1", "email": "u@x.com", "status": "hot", "score": 9},
        on_conflict="id").execute()
    row = client.table("leads").select("*").eq("id", "u1").single().execute().data
    assert row["status"] == "hot" and row["score"] == 9


def test_auth_refuses_loudly(client):
    with pytest.raises(CompatError, match="did not migrate"):
        client.auth.get_user()


def test_storage_is_r2_backed_not_a_refuser(client):
    """`.storage` used to raise. It now resolves to R2 — see r2_storage.py.

    Asserted here rather than only in test_r2_storage.py because the wiring is
    what production depends on: send_gateway reaches storage through this
    attribute, and a `_Refuser` left in place sends the funder an email with no
    contract attached."""
    from lib.r2_storage import R2Bucket

    assert isinstance(client.storage.from_("lead-documents"), R2Bucket)


def test_unknown_rpc_raises_never_noops(client):
    """An unported RPC must raise, never return an empty result.

    The name here is deliberately one that will never exist. The original used
    `materialize_today_plan` as its example of "unported" -- and when that
    function was actually ported, this test failed for the wrong reason. A test
    whose fixture is a real backlog item goes stale the moment someone clears
    the backlog, and the failure looks like a regression instead of progress.
    """
    with pytest.raises(CompatError, match="no Turso port"):
        client.rpc("a_function_that_will_never_be_ported__fixture", {}).execute()


def test_every_registered_rpc_is_callable_by_name(client):
    """The registry and the dispatcher must not disagree.

    A name present in RPC_REGISTRY but unreachable through .rpc() would raise
    "no Turso port" for a function that HAS been ported -- the same loud failure
    as a genuine gap, which would send the next person porting it twice.
    """
    from lib.turso_supabase_compat import RPC_REGISTRY

    for name in RPC_REGISTRY:
        try:
            client.rpc(name, {}).execute()
        except CompatError as exc:
            assert "no Turso port" not in str(exc), (
                f"{name} is in RPC_REGISTRY but .rpc() reports it unported")
        except Exception:
            # Any other error means it dispatched and the body ran with empty
            # args, which is all this test cares about.
            pass


# ------------------------------------------------------ reserve_send_slot port

def test_reserve_send_slot_first_wins_second_dedupes(client):
    p = {"p_lead_id": "L1", "p_channel": "email", "p_subject": "hi",
         "p_content_preview": "x", "p_agent_source": "seq:1",
         "p_cooldown_until": None, "p_metadata": {}, "p_window_minutes": 10,
         "p_actor_user_id": None}
    first = client.rpc("reserve_send_slot", p).execute().data
    assert first["reservation_id"] and first["existing_id"] is None
    second = client.rpc("reserve_send_slot", p).execute().data
    assert second["reservation_id"] is None
    assert second["existing_id"] == first["reservation_id"], \
        "second reservation in-window must dedupe to the first — double-send otherwise"


def test_reserve_send_slot_different_channels_do_not_collide(client):
    base = {"p_lead_id": "L2", "p_subject": "s", "p_content_preview": "c",
            "p_agent_source": None, "p_cooldown_until": None, "p_metadata": {},
            "p_window_minutes": 10, "p_actor_user_id": None}
    email = client.rpc("reserve_send_slot", {**base, "p_channel": "email"}).execute().data
    sms = client.rpc("reserve_send_slot", {**base, "p_channel": "sms"}).execute().data
    assert email["reservation_id"] and sms["reservation_id"]


def test_reserve_send_slot_concurrent_racers_converge_on_one_winner(client):
    p = {"p_lead_id": "RACE", "p_channel": "email", "p_subject": "s",
         "p_content_preview": "c", "p_agent_source": None, "p_cooldown_until": None,
         "p_metadata": {}, "p_window_minutes": 10, "p_actor_user_id": None}
    results = []
    lock = threading.Lock()

    def go():
        r = client.rpc("reserve_send_slot", p).execute().data
        with lock:
            results.append(r)

    threads = [threading.Thread(target=go) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    winners = [r for r in results if r["reservation_id"]]
    assert len(winners) == 1, f"exactly one reservation must survive, got {len(winners)}"
    remaining = client.table("lead_interactions").select("id").eq(
        "lead_id", "RACE").execute().data
    assert len(remaining) == 1, "losers must withdraw their rows"


# ----------------------------------------------------------- event-bus ports

def _seed_events(client, n=3, agent=None):
    for i in range(n):
        client.table("agent_events").insert(
            {"id": f"e{i}", "event_type": "t", "target_agent": agent,
             "status": "pending", "published_at": f"2026-08-05T0{i}:00:00+00:00"}).execute()


def test_claim_events_claims_oldest_first_and_marks_processing(client):
    _seed_events(client, 3)
    got = client.rpc("claim_events", {"p_agent": "bravo", "p_max": 2}).execute().data
    assert [e["id"] for e in got] == ["e0", "e1"]
    assert all(e["status"] == "processing" for e in got)


def test_claim_events_no_double_claim(client):
    _seed_events(client, 1)
    a = client.rpc("claim_events", {"p_agent": "a1", "p_max": 5}).execute().data
    b = client.rpc("claim_events", {"p_agent": "a2", "p_max": 5}).execute().data
    assert len(a) == 1 and len(b) == 0, "a claimed event must be invisible to the next claimer"


def test_ack_event_and_fail_event_lifecycle(client):
    _seed_events(client, 1)
    client.rpc("claim_events", {"p_agent": "w", "p_max": 1}).execute()
    assert client.rpc("ack_event", {"p_event_id": "e0", "p_agent": "w"}).execute().data is True
    assert client.rpc("ack_event", {"p_event_id": "e0", "p_agent": "w"}).execute().data is False, \
        "acking a done event must return False like the PL/pgSQL FOUND"


def test_fail_event_dead_letters_at_max_retries(client):
    _seed_events(client, 1)
    statuses = [client.rpc("fail_event", {
        "p_event_id": "e0", "p_agent": "w", "p_error": "boom",
        "p_max_retries": 3}).execute().data for _ in range(3)]
    assert statuses == ["pending", "pending", "dead"]


def test_mark_event_consumed_is_idempotent_per_agent(client):
    _seed_events(client, 1)
    assert client.rpc("mark_event_consumed",
                      {"p_event_id": "e0", "p_agent": "atlas"}).execute().data is True
    assert client.rpc("mark_event_consumed",
                      {"p_event_id": "e0", "p_agent": "atlas"}).execute().data is False
    assert client.rpc("mark_event_consumed",
                      {"p_event_id": "e0", "p_agent": "maven"}).execute().data is True


def test_record_inbound_creates_lead_interaction_and_event(client):
    """The */5-min inbound email pipeline's chokepoint — full flow."""
    out = client.rpc("record_inbound_from_n8n", {
        "p_from_email": "  Prospect@Example.COM ",
        "p_subject": "Re: your offer",
        "p_content": "I want to book a call",
        "p_classification": {"priority": "hot", "intent": "booking"},
        "p_message_id": "m-1",
    }).execute().data
    assert out["status"] == "ok" and out["lead_was_new"] is True
    assert out["severity"] == "warn", "hot/booking must lift severity for Telegram digests"
    lead = client.table("leads").select("*").eq("email", "prospect@example.com").single().execute().data
    assert lead["source"] == "inbound_n8n"
    ev = client.table("agent_events").select("*").eq(
        "event_type", "inbound.classified").single().execute().data
    assert ev["payload"]["lead_id"] == lead["id"]

    # Second email from the same address must NOT create a second lead.
    again = client.rpc("record_inbound_from_n8n", {
        "p_from_email": "prospect@example.com", "p_content": "following up",
    }).execute().data
    assert again["lead_was_new"] is False and again["lead_id"] == lead["id"]
    assert again["severity"] == "info"


def test_record_inbound_refuses_garbage_email(client):
    with pytest.raises(CompatError, match="must look like an email"):
        client.rpc("record_inbound_from_n8n", {"p_from_email": "not-an-email"}).execute()


def test_reap_stuck_events_requeues_expired_processing(client):
    _seed_events(client, 1)
    client.rpc("claim_events", {"p_agent": "w", "p_max": 1,
                                "p_visibility_seconds": -5}).execute()
    n = client.rpc("reap_stuck_events", {}).execute().data
    assert n == 1
    row = client.table("agent_events").select("*").eq("id", "e0").single().execute().data
    assert row["status"] == "pending"
    assert "visibility-timeout-reaped" in row["last_error"]
