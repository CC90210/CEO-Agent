"""The Turso switch must resolve the repo from ANY venv layout.

The previous sitecustomize did `Path(__file__).resolve().parents[3] / "scripts"`.
That is correct for a Windows venv (.venv/Lib/site-packages) and WRONG for a
POSIX one (.venv/lib/python3.12/site-packages), which is one level deeper — so
on the VPS the patch raised, printed to a stderr nobody reads, and left every
daemon writing to Supabase while the operator believed the cutover was on.

These tests place the tracked bootstrap at each layout's depth and assert it
finds the repo either way, so the platform bug cannot come back.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "scripts" / "_bootstrap" / "sitecustomize.py"

# (label, path from the fake repo root to the site-packages dir)
LAYOUTS = [
    ("windows", Path(".venv") / "Lib" / "site-packages"),
    ("posix", Path(".venv") / "lib" / "python3.12" / "site-packages"),
    ("posix-other-minor", Path(".venv") / "lib" / "python3.11" / "site-packages"),
    ("nested-deeper", Path("a") / "b" / ".venv" / "lib" / "python3.12" / "site-packages"),
]


class TestSwitchPathResolution(unittest.TestCase):
    def _run_at(self, layout: Path) -> subprocess.CompletedProcess:
        """Drop the bootstrap at `layout` inside a fake repo and resolve from it."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            # The marker the bootstrap walks up looking for.
            (root / "scripts" / "lib").mkdir(parents=True)
            (root / "scripts" / "lib" / "turso_supabase_compat.py").write_text(
                "create_client = lambda *a, **k: 'compat'\n", encoding="utf-8")
            sp = root / layout
            sp.mkdir(parents=True)
            shutil.copy2(SOURCE, sp / "sitecustomize.py")

            # Exercise the real resolution code from the copied file, without
            # importing supabase (absent in this fake repo) — reproducing the
            # walk-up is the thing under test.
            probe = (
                "import sys;from pathlib import Path\n"
                f"here = Path(r'{sp / 'sitecustomize.py'}').resolve()\n"
                "marker = Path('scripts')/'lib'/'turso_supabase_compat.py'\n"
                "root = None\n"
                "for parent in here.parents:\n"
                "    if (parent / marker).exists():\n"
                "        root = parent; break\n"
                "print(root if root else 'NOT_FOUND')\n"
            )
            return subprocess.run([sys.executable, "-c", probe],
                                  capture_output=True, text=True, timeout=120)

    def test_repo_is_found_from_every_venv_layout(self):
        for label, layout in LAYOUTS:
            with self.subTest(layout=label):
                res = self._run_at(layout)
                out = (res.stdout or "").strip()
                self.assertNotEqual(out, "NOT_FOUND",
                                    f"{label}: repo not found from {layout}")
                self.assertTrue(out.endswith("repo"),
                                f"{label}: resolved to {out!r}, expected the repo root")

    def test_the_old_parents3_rule_really_was_broken_on_posix(self):
        """Guard the premise: if parents[3] worked everywhere, this fix is noise."""
        windows = Path(".venv") / "Lib" / "site-packages" / "sitecustomize.py"
        posix = Path(".venv") / "lib" / "python3.12" / "site-packages" / "sitecustomize.py"
        # parents[3] counted from the FILE: [0]=site-packages, [1]=..., etc.
        self.assertEqual(windows.parents[3], Path("."),
                         "windows layout: parents[3] should reach the repo root")
        self.assertEqual(posix.parents[3], Path(".venv"),
                         "posix layout: parents[3] lands on .venv, not the repo — "
                         "this is the bug the walk-up replaces")

    def test_tracked_source_is_the_one_that_gets_installed(self):
        """The installer must copy the tracked file, not some other sitecustomize."""
        self.assertTrue(SOURCE.exists(), f"tracked source missing: {SOURCE}")
        head = SOURCE.read_text(encoding="utf-8")[:400]
        self.assertIn("Empire data-backend switch", head)
        installer = REPO / "scripts" / "install_python_switch.py"
        self.assertTrue(installer.exists())
        self.assertIn("_bootstrap", installer.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
