"""publish_ownership_map — keep the shared copy of OWNERSHIP_MAP.yaml honest.

The ownership map exists in two places on purpose:

  brain/OWNERSHIP_MAP.yaml                                   SOURCE (Bravo reads this)
  <oasis-command-center>/docs/coordination/OWNERSHIP_MAP.yaml PUBLISHED (APEX reads this)

Bravo's code reads the local copy so `scripts/lib/ownership.py` has no dependency
on a sibling repo being cloned — that must keep working on a fresh machine. APEX
reads the published copy because it cannot read this repo at all, which was its
§10.12 point and a fair one.

Two copies of a NEGOTIATED CROSS-AGENT ARTIFACT is a drift bomb, and this is the
third instance of that same class in this subsystem:

  1. agent_activity.claims() vs coord_claim.conflicts()  — two claim mechanisms
  2. ownership._matches   vs repo_paths.covers            — two coverage impls
  3. this file                                            — two ownership maps

The first two were consolidated to one definition. This one cannot be, because
the whole point is that the artifact lives in a repo the peer can read. So it
gets the treatment this repo already uses for exactly this shape — a generated
copy plus a pre-commit check that refuses to let them diverge, the same as
scripts/_bridge_manifest.json and the README counts.

The failure this prevents is specific and was already scheduled: Bravo promised
APEX it would REGENERATE the map once APEX pushes its ~1,000 unpushed commits.
Without this check, that regeneration updates the source, leaves the published
copy stale, and APEX keeps making ownership decisions from a map that no longer
matches — silently, because nothing compares them.

  python scripts/publish_ownership_map.py --check     exit 1 if they differ
  python scripts/publish_ownership_map.py --publish   copy source -> published
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE = PROJECT_ROOT / "brain" / "OWNERSHIP_MAP.yaml"

# The shared repo is a sibling clone. Resolved by remote-derived slug, the same
# rule the leases use, so this cannot drift from the lease namespace either.
SHARED_REPO_SLUG = "oasis-command-center"
PUBLISHED_REL = Path("docs") / "coordination" / "OWNERSHIP_MAP.yaml"


def published_path() -> Path | None:
    """Local clone of the shared repo, or None if it is not on this machine."""
    for candidate in (Path.home() / "APPS" / SHARED_REPO_SLUG,
                      PROJECT_ROOT.parent / SHARED_REPO_SLUG):
        if (candidate / ".git").exists():
            return candidate / PUBLISHED_REL
    return None


def _read(p: Path) -> str | None:
    try:
        # Normalise line endings — this repo converts CRLF/LF on checkout, and a
        # pure line-ending difference is not drift worth blocking a commit over.
        return p.read_text(encoding="utf-8").replace("\r\n", "\n")
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="exit 1 if the copies differ")
    g.add_argument("--publish", action="store_true", help="copy source -> published")
    a = ap.parse_args()

    src = _read(SOURCE)
    if src is None:
        print(f"[ownership-map] source missing: {SOURCE}", file=sys.stderr)
        return 1

    dst_path = published_path()
    if dst_path is None:
        # Not an error. Bravo runs on machines that do not clone the shared repo,
        # and blocking every commit there would be worse than the drift.
        print("[ownership-map] shared repo not cloned here — nothing to publish "
              f"(looked for {SHARED_REPO_SLUG}). Skipping.")
        return 0

    if a.publish:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE, dst_path)
        print(f"[ownership-map] published -> {dst_path}")
        print("  NOTE: this only updates the working tree. Commit and push it in "
              f"{dst_path.parents[2].name}, or APEX still reads the old map.")
        return 0

    dst = _read(dst_path)
    if dst is None:
        print(f"[ownership-map] Commit blocked: published copy missing at {dst_path}\n"
              "  Run: python scripts/publish_ownership_map.py --publish", file=sys.stderr)
        return 1
    if src != dst:
        print("[ownership-map] Commit blocked: brain/OWNERSHIP_MAP.yaml has drifted "
              "from the copy APEX reads.\n"
              f"  published: {dst_path}\n"
              "  APEX makes ownership and lease decisions from the published copy. "
              "A stale one is not a cosmetic problem — it is the peer acting on a "
              "map that no longer matches reality.\n"
              "  Run:  python scripts/publish_ownership_map.py --publish\n"
              "  Then: commit and push it in the shared repo.", file=sys.stderr)
        return 1

    print("[ownership-map] source and published copy are in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
