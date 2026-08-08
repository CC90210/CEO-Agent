#!/usr/bin/env python3
"""Point image columns at the app's media route instead of an r2.dev host.

The storage ETL rewrote these columns to the r2.dev URL of whatever bucket was
configured at the time — which was the PRIVATE bucket, before the public/private
split. That domain is now disabled, so every one of these images 404s. Pointing
them at the public bucket's r2.dev host would not help either: Cloudflare will
not serve it, and documents it as non-production.

So they move to `/api/media/<bucket>/<path>` — a permanent, same-origin path.
The app signs an R2 URL on demand and redirects. No bucket needs public access
at all, which is the outcome worth having: nothing is world-readable and the
private bucket keeps 4,088 bank statements behind a credential.

    python scripts/rewrite_image_pointers.py            # dry run
    python scripts/rewrite_image_pointers.py --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

import libsql  # noqa: E402

from lib.db_turso import resolve_project_target  # noqa: E402

# project -> [(table, column)] holding a full URL to a stored object.
TARGETS: dict[str, list[tuple[str, str]]] = {
    "nostalgic": [("dj_profiles", "profile_image_url")],
    "propflow": [("areas", "image_url"), ("buildings", "image_url")],
}

# Any r2.dev host, either bucket — both are wrong for a stored pointer.
R2DEV = re.compile(r"^https?://pub-[0-9a-f]+\.r2\.dev/(.+)$", re.I)
# Supabase public URLs, in case any survived the first rewrite.
SUPA = re.compile(r"^https?://[a-z0-9]+\.supabase\.co/storage/v1/object/public/(.+)$", re.I)


def new_value(current: str) -> str | None:
    """The /api/media path for a stored URL, or None if it needs no change."""
    for rx in (R2DEV, SUPA):
        m = rx.match(current.strip())
        if m:
            key = m.group(1).split("?")[0].lstrip("/")
            return f"/api/media/{key}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    total = changed = 0
    for proj, cols in TARGETS.items():
        url, tok, _ = resolve_project_target(proj)
        conn = libsql.connect(database=url, auth_token=tok)
        print(f"\n=== {proj}")
        for tbl, col in cols:
            try:
                rows = conn.execute(
                    f'SELECT rowid, "{col}" FROM "{tbl}" '
                    f'WHERE "{col}" IS NOT NULL AND "{col}" <> \'\'').fetchall()
            except Exception as exc:
                print(f"  {tbl}.{col}: {str(exc)[:80]}")
                continue
            for rid, cur in rows:
                total += 1
                nxt = new_value(str(cur))
                if not nxt:
                    print(f"  keep    {tbl}.{col} rowid={rid}: {str(cur)[:60]}")
                    continue
                changed += 1
                print(f"  rewrite {tbl}.{col} rowid={rid}")
                print(f"          {str(cur)[:70]}")
                print(f"       -> {nxt[:70]}")
                if args.apply:
                    conn.execute(f'UPDATE "{tbl}" SET "{col}" = ? WHERE rowid = ?',
                                 (nxt, rid))
        if args.apply:
            conn.commit()

    print(f"\n{changed} of {total} pointer(s) "
          f"{'rewritten' if args.apply else 'would be rewritten'}")
    if not args.apply and changed:
        print("(dry run — pass --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
