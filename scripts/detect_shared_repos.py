# bridge_mutating: false
"""detect_shared_repos — find app repos that BOTH agents commit to, and are unmapped.

WHY THIS EXISTS
---------------
`brain/OWNERSHIP_MAP.yaml` covers `oasis-command-center` and `ceo-agent`. That is
correct TODAY — measured 2026-08-28, those are the only repos with commits from
both the CC side and the Adon side in the last 120 days.

It is correct today and will be wrong silently. The first time Adon opens
`breeze-portal` or `sunbiz-funding`, that repo becomes a shared surface with no
ownership entry, no contested-path list, and therefore no lease requirement and
no guard nudge. Nothing announces it. The collision announces it, later, as a
silently reverted commit — which is exactly how the original 226-file overlap
accumulated in oasis-command-center before anyone measured it.

So the question "which repos are shared?" gets answered by evidence on a
schedule instead of by memory once.

Identity comes from `brain/OWNERSHIP_MAP.yaml` git_identities, not a second
hardcoded list — that duplicate-definition class has already bitten five times
in this subsystem.

  python scripts/detect_shared_repos.py            # report
  python scripts/detect_shared_repos.py --json
  python scripts/detect_shared_repos.py --check    # exit 1 if an unmapped repo is shared
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import ownership, repo_paths  # noqa: E402

APPS = Path.home() / "APPS"
WINDOW_DAYS = 120
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _identities() -> tuple[set[str], set[str]]:
    """(bravo_side, apex_side) git author names, from the ownership map."""
    agents = ownership.load().get("agents") or {}
    b = set((agents.get("bravo") or {}).get("git_identities") or [])
    a = set((agents.get("apex") or {}).get("git_identities") or [])
    return b, a


def _authors(repo: Path) -> dict[str, int]:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "log", f"--since={WINDOW_DAYS} days ago", "--format=%an"],
            capture_output=True, text=True, timeout=120, errors="ignore",
            creationflags=_NO_WINDOW).stdout
    except Exception:  # noqa: BLE001
        return {}
    counts: dict[str, int] = {}
    for line in out.splitlines():
        n = line.strip()
        if n:
            counts[n] = counts.get(n, 0) + 1
    return counts


def scan() -> list[dict]:
    bravo_ids, apex_ids = _identities()
    mapped = {k.lower() for k in (ownership.load().get("repos") or {})}
    out = []
    if not APPS.is_dir():
        return out
    for d in sorted(APPS.iterdir()):
        if not (d / ".git").exists():
            continue
        counts = _authors(d)
        if not counts:
            continue
        b = sum(n for a, n in counts.items() if a in bravo_ids)
        a_ = sum(n for a, n in counts.items() if a in apex_ids)
        if not (b and a_):
            continue                      # not shared — one side only
        # Slug by the SAME rule leases use, so a hit here is actionable as-is.
        slug = repo_paths.repo_slug(d)
        out.append({
            "dir": d.name, "slug": slug, "bravo_commits": b, "apex_commits": a_,
            "total": sum(counts.values()), "mapped": slug.lower() in mapped,
        })

    # Collapse by SLUG. ~/APPS holds seven separate checkouts that all resolve to
    # `oasis-command-center` (auth-hotfix, pipeline-fix, sales-engine, ...), and
    # a per-directory listing printed it seven times. That is not cosmetic: a
    # genuinely NEW shared repo — the only thing this tool exists to surface —
    # would be buried among the duplicates. The slug is the unit of coordination,
    # so it is the unit of the report.
    merged: dict[str, dict] = {}
    for r in out:
        m = merged.setdefault(r["slug"], {
            "slug": r["slug"], "dirs": [], "bravo_commits": 0,
            "apex_commits": 0, "mapped": r["mapped"]})
        m["dirs"].append(r["dir"])
        # Checkouts of one repo share history, so summing would multiply the same
        # commits. The max across checkouts is the honest figure.
        m["bravo_commits"] = max(m["bravo_commits"], r["bravo_commits"])
        m["apex_commits"] = max(m["apex_commits"], r["apex_commits"])
    return sorted(merged.values(), key=lambda x: -x["apex_commits"])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--json", action="store_true")
    p.add_argument("--check", action="store_true",
                   help="exit 1 if a shared repo has no ownership entry")
    a = p.parse_args()

    rows = scan()
    unmapped = [r for r in rows if not r["mapped"]]

    if a.json:
        print(json.dumps({"shared": rows, "unmapped": unmapped}, indent=2))
        return 1 if (a.check and unmapped) else 0

    if not rows:
        print("no shared repos found (no repo has commits from both sides in "
              f"the last {WINDOW_DAYS} days)")
        return 0

    print(f"repos with commits from BOTH sides in the last {WINDOW_DAYS} days:")
    for r in rows:
        flag = "mapped" if r["mapped"] else "*** NOT IN OWNERSHIP MAP ***"
        n = len(r.get("dirs") or [])
        where = f" ({n} local checkouts)" if n > 1 else ""
        print(f"  {r['slug']:<28} bravo={r['bravo_commits']:<5} apex={r['apex_commits']:<5} {flag}{where}")

    if unmapped:
        print()
        print("A shared repo with no ownership entry has no contested-path list, so")
        print("no lease is required and the guard never nudges. Nothing announces")
        print("this — the collision does, later, as a silently reverted commit.")
        print("Add each to brain/OWNERSHIP_MAP.yaml under `repos:` keyed by SLUG,")
        print("then: python scripts/publish_ownership_map.py --publish")
    return 1 if (a.check and unmapped) else 0


if __name__ == "__main__":
    sys.exit(main())
