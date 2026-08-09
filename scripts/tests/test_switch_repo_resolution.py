"""One interpreter, three sibling agents, three different `lib` packages.

Bravo, Atlas (CFO-Agent) and Maven (CMO-Agent) all run under the same system
Python on CC's machine. Each ships its own REGULAR scripts/lib package. Python
binds a regular package to exactly one directory, so whichever repo reaches
sys.path first owns `lib` for the entire process and every sibling's lib.*
module disappears.

2026-08-08: setting EMPIRE_REPO_ROOT to Bravo in order to flip atlas-scheduler
put Bravo's scripts/ first. Atlas crash-looped on
`ModuleNotFoundError: lib.schedule_helpers` after 29h of uptime.

The fix is precedence: the SCRIPT BEING RUN decides the repo, because that is
the only signal that differs per process. EMPIRE_REPO_ROOT is a single global
value and therefore cannot answer a per-process question -- it is now last.

These tests pin that ordering.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO / "scripts" / "_bootstrap" / "sitecustomize.py"


def _load():
    """Import the bootstrap WITHOUT executing its install (no flag set)."""
    spec = importlib.util.spec_from_file_location("_sc_under_test", BOOTSTRAP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_repo(root: Path, name: str) -> Path:
    """A directory shaped like a repo carrying the shim."""
    r = root / name
    (r / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (r / "scripts" / "lib" / "turso_supabase_compat.py").write_text(
        "# marker\n", encoding="utf-8")
    return r


class TestRepoResolution(unittest.TestCase):
    def setUp(self):
        self.mod = _load()
        self._tmp = TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_running_script_decides_the_repo(self):
        """The whole point: two repos, argv[0] picks the right one."""
        atlas = _fake_repo(self.tmp, "CFO-Agent")
        bravo = _fake_repo(self.tmp, "Business-Empire-Agent")
        script = atlas / "scripts" / "core" / "scheduler.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("", encoding="utf-8")

        with mock.patch.object(sys, "argv", [str(script)]), \
                mock.patch.dict("os.environ", {"EMPIRE_REPO_ROOT": str(bravo)},
                                clear=False):
            got = self.mod._find_root()
        self.assertEqual(
            got, atlas,
            "resolution followed EMPIRE_REPO_ROOT instead of the running "
            "script -- this is precisely what crash-looped Atlas")

    def test_env_root_is_a_last_resort_not_a_first_choice(self):
        """It must only win when nothing else can answer.

        The module's __file__ has to be neutralised for this to mean anything:
        run from inside the real repo, the __file__ walk-up legitimately finds
        Bravo at step 3 and env_root never gets a turn. In a real deployment
        __file__ lives in site-packages, outside any repo, so step 3 returns
        None and this is the path that runs.
        """
        import os

        bravo = _fake_repo(self.tmp, "Business-Empire-Agent")
        nowhere = self.tmp / "unrelated" / "deep" / "path"
        nowhere.mkdir(parents=True, exist_ok=True)
        script = nowhere / "run.py"
        script.write_text("", encoding="utf-8")
        neutral = self.tmp / "site-packages" / "empire_turso_switch.py"
        neutral.parent.mkdir(parents=True, exist_ok=True)
        neutral.write_text("", encoding="utf-8")

        cwd0 = os.getcwd()
        os.chdir(nowhere)
        try:
            with mock.patch.object(sys, "argv", [str(script)]), \
                    mock.patch.object(self.mod, "__file__", str(neutral)), \
                    mock.patch.dict("os.environ",
                                    {"EMPIRE_REPO_ROOT": str(bravo)}, clear=False):
                got = self.mod._find_root()
        finally:
            os.chdir(cwd0)
        self.assertEqual(got, bravo,
                         "with no other signal, the explicit override should win")

    def test_cwd_answers_when_argv_is_not_a_path(self):
        """`python -m package` leaves argv[0] as a module name, not a file.

        Uses a real chdir, not mock.patch(Path.cwd): Path.resolve() consults
        os.getcwd() directly, so patching the classmethod changes nothing.
        """
        import os

        maven = _fake_repo(self.tmp, "CMO-Agent")
        neutral = self.tmp / "site-packages" / "empire_turso_switch.py"
        neutral.parent.mkdir(parents=True, exist_ok=True)
        neutral.write_text("", encoding="utf-8")

        cwd0 = os.getcwd()
        os.chdir(maven)
        try:
            os.environ.pop("EMPIRE_REPO_ROOT", None)
            with mock.patch.object(sys, "argv", ["-m"]), \
                    mock.patch.object(self.mod, "__file__", str(neutral)):
                got = self.mod._find_root()
        finally:
            os.chdir(cwd0)
        self.assertEqual(got, maven)

    def test_a_script_deep_inside_a_repo_still_finds_its_root(self):
        atlas = _fake_repo(self.tmp, "CFO-Agent")
        deep = atlas / "scripts" / "tools" / "sub" / "thing.py"
        deep.parent.mkdir(parents=True, exist_ok=True)
        deep.write_text("", encoding="utf-8")
        with mock.patch.object(sys, "argv", [str(deep)]):
            import os

            os.environ.pop("EMPIRE_REPO_ROOT", None)
            self.assertEqual(self.mod._find_root(), atlas)

    def test_no_repo_anywhere_returns_none_rather_than_guessing(self):
        empty = self.tmp / "empty"
        empty.mkdir(parents=True, exist_ok=True)
        script = empty / "x.py"
        script.write_text("", encoding="utf-8")
        with mock.patch.object(sys, "argv", [str(script)]), \
                mock.patch.object(Path, "cwd", staticmethod(lambda: empty)):
            import os

            os.environ.pop("EMPIRE_REPO_ROOT", None)
            # __file__ walk-up still finds the real repo this test lives in,
            # which is correct behaviour -- assert it never invents a root.
            got = self.mod._find_root()
            self.assertTrue(got is None or (got / "scripts" / "lib" /
                                            "turso_supabase_compat.py").exists())

    def test_the_error_names_the_real_fix(self):
        """A failure here is confusing unless it says what to do."""
        with mock.patch.object(self.mod, "_find_root", lambda: None):
            with self.assertRaises(RuntimeError) as ctx:
                self.mod._install()
        msg = str(ctx.exception)
        self.assertIn("shadow", msg.lower())
        self.assertIn("copy the shim", msg.lower())


if __name__ == "__main__":
    unittest.main()
