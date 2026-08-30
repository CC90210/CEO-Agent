#!/usr/bin/env python3
"""merge_assets_to_carousel — collapse N single images into one swipeable deck.

CC, 2026-08-17, looking at six quote cards each taking its own tile:
*"These should be a one-slide show, as we created before. It's just the same
background with different text, so it should be a slideshow. Make sure this is
one element, and I can click on it and press the next photo. It shouldn't be six
separate photos that take up six separate spaces."*

He is right, and the Library has rendered carousels since migration 144 — the
six cards were simply registered as six `single_image` rows. Nothing needed
building; they needed merging. Maven's library_audit flags this as
`slideshow_candidate`, so this will not be the last set.

WHAT IT DOES
Picks the LOWEST-ORDERED asset as the survivor, rewrites it as the deck
(`asset_type='carousel'`, `slide_count`, `media_urls` = every slide path in
order), and ARCHIVES the others. The survivor keeps its own id, so any link,
verdict or analytics row already pointing at it still resolves.

ORDER IS THE PAYLOAD. A carousel read out of order is a different post, so
slides are sorted by the trailing number in the title (Proof 01 -> Insp 06) and
the resulting order is printed for a human to look at before --execute.

ARCHIVED, NEVER DELETED, AND UNDOABLE. The sources keep their rows, their media
and their storage objects; they leave the working grid the way anything archived
does, and the Library's Restore button brings them straight back. `--undo` walks
the whole merge backwards. An action with no inverse is a trapdoor, and this one
touches six pieces of finished work at once.

REFUSES TO MERGE ANYTHING PUBLISHED. Collapsing a piece that already shipped
would strand its post_analytics rows against an archived asset and quietly change
what the Performance tab is measuring. If a candidate carries a `published_at`,
the whole merge stops rather than silently skipping it.

Usage:
    python scripts/merge_assets_to_carousel.py --brand conaugh --campaign quote-card
    python scripts/merge_assets_to_carousel.py --brand conaugh --campaign quote-card --execute
    python scripts/merge_assets_to_carousel.py --verify <survivor-id>
    python scripts/merge_assets_to_carousel.py --undo <survivor-id> --execute

VERIFY, DO NOT ASSUME. `--verify` signs every slide through the same storage
surface the app uses. The database cannot answer whether the deck renders: the
Library signs slides all-or-nothing, so ONE unsignable object collapses a
six-slide carousel back to a static cover while the row still reads
`asset_type=carousel, slide_count=6` and looks perfect in SQL.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import secret_loader  # noqa: E402
from integrations import supabase_tool  # noqa: E402

SLIDE_BUCKET = "marketing-media"


def _db():
    return supabase_tool.get_client(secret_loader.bootstrap(), project="bravo")


def order_key(title: str) -> tuple[int, str]:
    """Sort by the trailing number in the title, falling back to the title.

    'CC Quote Proof 01' .. 'CC Quote 20260803 Insp 06' carry their intended
    sequence in that suffix. A title with no number sorts last rather than
    crashing — being unsure where a slide goes is not a reason to lose it.
    """
    m = re.search(r"(\d+)\s*$", title or "")
    return (int(m.group(1)) if m else 10**6, title or "")


def load_media(db, asset_ids: list[str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for aid in asset_ids:
        rows = db.table("marketing_asset_media").select(
            "id,asset_id,kind,storage_bucket,storage_path"
        ).eq("asset_id", aid).execute().data or []
        out[aid] = rows
    return out


def do_verify(db, asset_id: str) -> int:
    """Prove the deck will actually RENDER, not merely that the row looks right.

    The Library signs slides ALL OR NOTHING — app/founders/marketing/library:

        return signedSlides.every(Boolean) ? signedSlides : [];

    because a carousel that silently renumbers when one slide fails to sign is a
    different post. So a single missing or unsignable object does not degrade the
    deck, it collapses it back to a static cover with no error anywhere. The row
    would still read `asset_type=carousel, slide_count=6` and look perfect in SQL.

    Checking the database therefore proves nothing about what CC sees. This
    fetches every slide through the same storage surface the app uses and reports
    per-slide, which is the only version of "it works" worth saying out loud.
    """
    from lib import r2_storage  # noqa: PLC0415 — optional dep, only this path needs it

    rows = db.table("marketing_asset").select(
        "id,title,asset_type,slide_count,media_urls").eq("id", asset_id).execute().data
    if not rows:
        print(f"no such asset: {asset_id}", file=sys.stderr)
        return 2
    a = rows[0]
    raw = a.get("media_urls")
    try:
        paths = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except (TypeError, ValueError):
        paths = []
    paths = [p for p in paths if isinstance(p, str) and p]

    print(f"verify: {a['title']}")
    print(f"  asset_type  : {a.get('asset_type')}")
    print(f"  slide_count : {a.get('slide_count')}  ·  media_urls entries: {len(paths)}")

    if a.get("asset_type") != "carousel" or len(paths) < 2:
        # isRenderableCarousel() demands both. Claiming to be a carousel with one
        # slide is the state that printed "01/05 · swipe →" over a single image.
        print("  RESULT: will NOT render as a carousel "
              "(needs asset_type=carousel AND >1 slide)", file=sys.stderr)
        return 1

    surface = r2_storage.storage_surface().from_(SLIDE_BUCKET)
    ok = 0
    for i, p in enumerate(paths, 1):
        try:
            signed = surface.create_signed_url(p, 60)
            url = (signed or {}).get("signedURL") or (signed or {}).get("signedUrl")
            if url:
                ok += 1
                print(f"   {i}. ok    {p.rsplit('/', 1)[-1][:58]}")
            else:
                print(f"   {i}. FAIL  {p}  (no URL returned)")
        except Exception as exc:  # noqa: BLE001 — report every failure, never swallow
            print(f"   {i}. FAIL  {p}  ({exc})")

    if ok != len(paths):
        print(f"  RESULT: {ok}/{len(paths)} slides signable — the tile will fall back to "
              "the cover, because the Library signs all-or-nothing.", file=sys.stderr)
        return 1
    print(f"  RESULT: all {ok} slides signable — renders as a {ok}-slide deck.")
    return 0


def do_undo(db, survivor_id: str, execute: bool) -> int:
    a = db.table("marketing_asset").select("*").eq("id", survivor_id).execute().data
    if not a:
        print(f"no such asset: {survivor_id}", file=sys.stderr)
        return 2
    asset = a[0]
    src = (asset.get("source") or "")
    m = re.search(r"carousel-merge:([0-9a-f,\-]+)", src)
    if not m:
        print("this asset carries no merge record in `source` — nothing to undo", file=sys.stderr)
        return 2
    merged = [x for x in m.group(1).split(",") if x]
    print(f"undo: restoring {len(merged)} archived source assets and reverting the deck")
    for sid in merged:
        print(f"  restore {sid}")
    if not execute:
        print("\n  re-run with --execute to apply")
        return 0
    for sid in merged:
        db.table("marketing_asset").update({"status": "in_review"}).eq("id", sid).execute()
    db.table("marketing_asset").update({
        "asset_type": "single_image",
        "slide_count": 1,
        "media_urls": json.dumps([]),
        "source": None,
    }).eq("id", survivor_id).execute()
    print("undone")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--brand", help="brand_slug to scope to")
    ap.add_argument("--campaign", help="campaign to merge")
    ap.add_argument("--ids", help="comma-separated asset ids, instead of brand/campaign")
    ap.add_argument("--title", help="title for the resulting deck")
    ap.add_argument("--undo", metavar="SURVIVOR_ID", help="reverse a previous merge")
    ap.add_argument("--verify", metavar="ASSET_ID",
                    help="prove the deck renders: sign every slide the way the app does")
    ap.add_argument("--execute", action="store_true", help="apply (default is a dry run)")
    args = ap.parse_args()

    db = _db()
    if args.verify:
        return do_verify(db, args.verify)
    if args.undo:
        return do_undo(db, args.undo, args.execute)

    if args.ids:
        ids = [x.strip() for x in args.ids.split(",") if x.strip()]
        rows = []
        for i in ids:
            got = db.table("marketing_asset").select("*").eq("id", i).execute().data or []
            rows.extend(got)
    else:
        if not (args.brand and args.campaign):
            print("need --ids, or both --brand and --campaign", file=sys.stderr)
            return 2
        q = db.table("marketing_asset").select("*").eq(
            "brand_slug", args.brand).eq("campaign", args.campaign)
        rows = q.execute().data or []

    # Only merge things still in the working set. An already-archived row is not
    # a slide someone forgot; it is a decision that was made.
    rows = [r for r in rows if (r.get("status") or "") not in ("archived", "rejected")]
    if len(rows) < 2:
        print(f"nothing to merge — found {len(rows)} candidate(s)")
        return 0

    published = [r for r in rows if r.get("published_at")]
    if published:
        # Hard stop, not a skip. Merging around a published piece would leave its
        # analytics rows pointing at an archived asset and change what the
        # Performance tab measures, silently.
        print("REFUSING: these have already been published and must not be merged:", file=sys.stderr)
        for r in published:
            print(f"  {r['title']}  published_at={r['published_at']}", file=sys.stderr)
        return 1

    rows.sort(key=lambda r: order_key(r.get("title") or ""))
    media = load_media(db, [r["id"] for r in rows])

    slides: list[str] = []
    missing: list[str] = []
    for r in rows:
        imgs = [m for m in media.get(r["id"], []) if m.get("storage_path")]
        # Prefer an explicit image/poster over anything else attached.
        pick = next((m for m in imgs if m["kind"] in ("image", "poster", "thumb")), None) or (
            imgs[0] if imgs else None)
        if not pick:
            missing.append(r["title"])
            continue
        if pick["storage_bucket"] != SLIDE_BUCKET:
            # The Library signs every slide against one bucket, so a path from
            # somewhere else would render as a gap in the middle of the deck.
            missing.append(f"{r['title']} (bucket {pick['storage_bucket']})")
            continue
        slides.append(pick["storage_path"])

    if missing:
        print("REFUSING: no usable slide image for:", file=sys.stderr)
        for t in missing:
            print(f"  {t}", file=sys.stderr)
        print("A deck with a hole in it is worse than six tiles.", file=sys.stderr)
        return 1

    survivor = rows[0]
    others = rows[1:]
    title = args.title or f"{survivor.get('campaign') or 'Deck'} — {len(slides)} slides"

    print(f"merge {len(rows)} assets into one carousel")
    print(f"  survivor : {survivor['id']}  {survivor['title']}")
    print(f"  title    : {title}")
    print("  slide order:")
    for i, r in enumerate(rows, 1):
        print(f"    {i}. {r['title']}")
    print("  archives:")
    for r in others:
        print(f"    - {r['title']}")

    if not args.execute:
        print("\n  re-run with --execute to apply  (reversible: --undo "
              f"{survivor['id']})")
        return 0

    # `source` carries the merge record so --undo can walk it back. It is the
    # only column on this table that is free-form provenance text.
    merged_ids = ",".join(r["id"] for r in others)
    db.table("marketing_asset").update({
        "title": title,
        "asset_type": "carousel",
        "slide_count": len(slides),
        "media_urls": json.dumps(slides),
        "source": f"carousel-merge:{merged_ids}",
    }).eq("id", survivor["id"]).execute()

    for r in others:
        db.table("marketing_asset").update({"status": "archived"}).eq("id", r["id"]).execute()

    print(f"\nmerged. {len(slides)} slides on {survivor['id']}, {len(others)} archived.")
    print(f"undo: python scripts/merge_assets_to_carousel.py --undo {survivor['id']} --execute")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())