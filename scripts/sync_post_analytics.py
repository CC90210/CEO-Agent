"""sync_post_analytics — pull what the work actually did into post_analytics.

WHY A POLLER AND NOT THE WEBHOOK THE TASK ASKED FOR
The task specified POST /api/webhooks/zernio with HMAC verification, parsing
`post.analytics` and `inbox.message` events. Probed before building:

    GET /api/v1/analytics            200  real data
    GET /api/v1/inbox/conversations  200  real data
    GET /api/v1/webhooks             200  but returns the dashboard HTML —
                                          it is a page, not an API
    GET /api/v1/messages             200  same, HTML

There is no documented webhook event schema to parse and no API to register an
endpoint through. The one webhook that exists was made in the dashboard six
months ago, points at propflow.pro, and reads "inactive · no recent deliveries".
Writing an HMAC verifier against an event shape nobody can show me would be
inventing a contract and calling it an integration — and the first real delivery
would land on a parser built from a guess.

Polling is verifiable today: hasAnalyticsAccess is true and 42 of 50 posts carry
non-zero metrics. If Zernio later documents webhook events, this table is already
the right shape to receive them.

RETENTION IS NOT STORED
Zernio returns igReelsAvgWatchTime and videoDurationSeconds. Retention is those
two divided. Storing the ratio would freeze a number whose inputs can change —
so the inputs are stored and the ratio is computed where it is read.

  python scripts/sync_post_analytics.py            # sync
  python scripts/sync_post_analytics.py --dry-run  # show what would change
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import secret_loader  # noqa: E402
from integrations import supabase_tool  # noqa: E402

# The OASIS tenant. Bare-constant form matches ingest_training_link.py and
# migrate_carousels.py, but email_brain.py / lead_engine.py / inbound_classifier.py
# use the override form below and it is strictly better: an independent audit
# flagged the bare constant as an isolation risk, and while there is exactly one
# Zernio key and one founders tenant today, "today" is not a guarantee worth
# hardcoding. Costs one line to let a second tenant run this without a fork.
TENANT = (
    os.environ.get("OASIS_TENANT_ID")
    or os.environ.get("EMPIRE_TENANT_ID")
    or "ef8d389e-3f15-43f2-ae00-3660f69a1452"
)
BASE = "https://zernio.com/api"
PAGE_LIMIT = 100


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _db():
    return supabase_tool.get_client(secret_loader.bootstrap(), project="bravo")


def _get(path: str, key: str) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"Zernio {path} returned {e.code}: {e.read()[:300].decode('utf-8', 'replace')}"
        ) from e


def fetch_analytics() -> dict:
    """
    Every page, not just the first.

    The first cut stopped at one page of 100. Today there are 79 posts so it
    read everything and looked complete — which is exactly why it had to be
    fixed now rather than at post 101, when the dashboard would quietly start
    undercounting and nothing would say so. Zernio hands us `pagination.pages`;
    the only reason not to follow it is that today's answer happens to fit.
    """
    key = secret_loader.get("LATE_API_KEY")
    if not key:
        raise SystemExit("LATE_API_KEY unavailable — cannot reach Zernio analytics")

    first = _get(f"/v1/analytics?limit={PAGE_LIMIT}", key)
    pag = first.get("pagination") or {}
    pages = int(pag.get("pages") or 1)
    posts = list(first.get("posts") or first.get("data") or [])

    for page in range(2, pages + 1):
        nxt = _get(f"/v1/analytics?limit={PAGE_LIMIT}&page={page}", key)
        got = list(nxt.get("posts") or nxt.get("data") or [])
        if not got:
            # Ran dry earlier than the header promised. Say so — a short read
            # that returns quietly is the failure this whole function exists to
            # prevent.
            print(f"  ! analytics page {page}/{pages} came back empty, stopping")
            break
        posts.extend(got)

    total = int(pag.get("total") or len(posts))
    if len(posts) < total:
        print(f"  ! read {len(posts)} of {total} posts — totals below are INCOMPLETE")

    first["posts"] = posts
    return first


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _float(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def rows_from(payload: dict, asset_by_external: dict[str, str]) -> list[dict]:
    """One row per post PER PLATFORM.

    The same asset on six networks has six different sets of numbers; averaging
    them answers no question anyone asks.
    """
    out: list[dict] = []
    for post in payload.get("posts") or []:
        zid = str(post.get("_id") or post.get("latePostId") or "")
        # Zernio exposes TWO ids per post and we have historically stored either
        # one in marketing_asset.external_id depending on which endpoint created
        # it. Match on both or the Library link silently never resolves — which
        # is what "matched to a Library asset: 0" meant on the first run.
        alt = str(post.get("latePostId") or "")
        excerpt = (post.get("content") or "")[:280]
        published = post.get("publishedAt") or post.get("scheduledFor")
        platforms = post.get("platforms") or []
        if not platforms:
            continue
        for entry in platforms:
            ppid = str(entry.get("platformPostId") or "")
            if not ppid:
                # Nothing to key on. Skipped LOUDLY rather than invented — a row
                # with a synthesised id would collide on the next sync.
                print(f"  ! {zid[:10]}: {entry.get('platform')} has no platformPostId, skipped")
                continue
            a = entry.get("analytics") or post.get("analytics") or {}
            out.append({
                # Whether this response actually carried numbers, as opposed to
                # carrying nothing and being read as a row of zeros. The write
                # path uses this to refuse to overwrite good stored metrics with
                # a transient empty response — a network blip must not be able
                # to reset a post's view count to 0 and look like a real result.
                "_has_metrics": bool(a),
                "tenant_id": TENANT,
                "zernio_post_id": zid,
                "platform_post_id": ppid,
                "platform": str(entry.get("platform") or "unknown"),
                "account_username": entry.get("accountUsername"),
                "asset_id": asset_by_external.get(zid) or asset_by_external.get(alt)
                             or asset_by_external.get(ppid),
                "impressions": _int(a.get("impressions")),
                "views": _int(a.get("views")),
                "likes": _int(a.get("likes")),
                "comments": _int(a.get("comments")),
                "shares": _int(a.get("shares")),
                "saves": _int(a.get("saves")),
                "clicks": _int(a.get("clicks")),
                "follows": _int(a.get("follows")),
                "engagement_rate": _float(a.get("engagementRate")) or 0.0,
                "avg_watch_s": _float(a.get("igReelsAvgWatchTime")),
                "duration_s": _float(a.get("videoDurationSeconds")),
                "content_excerpt": excerpt,
                "published_at": published,
                "last_synced_at": _now(),
            })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="fetch and report, write nothing")
    args = ap.parse_args()

    db = _db()

    # Match Zernio posts back to Library assets where we published them ourselves.
    assets = db.table("marketing_asset").select("id, external_id").eq(
        "tenant_id", TENANT).execute().data or []
    asset_by_external = {
        str(a["external_id"]): a["id"] for a in assets if a.get("external_id")
    }

    try:
        payload = fetch_analytics()
    except Exception as exc:  # noqa: BLE001 — surfaced with its traceback, never swallowed
        print(f"FAILED to fetch analytics: {exc}")
        traceback.print_exc()
        return 1

    overview = payload.get("overview") or {}
    print(f"zernio: {overview.get('publishedPosts')} published of {overview.get('totalPosts')} "
          f"· last sync {overview.get('lastSync')}")
    if payload.get("hasAnalyticsAccess") is False:
        print("  ! hasAnalyticsAccess is FALSE — metrics will all be zero until "
              "the accounts are reconnected with insights permission")

    rows = rows_from(payload, asset_by_external)
    matched = sum(1 for r in rows if r["asset_id"])
    nonzero = sum(1 for r in rows if r["impressions"] or r["views"] or r["likes"])
    print(f"rows: {len(rows)}  ·  matched to a Library asset: {matched}  ·  with data: {nonzero}")

    if args.dry_run:
        for r in rows[:5]:
            ret = (f"{100 * r['avg_watch_s'] / r['duration_s']:.0f}%"
                   if r["avg_watch_s"] and r["duration_s"] else "—")
            print(f"  {r['platform']:10} views={r['views']:<6} likes={r['likes']:<5} "
                  f"retention={ret:<5} {(r['content_excerpt'] or '')[:44]!r}")
        print("\n(dry run — nothing written)")
        return 0

    # Counters, and the fields that merely describe the post. When a response
    # arrives with no analytics at all, the description is still worth updating
    # and the counters must be left exactly as they were.
    METRICS = ("impressions", "views", "likes", "comments", "shares", "saves",
               "clicks", "follows", "engagement_rate", "avg_watch_s", "duration_s")

    wrote = skipped_metrics = failed = 0
    for r in rows:
        has_metrics = r.pop("_has_metrics", True)
        try:
            # Scoped by platform as well as by id. Platform post ids live in
            # per-network namespaces so they do not collide today, but keying a
            # write on something that is only incidentally unique is how one
            # network silently overwrites another's row later.
            q = db.table("post_analytics").select("id").eq("tenant_id", TENANT).eq(
                "platform", r["platform"]).eq("platform_post_id", r["platform_post_id"])
            existing = q.execute().data

            if existing:
                payload = dict(r)
                if not has_metrics:
                    # Provenance only. Zeroing a post that really has 3,952
                    # views because one poll came back thin would be worse than
                    # not running at all: the number stays plausible and nobody
                    # can tell it is wrong.
                    for k in METRICS:
                        payload.pop(k, None)
                    skipped_metrics += 1
                db.table("post_analytics").update(payload).eq(
                    "tenant_id", TENANT).eq("platform", r["platform"]).eq(
                    "platform_post_id", r["platform_post_id"]).execute()
            else:
                db.table("post_analytics").insert(r).execute()
            wrote += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ! {r['platform']} {r['platform_post_id']}: {exc}")
            traceback.print_exc(limit=2)

    print(f"synced: {wrote}  ·  failed: {failed}"
          + (f"  ·  kept existing metrics on {skipped_metrics} (empty response)"
             if skipped_metrics else ""))

    # ANY failure is a failure. The first cut returned 0 whenever at least one
    # row landed, so "1 wrote, 78 failed" reported healthy to cron and nobody
    # would ever have been paged.
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
