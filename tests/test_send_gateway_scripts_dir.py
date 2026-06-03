#!/usr/bin/env python3
"""Regression test: send_gateway._SCRIPTS_DIR must point at CEO-Agent/scripts.

Bug (2026-06-03): _SCRIPTS_DIR was Path(__file__).resolve().parent.parent.parent
(the repo ROOT) instead of parent.parent (the scripts/ dir where casl_compliance,
lib.*, integrations.* live). That broke the documented CLI
`python scripts/integrations/send_gateway.py doctor ...` (and the SunBiz
scripts/send_gateway.py symlink) with ModuleNotFoundError: casl_compliance,
while PROJECT_ROOT must stay at the repo root so .env.agents resolves.

Dependency-free: run with `python3 tests/test_send_gateway_scripts_dir.py`
or under pytest.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))


def test_scripts_dir_and_project_root():
    from integrations import send_gateway as sg

    # _SCRIPTS_DIR is the scripts/ dir (so sibling imports resolve as a CLI).
    assert sg._SCRIPTS_DIR == SCRIPTS, f"_SCRIPTS_DIR={sg._SCRIPTS_DIR} != {SCRIPTS}"
    assert sg._SCRIPTS_DIR.name == "scripts"
    # PROJECT_ROOT stays the repo root (so PROJECT_ROOT/.env.agents resolves).
    assert sg.PROJECT_ROOT == REPO, f"PROJECT_ROOT={sg.PROJECT_ROOT} != {REPO}"
    # The sibling modules that the bug hid must be importable + co-located.
    assert (sg._SCRIPTS_DIR / "casl_compliance.py").exists()
    import casl_compliance  # noqa: F401  (would raise if path were wrong)


if __name__ == "__main__":
    test_scripts_dir_and_project_root()
    print("PASS: _SCRIPTS_DIR -> scripts/, PROJECT_ROOT -> repo root, casl_compliance importable")
