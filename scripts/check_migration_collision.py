# bridge_mutating: true
#
# Deliberate, not defaulted. Two of the three verbs (`next`, `check`) are
# read-only and one (`reserve`) writes a lease and posts an agent_activity row.
# The flag is per-file, so the choice is: over-confirm two reads, or let a write
# through unconfirmed. Same asymmetry as the coverage over-match — a needless tap
# costs a second; an unapproved reservation takes a number out from under the
# peer. Do not flip this to false to quiet the prompts.
"""check_migration_collision — reserve a migration number before you take it.

APEX ask 6 (2026-08-27): `database/**` is a contested surface and migration
numbers collide SILENTLY. Two agents on two machines both pick `015`, both
commit, and the loser's migration either never applies or applies out of order
against a schema it did not expect. Nothing errors at write time; it surfaces
later as a missing column in production.

This makes the number a claim rather than a guess:

  python scripts/check_migration_collision.py next
      -> the next free number, per prefix

  python scripts/check_migration_collision.py check 015
      -> exit 0 free · exit 3 taken (locally or by a peer's live lease)

  python scripts/check_migration_collision.py reserve 015 --task "coord audit"
      -> takes a coord_claims lease on the numbered path AND posts an
         agent_activity row, so the peer sees it in both channels

It checks THREE sources, because any one alone is a false negative:
  1. files on disk in database/ and database/turso_migrations/
  2. live coord_claims leases covering a migration path (the peer may have
     reserved a number without having pushed a file yet — this is the case a
     plain `ls` misses, and it is the one that actually bites)
  3. the local git index, for a number staged but not committed
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import repo_paths  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIRS = [PROJECT_ROOT / "database", PROJECT_ROOT / "database" / "turso_migrations"]
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# `102_agent_activity.sql` and `bravo__013_coord_claims.sql`
_NUM_RE = re.compile(r"^(?:(?P<prefix>[a-z]+)__)?(?P<num>\d{3,4})[_-]", re.I)


def taken_on_disk() -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    for d in DIRS:
        if not d.is_dir():
            continue
        for f in d.glob("*.sql"):
            m = _NUM_RE.match(f.name)
            if m:
                out.setdefault((m.group("prefix") or "").lower(), set()).add(int(m.group("num")))
    return out


def taken_in_index() -> set[str]:
    """Staged-but-uncommitted migration filenames — invisible to a peer, and to
    a plain directory listing on any other machine."""
    try:
        r = subprocess.run(["git", "diff", "--cached", "--name-only"],
                           cwd=PROJECT_ROOT, capture_output=True, text=True,
                           timeout=15, creationflags=_NO_WINDOW)
        return {ln.strip() for ln in r.stdout.splitlines() if ln.strip().endswith(".sql")}
    except Exception:  # noqa: BLE001
        return set()


def peer_reservations() -> list[dict]:
    """Live leases covering anything under database/. This is the source a
    directory listing cannot see: the peer reserved the number minutes ago and
    has not pushed a file."""
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))
        import coord_claim  # noqa: PLC0415
        me = coord_claim.ME
        return [c for c in coord_claim.live_claims()
                if c.get("agent") != me and "database" in (c.get("path_glob") or "")]
    except Exception as e:  # noqa: BLE001
        print(f"WARN: could not read peer lease reservations ({type(e).__name__}: {e}). "
              f"Disk check only — a number the peer reserved but has not pushed will "
              f"look FREE. Do not treat this run as authoritative.", file=sys.stderr)
        return []


def taken_numbers(prefix: str = "bravo") -> set[int]:
    """Every number that is taken for this prefix — the ONE definition.

    `next_free()` used `prefixed OR unprefixed` while `check`/`reserve` used
    `prefixed | unprefixed`, so the tool CONTRADICTED ITSELF: `next` recommended
    015 and `check 015` immediately refused it, because 015 exists unprefixed.
    An allocator whose own validator rejects its recommendation is worse than no
    allocator — it burns the operator's trust on the first use.

    Migration numbers share one ordering on disk regardless of prefix, so the
    union is the correct rule and both callers now use it.
    """
    disk = taken_on_disk()
    return disk.get(prefix.lower(), set()) | disk.get("", set())


def next_free(prefix: str = "bravo") -> int:
    nums = taken_numbers(prefix)
    return (max(nums) + 1) if nums else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    pn = sub.add_parser("next", help="next free migration number")
    pn.add_argument("--prefix", default="bravo")

    pc = sub.add_parser("check", help="is this number free? exit 3 if taken")
    pc.add_argument("number", type=int)
    pc.add_argument("--prefix", default="bravo")

    pr = sub.add_parser("reserve", help="lease + announce a migration number")
    pr.add_argument("number", type=int)
    pr.add_argument("--prefix", default="bravo")
    pr.add_argument("--task", required=True)

    a = p.parse_args()
    prefix = a.prefix.lower()

    if a.cmd == "next":
        n = next_free(prefix)
        print(f"next free for prefix {prefix!r}: {n:03d}")
        print(f"  taken on disk: {sorted(taken_numbers(prefix))[-8:]}")
        for c in peer_reservations():
            print(f"  PEER RESERVED: {c['agent']} holds {c['repo']}/{c['path_glob']} "
                  f"(task: {c['task']})")
        return 0

    num = a.number
    nums = taken_numbers(prefix)      # SAME definition next_free() uses
    reasons = []
    if num in nums:
        reasons.append(f"a file with number {num:03d} already exists on disk")
    for f in taken_in_index():
        m = _NUM_RE.match(Path(f).name)
        if m and int(m.group("num")) == num:
            reasons.append(f"{f} is STAGED but not committed (invisible to the peer)")
    for c in peer_reservations():
        if f"{num:03d}" in (c.get("path_glob") or "") or f"{num:03d}" in (c.get("task") or ""):
            reasons.append(f"{c['agent']} holds a live lease naming {num:03d} "
                           f"(task: {c['task']}, machine: {c['machine']})")

    if a.cmd == "check":
        if reasons:
            print(f"TAKEN — {num:03d} is not free:")
            for r in reasons:
                print(f"  · {r}")
            print(f"\nUse {next_free(prefix):03d} instead.")
            return 3
        print(f"FREE — {prefix}__{num:03d} is available. Reserve it before you write:\n"
              f"  python scripts/check_migration_collision.py reserve {num} --task \"<what>\"")
        return 0

    # reserve
    if reasons:
        print(f"REFUSED — {num:03d} is not free:", file=sys.stderr)
        for r in reasons:
            print(f"  · {r}", file=sys.stderr)
        return 3
    path = f"database/turso_migrations/{prefix}__{num:03d}_*.sql"
    sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))
    import coord_claim  # noqa: PLC0415
    import agent_activity  # noqa: PLC0415
    slug = repo_paths.repo_slug(PROJECT_ROOT)
    res = coord_claim.acquire(slug, [path], f"migration {num:03d}: {a.task}",
                              strict=False)
    if not res.get("acquired"):
        print(f"REFUSED — peer holds a conflicting lease: {res.get('conflicts')}",
              file=sys.stderr)
        return 3
    agent_activity.post("working", f"Reserving migration {prefix}__{num:03d} — {a.task}",
                        files=[path], detail="Announced before taking the number so it "
                                             "cannot collide silently (APEX ask 6).")
    print(f"RESERVED {prefix}__{num:03d} — lease held on {slug}/{path} and announced "
          f"on agent_activity.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
