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

    def test_on_windows_duplicate_roots_are_visible_as_down(self):
        rows = [{"name": "bravo-scheduler", "ident": "scheduler.py",
                 "root_count": 2, "root_pids": [100, 200]}]
        with mock.patch.object(lb, "_IS_WINDOWS", True), \
             mock.patch.object(lb, "safe_run", side_effect=AssertionError("pm2 called on Windows")), \
             mock.patch("ops.fleet_watchdog.status", return_value=rows), \
             mock.patch("ops.fleet_watchdog.classify", return_value="duplicate"):
            out = lb.detect_pm2_daemons()
        row = out["pm2.bravo-scheduler"]
        self.assertEqual(row["status"], "down")
        self.assertIn("duplicate", row["metadata"]["pm2_status"])
        self.assertEqual(row["metadata"]["root_pids"], [100, 200])

    def test_on_windows_a_failed_fleet_read_is_a_down_row_not_an_absence(self):
        # 2026-09-23: status() raised inside the long-running bridge, the pm2.*
        # rows silently dropped out of the ping, and the panel showed twelve
        # running daemons as "Down" for a day. The failure must be a row.
        with mock.patch.object(lb, "_IS_WINDOWS", True), \
             mock.patch.object(lb, "_log") as log, \
             mock.patch("ops.fleet_watchdog.status",
                        side_effect=RuntimeError("process table unreadable")), \
             contextlib.redirect_stderr(io.StringIO()):
            out = lb.detect_pm2_daemons()
        self.assertEqual([k for k in out if k.startswith("pm2.")], [])
        row = out["fleet_watchdog"]
        self.assertEqual(row["status"], "down")
        self.assertEqual(row["metadata"]["reason"], "status_source_unavailable")
        self.assertIn("process table unreadable", row["metadata"]["error"])
        # Written to the bridge log file, which survives a detached process.
        self.assertIn("fleet status unavailable", log.call_args.args[0])

    def test_on_windows_a_good_fleet_read_reports_its_source_healthy(self):
        rows = [{"name": "bravo-scheduler", "ident": "scheduler.py"},
                {"name": "event-router", "ident": "event_router.py"}]
        with mock.patch.object(lb, "_IS_WINDOWS", True), \
             mock.patch("ops.fleet_watchdog.status", return_value=rows), \
             mock.patch("ops.fleet_watchdog.classify", return_value="running"):
            out = lb.detect_pm2_daemons()
        self.assertEqual(out["fleet_watchdog"]["status"], "healthy")
        self.assertEqual(out["fleet_watchdog"]["metadata"]["workers_reported"], 2)

    def test_fleet_module_is_reloaded_when_its_file_changes(self):
        # The bridge runs for days; a fix to fleet_watchdog.py must reach it
        # without a restart.
        lb._fleet_watchdog_module()
        lb._FLEET_MODULE_STATE["mtime"] = -1.0  # pretend the file changed
        with mock.patch("importlib.reload", side_effect=lambda m: m) as reload, \
             mock.patch.object(lb, "_log"):
            lb._fleet_watchdog_module()
        reload.assert_called_once()
        with mock.patch("importlib.reload") as reload_again:
            lb._fleet_watchdog_module()
        reload_again.assert_not_called()

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
