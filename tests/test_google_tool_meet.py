#!/usr/bin/env python3
"""Contract suite for per-event Google Meet rooms in `google_tool calendar create`.

WHAT THIS PINS, and why each pin exists:

  * The legacy `--meet` request body is UNCHANGED. `google_tool` is shared
    substrate: book_discovery_call.py, booking_engine.py and outreach_engine.py
    all ride the static-link path today. The per-event feature is additive or it
    is a regression in three other callers.
  * `--meet-per-event` sends `conferenceData.createRequest` with a requestId and
    a conferenceSolutionKey, and NOTHING else — no entryPoints, no conferenceId,
    and above all no static URL. Google mints the room; we do not name it.
  * The static room is not merely unused in per-event mode, it is UNREACHABLE.
    A silent fallback to the one shared GOOGLE_MEET_LINK is how two prospects
    end up in the same call with nobody noticing.
  * The link is READ BACK off the API response, never assumed. `createRequest`
    can come back `pending` (room not minted yet) or `failure` (Meet creation
    disabled for the Workspace) while the EVENT STILL EXISTS and Google has
    already mailed the invite (sendUpdates: "all"). Both cases must fail loudly,
    with the event id, at a distinct exit code — not as a generic error, and
    never as a success carrying the shared room.
  * requestId is the idempotency key. An over-long or empty one is rejected
    before the call, not silently truncated into a second room on retry.

NOTHING IN HERE TOUCHES PRODUCTION. `run_gws` is monkeypatched in every test
that reaches it; no calendar event is created, no invite is mailed, no
credential is read (an autouse fixture makes any call to the real `run_gws` or
to `load_env` an immediate, loud failure).

Run:
    python -m pytest tests/test_google_tool_meet.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(REPO_ROOT / "scripts"), str(REPO_ROOT / "scripts" / "integrations")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import google_tool  # noqa: E402

# A stand-in for the real shared room. The real GOOGLE_MEET_LINK lives in
# .env.agents and is never read here.
FAKE_STATIC = "https://meet.google.com/static-shared-room"


@pytest.fixture(autouse=True)
def _no_live_google(monkeypatch):
    """Any unstubbed escape to Google or to .env.agents fails the test."""
    def _boom(*_a, **_kw):  # pragma: no cover - only runs on a real defect
        raise AssertionError("test attempted a live gws / credential call")
    monkeypatch.setattr(google_tool, "run_gws", _boom)
    monkeypatch.setattr(google_tool, "load_env", _boom)
    monkeypatch.delenv("GOOGLE_MEET_LINK", raising=False)


def _args(**over):
    base = dict(title="t", start="2026-08-25T09:00", end="2026-08-25T09:30",
                attendees=None, meet=False, meet_per_event=False,
                meet_request_id=None, description=None,
                timezone="America/Toronto", dry_run=False, json_output=False)
    base.update(over)
    return SimpleNamespace(**base)


def _body(capsys, **over):
    """Run calendar_create in --dry-run and return the events.insert body."""
    google_tool.calendar_create(_args(dry_run=True, **over))
    return json.loads(capsys.readouterr().out)


# ── the legacy path must not move ──────────────────────────────────────────

def test_static_meet_body_is_byte_for_byte_the_legacy_shape(capsys, monkeypatch):
    monkeypatch.setenv("GOOGLE_MEET_LINK", FAKE_STATIC)
    conf = _body(capsys, meet=True)["event"]["conferenceData"]
    assert conf == {
        "entryPoints": [{
            "entryPointType": "video",
            "uri": FAKE_STATIC,
            "label": "meet.google.com/static-shared-room",
        }],
        "conferenceSolution": {"key": {"type": "hangoutsMeet"}, "name": "Google Meet"},
        "conferenceId": "static-shared-room",
    }


def test_static_meet_without_env_still_omits_conference_data(capsys):
    # Historical behaviour, deliberately preserved: no static link configured
    # means an event with no room. ig_closer.resolve_meet_link() is what guards
    # that for the booking path; changing it here would change three callers.
    assert "conferenceData" not in _body(capsys, meet=True)["event"]


def test_no_meet_flag_sends_no_conference_data(capsys, monkeypatch):
    monkeypatch.setenv("GOOGLE_MEET_LINK", FAKE_STATIC)
    assert "conferenceData" not in _body(capsys)["event"]


# ── the per-event request body ─────────────────────────────────────────────

def test_per_event_sends_create_request_and_nothing_else(capsys):
    conf = _body(capsys, meet_per_event=True, meet_request_id="rid-123")["event"]["conferenceData"]
    assert conf == {"createRequest": {"requestId": "rid-123",
                                      "conferenceSolutionKey": {"type": "hangoutsMeet"}}}


def test_per_event_never_carries_the_static_room(capsys, monkeypatch):
    monkeypatch.setenv("GOOGLE_MEET_LINK", FAKE_STATIC)
    payload = _body(capsys, meet_per_event=True, meet=True, meet_request_id="rid")
    assert FAKE_STATIC not in json.dumps(payload)
    assert "createRequest" in payload["event"]["conferenceData"]


def test_params_carry_conference_data_version_and_send_updates(capsys):
    # Without conferenceDataVersion=1 the API silently ignores conferenceData
    # entirely and the event is created with no room at all.
    params = _body(capsys, meet_per_event=True, meet_request_id="rid")["params"]
    assert params["conferenceDataVersion"] == 1
    assert params["sendUpdates"] == "all"


def test_dry_run_creates_nothing(capsys):
    # The autouse fixture turns any run_gws call into an AssertionError, so
    # reaching this line at all proves the dry path is inert.
    payload = _body(capsys, meet_per_event=True, meet_request_id="rid")
    assert payload["dry_run"] is True and payload["meet_mode"] == "per_event"


# ── requestId is the idempotency key ───────────────────────────────────────

def test_generated_request_id_is_unique_and_within_googles_limit():
    a = google_tool.build_meet_request_id()
    b = google_tool.build_meet_request_id()
    assert a != b and 0 < len(a) <= google_tool.MEET_REQUEST_ID_MAX


def test_supplied_request_id_is_used_verbatim_so_a_retry_reuses_the_room():
    assert google_tool.build_meet_request_id("igdm-abc-20260825T0900") == "igdm-abc-20260825T0900"


@pytest.mark.parametrize("bad", ["", "   ", "x" * 65])
def test_bad_request_id_is_rejected_not_truncated(bad):
    with pytest.raises(ValueError):
        google_tool.build_meet_request_id(bad)


# ── the link is read back, never assumed ───────────────────────────────────

def _stub_insert(monkeypatch, response):
    monkeypatch.setattr(google_tool, "run_gws", lambda *_a, **_kw: (response, None))


def test_success_reads_the_minted_link_off_the_response(capsys, monkeypatch):
    _stub_insert(monkeypatch, {
        "id": "evt_1", "summary": "t", "htmlLink": "https://cal/evt_1",
        "start": {"dateTime": "2026-08-25T09:00:00-04:00"},
        "conferenceData": {"createRequest": {"status": {"statusCode": "success"}},
                           "entryPoints": [{"entryPointType": "video",
                                            "uri": "https://meet.google.com/minted-abc"}]},
        "hangoutLink": "https://meet.google.com/minted-abc",
    })
    google_tool.calendar_create(_args(meet_per_event=True, meet_request_id="rid"))
    out = capsys.readouterr().out
    assert "https://meet.google.com/minted-abc" in out
    assert "per-event" in out and "evt_1" in out


def test_entry_point_uri_is_used_when_hangout_link_is_absent(capsys, monkeypatch):
    _stub_insert(monkeypatch, {
        "id": "evt_2", "summary": "t", "start": {},
        "conferenceData": {"createRequest": {"status": {"statusCode": "success"}},
                           "entryPoints": [{"entryPointType": "video",
                                            "uri": "https://meet.google.com/from-entry"}]},
    })
    google_tool.calendar_create(_args(meet_per_event=True, meet_request_id="rid"))
    assert "https://meet.google.com/from-entry" in capsys.readouterr().out


@pytest.mark.parametrize("response,label", [
    ({"id": "evt_p", "summary": "t", "htmlLink": "https://cal/evt_p", "start": {},
      "conferenceData": {"createRequest": {"status": {"statusCode": "pending"}}}}, "pending"),
    ({"id": "evt_f", "summary": "t", "htmlLink": "https://cal/evt_f", "start": {},
      "conferenceData": {"createRequest": {"status": {"statusCode": "failure"}}}}, "failure"),
    ({"id": "evt_n", "summary": "t", "htmlLink": "https://cal/evt_n", "start": {}}, ""),
])
def test_no_room_fails_loudly_with_the_event_id(capsys, monkeypatch, response, label):
    monkeypatch.setenv("GOOGLE_MEET_LINK", FAKE_STATIC)
    _stub_insert(monkeypatch, response)
    with pytest.raises(SystemExit) as exc:
        google_tool.calendar_create(_args(meet_per_event=True, meet_request_id="rid"))
    assert exc.value.code == google_tool.EXIT_EVENT_WITHOUT_MEET
    cap = capsys.readouterr()
    # The operator is told the event EXISTS and how to cancel it.
    assert "EVENT CREATED BUT IT HAS NO PER-EVENT MEET ROOM" in cap.err
    assert response["id"] in cap.err
    # And it is machine-readable without --json, because the caller needs the
    # id to clean up and must not scrape stderr for it.
    payload = json.loads(cap.out)
    assert payload == {"ok": False, "error": "meet_room_not_created",
                       "event_created": True, "event_id": response["id"],
                       "html_link": response["htmlLink"], "meet_status": label,
                       "meet_link": None}
    # The disaster case: a shared room quietly presented as this call's room.
    assert FAKE_STATIC not in cap.out and FAKE_STATIC not in cap.err


def test_no_room_exit_code_is_distinct_from_plain_failure(capsys, monkeypatch):
    # exit 1 means nothing was created and a retry is safe. The no-room case is
    # NOT that: an event and an invite are already out there.
    assert google_tool.EXIT_EVENT_WITHOUT_MEET != 1
    monkeypatch.setattr(google_tool, "run_gws", lambda *_a, **_kw: (None, "boom"))
    with pytest.raises(SystemExit) as exc:
        google_tool.calendar_create(_args(meet_per_event=True, meet_request_id="rid"))
    assert exc.value.code == 1
    capsys.readouterr()


def test_legacy_static_path_does_not_gain_the_no_room_gate(capsys, monkeypatch):
    # A static-link event whose response carries no conferenceData is the
    # historical norm; it must keep exiting 0 or three callers start failing.
    monkeypatch.setenv("GOOGLE_MEET_LINK", FAKE_STATIC)
    _stub_insert(monkeypatch, {"id": "evt_s", "summary": "t", "htmlLink": "h", "start": {}})
    google_tool.calendar_create(_args(meet=True))
    assert "Event created" in capsys.readouterr().out


def test_extract_conference_tolerates_junk():
    assert google_tool.extract_conference(None) == ("", "")
    assert google_tool.extract_conference("<html>") == ("", "")
    assert google_tool.extract_conference({}) == ("", "")
