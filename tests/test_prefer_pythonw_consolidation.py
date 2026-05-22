"""Lock the python→pythonw consolidation.

Originally consolidated two callers:
  - bravo_cli/local_bridge.py:_resolve_pythonw  (used by wizard, schtasks
    install, plist install, .vbs install)
  - scripts/skool_watchdog.py:_resolve_daemon_python  (used to spawn the
    skool_engine daemon)  ← ARCHIVED 2026-05-18 with the rest of Skool;
    when CC's primary retainer ended, the daemon moved to
    scripts/_archive/skool/.

The remaining live caller is bravo_cli/local_bridge.py. This test still
enforces:

1. Both _subprocess_helpers modules export the primitive (the scripts
   helper is kept for any future daemon that needs it).
2. The two functions agree on the same input.
3. The live caller doesn't re-implement the inline replace pattern.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def test_both_helper_modules_export_prefer_pythonw():
    from bravo_cli._subprocess_helpers import prefer_pythonw as cli_ppw
    from _subprocess_helpers import prefer_pythonw as scripts_ppw  # type: ignore
    assert callable(cli_ppw)
    assert callable(scripts_ppw)


def test_both_primitives_agree_on_sys_executable():
    """The two helper modules ARE separate (different package boundaries
    don't permit cross-imports without sys.path gymnastics), so we have
    a 5-line function duplicated. This test guards that the duplicate
    stays correct — if someone tweaks one, the diff breaks here."""
    from bravo_cli._subprocess_helpers import prefer_pythonw as cli_ppw
    from _subprocess_helpers import prefer_pythonw as scripts_ppw  # type: ignore
    assert cli_ppw(sys.executable) == scripts_ppw(sys.executable), (
        "bravo_cli and scripts prefer_pythonw helpers diverged — pick one"
    )


def test_no_inline_pythonw_replace_in_callers():
    """Live callers may not reinstate the inline `replace("python.exe",
    "pythonw.exe")` pattern — that's the consolidation regression we're
    guarding against."""
    inline_pat = re.compile(r"\.replace\([\"']python\.exe[\"']\s*,\s*[\"']pythonw\.exe[\"']\)")
    callers = [
        ROOT / "bravo_cli" / "local_bridge.py",
    ]
    leaks: list[str] = []
    for path in callers:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if inline_pat.search(text):
            leaks.append(path.name)
    assert not leaks, (
        f"Inline python→pythonw replace returned in: {leaks}. "
        "Use prefer_pythonw() from _subprocess_helpers instead."
    )


def test_callers_import_prefer_pythonw():
    """Sanity: the live callers must actually import prefer_pythonw."""
    for path in [
        ROOT / "bravo_cli" / "local_bridge.py",
    ]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        assert "prefer_pythonw" in text, (
            f"{path.name} doesn't reference prefer_pythonw — did the migration "
            "get reverted?"
        )
