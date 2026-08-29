#!/usr/bin/env python3
"""link_library_to_posts — join the Library to the posts that actually went out.

THE PROBLEM CC HIT
The founders Library said 41 of 43 assets were "in review", so nothing looked
posted. Meanwhile post_analytics held 100 real posts with real view counts. Both
were reading truthfully from different tables that had never been joined:

    OASIS The Unpaved Mile   marketing_asset   status=in_review, published_at=NULL
    "the road they gave you  post_analytics    tiktok 317 · instagram 309 ·
     ends here."                               youtube · threads · linkedin,
                                               all on 2026-08-14

CC: "we already have posted the unpaved mile... it should automatically archive
it... some of it's not taken account for correctly."

WHY THE EXISTING LINK NEVER FIRED
sync_post_analytics.py matches on `marketing_asset.external_id` against Zernio's
post ids. That works for assets Zernio itself created, and not at all for the
ones library_sync.py registers — produced creative that reaches the Library by a
different road than the posting queue, carrying no Zernio id. The column is there;
for these rows it is simply empty, so the join had nothing to match on.

WHAT IT MATCHES ON INSTEAD
The caption. Every one of these posts opens with the asset's own `hook`, verbatim
— it is the first line Maven writes into the copy and the first line that ships.
So: normalise both sides and require the caption to START WITH the hook.

WHY THAT IS SAFE ENOUGH TO WRITE TO THE DATABASE
A prefix match on a short string would be reckless — "join the waitlist" opens
several outro cards. Three rules keep it honest:

  1. MIN_HOOK. A hook under 24 characters is not evidence and is skipped, left
     for a human. Precision over coverage: an unlinked asset is a visible gap,
     while a WRONGLY linked one silently reports someone else's view counts as
     yours, and looks like working accounting.
  2. AMBIGUITY IS REFUSAL. If one caption matches more than one asset, nothing is
     written for it — a collision is reported, never resolved by picking.
  3. DRY RUN IS THE DEFAULT. Nothing mutates without --execute.

A RE-POST IS NOT AN AMBIGUITY. This first refused any asset whose matches spanned
more than one day, on the theory that choosing a date was guessing. That was the
wrong instinct: the asset is demonstrably live either way, and refusing left it in
"needs a verdict" — the exact complaint this exists to fix. Both real cases were
genuine repeats, not reused hooks ("Gen G2 Tick Tax" ran the full cross-post on
08-04 AND 08-05; "Receipt Week" across three days). So it stamps the FIRST ship
date, links every row from every run, and REPORTS the repeat: when it went live is
a fact about the asset, that the poster published it twice is a fact about the
poster, and the operator wants to see the second rather than have it merged away.

WHAT IT WRITES
  post_analytics.asset_id      the link itself, so Performance can reach the asset
  marketing_asset.published_at earliest platform publish — this is what flips the
                               Library to "Posted", because lifecycleOf() derives
                               distribution from evidence rather than from `status`
  marketing_asset.platforms    the platforms that ACTUALLY took it, replacing the
                               backfilled single-element copy of `channel`

`status` is deliberately NOT touched. Review state and distribution state are
different questions (see lib/founders-marketing-core.ts) and the UI already lets
distribution win; overwriting a verdict CC recorded would destroy the one thing
`status` is genuinely for.

Idempotent: re-running relinks the same pairs and writes the same values.

Usage:
    python scripts/link_library_to_posts.py                # dry run, prints the plan
    python scripts/link_library_to_posts.py --execute      # apply
    python scripts/link_library_to_posts.py --json         # machine-readable
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import secret_loader  # noqa: E402
from integrations import supabase_tool  # noqa: E402

# A hook shorter than this is not distinctive enough to bet a view count on.
# "join the waitlist" (17) is the case that motivated the number.
MIN_HOOK = 24


def _db():
    return supabase_tool.get_client(secret_loader.bootstrap(), project="bravo")


def norm(s: str | None) -> str:
    """Lowercase, collapse whitespace, drop the punctuation that drifts.

    Captions pick up smart quotes and em dashes on the way to a platform, and
    line breaks differ per network — the Instagram copy of a post has a blank
    line where the TikTok copy has none. None of that changes whether it is the
    same piece of writing.
    """
    s = (s or "").lower()
    s = s.replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("—", "-").replace("–", "-")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def plan_links(assets: list[dict], posts: list[dict]) -> dict:
    """Work out which assets shipped, and where. PURE — no database, no clock.

    Split out from main() so the rules that decide what gets WRITTEN TO
    PRODUCTION can be exercised without one: the tenant boundary, the hook-length
    floor, the ambiguity refusal and the re-post rule are all decisions, and a
    decision nothing tests is a decision nobody has checked. This script runs
    hourly against live data; that is precisely the code that should not be
    reachable only through a network call.
    """
    usable = [a for a in assets if len(norm(a.get("hook"))) >= MIN_HOOK]
    skipped_short = len(assets) - len(usable)

    # post id -> the assets whose hook opens its caption. More than one is a
    # collision and disqualifies the post rather than picking a winner.
    hits: dict[str, list[dict]] = defaultdict(list)
    for p in posts:
        cap = norm(p.get("content_excerpt"))
        if not cap:
            continue
        for a in usable:
            # THE TENANT BOUNDARY. This reads every tenant in one pass so a single
            # run covers the fleet, which makes this line the only thing standing
            # between our asset and someone else's view counts. Linking across it
            # would be invisible once written and would look like working
            # accounting. Pinned by test_link_library_to_posts.
            if a["tenant_id"] != p["tenant_id"]:
                continue
            h = norm(a.get("hook"))
            # CONTAINS, not just startswith. YouTube prefixes the video TITLE
            # before the caption body — "The Unpaved Mile\n\nthe road they gave
            # you ends here." — so a strict prefix match dropped the YouTube row
            # of a post it had already matched on three other networks, and the
            # platform list came out short.
            #
            # Safe at this length: the hook is >= 24 characters of a specific
            # sentence, and any caption matching two different assets is thrown
            # out below rather than resolved by guessing.
            #
            # LinkedIn still will not match, and should not. It gets its own
            # rewritten caption register, so there is no shared text to key on —
            # that link needs a real id, not a cleverer regex.
            if h and h in cap:
                hits[p["id"]].append(a)

    ambiguous_posts = {pid for pid, aa in hits.items() if len({x["id"] for x in aa}) > 1}

    # asset -> the posts that matched it
    by_asset: dict[str, list[dict]] = defaultdict(list)
    post_by_id = {p["id"]: p for p in posts}
    for pid, aa in hits.items():
        if pid in ambiguous_posts:
            continue
        by_asset[aa[0]["id"]].append(post_by_id[pid])

    asset_by_id = {a["id"]: a for a in assets}
    plan, reposts = [], []
    for aid, ps in by_asset.items():
        stamps = sorted([p["published_at"] for p in ps if p.get("published_at")])
        if not stamps:
            continue
        # A real cross-post lands within minutes, so clusters days apart mean the
        # SAME creative went out more than once.
        #
        # This used to refuse those outright, on the theory that picking a date
        # was guessing. Wrong instinct: the asset is demonstrably live either way,
        # and refusing left it sitting in "needs a verdict" — the exact complaint
        # this whole change exists to fix. Investigated on 2026-08-16 and both
        # cases were genuine re-posts, not reused hooks: "Gen G2 Tick Tax" ran the
        # full cross-post on 08-04 AND 08-05 (Instagram 57 views then 35),
        # "Receipt Week" across three days.
        #
        # So: stamp the FIRST time it shipped, link every analytics row from every
        # run, and REPORT the repeat. When it went live is a fact about the asset;
        # that the poster published it twice is a fact about the poster, and the
        # operator wants to know the second one rather than have it silently
        # merged away.
        days = sorted({s[:10] for s in stamps})
        platforms = sorted({p["platform"] for p in ps if p.get("platform")})
        if len(days) > 1:
            reposts.append({
                "asset_id": aid,
                "title": asset_by_id[aid]["title"],
                "days": days,
                "platforms": platforms,
            })
        plan.append({
            "asset_id": aid,
            "title": asset_by_id[aid]["title"],
            "already_linked": bool(asset_by_id[aid].get("published_at")),
            "published_at": stamps[0],
            "platforms": platforms,
            "post_ids": [p["id"] for p in ps],
            "views_visible": True,
        })

    plan.sort(key=lambda r: r["published_at"])

    return {
        "assets": len(assets),
        "posts": len(posts),
        "skipped_short_hook": skipped_short,
        "ambiguous_posts": len(ambiguous_posts),
        "reposts": reposts,
        "linkable_assets": len(plan),
        "linked_posts": sum(len(r["post_ids"]) for r in plan),
        "executed": False,
        "plan": plan,
    }


def _apply(db, plan: list[dict]) -> None:
    """Write the links. Separated from planning so the decisions above can be
    tested without a database and this can stay dumb enough to read at a glance."""
    for row in plan:
        db.table("marketing_asset").update({
            "published_at": row["published_at"],
            "platforms": json.dumps(row["platforms"]),
        }).eq("id", row["asset_id"]).execute()
        for pid in row["post_ids"]:
            db.table("post_analytics").update(
                {"asset_id": row["asset_id"]}
            ).eq("id", pid).execute()


def _print(result: dict, executed: bool) -> None:
    mode = "APPLIED" if executed else "DRY RUN — nothing written"
    print(f"link_library_to_posts [{mode}]")
    print(f"  assets {result['assets']} · analytics rows {result['posts']}")
    print(f"  hook too short to match safely : {result['skipped_short_hook']}")
    print(f"  captions matching >1 asset     : {result['ambiguous_posts']} (skipped)")
    print(f"  RE-POSTED (same creative twice+): {len(result['reposts'])}")
    print(f"  LINKABLE ASSETS                : {result['linkable_assets']}  "
          f"({result['linked_posts']} analytics rows)")
    for row in result["plan"]:
        mark = "=" if row["already_linked"] else "+"
        print(f"   {mark} {row['published_at'][:10]}  {row['title'][:52]:<52} "
              f"{','.join(row['platforms'])}")
    for r in result["reposts"]:
        print(f"   ~ {r['title'][:52]:<52} PUBLISHED {len(r['days'])}x: {', '.join(r['days'])}")
    if not executed:
        print("\n  re-run with --execute to write these links")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true", help="apply (default is a dry run)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--tenant", default=None, help="restrict to one tenant_id")
    args = ap.parse_args()

    db = _db()

    aq = db.table("marketing_asset").select(
        "id,tenant_id,title,hook,published_at,platforms,status,brand_slug"
    )
    if args.tenant:
        aq = aq.eq("tenant_id", args.tenant)
    assets = aq.execute().data or []

    pq = db.table("post_analytics").select(
        "id,tenant_id,platform,platform_post_id,content_excerpt,published_at,asset_id"
    )
    if args.tenant:
        pq = pq.eq("tenant_id", args.tenant)
    posts = pq.execute().data or []

    result = plan_links(assets, posts)

    if args.execute:
        _apply(db, result["plan"])
        result["executed"] = True

    if args.json:
        # ONE compact line. scheduler.py's out[-1][:200] slice — which turned
        # pretty JSON into a lone bracket and made the run read as OPAQUE — was
        # replaced by summarize_stdout on 2026-08-29, so this is preference now
        # rather than a workaround. Compact is still the right shape.
        print(json.dumps(result, separators=(",", ":")))
    else:
        _print(result, result["executed"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
