"""notify() may borrow SunBiz's EZRA Telegram channel only on SunBiz's own box.

EZRA_TELEGRAM_* is SunBiz's operations channel. notify() fell back to it
whenever Bravo's keys were missing, on the private lane and the group lane, on
any box. CC's machine holds EZRA keys too, so one missing Bravo key there would
have put OASIS alerts in the client's chat. On SunBiz's VPS the fallback stays
exactly as it was: it is the only way that box's daemons can alert anyone.

The box's company is the company of its authenticating mailbox
(lib/tenant_brand.host_mailbox), read from the same env the keys come from.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import notify as nf  # noqa: E402

SUNBIZ_BOX = {"GMAIL_USER": "submissions@sunbizfunding.com"}
OASIS_BOX = {"GMAIL_USER": "conaugh@oasisai.work"}
EZRA = {"EZRA_TELEGRAM_BOT_TOKEN": "ezra-token", "EZRA_TELEGRAM_CHAT_ID": "333"}
BRAVO = {"TELEGRAM_BOT_TOKEN": "bravo-token", "TELEGRAM_ALLOWED_USERS": "111"}


@pytest.fixture(autouse=True)
def _fresh():
    importlib.reload(nf)
    yield


def _capture(monkeypatch, env: dict) -> dict:
    """Run notify() against a fake env and a fake requests; return what was sent."""
    sent: dict = {}
    monkeypatch.setattr(nf, "_load_env", lambda: env)
    monkeypatch.setattr(nf, "_notify_disabled", lambda: False)
    monkeypatch.setattr(nf, "_dedup_should_send", lambda *a, **k: True)
    monkeypatch.setattr(nf, "_get_blocked_categories", lambda: set())

    class _Resp:
        status_code = 200
        text = "ok"

        @staticmethod
        def json():
            return {"ok": True}

    import requests as _real_requests

    class _Req:
        exceptions = _real_requests.exceptions

        @staticmethod
        def post(url, **kw):
            sent["url"] = url
            sent["json"] = kw.get("json") or kw.get("data")
            return _Resp()

    monkeypatch.setitem(sys.modules, "requests", _Req)
    return sent


# ── private lane ──────────────────────────────────────────────────────────────

def test_the_sunbiz_box_still_alerts_through_ezra(monkeypatch):
    sent = _capture(monkeypatch, {**SUNBIZ_BOX, **EZRA})
    assert nf.notify("event-router crashed", category="system") is True
    assert "ezra-token" in sent["url"]
    assert "333" in str(sent["json"])


def test_an_oasis_box_refuses_ezra_instead_of_alerting_sunbiz(monkeypatch, capsys):
    sent = _capture(monkeypatch, {**OASIS_BOX, **EZRA})
    assert nf.notify("event-router crashed", category="system") is False
    assert sent == {}, "an OASIS alert reached SunBiz's channel"
    err = capsys.readouterr().err
    assert "REFUSED" in err and "SunBiz" in err and "oasis" in err


def test_an_oasis_box_with_a_bot_but_no_chat_does_not_borrow_ezras_chat(monkeypatch):
    sent = _capture(monkeypatch, {**OASIS_BOX, "TELEGRAM_BOT_TOKEN": "bravo-token", **EZRA})
    assert nf.notify("event-router crashed", category="system") is False
    assert sent == {}


@pytest.mark.parametrize("box", [{}, {"GMAIL_USER": "someone@gmail.com"}])
def test_a_box_whose_mailbox_belongs_to_no_company_refuses(monkeypatch, capsys, box):
    sent = _capture(monkeypatch, {**box, **EZRA})
    assert nf.notify("event-router crashed", category="system") is False
    assert sent == {}
    assert "no registered company" in capsys.readouterr().err


@pytest.mark.parametrize("box", [OASIS_BOX, SUNBIZ_BOX])
def test_bravos_own_keys_still_win_on_every_box(monkeypatch, box):
    sent = _capture(monkeypatch, {**box, **BRAVO, **EZRA})
    assert nf.notify("event-router crashed", category="system") is True
    assert "bravo-token" in sent["url"]


def test_a_blank_gmail_user_does_not_mask_gmail_address(monkeypatch):
    env = {"GMAIL_USER": "  ", "GMAIL_ADDRESS": "submissions@sunbizfunding.com", **EZRA}
    sent = _capture(monkeypatch, env)
    assert nf.notify("event-router crashed", category="system") is True
    assert "ezra-token" in sent["url"]


# ── group lane ────────────────────────────────────────────────────────────────

def test_the_group_lane_refuses_ezra_on_an_oasis_box(monkeypatch, capsys):
    env = {**OASIS_BOX, "EZRA_TELEGRAM_BOT_TOKEN": "ezra-token",
           "GROUP_TELEGRAM_CHAT_ID": "-100200"}
    sent = _capture(monkeypatch, env)
    assert nf.notify("deploy finished", category="system", group=True) is False
    assert sent == {}
    assert "REFUSED" in capsys.readouterr().err


def test_the_group_lane_keeps_ezra_on_the_sunbiz_box(monkeypatch):
    env = {**SUNBIZ_BOX, "EZRA_TELEGRAM_BOT_TOKEN": "ezra-token",
           "GROUP_TELEGRAM_CHAT_ID": "-100300"}
    sent = _capture(monkeypatch, env)
    assert nf.notify("deploy finished", category="system", group=True) is True
    assert "ezra-token" in sent["url"]
