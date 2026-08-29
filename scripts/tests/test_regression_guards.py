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


# ===========================================================================
# TIER 2 — DESIGN EFFECTIVENESS
#
# SOC2/ISO27001 separate two questions about any control, and conflating them
# is how a compliance programme becomes theatre:
#
#   design effectiveness    — does a control EXIST and would it work?
#   operating effectiveness — does it actually work when exercised?
#
# Everything above this line is operating-tested: the guard is exercised and
# must produce the right behaviour. Below it are controls whose enforcement
# lives outside this repo (oasis-command-center) or in operator judgement, so
# only their DESIGN can be verified here — the codified rule still exists.
#
# That distinction is reported separately in the accuracy trend rather than
# folded into one number. A design-only guard proves the lesson has not been
# deleted; it does NOT prove the behaviour still holds, and claiming otherwise
# would be exactly the fake pass this suite exists to prevent.
# ===========================================================================

MEMORY_DIR = (Path.home() / ".claude" / "projects"
              / "c--Users-User-Business-Empire-Agent" / "memory")


def _codified(*names: str) -> bool:
    """Is the lesson still written down where future sessions will read it?"""
    for n in names:
        if (MEMORY_DIR / f"{n}.md").is_file():
            return True
        for hay in ("memory/PATTERNS.md", "memory/MISTAKES.md", "brain/AGENTS.md"):
            p = REPO / hay
            if p.is_file() and n.replace("_", " ").lower() in p.read_text(
                    encoding="utf-8", errors="replace").lower():
                return True
    return False


# --- 2026-05-18: Vercel deploys blocked 90 min on committer identity --------
# OPERATING-tested, not design: the control is a real git config value and it
# is read back and compared.

CANONICAL_COMMITTER = "214530671+CC90210@users.noreply.github.com"


def test_vercel_linked_repo_keeps_the_canonical_committer_identity():
    """Vercel rejected 90 minutes of deploys because agent-authored commits
    carried the wrong committer. The fix locked a per-repo user.email on
    oasis-command-center. If it is ever reset to a global identity, deploys
    silently start failing that check again."""
    import subprocess
    repo = Path.home() / "APPS" / "oasis-command-center"
    if not (repo / ".git").is_dir():
        pytest.skip("oasis-command-center not present on this machine")
    got = subprocess.run(["git", "-C", str(repo), "config", "user.email"],
                         capture_output=True, text=True).stdout.strip()
    assert got == CANONICAL_COMMITTER, (
        f"oasis-command-center commits as {got!r}; Vercel requires "
        f"{CANONICAL_COMMITTER!r} or deploys are blocked")


# --- 2026-05-09: leaked background bash spammed console popups every 8s -----
# OPERATING-tested: the windowless flag is read out of the module that runs
# periodically, which is where the popups came from.

def test_periodic_health_check_spawns_windowless():
    """Console windows popped up every 8 seconds because a periodically-run
    script spawned children with a visible console. The fix routes them through
    WINDOWLESS_FLAGS."""
    src = (REPO / "scripts" / "core" / "system_health_check.py").read_text(
        encoding="utf-8", errors="replace")
    assert "WINDOWLESS_FLAGS" in src, "windowless import removed"
    assert "creationflags=" in src, (
        "subprocess calls no longer pass creationflags — console windows return")


# --- design-tier: the lesson must still be written down ---------------------

@pytest.mark.parametrize("incident,rules", [
    ("cross-tenant chrome leak on public form pages",
     ("feedback_public_routes_two_layer_gate", "feedback_tenant_chrome_bleed_check")),
    ("copy-link button exposed the operator edit URL",
     ("feedback_test_user_journey_incognito", "feedback_verification_means_actual_probing")),
    ("public-form infrastructure shipped without adversarial review",
     ("feedback_adversarial_review_before_done", "feedback_security_must_be_server_side")),
    ("auto-sync would have reverted MRR",
     ("pre-automation cleanup audit", "pattern_verify_by_executing_not_counting")),
    ("assumed shared Supabase tenanting for a new client product",
     ("feedback_turso_for_client_automations",)),
    ("shipped wizard changes without testing the real curl|bash path",
     ("feedback_verification_means_actual_probing",)),
])
def test_incident_lesson_is_still_codified(incident, rules):
    """DESIGN effectiveness only. Enforcement for these lives in
    oasis-command-center or in operator judgement, so what can be verified here
    is that the lesson has not been deleted — a future session still boots with
    it. This does NOT prove the behaviour holds, and is reported as a separate
    tier for exactly that reason."""
    assert _codified(*rules), (
        f"the codified lesson for {incident!r} is gone — a future session will "
        f"boot without it (looked for: {rules})")


def test_the_anti_pattern_hook_actually_blocks():
    """OPERATING tier for the retired cold-outreach cron.

    The sibling test above verifies the RULE is registered. That is design
    effectiveness — it proves the configuration exists, not that the hook does
    anything with it. This drives the real PreToolUse entrypoint with the real
    payload schema and asserts the decision comes back as a block.

    The distinction is not academic: a hook whose rule file is perfect but whose
    matcher silently stopped firing looks identical from the registry side, and
    the pings would resume with the config still looking correct.
    """
    import subprocess
    hook = REPO / "scripts" / "hooks" / "anti_pattern_hook.py"
    payload = json.dumps({
        "tool_name": "Bash",
        # The exact shape the rule retires: recreating the approval cron.
        "tool_input": {"command": "python scripts/outreach_" + "batch.py --daily"},
    })
    r = subprocess.run([sys.executable, str(hook)], input=payload,
                       capture_output=True, text=True, timeout=60)
    blob = (r.stdout or "") + (r.stderr or "")
    assert "cold-outreach" in blob.lower() or "deny" in blob.lower() or r.returncode != 0, (
        "the anti-pattern hook did NOT block a command that recreates the "
        f"retired cold-outreach cron (rc={r.returncode}, out={blob[:200]!r})")


def test_the_anti_pattern_hook_allows_ordinary_commands():
    """Break the test before trusting it: a hook that blocks everything would
    pass the assertion above while making the machine unusable."""
    import subprocess
    hook = REPO / "scripts" / "hooks" / "anti_pattern_hook.py"
    payload = json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": "git status --short"}})
    r = subprocess.run([sys.executable, str(hook)], input=payload,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, "the hook blocked an ordinary command"
    assert "deny" not in (r.stdout or "").lower()
