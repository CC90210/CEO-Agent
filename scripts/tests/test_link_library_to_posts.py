#!/usr/bin/env python3
"""The rules that decide what link_library_to_posts writes to production.

This script runs hourly with --execute against live data and shipped with no test
at all. Every assertion below is a decision it makes about REAL rows — which
asset counts as posted, whose analytics get attached to it, when to refuse.

The nastiest failure here is not a crash. It is a WRONG link: an asset silently
reporting another piece's view counts, which looks exactly like accounting that
works. So most of this file is about what the planner must REFUSE.

Run: python scripts/tests/test_link_library_to_posts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from link_library_to_posts import MIN_HOOK, norm, plan_links  # noqa: E402

T1 = "tenant-oasis"
T2 = "tenant-someone-else"

HOOK = "the road they gave you ends here"  # 32 chars — comfortably over MIN_HOOK


def asset(aid, tenant=T1, hook=HOOK, title="An Asset", published=None):
    return {
        "id": aid, "tenant_id": tenant, "title": title, "hook": hook,
        "published_at": published, "platforms": None, "status": "in_review",
        "brand_slug": "oasis-ai",
    }


def post(pid, tenant=T1, caption=HOOK, platform="instagram", when="2026-08-14T14:36:21Z"):
    return {
        "id": pid, "tenant_id": tenant, "platform": platform,
        "platform_post_id": f"pp-{pid}", "content_excerpt": caption,
        "published_at": when, "asset_id": None,
    }


def check(name, cond):
    if not cond:
        print(f"FAIL: {name}")
        sys.exit(1)


# ── normalisation ────────────────────────────────────────────────────────────
# Captions pick up smart quotes and per-platform line breaks on the way out;
# none of that makes it a different piece of writing.
check("smart quotes fold", norm("It's") == norm("It’s"))
check("em dash folds", norm("a - b") == norm("a — b"))
check("whitespace collapses", norm("a\n\n  b") == "a b")
check("empty is empty", norm(None) == "" and norm("") == "")

# ── the happy path: one asset, five networks, one publish moment ─────────────
res = plan_links(
    [asset("a1", title="The Unpaved Mile")],
    [
        post("p1", platform="instagram"),
        post("p2", platform="tiktok", when="2026-08-14T14:35:36Z"),
        # YouTube puts the TITLE before the caption body. This is why the match is
        # containment rather than prefix — a strict prefix dropped the YouTube row
        # of a post already matched on three other networks.
        post("p3", platform="youtube", caption=f"The Unpaved Mile\n\n{HOOK}."),
    ],
)
check("one asset planned", res["linkable_assets"] == 1)
plan = res["plan"][0]
check("all three rows linked", sorted(plan["post_ids"]) == ["p1", "p2", "p3"])
check("youtube matched despite title prefix", "youtube" in plan["platforms"])
check("earliest stamp wins", plan["published_at"] == "2026-08-14T14:35:36Z")
check("no repost reported", res["reposts"] == [])

# ── THE TENANT BOUNDARY ──────────────────────────────────────────────────────
# The script reads every tenant at once so one run covers the fleet. Linking
# across that line would attach another tenant's numbers to our asset — the
# single worst thing this code could do, and invisible once written.
res = plan_links([asset("a1", tenant=T1)], [post("p1", tenant=T2)])
check("never links across tenants", res["linkable_assets"] == 0)

# ── the hook-length floor ────────────────────────────────────────────────────
# "join the waitlist" opens several outro cards. A short hook is not evidence.
short = "join the waitlist"
check("the floor is meaningful", len(short) < MIN_HOOK)
res = plan_links([asset("a1", hook=short)], [post("p1", caption=short + " now")])
check("short hooks are skipped", res["linkable_assets"] == 0)
check("and reported rather than silently dropped", res["skipped_short_hook"] == 1)

# ── ambiguity is refusal ─────────────────────────────────────────────────────
# One caption matching two assets is a collision. Picking a winner is how a view
# count ends up on the wrong asset.
res = plan_links(
    [asset("a1", hook=HOOK), asset("a2", hook=HOOK)],
    [post("p1")],
)
check("ambiguous caption links nothing", res["linkable_assets"] == 0)
check("ambiguity is counted", res["ambiguous_posts"] == 1)

# ── a re-post is not an ambiguity ────────────────────────────────────────────
# Both real cases were the same creative published again days later. Refusing
# these left demonstrably-live work sitting in "needs a verdict".
res = plan_links(
    [asset("a1", title="Tick Tax")],
    [
        post("p1", when="2026-08-04T12:00:00Z"),
        post("p2", when="2026-08-05T12:00:00Z", platform="threads"),
    ],
)
check("a re-post still counts as posted", res["linkable_assets"] == 1)
check("stamped with the FIRST ship", res["plan"][0]["published_at"] == "2026-08-04T12:00:00Z")
check("every run is linked", sorted(res["plan"][0]["post_ids"]) == ["p1", "p2"])
check("and the repeat is surfaced", len(res["reposts"]) == 1)
check("naming both days", res["reposts"][0]["days"] == ["2026-08-04", "2026-08-05"])

# ── nothing to say ───────────────────────────────────────────────────────────
res = plan_links([], [])
check("empty input is a no-op, not a crash", res["linkable_assets"] == 0)
res = plan_links([asset("a1")], [post("p1", caption="a completely unrelated caption")])
check("no match links nothing", res["linkable_assets"] == 0)
# A post with no publish timestamp cannot date an asset, so it must not create
# one — `published_at` is the column the whole Library reads to decide "Posted".
res = plan_links([asset("a1")], [post("p1", when=None)])
check("a post with no timestamp links nothing", res["linkable_assets"] == 0)

# ── idempotence ──────────────────────────────────────────────────────────────
# The hourly cron re-runs this forever. An already-linked asset must plan the
# same values, flagged as already linked rather than treated as new.
res = plan_links(
    [asset("a1", published="2026-08-14T14:35:36Z")],
    [post("p1", when="2026-08-14T14:35:36Z")],
)
check("re-running plans the same stamp", res["plan"][0]["published_at"] == "2026-08-14T14:35:36Z")
check("and knows it was already linked", res["plan"][0]["already_linked"] is True)

print("link_library_to_posts: all assertions passed")
