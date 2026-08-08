"""A backup that skipped documents must never report success.

cmd_export guards against pulling objects outside the SunBiz tenant prefix —
correct — but it used to `continue` SILENTLY: the object never reached the
archive, nothing was counted, nothing was printed, and the run still finished
with "export OK". An archive that is quietly missing documents is worse than one
that admits it, because it gets trusted for a restore it cannot perform.

The guard had no test at all, so the new fail-loud behaviour would otherwise be
asserted rather than proven.
"""
from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ops import _supabase_backup as bk  # noqa: E402

TENANT = bk.SUNBIZ_TENANT_ID
GOOD = f"{TENANT}/lead-1/statement.pdf"
FOREIGN = "some-other-tenant/lead-9/secret.pdf"


def _run_export(doc_rows, download_ok=True):
    """Run cmd_export against stubbed table + storage reads."""
    def fake_page_table(_sb, table):
        return doc_rows if table == "lead_documents" else []

    class FakeBucket:
        def download(self, path):
            if not download_ok:
                raise RuntimeError("object missing")
            return b"%PDF-1.4 fake"

    class FakeStorage:
        def from_(self, _bucket):
            return FakeBucket()

    fake_sb = mock.Mock()
    fake_sb.storage = FakeStorage()

    with TemporaryDirectory() as tmp:
        out = Path(tmp) / "backup"
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(bk, "_client", return_value=fake_sb), \
             mock.patch.object(bk, "_page_table", fake_page_table), \
             mock.patch.object(bk, "TABLES", []), \
             redirect_stdout(stdout), redirect_stderr(stderr):
            code = bk.cmd_export(out)
        manifest = {}
        mf = out / "manifest.json"
        if mf.exists():
            import json
            manifest = json.loads(mf.read_text(encoding="utf-8"))
        return code, manifest, stdout.getvalue(), stderr.getvalue()


class TestBackupCompleteness(unittest.TestCase):
    def test_a_clean_run_reports_ok(self):
        code, man, out, _err = _run_export([{"storage_path": GOOD}])
        self.assertEqual(code, 0, "a complete backup should exit 0")
        self.assertEqual(man["storage"]["objects"], 1)
        self.assertEqual(man["storage"]["skipped_foreign"], 0)
        self.assertIn("export OK", out)

    def test_a_skipped_object_is_counted_not_dropped(self):
        _code, man, _out, _err = _run_export([
            {"storage_path": GOOD}, {"storage_path": FOREIGN}])
        self.assertEqual(man["storage"]["skipped_foreign"], 1,
                         "the guard must COUNT what it refuses")
        self.assertEqual(man["storage"]["objects"], 1,
                         "the in-tenant object should still be archived")

    def test_a_skipped_object_forbids_export_ok(self):
        """The regression this file exists for."""
        code, _man, out, err = _run_export([
            {"storage_path": GOOD}, {"storage_path": FOREIGN}])
        self.assertNotEqual(code, 0, "a backup missing a document exited 0")
        self.assertNotIn("export OK", out,
                         "a backup missing a document reported success")
        self.assertIn("INCOMPLETE", err)
        self.assertIn("SKIPPED", err, "the operator needs the per-object line")

    def test_the_message_names_both_possible_causes(self):
        """Either cause is actionable; a bare count is not."""
        _code, _man, _out, err = _run_export([{"storage_path": FOREIGN}])
        self.assertIn("another tenant", err)
        self.assertIn("over-matching", err)

    def test_an_unreadable_object_still_fails_loudly(self):
        """The pre-existing guarantee must survive the change."""
        code, man, out, err = _run_export([{"storage_path": GOOD}],
                                          download_ok=False)
        self.assertNotEqual(code, 0)
        self.assertEqual(man["storage"]["failed"], 1)
        self.assertNotIn("export OK", out)
        self.assertIn("UNREADABLE", err)

    def test_both_failure_modes_are_reported_together(self):
        _code, _man, _out, err = _run_export(
            [{"storage_path": GOOD}, {"storage_path": FOREIGN}], download_ok=False)
        self.assertIn("UNREADABLE", err)
        self.assertIn("SKIPPED", err)


if __name__ == "__main__":
    unittest.main()
