"""Focused regressions for dashboard-email consumer liveness.

The queue monitor must use the fleet supervisor's live OS-process verdict. A
missing legacy PM2 snapshot or an omitted manifest row is not evidence that a
consumer is down, and alert copy must not direct operators back to retired PM2.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import dashboard_email_queue_monitor as monitor  # noqa: E402
from ops import fleet_watchdog  # noqa: E402


def _fleet_row(*, running: bool, disabled: bool = False) -> dict:
    return {
        "name": monitor.CONSUMER_PROC,
        "running": running,
        "disabled": disabled,
        "root_count": 1 if running else 0,
        "unrunnable": "",
    }


def test_windows_liveness_uses_the_supervisors_live_process_verdict(monkeypatch):
    monkeypatch.setattr(monitor, "_IS_WINDOWS", True)
    monkeypatch.setattr(fleet_watchdog, "status", lambda: [_fleet_row(running=True)])

    assert monitor._consumer_online() is True

    monkeypatch.setattr(fleet_watchdog, "status", lambda: [_fleet_row(running=False)])
    assert monitor._consumer_online() is False


def test_missing_supervisor_row_is_unknown_not_a_false_down(monkeypatch):
    """A stale/omitted declaration must not masquerade as live liveness data."""
    monkeypatch.setattr(monitor, "_IS_WINDOWS", True)
    monkeypatch.setattr(fleet_watchdog, "status", list)

    assert monitor._consumer_online() is None


def test_down_alert_names_the_supervisor_not_retired_pm2(monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(monitor, "_consumer_online", lambda: False)
    monkeypatch.setattr(monitor, "_stale_queued", lambda _env, _scope: (0, None))
    monkeypatch.setattr(monitor, "_read_state", dict)
    monkeypatch.setattr(monitor, "_write_state", lambda _state: None)
    monkeypatch.setattr(
        monitor,
        "_telegram",
        lambda _env, _company, text: sent.append(text) or True,
    )

    result = monitor.check({
        "GMAIL_USER": "submissions@sunbizfunding.com",
        "GMAIL_APP_PASSWORD": str(mock.sentinel.password),
    })

    assert result["problems"] == [
        "supervised process 'dashboard-email-consumer' is DOWN",
    ]
    assert sent and "pm2" not in sent[0].lower()


@pytest.mark.parametrize("kind", ["disabled", "unrunnable"])
def test_non_operational_supervisor_states_do_not_page_as_down(monkeypatch, kind):
    row = _fleet_row(running=False, disabled=kind == "disabled")
    if kind == "unrunnable":
        row["unrunnable"] = "missing launch target"
    monkeypatch.setattr(monitor, "_IS_WINDOWS", True)
    monkeypatch.setattr(fleet_watchdog, "status", lambda: [row])

    assert monitor._consumer_online() is None
