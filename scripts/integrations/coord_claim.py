"""coord_claim — file-path LEASES for cross-agent, cross-machine coordination.

Bravo (CC) and APEX (Adon) both edit the same OASIS repos from different
machines. `agent_activity` carries the human-readable narrative; THIS module
carries the machine-checkable half: who currently holds which path.

WHY A LEASE AND NOT A ROW
-------------------------
`agent_activity.files` was the claim mechanism from 2026-06 to 2026-08 and it
never once prevented a collision. Measured over the 90 days to 2026-08-27:
~60% of rows carried no files at all; the ones that did were not comparable
(Bravo wrote "pipeline"/"Turso", APEX wrote "services/leadgen/**"), and
`claims()` compared them by exact string; and nothing released them — 60
`working` rows against 25 `done`, so a claim ended only by ageing out of a 6h
read window. Result: 226 of 1,596 files in oasis-command-center touched by both
sides, 117 same-file cross-side edits inside 48h.

The three fixes, all enforced here rather than documented:
  1. GRAMMAR   — a path must resolve inside the named repo, or acquire() refuses
                 it. This is what makes overlap computable at all.
  2. TTL       — every lease has an absolute expiry, refreshed by heartbeat().
                 A crashed agent's lease frees itself; it does not wedge a repo.
  3. REPO      — paths are repo-relative POSIX, scoped by repo slug, so the same
                 filename in two repos is two different things.

Semantics are deliberately the ones scripts/bridge_lock.py already proved for
Telegram bridge arbitration (acquire / heartbeat / release / stale reclaim,
holder host recorded). The difference: bridge_lock is a local file arbitrating
one machine's daemons; this is Turso, arbitrating two orgs' agents.

Read by scripts/state/coord_guard.py on every Edit/Write. That hook is the
reason this exists — a protocol nothing enforces decays to nothing, which is
exactly what happened to the last one.

USAGE
-----
  python scripts/integrations/coord_claim.py acquire --repo oasis-command-center \
      --paths "lib/drips/executor.ts,lib/drips/send.ts" \
      --task "drip timezone fix" --branch cc/drip-tz [--ttl-min 90]

  python scripts/integrations/coord_claim.py conflicts --repo oasis-command-center \
      --paths "lib/drips/executor.ts"     # exit 3 if a peer holds it

  python scripts/integrations/coord_claim.py heartbeat --task "drip timezone fix"
  python scripts/integrations/coord_claim.py release   --task "drip timezone fix"
  python scripts/integrations/coord_claim.py release   --session <id>
  python scripts/integrations/coord_claim.py status [--repo <slug>] [--all-agents]

Exit codes: 0 = ok · 1 = error · 2 = bad args · 3 = conflict (peer holds a path).
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import repo_paths as _rp  # noqa: E402
from lib.db_turso import get_db  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

TABLE = "coord_claims"
DEFAULT_TTL_MIN = 90
UNSCOPED_REASON = "cross-agent coordination: coord_claims is fleet-wide, not tenant-scoped"

# Canonical agent identity. The table carried FOUR keys for two agents
# ('cc-agent' 108 rows, 'apex' 91, 'bravo' 1, 'codex' 3) and the single 'bravo'
# row was invisible to every peer read that filtered on 'cc-agent'. One key per
# agent, set once, overridable only by env for a non-Bravo runtime.
ME = os.environ.get("COORD_AGENT_KEY", "bravo").strip().lower()

# Windows: CREATE_NO_WINDOW keeps `git` from flashing a console when this module
# is called from a pythonw-hosted hook. Guarded by scripts/hooks/subprocess_guard.py.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


CANONICAL_TS = "%Y-%m-%dT%H:%M:%S.%f+00:00"


def _iso(dt: datetime) -> str:
    """The CANONICAL cross-agent timestamp. Fixed width, always six fractional
    digits, always an explicit +00:00 offset, never a `Z` suffix.

    `dt.isoformat()` is NOT this. It omits the fractional part entirely when
    microseconds happen to be zero:

        datetime(...,  0).isoformat()  ->  2026-08-27T17:15:47+00:00
        datetime(..., 116239).isoformat() -> 2026-08-27T17:15:47.116239+00:00

    APEX pinned the format on its side and kept a LEXICAL comparison, so a
    variable-width stamp from here would break its ordering — and it would break
    it precisely on a tie-break, because a tie-break only runs when two inserts
    land in the same instant. Two shapes of the same instant do not compare
    equal, so the tie the rule exists to resolve becomes invisible to it.

    Bravo compares parsed instants and is immune either way. This exists to hold
    up Bravo's end of a format the PEER depends on lexically.
    """
    return dt.astimezone(timezone.utc).strftime(CANONICAL_TS)


def _machine() -> str:
    return os.environ.get("COORD_MACHINE") or socket.gethostname()


# --------------------------------------------------------------------------
# Repo + path grammar — the fix that makes overlap computable
# --------------------------------------------------------------------------

# Path/repo resolution and glob coverage live in scripts/lib/repo_paths.py —
# ONE definition, imported by both this CLI and the coord_guard hook. The hook
# must not import this module (it pulls in db_turso, which connects at import
# time and cost 4-5s per edit before the split).
repo_root = _rp.repo_root
overlaps = _rp.overlaps
intersects = _rp.intersects
repo_slug = _rp.repo_slug
resolve = _rp.resolve
covers = _rp.covers


def _repo_root_for_slug(slug: str) -> Path | None:
    """Best-effort local root for a slug: cwd's repo if it matches, else ~/APPS/<slug>."""
    here = repo_root()
    if here is not None and repo_slug(here) == slug:
        return here
    cand = Path.home() / "APPS" / slug
    return cand if cand.is_dir() else None


def _validate_paths(repo: str, paths: list[str], *, strict: bool) -> list[str]:
    """Enforce the grammar. A claim that cannot be matched is worse than none —
    it reads as coverage while protecting nothing, which is precisely how
    files=["pipeline","Turso"] passed review for two months.

    Globs are accepted as-is (they cannot be stat'd); literal paths must exist
    in the named repo when strict.
    """
    cleaned: list[str] = []
    for raw in paths:
        rel = raw.strip().replace("\\", "/")
        while rel.startswith("./"):
            rel = rel[2:]
        if not rel:
            continue
        # Absoluteness must be judged for BOTH platforms, not the host's.
        # Path("/etc/passwd").is_absolute() is False on Windows and
        # Path("C:/x").is_absolute() is False on POSIX — so relying on pathlib
        # alone lets the other OS's absolute paths through as "relative". APEX
        # may well be on macOS; a claim written there is read here.
        head = rel.split("/")[0]
        looks_absolute = (
            rel.startswith("/")
            or rel.startswith("\\")
            or (len(head) == 2 and head[1] == ":" and head[0].isalpha())
        )
        if looks_absolute or rel.startswith("../"):
            raise ValueError(
                f"{raw!r} must be repo-relative, not absolute or escaping the repo.")
        if ":" in head:
            raise ValueError(
                f"{raw!r} uses a namespace prefix (e.g. 'oasis:', 'turso:'). "
                "Claims are repo-relative POSIX paths; pass --repo for the namespace.")
        is_glob = any(ch in rel for ch in "*?[")
        # APEX contract §3.3 edge case: a single extensionless segment is
        # indistinguishable from a concept name ("pipeline", "settings", "auth")
        # unless the file really exists. `Makefile` and `Dockerfile` are legal;
        # `pipeline` is not. Checked even when strict is off, because this is the
        # exact class that made the old mechanism unmatchable.
        if not is_glob and "/" not in rel and "." not in rel:
            root = _repo_root_for_slug(repo)
            if root is None or not (root / rel).exists():
                raise ValueError(
                    f"{raw!r} is a single extensionless segment and no such file "
                    f"exists in {repo!r}. That is indistinguishable from a concept "
                    "name ('pipeline', 'settings', 'Turso'), which is what made "
                    "the previous claim mechanism unmatchable. Use a real path.")
        if strict and not is_glob:
            root = _repo_root_for_slug(repo)
            if root is not None and not (root / rel).exists():
                raise ValueError(
                    f"{rel!r} does not exist in repo {repo!r}. A claim on a "
                    "non-existent path protects nothing — check the path, or pass "
                    "--no-strict if you are claiming a file you are about to create.")
        cleaned.append(rel)
    if not cleaned:
        raise ValueError("no valid paths given")
    return cleaned


# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------

def parse_ts(value) -> datetime | None:
    """Parse any ISO-8601 spelling into an aware UTC datetime, or None.

    Accepts the `Z` suffix (fromisoformat rejects it before 3.11) and treats a
    naive timestamp as UTC. Returning None means "unparseable" — callers must
    treat that as NOT live rather than as live, so a corrupt row frees a path
    instead of wedging it.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        txt = str(value).strip()
        if txt.endswith(("Z", "z")):
            txt = txt[:-1] + "+00:00"
        dt = datetime.fromisoformat(txt)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def is_live(claim: dict, now: datetime | None = None) -> bool:
    """A lease is live only if it is held AND its expiry parses AND is future."""
    if (claim.get("status") or "held") != "held":
        return False
    exp = parse_ts(claim.get("expires_at"))
    return exp is not None and exp > (now or _now())


_COLS = ["id", "agent", "machine", "repo", "path_glob", "task", "branch",
         "session_id", "acquired_at", "heartbeat_at", "expires_at"]


def live_claims(repo: str | None = None, *, exclude_agent: str | None = None,
                only_agent: str | None = None) -> list[dict]:
    """Every unexpired, unreleased lease. Expiry is compared as an ISO-8601 UTC
    string — lexical order is chronological for that format, so SQLite can do it
    without a date function."""
    # NOTE: no expiry predicate in SQL. An earlier version compared
    # `expires_at > ?` lexically, which is only sound if every writer emits the
    # identical UTC format. APEX is a SECOND writer on this table and may emit a
    # `Z` suffix — and "…Z" sorts ABOVE "…+00:00" (0x5A > 0x2B), so an expired
    # Z-suffixed lease would read as live. Expiry is now decided in Python by
    # parsing, which handles every ISO-8601 spelling. (Codex adversarial review,
    # 2026-08-27.)
    sql = ('SELECT id, agent, machine, repo, path_glob, task, branch, session_id, '
           'acquired_at, heartbeat_at, expires_at FROM "' + TABLE + '" '
           "WHERE status = 'held'")
    params: list = []
    if repo:
        sql += " AND repo = ?"
        params.append(repo)
    if exclude_agent:
        sql += " AND agent != ?"
        params.append(exclude_agent)
    if only_agent:
        sql += " AND agent = ?"
        params.append(only_agent)
    sql += " ORDER BY acquired_at DESC"
    rows = _db().query(sql, params, allow_unscoped=True, reason=UNSCOPED_REASON)
    out = [r if isinstance(r, dict) else dict(zip(_COLS, r)) for r in rows]
    return [r for r in out if is_live(r)]


def _db():
    return get_db()


def conflicts(repo: str, paths: list[str], *, agent: str | None = None) -> list[dict]:
    """Live leases held by SOMEONE ELSE that cover any of `paths`."""
    me = (agent or ME).lower()
    held = live_claims(repo, exclude_agent=me)
    out = []
    for c in held:
        for p in paths:
            # overlaps(), not covers(): a candidate may itself be a GLOB, and two
            # globs can intersect without either matching the other as a string
            # (Codex P1, 2026-08-27). covers() alone is blind to exactly the
            # broad claims we encourage.
            if overlaps(c["path_glob"], p):
                out.append({**c, "conflicting_path": p})
                break
    return out


def _warn_out_of_surface(repo: str, paths: list[str], me: str) -> None:
    """Say so when you are claiming inside the PEER's surface.

    `brain/OWNERSHIP_MAP.yaml` names this module as a consumer, and until now
    that was untrue — the map was read by the guard but never by the thing that
    takes the lease. A doc that advertises a behaviour nobody implemented is the
    same defect as a claim that cannot be matched: it reads as coverage.

    This never BLOCKS. Crossing into a peer's surface is explicitly allowed by
    the contract; it just requires a lease (which you are taking) and a peer
    `ack` before merge. The warning is the reminder about the ack.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from lib import ownership  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return
    for rel in paths:
        try:
            owner = ownership.owner(repo, rel)
        except Exception:  # noqa: BLE001
            continue
        if owner and owner not in (me, "shared"):
            print(f"[coord_claim] NOTE {repo}/{rel} is {owner.upper()}'s surface. "
                  f"Allowed — but it needs an `ack` row from {owner} before you merge "
                  f"(two-step verification). Tell them what you are changing and why.",
                  file=sys.stderr)


def acquire(repo: str, paths: list[str], task: str, *, branch: str | None = None,
            ttl_min: int = DEFAULT_TTL_MIN, session_id: str | None = None,
            agent: str | None = None, strict: bool = True,
            force: bool = False) -> dict:
    me = (agent or ME).lower()
    cleaned = _validate_paths(repo, paths, strict=strict)
    _warn_out_of_surface(repo, cleaned, me)
    clash = conflicts(repo, cleaned, agent=me)
    if clash and not force:
        return {"acquired": False, "conflicts": clash, "paths": cleaned}

    now = _now()
    expires = now + timedelta(minutes=ttl_min)
    db = _db()
    rows = []
    for rel in cleaned:
        row = {
            "id": str(uuid.uuid4()),
            "agent": me,
            "machine": _machine(),
            "repo": repo,
            "path_glob": rel,
            "task": task,
            "branch": branch,
            "session_id": session_id or os.environ.get("CLAUDE_SESSION_ID"),
            "status": "held",
            "acquired_at": _iso(now),
            "heartbeat_at": _iso(now),
            "expires_at": _iso(expires),
        }
        db.insert(TABLE, row, allow_unscoped=True, reason=UNSCOPED_REASON)
        rows.append(row)
    db.commit()

    # POST-INSERT RECHECK — closes the check-then-insert race.
    #
    # conflicts() above and the inserts here are not one atomic operation, so two
    # agents polling within the same ~200ms window can BOTH see a clear path and
    # BOTH insert. That defeats the single invariant this module exists to
    # provide, under exactly the concurrent cross-machine case it is built for
    # (Codex adversarial review, 2026-08-27).
    #
    # libSQL gives us no cross-connection advisory lock, so we resolve rather
    # than prevent: after committing, look again. If a peer holds a lease on any
    # of our paths that was acquired BEFORE ours, they won the race — we release
    # ours and report the conflict. The tiebreak is (acquired_at, id), both
    # already stored and both total orders, so BOTH agents independently reach
    # the SAME verdict without talking to each other. Ties on timestamp fall
    # through to the uuid, which is stable and arbitrary but consistent.
    if not force:
        losers = []
        for c in conflicts(repo, cleaned, agent=me):
            mine_for_path = next((r for r in rows if covers(r["path_glob"], c["conflicting_path"])
                                  or r["path_glob"] == c["path_glob"]), None)
            if mine_for_path is None:
                continue
            # Compare PARSED INSTANTS, never the raw strings.
            #
            # v3 of the contract said "compare acquired_at as a string first".
            # APEX implemented against it, hit the bug, and was right: Python
            # emits 2026-08-27T23:32:12.667878+00:00 and JS emits
            # ...T23:32:12.667Z, so at an equal millisecond prefix the strings
            # order on '8' vs 'Z' — which has nothing to do with real time.
            #
            # The mutual-exclusion break is subtler than "wrong winner". If one
            # side follows the contract literally (string compare) and the other
            # does the sane thing (instant compare), each can conclude the peer
            # is LATER and BOTH KEEP. Two holders on one path, from two correct-
            # looking implementations of the same sentence.
            #
            # Instants are format-agnostic. `id` breaks a genuine exact tie and
            # is a uuid, so it collates identically in both languages.
            theirs_ts, ours_ts = parse_ts(c.get("acquired_at")), parse_ts(mine_for_path["acquired_at"])
            if theirs_ts is None or ours_ts is None:
                # An unparseable acquired_at cannot be ordered. Yield rather than
                # guess: a spurious release costs one retry, a wrong keep costs a
                # silent double-hold.
                losers.append(c)
                continue
            theirs = (theirs_ts, str(c.get("id") or ""))
            ours = (ours_ts, str(mine_for_path["id"] or ""))
            if theirs < ours:          # they got there first
                losers.append(c)
        if losers:
            db.execute(
                'UPDATE "' + TABLE + '" SET status = \'released\', released_at = ? '
                "WHERE agent = ? AND task = ? AND status = 'held'",
                [_iso(_now()), me, task],
                allow_unscoped=True, reason=UNSCOPED_REASON)
            db.commit()
            return {"acquired": False, "conflicts": losers, "paths": cleaned,
                    "lost_race": True}

    return {"acquired": True, "conflicts": clash if force else [],
            "claims": rows, "expires_at": _iso(expires)}


def heartbeat(task: str, *, ttl_min: int = DEFAULT_TTL_MIN, agent: str | None = None) -> int:
    me = (agent or ME).lower()
    now = _now()
    db = _db()
    db.execute(
        'UPDATE "' + TABLE + '" SET heartbeat_at = ?, expires_at = ? '
        "WHERE agent = ? AND task = ? AND status = 'held'",
        [_iso(now), _iso(now + timedelta(minutes=ttl_min)), me, task],
        allow_unscoped=True, reason=UNSCOPED_REASON)
    db.commit()
    return len(live_claims(only_agent=me))


def release(*, task: str | None = None, session_id: str | None = None,
            agent: str | None = None) -> int:
    """Release by task or by session. SessionEnd calls the session form so a
    crashed or closed session cannot leave a repo wedged — the failure mode
    that produced 60 `working` rows against 25 `done`."""
    me = (agent or ME).lower()
    if not task and not session_id:
        raise ValueError("release needs --task or --session")
    before = [c for c in live_claims(only_agent=me)
              if (task and c["task"] == task)
              or (session_id and c.get("session_id") == session_id)]
    sql = ('UPDATE "' + TABLE + '" SET status = \'released\', released_at = ? '
           "WHERE agent = ? AND status = 'held'")
    params: list = [_iso(_now()), me]
    if task:
        sql += " AND task = ?"
        params.append(task)
    if session_id:
        sql += " AND session_id = ?"
        params.append(session_id)
    db = _db()
    db.execute(sql, params, allow_unscoped=True, reason=UNSCOPED_REASON)
    db.commit()
    return len(before)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _fmt(c: dict) -> str:
    age = ""
    try:
        mins = int((datetime.fromisoformat(c["expires_at"]) - _now()).total_seconds() // 60)
        age = f" (expires in {mins}m)"
    except Exception:  # noqa: BLE001
        pass
    br = f" branch {c['branch']}" if c.get("branch") else ""
    return (f"  {c['agent'].upper():6} {c['repo']}/{c['path_glob']}"
            f"\n         task: {c['task']}{br} · on {c['machine']}{age}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("acquire", help="take a lease on one or more paths")
    pa.add_argument("--repo", required=True)
    pa.add_argument("--paths", required=True, help="comma-separated repo-relative paths or globs")
    pa.add_argument("--task", required=True)
    pa.add_argument("--branch")
    pa.add_argument("--ttl-min", type=int, default=DEFAULT_TTL_MIN)
    pa.add_argument("--session")
    pa.add_argument("--no-strict", action="store_true",
                    help="allow claiming a path that does not exist yet")
    pa.add_argument("--force", action="store_true", help="acquire despite a peer conflict (logged)")
    pa.add_argument("--json", action="store_true")

    pc = sub.add_parser("conflicts", help="peer leases covering these paths (exit 3 if any)")
    pc.add_argument("--repo", required=True)
    pc.add_argument("--paths", required=True)
    pc.add_argument("--json", action="store_true")

    ph = sub.add_parser("heartbeat", help="extend this agent's leases for a task")
    ph.add_argument("--task", required=True)
    ph.add_argument("--ttl-min", type=int, default=DEFAULT_TTL_MIN)

    prl = sub.add_parser("release", help="release by task or session")
    prl.add_argument("--task")
    prl.add_argument("--session")

    ps = sub.add_parser("status", help="live leases")
    ps.add_argument("--repo")
    ps.add_argument("--all-agents", action="store_true")
    ps.add_argument("--json", action="store_true")

    a = p.parse_args()
    paths = [x.strip() for x in a.paths.split(",")] if getattr(a, "paths", None) else []

    if a.cmd == "acquire":
        try:
            res = acquire(a.repo, paths, a.task, branch=a.branch, ttl_min=a.ttl_min,
                          session_id=a.session, strict=not a.no_strict, force=a.force)
        except ValueError as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 2
        if a.json:
            print(json.dumps(res, indent=2, default=str))
        elif res["acquired"]:
            print(f"ACQUIRED {len(res['claims'])} lease(s) on {a.repo} until {res['expires_at']}")
            if res["conflicts"]:
                print("  WARNING --force used over a live peer lease:")
                for c in res["conflicts"]:
                    print(_fmt(c))
        else:
            print(f"CONFLICT — a peer holds {len(res['conflicts'])} of these path(s):")
            for c in res["conflicts"]:
                print(_fmt(c))
            print("\nDo not edit these. Pick other work, or ask the peer to release.")
        return 0 if res["acquired"] else 3

    if a.cmd == "conflicts":
        cl = conflicts(a.repo, paths)
        if a.json:
            print(json.dumps(cl, indent=2, default=str))
        elif cl:
            print(f"CONFLICT — {len(cl)} peer lease(s):")
            for c in cl:
                print(_fmt(c))
        else:
            print("clear — no peer lease covers those paths")
        return 3 if cl else 0

    if a.cmd == "heartbeat":
        print(f"heartbeat ok — {heartbeat(a.task, ttl_min=a.ttl_min)} live lease(s) held by {ME}")
        return 0

    if a.cmd == "release":
        try:
            n = release(task=a.task, session_id=a.session)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        print(f"released {n} lease(s)")
        return 0

    if a.cmd == "status":
        cl = live_claims(a.repo, only_agent=None if a.all_agents else ME)
        if a.json:
            print(json.dumps(cl, indent=2, default=str))
        elif not cl:
            print("(no live leases)")
        else:
            print(f"{len(cl)} live lease(s):")
            for c in cl:
                print(_fmt(c))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
