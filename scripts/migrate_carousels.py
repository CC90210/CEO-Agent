"""migrate_carousels — register the carousel slides that were never uploaded.

WHAT IS ACTUALLY WRONG (measured, not assumed)
Six carousels sit in the Library as one row each with EXACTLY ONE media row. The
other four slides of each were rendered and never uploaded — they are on disk at
CMO-Agent/output/carousels/<slug>/slide_1..5.png, and each carousel's
manifest.json lists all five in order. The "01/05 · swipe →" a reviewer sees is
artwork printed on the cover, promising slides the database has never held.

WHY THIS DOES NOT GROUP ROWS BY TITLE
The task described detecting "split slide rows" and merging them by title prefix.
There are none. The six 4:5 rows sharing the "OASIS Oasis" prefix are six
DIFFERENT posts — ai-myths, manual-ops-cost, owner-dependency, repetition-01,
tried-and-failed, what-we-automate — each with its own slug and its own subject.
Grouping them by prefix would have collapsed six campaigns into one and lost five
of them. The manifests say what belongs together; titles only look like they do.

SO: for each asset whose `source` slug has a manifest on disk, upload the missing
slides to R2 in order, insert their media rows, and set asset_type='carousel',
slide_count=N, media_urls=[ordered storage paths].

Idempotent. A slide already registered (same storage_path suffix) is skipped, so
a re-run after a partial failure finishes the job rather than duplicating it.

  python scripts/migrate_carousels.py --dry-run   # show the plan, touch nothing
  python scripts/migrate_carousels.py             # do it
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import uuid
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import secret_loader, r2_storage  # noqa: E402
from integrations import supabase_tool  # noqa: E402

CMO = pathlib.Path(r"C:\Users\User\CMO-Agent")
CAROUSELS = CMO / "output" / "carousels"
TENANT = "ef8d389e-3f15-43f2-ae00-3660f69a1452"
BUCKET = "marketing-media"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _db():
    return supabase_tool.get_client(secret_loader.bootstrap(), project="bravo")


def slug_of(source: str | None) -> str | None:
    """`maven:oasis-tried-and-failed:post` -> `oasis-tried-and-failed`."""
    if not source:
        return None
    parts = source.split(":")
    return parts[1] if len(parts) >= 2 else None


def manifest_for(slug: str) -> list[pathlib.Path] | None:
    """Ordered slide files for a slug, or None when it is not a carousel.

    The manifest is the authority on ORDER — a carousel read out of order is a
    different post. Falls back to a numeric sort of slide_*.png only when the
    manifest is missing, and says so.
    """
    folder = CAROUSELS / slug
    mf = folder / "manifest.json"
    if mf.exists():
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            images = data.get("images") or []
            paths = [CMO / p for p in images]
            if paths and all(p.exists() for p in paths):
                return paths
            missing = [str(p) for p in paths if not p.exists()]
            print(f"    manifest lists files that are not on disk: {missing[:2]}")
        except Exception as exc:  # noqa: BLE001 — reported, never swallowed
            print(f"    manifest unreadable ({exc}); falling back to a numeric sort")
    loose = sorted(folder.glob("slide_*.png"), key=lambda p: int(p.stem.split("_")[1]))
    return loose or None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="show the plan, change nothing")
    args = ap.parse_args()

    if not CAROUSELS.exists():
        print(f"no carousel renders at {CAROUSELS} — nothing to migrate")
        return 0

    db = _db()
    assets = db.table("marketing_asset").select(
        "id, title, source, format, asset_type, slide_count"
    ).eq("tenant_id", TENANT).execute()

    planned = 0
    changed = 0
    for a in list(assets.data or []):
        slug = slug_of(a.get("source"))
        if not slug:
            continue
        slides = manifest_for(slug)
        if not slides or len(slides) < 2:
            continue  # a single image is not a carousel

        existing = db.table("marketing_asset_media").select(
            "id, storage_path, kind"
        ).eq("tenant_id", TENANT).eq("asset_id", a["id"]).execute()
        have = list(existing.data or [])
        have_names = {pathlib.Path(str(m.get("storage_path") or "")).name for m in have}

        print(f"\n{a['title']}  ({slug})")
        print(f"  manifest: {len(slides)} slides · registered: {len(have)}")
        planned += 1

        if args.dry_run:
            for i, p in enumerate(slides, 1):
                mark = "have" if any(p.name in n for n in have_names) else "UPLOAD"
                print(f"    {i}. {p.name:16} {mark}")
            continue

        surface = r2_storage.storage_surface().from_(BUCKET)
        ordered_paths: list[str] = []
        for i, path in enumerate(slides, 1):
            match = next((m for m in have if path.name in str(m.get("storage_path") or "")), None)
            if match:
                ordered_paths.append(str(match["storage_path"]))
                continue
            key = (f"{TENANT}/{a['id']}/"
                   f"{int(datetime.now(timezone.utc).timestamp() * 1000)}_{uuid.uuid4()}_{path.name}")
            surface.upload(key, path.read_bytes(), {"contentType": "image/png"})
            db.table("marketing_asset_media").insert({
                "id": str(uuid.uuid4()),
                "tenant_id": TENANT,
                "asset_id": a["id"],
                "kind": "image",
                "storage_bucket": BUCKET,
                "storage_path": key,
                "mime": "image/png",
                "bytes": path.stat().st_size,
                "label": f"Slide {i} of {len(slides)}",
                "created_at": _now(),
            }).execute()
            ordered_paths.append(key)
            print(f"    {i}. {path.name:16} uploaded")

        db.table("marketing_asset").update({
            "asset_type": "carousel",
            "slide_count": len(slides),
            "media_urls": json.dumps(ordered_paths),
            "updated_at": _now(),
        }).eq("tenant_id", TENANT).eq("id", a["id"]).execute()
        changed += 1
        print(f"    -> carousel, {len(slides)} slides, order recorded")

    print(f"\n{'planned' if args.dry_run else 'migrated'}: {changed if not args.dry_run else planned}"
          f" carousel(s) of {planned} matched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
