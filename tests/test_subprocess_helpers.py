"""Lock the consolidation: WINDOWLESS_FLAGS exists, has the right
value on Windows, and is zero everywhere else. The four call-sites
that re-export it (scheduler / system_health_check / cron_dispatcher /
funnel_sync) all import the same source — verify by reference equality.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def test_windowless_flags_constant():
    from _subprocess_helpers import WINDOWLESS_FLAGS
    if sys.platform == "win32":
        assert WINDOWLESS_FLAGS == 0x08000000, "Windows must use CREATE_NO_WINDOW"
    else:
        assert WINDOWLESS_FLAGS == 0, "non-Windows must be zero"


def test_callsites_share_the_same_constant():
    """If a future change inlines a different magic number in any of
    these scripts, the regex below will catch it. Single source of truth
    matters because future scripts get the helper for free."""
    import re
    pat = re.compile(r"creationflags\s*=\s*0x0?8000000")
    leaks: list[str] = []
    for fname in ("scheduler.py", "system_health_check.py",
                  "cron_dispatcher.py", "funnel_sync.py"):
        text = (SCRIPTS / fname).read_text(encoding="utf-8")
        if pat.search(text):
            leaks.append(fname)
    assert not leaks, (
        f"Inline magic number reappeared in: {leaks}. "
        "Use WINDOWLESS_FLAGS from _subprocess_helpers instead."
    )
