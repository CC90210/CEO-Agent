"""Database restore-point tool — the enforcer behind V9.0 Defense #5.

WHY THIS EXISTS. Defense #5 said "name a verified restore point before a
destructive schema change" and pointed at nothing runnable, because
`apply_migration.py` states in its own source that its BLOCKED_PATTERNS guard
"is a client-side guard, not a substitute for backups". A defense you cannot
execute is a sentence, not a gate. This makes it a command with an exit code.

WHAT IT IS — HONESTLY. A **logical** snapshot: every table's column set and its
exact row count, checksummed, plus optional row export (`--rows`). That is
enough to (a) prove a baseline existed before a migration and (b) detect what a
migration actually changed — table dropped, column vanished, rows deleted. It
is NOT a byte-level backup: full point-in-time restore is Supabase PITR, which
lives in the dashboard and cannot be driven from here. `verify` says exactly
which of the two you have; it never implies more coverage than it captured.

CLI:
  python scripts/db_snapshot.py create                       # counts + schema
  python scripts/db_snapshot.py create --name pre-0061 --rows 500
  python scripts/db_snapshot.py create --rows all --project oasis
  python scripts/db_snapshot.py verify                       # newest snapshot
  python scripts/db_snapshot.py verify --max-age-hours 2 --strict --json

Gate usage (the point of the tool):
  python scripts/db_snapshot.py create --name pre-0061 && \
  python scripts/db_snapshot.py verify --max-age-hours 1 && \
  python scripts/apply_migration.py database/0061_thing.sql
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = PROJECT_ROOT / "tmp" / "snapshots"
SNAPSHOT_VERSION = 1
DEFAULT_MAX_AGE_HOURS = 24
ROW_PAGE = 1000
MAX_ROWS_PER_TABLE = 50_000

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

CAPABILITY_META = {
    "category": "data.supabase",
    "lifecycle": "active",
    # Reads the DB, writes only a local snapshot file — never mutates Supabase.
    "risk": "local_write",
    "triggers": [
        "database snapshot",
        "restore point before migration",
        "verify database backup",
        "schema baseline",
    ],
    "owner": "bravo",
    "project": "empire",
    "bridge": {
        "visible": True,
        "confirm": False,
        "subcommands": {
            "create": {"key": "db_snapshot_create", "visible": True, "confirm": False},
            "verify": {"key": "db_snapshot_verify", "visible": True, "confirm": False},
        },
    },
}


# ── helpers ──────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _git_commit() -> str:
    """The commit the snapshot was taken at — so a restore knows which schema
    the counts belong to. Best-effort; a missing git is not a snapshot failure."""
    try:
        from _subprocess_helpers import WINDOWLESS_FLAGS
    except ImportError:
        WINDOWLESS_FLAGS = 0
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10, cwd=str(PROJECT_ROOT),
            encoding="utf-8", errors="replace", creationflags=WINDOWLESS_FLAGS,
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _checksum(payload: dict) -> str:
    """sha256 over the payload with the checksum field itself excluded, so a
    truncated or hand-edited snapshot fails verification instead of passing."""
    body = {k: v for k, v in payload.items() if k != "content_sha256"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
        .encode("utf-8")
    ).hexdigest()


def _supabase():
    """Import the shared client factory. Kept lazy so `verify --no-live` and
    `--help` work on a box with no supabase package installed."""
    sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))
    import supabase_tool  # noqa: E402
    return supabase_tool


def discover_schema(url: str, key: str) -> dict[str, dict]:
    """Table → {"columns": [...], "pk": [...]}, from PostgREST's OpenAPI root.

    The primary key matters for more than documentation: paginated row export
    without a stable sort can repeat or skip rows between pages, which would
    hand back a silently corrupt export. PostgREST marks key columns with a
    `<pk/>` tag in the property description.

    Raises RuntimeError on failure. A snapshot that silently captured zero
    tables would be the worst possible outcome here — it would verify clean and
    protect nothing.
    """
    import requests

    resp = requests.get(
        f"{url.rstrip('/')}/rest/v1/",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"PostgREST schema root returned HTTP {resp.status_code} — cannot "
            f"enumerate tables, refusing to write a partial snapshot"
        )
    spec = resp.json()
    definitions = spec.get("definitions") or {}
    schema: dict[str, dict] = {}
    for table, body in definitions.items():
        props = body.get("properties") or {}
        schema[table] = {
            "columns": sorted(props.keys()),
            "pk": sorted(c for c, p in props.items()
                         if "<pk/>" in (p.get("description") or "")),
        }
    if not schema:
        # Fall back to paths (older PostgREST emits paths without definitions).
        schema = {
            p.strip("/"): {"columns": [], "pk": []}
            for p in (spec.get("paths") or {})
            if p not in ("/",) and not p.startswith("/rpc/")
        }
    if not schema:
        raise RuntimeError("PostgREST returned no tables — refusing to write an "
                           "empty snapshot that would verify clean")
    return schema


def _count(client, table: str) -> int:
    res = client.table(table).select("*", count="exact").limit(0).execute()
    if res.count is None:
        raise RuntimeError(f"{table}: exact count unavailable")
    return int(res.count)


def _fetch_rows(client, table: str, want: int,
                order_by: str | None = None) -> tuple[list[dict], bool]:
    """Return (rows, truncated). `want` <= 0 means none; MAX_ROWS_PER_TABLE caps
    an --rows all request so one huge table cannot fill the disk.

    `order_by` (the primary key) pins a stable sort across pages. Without it
    Postgres may return rows in a different order per page, so a paginated
    export can duplicate and skip rows — a corrupt export that looks fine.
    """
    if want <= 0:
        return [], False
    cap = min(want, MAX_ROWS_PER_TABLE)
    rows: list[dict] = []
    offset = 0
    while len(rows) < cap:
        page = min(ROW_PAGE, cap - len(rows))
        q = client.table(table).select("*")
        if order_by:
            q = q.order(order_by)
        res = q.range(offset, offset + page - 1).execute()
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < page:
            return rows, False
        offset += page
    return rows, True


# ── create ───────────────────────────────────────────────────────────────────

def cmd_create(args) -> int:
    args.project = args.project or "bravo"
    supabase_tool = _supabase()
    env = supabase_tool.load_env()
    config = supabase_tool.PROJECTS.get(args.project)
    if not config:
        print(f"ERROR: unknown project '{args.project}'. "
              f"Options: {sorted(supabase_tool.PROJECTS)}", file=sys.stderr)
        return 2
    url = env.get(config["url_key"])
    key = env.get(config["key_key"])
    if not url or not key:
        print(f"ERROR: missing {config['url_key']} / {config['key_key']} in "
              f".env.agents — run `python scripts/capability_probe.py check supabase`",
              file=sys.stderr)
        return 2

    # Parse --rows strictly (Codex [P2], 2026-08-02). An earlier draft mapped
    # any negative number to MAX_ROWS_PER_TABLE, so the typo `--rows -1` quietly
    # meant "export everything" — 50k production rows per table written
    # unencrypted to disk by a command the operator thought was a no-op.
    if args.rows == "all":
        want_rows = MAX_ROWS_PER_TABLE
    else:
        try:
            want_rows = int(args.rows)
        except (TypeError, ValueError):
            print(f"ERROR: --rows must be 0, a positive integer, or 'all' "
                  f"(got {args.rows!r})", file=sys.stderr)
            return 2
        if want_rows < 0:
            print(f"ERROR: --rows cannot be negative (got {want_rows}). Use 'all' "
                  f"to export up to {MAX_ROWS_PER_TABLE} rows per table.",
                  file=sys.stderr)
            return 2
    if want_rows:
        print(f"[db_snapshot] --rows {args.rows}: real row data will be written "
              f"UNENCRYPTED to {SNAPSHOT_DIR}. Treat the file as production data.",
              file=sys.stderr)

    try:
        schema = discover_schema(url, key)
    except Exception as exc:  # noqa: BLE001 — fail loud, never write a fake baseline
        print(f"ERROR: schema discovery failed: {exc}", file=sys.stderr)
        return 2

    client = supabase_tool.get_client(env, args.project)

    tables: dict[str, dict] = {}
    errors: list[str] = []
    for table, meta in sorted(schema.items()):
        columns = meta.get("columns") or []
        pk = meta.get("pk") or []
        entry: dict = {"columns": columns, "column_count": len(columns), "pk": pk}
        try:
            entry["row_count"] = _count(client, table)
        except Exception as exc:  # noqa: BLE001
            entry["row_count"] = None
            entry["error"] = str(exc)[:300]
            errors.append(f"{table}: {exc}")
        if want_rows and entry.get("row_count"):
            order_by = pk[0] if pk else None
            try:
                rows, truncated = _fetch_rows(client, table, want_rows, order_by)
                entry["rows"] = rows
                entry["rows_captured"] = len(rows)
                entry["rows_truncated"] = truncated
                # A multi-page export with no stable sort can duplicate/skip
                # rows. Record it rather than pretend the export is exact.
                entry["rows_ordered_by"] = order_by
                if order_by is None and len(rows) > ROW_PAGE:
                    errors.append(f"{table}: paginated export with no primary key "
                                  f"to sort by — export may be inexact")
            except Exception as exc:  # noqa: BLE001
                entry["error"] = f"{entry.get('error', '')} rows: {exc}".strip()[:300]
                errors.append(f"{table} rows: {exc}")
        tables[table] = entry

    counted = [t for t in tables.values() if t.get("row_count") is not None]
    payload = {
        "snapshot_version": SNAPSHOT_VERSION,
        "created_at": _now().isoformat(),
        "project": args.project,
        "label": args.name or "",
        "git_commit": _git_commit(),
        "complete": not errors,
        "errors": errors,
        "table_count": len(tables),
        "total_rows": sum(t["row_count"] for t in counted),
        "rows_captured": bool(want_rows) and any("rows" in t for t in tables.values()),
        "restore_scope": (
            "logical: schema + exact row counts"
            + (" + exported rows" if want_rows else "")
            + ". Byte-level point-in-time restore is Supabase PITR (dashboard), "
              "not this file."
        ),
        "tables": tables,
    }
    payload["content_sha256"] = _checksum(payload)

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _now().strftime("%Y%m%dT%H%M%SZ")
    # The project is IN THE FILENAME (Codex [P2], 2026-08-02) so a lookup for
    # the newest snapshot can be scoped without reading every file — otherwise
    # a fresh `oasis` snapshot satisfies a `bravo` pre-migration gate.
    path = SNAPSHOT_DIR / f"{stamp}_{args.project}_db_snapshot.json"
    # Never overwrite (Codex [P2], 2026-08-02). Two `create` runs in the same
    # second — routine in a scripted gate, or a rerun with different --rows —
    # would otherwise silently destroy the earlier restore-point evidence.
    n = 2
    while path.exists():
        path = SNAPSHOT_DIR / f"{stamp}-{n}_{args.project}_db_snapshot.json"
        n += 1
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    if args.output_json:
        print(json.dumps({
            "ok": payload["complete"], "path": str(path),
            "project": args.project, "tables": payload["table_count"],
            "total_rows": payload["total_rows"], "errors": errors,
        }, indent=2))
    else:
        print(f"Snapshot written: {path}")
        print(f"  project     : {args.project} @ {payload['git_commit']}")
        print(f"  tables      : {payload['table_count']}")
        print(f"  total rows  : {payload['total_rows']}")
        print(f"  rows exported: {'yes' if payload['rows_captured'] else 'no (counts only)'}")
        print(f"  scope       : {payload['restore_scope']}")
        if errors:
            print(f"  INCOMPLETE  : {len(errors)} table(s) failed — this is NOT a "
                  f"restore point:", file=sys.stderr)
            for e in errors[:10]:
                print(f"    - {e}", file=sys.stderr)

    # A partial snapshot must never exit 0 — that is precisely how a migration
    # gets applied against a baseline nobody actually captured.
    return 0 if payload["complete"] else 1


# ── verify ───────────────────────────────────────────────────────────────────

def _latest_snapshot(project: str) -> Path | None:
    """Newest snapshot FOR THIS PROJECT. Scoping matters: a Bravo pre-migration
    gate satisfied by a fresh OASIS snapshot is a gate that passes while no
    Bravo baseline exists at all."""
    if not SNAPSHOT_DIR.exists():
        return None
    # By mtime, not by name: the same-second collision suffix makes lexical
    # order unreliable within a second, and "newest" is what the gate means.
    files = sorted(SNAPSHOT_DIR.glob(f"*_{project}_db_snapshot.json"),
                   key=lambda p: (p.stat().st_mtime, p.name))
    if files:
        return files[-1]
    # Pre-2026-08-02 snapshots have no project in the filename — fall back to
    # reading the payload so an in-flight baseline still verifies.
    legacy = []
    for candidate in sorted(SNAPSHOT_DIR.glob("*_db_snapshot.json")):
        try:
            if json.loads(candidate.read_text(encoding="utf-8")).get("project") == project:
                legacy.append(candidate)
        except (OSError, json.JSONDecodeError):
            continue
    return legacy[-1] if legacy else None


def cmd_verify(args) -> int:
    project = args.project or "bravo"
    path = Path(args.file) if args.file else _latest_snapshot(project)
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> bool:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    if path is None or not path.exists():
        check("snapshot_exists", False,
              f"no '{project}' snapshot in {SNAPSHOT_DIR} — run "
              f"`python scripts/db_snapshot.py create --project {project}`")
        return _report(checks, None, args)
    check("snapshot_exists", True, str(path))

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        check("snapshot_parses", False, f"{type(exc).__name__}: {exc}")
        return _report(checks, None, args)
    check("snapshot_parses", True, f"snapshot_version={payload.get('snapshot_version')}")

    check("checksum_matches", payload.get("content_sha256") == _checksum(payload),
          "sha256 over the payload — a truncated or edited file fails here")

    # Explicit --project must match what the file actually captured. Catches
    # the --file case too: pointing the gate at another database's baseline.
    if args.project:
        check("project_matches", payload.get("project") == args.project,
              f"snapshot project={payload.get('project')!r}, requested={args.project!r}")

    check("capture_complete", bool(payload.get("complete")),
          f"{len(payload.get('errors') or [])} table error(s) at capture time")

    created = payload.get("created_at")
    age_h = None
    if created:
        try:
            age_h = (_now() - datetime.fromisoformat(created)).total_seconds() / 3600
        except ValueError:
            pass
    check("fresh_enough", age_h is not None and age_h <= args.max_age_hours,
          f"age {age_h:.1f}h (limit {args.max_age_hours}h)" if age_h is not None
          else "created_at unparseable")

    drift: list[dict] = []
    if not args.no_live:
        try:
            supabase_tool = _supabase()
            env = supabase_tool.load_env()
            client = supabase_tool.get_client(env, payload.get("project") or project)
            missing: list[str] = []
            for table, entry in (payload.get("tables") or {}).items():
                before = entry.get("row_count")
                if before is None:
                    continue
                try:
                    now_count = _count(client, table)
                except Exception as exc:  # noqa: BLE001
                    missing.append(table)
                    drift.append({"table": table, "before": before,
                                  "now": None, "error": str(exc)[:200]})
                    continue
                if now_count != before:
                    drift.append({"table": table, "before": before,
                                  "now": now_count, "delta": now_count - before})
            check("live_reachable", True, f"{len(payload.get('tables') or {})} tables re-queried")
            # DEFAULT-ON (Codex [P2], 2026-08-02). A captured table that is now
            # unreadable means the live schema no longer matches the baseline —
            # which is precisely the state this gate exists to catch. Printing
            # "VERIFIED RESTORE POINT" there, and only blocking if the caller
            # happened to know about a --strict flag, is a gate that fails open.
            if missing and not args.allow_missing_tables:
                check("no_tables_vanished", False,
                      f"unreadable since capture: {missing} — baseline no longer "
                      f"matches the live schema (pass --allow-missing-tables if "
                      f"the drop was intentional)")
            else:
                check("no_tables_vanished", True,
                      f"waived for {missing}" if missing else "all captured tables still present")
        except Exception as exc:  # noqa: BLE001
            check("live_reachable", False, f"{type(exc).__name__}: {exc}")

    return _report(checks, payload, args, drift=drift, path=path)


def _report(checks: list[dict], payload: dict | None, args,
            drift: list[dict] | None = None, path: Path | None = None) -> int:
    ok = all(c["ok"] for c in checks)
    drift = drift or []
    if args.output_json:
        print(json.dumps({
            "ok": ok,
            "snapshot": str(path) if path else None,
            "restore_scope": (payload or {}).get("restore_scope"),
            "checks": checks,
            "drift": drift,
        }, indent=2))
    else:
        print("Restore-point verification")
        for c in checks:
            print(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['check']}: {c['detail']}")
        if payload:
            print(f"  scope: {payload.get('restore_scope')}")
            if not payload.get("rows_captured"):
                print("  NOTE: counts only — for a destructive change, confirm the "
                      "Supabase PITR window covers this timestamp before applying.")
        if drift:
            print(f"  drift since capture ({len(drift)} table(s)):")
            # ASCII arrow on purpose: U+2192 is absent from cp1252 and crashed
            # the real Windows console the first time drift was non-empty.
            # Tests capture in utf-8, so only the live run ever saw it.
            for d in drift[:15]:
                print(f"    - {d['table']}: {d['before']} -> {d.get('now')}")
        print(f"VERDICT: {'VERIFIED RESTORE POINT' if ok else 'NO VERIFIED RESTORE POINT'}")
    return 0 if ok else 1


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    # The Windows console defaults to cp1252; any non-ASCII in a diagnostic
    # would raise UnicodeEncodeError and take the whole gate down mid-report.
    # A restore-point check must not die on its own output.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    p = argparse.ArgumentParser(
        description="Create and verify database restore points (V9.0 Defense #5)")
    sub = p.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", default=None,
                        help="Supabase project key from supabase_tool.PROJECTS (default: bravo). "
                             "On verify, an explicit value must match the snapshot's own project")
    common.add_argument("--json", dest="output_json", action="store_true",
                        help="Machine-readable output")

    c = sub.add_parser("create", parents=[common], help="Capture a restore point")
    c.add_argument("--name", help="Label for this snapshot (e.g. pre-0061)")
    c.add_argument("--rows", default="0",
                   help="Rows to export per table: 0 (default, counts only), N, or 'all' "
                        f"(capped at {MAX_ROWS_PER_TABLE}/table)")

    v = sub.add_parser("verify", parents=[common], help="Gate: is there a usable restore point?")
    v.add_argument("--file", help="Verify this snapshot instead of the newest")
    v.add_argument("--max-age-hours", type=float, default=DEFAULT_MAX_AGE_HOURS,
                   help=f"Fail if the snapshot is older (default {DEFAULT_MAX_AGE_HOURS})")
    v.add_argument("--no-live", action="store_true",
                   help="Skip the live re-query (offline integrity check only)")
    v.add_argument("--allow-missing-tables", action="store_true",
                   help="Downgrade a vanished/unreadable captured table from a gate "
                        "failure to a note (use when the drop was intentional)")

    args = p.parse_args()
    if args.command == "create":
        return cmd_create(args)
    return cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main())
