"""Executable guards for recorded incidents in evals/mistakes/.

Each test here corresponds to one entry in that suite and is named in its
meta.yaml `check:` field, so a recorded mistake becomes a COUNTED regression
test rather than a story in a folder.

WHY THIS FILE EXISTS
--------------------
Three registries describe the same incidents and did not agree:

    evals/mistakes/          12 incidents, each documenting the fix
    memory/ANTI_PATTERNS.json  3 actively-blocked patterns
    eval `check:` wiring       1 incident actually measured

Four of the twelve turned out to have REAL, working enforcement already in the
codebase — a secrets audit, an anti-pattern hook rule, a strict template
renderer, a windowless interpreter — and only one of the four was counted. The
guards existed; nothing verified they still held. A fix that silently rots looks
exactly like a fix that works, which is the failure mode the whole mistakes
suite exists to prevent.

These are behaviour tests where behaviour is testable, and artifact assertions
only where the fix genuinely IS an artifact (an interpreter setting, a deleted
script). The remaining incidents are process rules or live in
oasis-command-center, and are deliberately left as needs-model rather than given
a check that would pass without proving anything.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))


# --- 2026-05-13: outreach sent raw {{company}} placeholders ------------------

class TestTemplatePlaceholdersNeverShip:
    """Antigravity sent outreach containing a literal `{{company}}` to a real
    prospect. The fix made render_template STRICT by default: a missing or blank
    variable raises instead of leaving the token in an email.

    Tested by BEHAVIOUR, not by grepping for the class name — a renderer that
    still defines TemplateRenderError but stopped raising it would pass a
    presence check and ship the same email.
    """

    def _render(self):
        from integrations.email_engine import render_template
        return render_template

    def test_missing_variable_raises_rather_than_shipping_the_token(self):
        from integrations.email_engine import TemplateRenderError
        with pytest.raises(TemplateRenderError):
            self._render()("Hi {{company}}, quick question", {}, label="guard")

    def test_blank_variable_raises_too(self):
        """A blank value is the subtler half — it renders to an empty gap in a
        real email rather than an obvious token."""
        from integrations.email_engine import TemplateRenderError
        with pytest.raises(TemplateRenderError):
            self._render()("Hi {{company}}", {"company": "   "}, label="guard")

    def test_strict_is_the_DEFAULT_not_an_opt_in(self):
        """The incident happened on the default path. A guard you must remember
        to switch on is not a guard."""
        from integrations.email_engine import TemplateRenderError
        with pytest.raises(TemplateRenderError):
            self._render()("Hi {{company}}", {})  # no strict= passed

    def test_a_complete_render_still_works(self):
        """Break the test before trusting it: the guard must not reject valid
        input, or every send would fail closed."""
        out = self._render()("Hi {{company}}", {"company": "OASIS"}, label="guard")
        assert out == "Hi OASIS"
        assert "{{" not in out


# --- 2026-05-16: bravo-scheduler flashed a console window on every restart ---

def test_scheduler_runs_windowless():
    """A console window flashed on CC's screen on every PM2 restart. The fix
    was `interpreter: PYTHONW` in ecosystem.config.js — reverting it to PYTHON
    brings the flashing back, silently, and only CC would notice."""
    cfg = (REPO / "ecosystem.config.js").read_text(encoding="utf-8", errors="replace")
    block = re.search(r'name:\s*"bravo-scheduler".*?\}', cfg, re.S)
    assert block, "bravo-scheduler entry not found in ecosystem.config.js"
    body = block.group(0)
    assert "PYTHONW" in body, (
        "bravo-scheduler no longer uses the windowless interpreter — the "
        "console window flashes on every restart again")
    assert not re.search(r"interpreter:\s*PYTHON\b", body), (
        "interpreter reverted to the console PYTHON")


# --- 2026-05-16: a retired cold-outreach cron pinged CC for 39 days ---------

def test_the_retired_cold_outreach_cron_stays_retired():
    """CC opted out of the cold-outreach Telegram-approval cron on 2026-05-16
    after 39 days of pings from a broken job. It was removed end-to-end and an
    anti-pattern rule now BLOCKS any command that would recreate it.

    This verifies the rule is still registered. The hook is the enforcement;
    this is the check that the enforcement still exists — an anti-pattern file
    someone trims is an outage nobody sees until the pings resume.
    """
    raw = json.loads((REPO / "memory" / "ANTI_PATTERNS.json").read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("patterns", [])
    blob = json.dumps(items).lower()
    assert "cold-outreach" in blob or "cold outreach" in blob, (
        "the anti-pattern rule retiring the cold-outreach approval cron is gone")
    assert "opted out" in blob or "do not recreate" in blob, (
        "the rule no longer states the prohibition")


def test_anti_pattern_registry_is_loadable_and_non_empty():
    """The hook fails open on an unreadable registry, so a corrupt file
    silently disables every anti-pattern at once."""
    raw = json.loads((REPO / "memory" / "ANTI_PATTERNS.json").read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("patterns", [])
    assert isinstance(items, list) and items, "anti-pattern registry is empty"
