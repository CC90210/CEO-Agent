"""Every OpenNext app must ship the same static-asset header rules.

Cloudflare's asset handler defaults content-hashed build assets to
`max-age=0, must-revalidate`, where Vercel served them `immutable`. The fix is a
`public/_headers` file per app — which means the same file in a dozen repos, and
a dozen copies drift. Five apps got it during the migration and seven did not;
nothing would have told us.

So the content lives once in config/cloudflare/next_asset_headers.txt and this
test asserts every registered OpenNext app carries a byte-identical copy.

    python scripts/tests/test_worker_asset_headers.py         # check
    python scripts/tests/test_worker_asset_headers.py --fix   # propagate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANON = ROOT / "config" / "cloudflare" / "next_asset_headers.txt"
REGISTRY = ROOT / "config" / "cloudflare" / "apps.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true",
                    help="write the canonical copy into every app that is missing or stale")
    a = ap.parse_args()

    if not CANON.exists():
        sys.stderr.write(f"canonical header file missing: {CANON}\n")
        return 1
    want = CANON.read_text(encoding="utf-8")

    apps = json.loads(REGISTRY.read_text(encoding="utf-8"))["apps"]
    bad = 0
    for slug, cfg in sorted(apps.items()):
        if cfg.get("kind") != "opennext":
            continue                      # static-worker apps ship their own _headers
        target = Path(cfg["dir"]) / "public" / "_headers"
        if not Path(cfg["dir"]).exists():
            print(f"  SKIP    {slug:26} app directory not on this machine")
            continue

        have = target.read_text(encoding="utf-8") if target.exists() else None
        if have == want:
            print(f"  OK      {slug:26}")
            continue

        state = "MISSING" if have is None else "STALE"
        if not a.fix:
            print(f"  {state:7} {slug:26} {target}")
            bad += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(want, encoding="utf-8", newline="\n")
        # Re-read: a write that silently did not land is the failure this guards.
        if target.read_text(encoding="utf-8") != want:
            print(f"  FAILED  {slug:26} write did not land")
            bad += 1
        else:
            print(f"  FIXED   {slug:26} ({state.lower()})")

    print("\ntest_worker_asset_headers:", "OK" if not bad else f"{bad} app(s) out of sync")
    if bad and not a.fix:
        print("run with --fix to propagate the canonical copy.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
