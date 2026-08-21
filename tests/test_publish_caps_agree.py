"""The per-channel image caps must agree across every surface that enforces them.

There are three copies of one rule, in two languages and three repos:

  1. CMO-Agent/scripts/schedule_posts.py   PLATFORM_IMAGE_CAP   — Maven's scheduled path
  2. oasis-command-center lib/founders/publish-targets.ts       — picker + publish route
  3. scripts/marketing_publish_drain.py    PLATFORM_IMAGE_CAP   — the drain, last gate

No import can unify them, so this test is what stops them drifting. Drift here is
not a style problem: the surfaces disagree about what a channel can take, and the
disagreement only surfaces as a failed post minutes after an operator was told it
was queued.

The caps are read out of the TypeScript by regex on purpose — the alternative is
a build step to make a JSON artifact, and a regex that fails loudly when the file
is restructured is cheaper than a pipeline that can silently produce a stale one.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from sibling_repos import SIBLING_REPOS  # noqa: E402

# Key names come from sibling_repos.SIBLING_REPOS verbatim. Getting one wrong
# does not fail — it returns None and the test SKIPS, which reads as green.
# Asserted below rather than trusted.
DASHBOARD = SIBLING_REPOS.get("oasis-command-center")
MAVEN = SIBLING_REPOS.get("maven")

assert DASHBOARD is not None, (
    "sibling_repos has no 'oasis-command-center' key — the name moved, and this "
    "test would have silently skipped instead of comparing anything"
)
assert MAVEN is not None, "sibling_repos has no 'maven' key"


def _drain_caps() -> dict:
    from marketing_publish_drain import PLATFORM_IMAGE_CAP  # noqa: PLC0415

    return dict(PLATFORM_IMAGE_CAP)


def _maven_caps() -> dict:
    """Parsed rather than imported: schedule_posts pulls a large module graph and
    this test must not depend on Maven's runtime being importable."""
    path = (MAVEN or Path("/nonexistent")) / "scripts" / "schedule_posts.py"
    if not path.is_file():
        pytest.skip(f"CMO-Agent not installed on this machine ({path})")
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^PLATFORM_IMAGE_CAP\s*=\s*\{(.*?)\}", text, re.M | re.S)
    assert m, "PLATFORM_IMAGE_CAP not found in CMO-Agent/scripts/schedule_posts.py"
    return {k: int(v) for k, v in re.findall(r'"(\w+)"\s*:\s*(\d+)', m.group(1))}


def _dashboard_caps() -> dict:
    path = (DASHBOARD or Path("/nonexistent")) / "lib" / "founders" / "publish-targets.ts"
    if not path.is_file():
        pytest.skip(f"oasis-command-center not installed on this machine ({path})")
    text = path.read_text(encoding="utf-8", errors="replace")
    found = re.findall(r'id:\s*"(\w+)".*?imageCap:\s*(\d+)', text, re.S)
    assert found, "no imageCap entries found in publish-targets.ts"
    return {k: int(v) for k, v in found}


def test_the_drain_agrees_with_mavens_scheduled_path():
    """Maven's copy is the narrower one — it lists only image-capable surfaces.

    Every platform Maven caps must be capped identically here. The drain
    additionally carries tiktok/youtube at 0, which Maven's dict omits because
    its scheduled path never targets them; absence there is not a disagreement.
    """
    drain, maven = _drain_caps(), _maven_caps()
    mismatched = {
        p: (maven[p], drain.get(p))
        for p in maven
        if drain.get(p) != maven[p]
    }
    assert not mismatched, (
        "drain and CMO-Agent/scripts/schedule_posts.py disagree about image caps "
        f"(platform: maven_cap, drain_cap) -> {mismatched}. A surface that "
        "disagrees will accept a post the other refuses."
    )


def test_the_dashboard_agrees_with_the_drain():
    """The picker and publish route gate on these; the drain publishes on them."""
    drain, dash = _drain_caps(), _dashboard_caps()
    mismatched = {
        p: (dash[p], drain.get(p))
        for p in dash
        if drain.get(p) != dash[p]
    }
    assert not mismatched, (
        "oasis-command-center lib/founders/publish-targets.ts disagrees with the "
        f"drain (platform: dashboard_cap, drain_cap) -> {mismatched}. The picker "
        "would offer a channel the drain then drops, or refuse one it would accept."
    )


def test_video_only_surfaces_are_zero_not_absent():
    """0 means "cannot take an image deck"; absent would mean "no known limit".

    `PLATFORM_IMAGE_CAP.get(p, deck_size)` in the drain treats an unknown
    platform as unlimited, which is the right default for a surface nobody has
    characterised — and exactly the wrong answer for TikTok and YouTube, which
    cannot take images at all.
    """
    drain = _drain_caps()
    for p in ("tiktok", "youtube"):
        assert drain.get(p) == 0, (
            f"{p} is video-only and must be capped at 0, not left absent — "
            "absent reads as unlimited to the drain's .get() default"
        )
