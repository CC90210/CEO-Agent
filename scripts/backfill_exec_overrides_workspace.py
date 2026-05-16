"""One-off backfill: classify existing exec_overrides rows into workspace buckets.

Migration 048 (database/048_exec_overrides_workspace_label.sql) added
`workspace_label` and `cwd_path` columns to public.exec_overrides. New rows
get workspace_label written at insert time by exec_override_mirror.py.
Existing rows default to 'unknown'; this script regex-classifies the `command`
field to backfill them.

Idempotent: re-running only updates rows where workspace_label='unknown'.

Classification rules (more specific first):
  sunbiz_client    — Marketing-Agent / text_torrent / kixie / /t/sun/
                     / sun_biz / sunbiz in the command text
  suga_client      — CMO-Agent / sugasean / suga sean / suga brand
  propflow_client  — propflow / prop-flow / prop_flow
  empire           — Business-Empire-Agent / /oasis / oasis_seed / "empire"
  unknown          — none of the above (stays 'unknown')

Run:
  python scripts/backfill_exec_overrides_workspace.py            # dry-run
  python scripts/backfill_exec_overrides_workspace.py --apply    # commit
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# Single source of truth for the workspace classifier — shared with the
# write-time path so historical backfill and forward-going inserts can
# never drift apart.
from lib.exec_override_mirror import classify_workspace  # noqa: E402


def _classify(command: str) -> str:
    return classify_workspace(None, command)


def _client():
    from lib.secret_loader import load_env  # noqa: E402
    env = load_env()
    url = (env.get("BRAVO_SUPABASE_URL") or "").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        sys.stderr.write("ERROR: BRAVO_SUPABASE_URL + service role key required\n")
        sys.exit(2)
    from supabase import create_client
    return create_client(url, key)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--apply", action="store_true",
                   help="Commit the reclassification. Without this flag, dry-run only.")
    args = p.parse_args(argv)

    client = _client()
    res = (
        client.table("exec_overrides")
        .select("request_id, command, workspace_label")
        .eq("workspace_label", "unknown")
        .limit(1000)
        .execute()
    )
    rows = res.data or []
    if not rows:
        print("No 'unknown' rows to backfill.")
        return 0

    counts: dict[str, int] = {}
    plans: list[tuple[str, str]] = []
    for row in rows:
        label = _classify(row.get("command") or "")
        counts[label] = counts.get(label, 0) + 1
        if label != "unknown":
            plans.append((row["request_id"], label))

    print(f"Found {len(rows)} 'unknown' rows. Reclassification plan:")
    for label, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {label:18s} {n}")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to commit.")
        return 0

    if not plans:
        print("\nNothing to reclassify (all stayed 'unknown').")
        return 0

    print(f"\nApplying {len(plans)} updates ...")
    updated = 0
    for request_id, label in plans:
        try:
            client.table("exec_overrides").update({"workspace_label": label}).eq("request_id", request_id).execute()
            updated += 1
        except Exception as e:  # noqa: BLE001
            print(f"  WARN: failed {request_id} → {label}: {e}", file=sys.stderr)

    print(f"Done. {updated}/{len(plans)} rows updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
