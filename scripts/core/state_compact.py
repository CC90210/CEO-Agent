#!/usr/bin/env python3
"""state_compact — compact the LanceDB vector store to bound unbounded version growth (V7 EPIC 3).

Every PostToolUse edit re-indexes and appends a NEW LanceDB version with no cleanup, so
state/memory_lance/memory_chunks.lance grows unbounded (410 versions / 441 fragments / ~32 MB
at the 2026-06-10 audit). lancedb 0.30.2's Table.optimize(cleanup_older_than=…) compacts
fragments AND prunes versions older than the retention window in one call — turnkey, additive
(the current/latest version is always preserved; only stale append-versions are reclaimed).

Usage:
  python scripts/core/state_compact.py [--retain-days N] [--dry-run] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Mirrors scripts/core/memory_retriever.py (_LANCE_DIR / _LANCE_TABLE) — the canonical store.
LANCE_DIR = PROJECT_ROOT / "state" / "memory_lance"
LANCE_TABLE = "memory_chunks"


def _dir_size_mb(p: Path) -> float:
    try:
        return round(sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1024 / 1024, 2)
    except Exception:
        return 0.0


def _version_count(p: Path) -> int:
    vd = p / f"{LANCE_TABLE}.lance" / "_versions"
    try:
        return sum(1 for _ in vd.glob("*")) if vd.exists() else 0
    except Exception:
        return 0


def compact(retain_days: int = 2, dry_run: bool = False) -> dict:
    before = {"versions": _version_count(LANCE_DIR), "size_mb": _dir_size_mb(LANCE_DIR)}
    if not LANCE_DIR.exists():
        return {"status": "skip", "reason": "no LanceDB store", **{"before": before}}
    if dry_run:
        return {"status": "dry-run", "before": before,
                "would": f"optimize(cleanup_older_than={retain_days}d) on {LANCE_DIR}"}
    try:
        import lancedb
    except Exception as e:
        return {"status": "error", "reason": f"lancedb import failed: {e}", "before": before}
    try:
        db = lancedb.connect(str(LANCE_DIR))
        table = db.open_table(LANCE_TABLE)
        table.optimize(cleanup_older_than=timedelta(days=retain_days))
    except Exception as e:
        return {"status": "error", "reason": f"optimize failed: {str(e)[:160]}", "before": before}
    after = {"versions": _version_count(LANCE_DIR), "size_mb": _dir_size_mb(LANCE_DIR)}
    return {"status": "ok", "before": before, "after": after,
            "versions_reclaimed": before["versions"] - after["versions"],
            "mb_reclaimed": round(before["size_mb"] - after["size_mb"], 2)}


def main() -> int:
    ap = argparse.ArgumentParser(description="state_compact — LanceDB compaction")
    ap.add_argument("--retain-days", type=int, default=2, help="keep versions newer than N days (default 2)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = compact(a.retain_days, a.dry_run)
    if a.json:
        # ONE compact line, deliberately — scheduler.py stores out[-1][:200] as
        # last_result, so pretty JSON ends in a lone bracket and the watchdog
        # classifies the run as OPAQUE ("verdict unknowable"). Same fix as the
        # Instagram poller; do not "improve" this back to indent=2.
        print(json.dumps(r, separators=(",", ":")))
    else:
        print(f"=== LanceDB compaction: {r['status']} ===")
        b = r.get("before", {})
        print(f"  before: {b.get('versions')} versions, {b.get('size_mb')} MB")
        if r.get("after"):
            a2 = r["after"]
            print(f"  after:  {a2['versions']} versions, {a2['size_mb']} MB  "
                  f"(reclaimed {r['versions_reclaimed']} versions, {r['mb_reclaimed']} MB)")
        if r.get("reason"):
            print(f"  note: {r['reason']}")
    return 0 if r["status"] in ("ok", "dry-run", "skip") else 1


if __name__ == "__main__":
    sys.exit(main())
