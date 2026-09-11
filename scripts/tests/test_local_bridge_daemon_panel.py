"""The bridge's daemon panel must work on BOTH platforms it runs on.

Windows (CC's machine): never call pm2 — its named pipe spawns an orphan PM2
daemon per call there — and read daemon state from fleet_watchdog.
Linux (the SunBiz VPS): PM2 is the supervisor and fleet_watchdog cannot read
the process table, so the panel comes from `pm2 jlist`.
"""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from bravo_cli import local_bridge as lb  # noqa: E402

_TABLE = json.dumps([
    {"name": "sunbiz-sequence-runner", "pid": 11,
     "pm2_env": {"status": "online", "restart_time": 2, "pm_uptime": 5}, "monit": {"memory": 1, "cpu": 0}},
    {"name": "event-router", "pid": 0, "pm2_env": {"status": "stopped"}},
])


class TestDaemonPanelOnEachPlatform(unittest.TestCase):
    def test_on_linux_the_panel_comes_from_pm2s_own_table(self):
        done = subprocess.CompletedProcess(["pm2", "jlist"], 0, stdout=_TABLE, stderr="")
        with mock.patch.object(lb, "_IS_WINDOWS", False), \
             mock.patch.object(lb.shutil, "which", return_value="/usr/bin/pm2"), \
             mock.patch.object(lb, "safe_run", return_value=done) as run, \
             mock.patch("ops.fleet_watchdog.status", side_effect=AssertionError("Windows-only reader used on Linux")):
            out = lb.detect_pm2_daemons()
        run.assert_called_once()
        self.assertEqual(out["pm2.sunbiz-sequence-runner"]["status"], "healthy")
        self.assertEqual(out["pm2.event-router"]["status"], "down")

    def test_on_windows_pm2_is_never_called(self):
        rows = [{"name": "bravo-scheduler", "ident": "scheduler.py"}]
        with mock.patch.object(lb, "_IS_WINDOWS", True), \
             mock.patch.object(lb, "safe_run", side_effect=AssertionError("pm2 called on Windows")), \
             mock.patch("ops.fleet_watchdog.status", return_value=rows), \
             mock.patch("ops.fleet_watchdog.classify", return_value="running"):
            out = lb.detect_pm2_daemons()
        self.assertEqual(out["pm2.bravo-scheduler"]["status"], "healthy")
        self.assertEqual(out["pm2.bravo-scheduler"]["metadata"]["supervisor"], "fleet_watchdog")

    def test_a_failed_pm2_read_on_linux_is_reported_not_silent(self):
        err = io.StringIO()
        with mock.patch.object(lb, "_IS_WINDOWS", False), \
             mock.patch.object(lb.shutil, "which", return_value="/usr/bin/pm2"), \
             mock.patch.object(lb, "safe_run", side_effect=OSError("pipe closed")), \
             contextlib.redirect_stderr(err):
            out = lb.detect_pm2_daemons()
        self.assertEqual([k for k in out if k.startswith("pm2.")], [])
        self.assertIn("pm2 jlist failed", err.getvalue())

    def test_pm2_noise_before_the_table_does_not_blank_the_panel(self):
        done = subprocess.CompletedProcess(["pm2", "jlist"], 0,
                                           stdout="[PM2] Spawning PM2 daemon\n" + _TABLE, stderr="")
        with mock.patch.object(lb, "_IS_WINDOWS", False), \
             mock.patch.object(lb.shutil, "which", return_value="/usr/bin/pm2"), \
             mock.patch.object(lb, "safe_run", return_value=done):
            out = lb.detect_pm2_daemons()
        self.assertIn("pm2.sunbiz-sequence-runner", out)

    def _linux(self, table):
        done = subprocess.CompletedProcess(["pm2", "jlist"], 0, stdout=json.dumps(table), stderr="")
        with mock.patch.object(lb, "_IS_WINDOWS", False), \
             mock.patch.object(lb.shutil, "which", return_value="/usr/bin/pm2"), \
             mock.patch.object(lb, "safe_run", return_value=done):
            return lb.detect_pm2_daemons()

    def test_duplicate_names_show_the_worst_instance_not_the_last(self):
        out = self._linux([
            {"name": "worker", "pid": 1, "pm2_env": {"status": "errored", "restart_time": 3, "pm_uptime": 100}},
            {"name": "worker", "pid": 2, "pm2_env": {"status": "online", "restart_time": 1, "pm_uptime": 200}},
        ])
        meta = out["pm2.worker"]["metadata"]
        self.assertEqual(out["pm2.worker"]["status"], "down", "a healthy instance hid a dead one")
        self.assertEqual((meta["instances"], meta["restart_count"], meta["pid"], meta["uptime_ms"]), (2, 4, 1, 100))

    def test_uptime_ms_is_the_start_time_the_panel_subtracts_from_now(self):
        # BackgroundWorkersPanel.tsx renders formatUptime(Date.now() - uptime_ms).
        # Sending elapsed time here would show "up 56 years".
        out = self._linux([{"name": "w", "pid": 1, "pm2_env": {"status": "online", "pm_uptime": 1757600000000}}])
        self.assertEqual(out["pm2.w"]["metadata"]["uptime_ms"], 1757600000000)


if __name__ == "__main__":
    unittest.main()
