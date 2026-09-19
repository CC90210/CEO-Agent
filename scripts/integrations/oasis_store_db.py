#!/usr/bin/env python
"""Operate on the oasis-store Turso database (migrations, invites, ops reads).

    python scripts/integrations/oasis_store_db.py migrate            # apply every database/*.sql not yet in the ledger
    python scripts/integrations/oasis_store_db.py tables
    python scripts/integrations/oasis_store_db.py invite             # mint a 24h admin invite link (prints the URL)
    python scripts/integrations/oasis_store_db.py orders  [--limit 20] [--json]
    python scripts/integrations/oasis_store_db.py subs    [--json]
    python scripts/integrations/oasis_store_db.py queues  [--json]   # outbox / fulfilment / pending approvals
    python scripts/integrations/oasis_store_db.py set-status --slug <slug> --status draft|unlisted|live|retired

Same ledger shape as the app's own scripts/migrate.ts (schema_migrations: filename,
checksum, applied_at, statements) so the two paths never disagree. Checksum
mismatch on an applied file is a hard refusal — write a NEW migration.

Credentials load through lib.secret_loader and travel only as an Authorization
header. Nothing here prints a token.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.app_registry import app_dir  # noqa: E402
from lib.secret_loader import load_env  # noqa: E402

APP_SLUG = "oasis-store"
URL_KEY = "OASIS_STORE_TURSO_DATABASE_URL"
TOKEN_KEY = "OASIS_STORE_TURSO_AUTH_TOKEN"


def site_repo() -> Path:
    return app_dir(APP_SLUG)


def _endpoint_and_token() -> tuple[str, str | None]:
    env = load_env()
    url = env.get(URL_KEY)
    if not url:
        raise SystemExit(f"{URL_KEY} is not set in the agents env store (run turso_admin.py create --db oasis-store --write-env)")
    return url.replace("libsql://", "https://").rstrip("/") + "/v2/pipeline", env.get(TOKEN_KEY)


def _typed(v) -> dict:
    """A bound argument in Turso's pipeline wire format, typed rather than stringified."""
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": "1" if v else "0"}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    return {"type": "text", "value": str(v)}


def execute(statements: list[str], args_per: list[list] | None = None) -> list[dict]:
    endpoint, token = _endpoint_and_token()
    reqs = []
    for i, s in enumerate(statements):
        stmt: dict = {"sql": s}
        if args_per and args_per[i]:
            stmt["args"] = [_typed(v) for v in args_per[i]]
        reqs.append({"type": "execute", "stmt": stmt})
    reqs.append({"type": "close"})
    req = urllib.request.Request(
        endpoint,
        data=json.dumps({"requests": reqs}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "oasis-store-db/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            body = json.load(response)
    except urllib.error.HTTPError as err:
        raise SystemExit(f"HTTP {err.code} from Turso: {err.read().decode('utf-8', 'replace')[:600]}") from None
    results = body.get("results", [])
    for statement, result in zip(statements, results):
        error = (result.get("error") or {}).get("message") or ((result.get("response") or {}).get("error") or {}).get("message")
        if error:
            raise SystemExit(f"SQL failed:\n  {re.sub(r'\\s+', ' ', statement)[:120]}\n  {error}")
    return results


def rows_of(result: dict) -> list[dict]:
    payload = (result.get("response") or {}).get("result") or {}
    columns = [c.get("name") for c in payload.get("cols", [])]
    out = []
    for row in payload.get("rows", []):
        record = {}
        for name, cell in zip(columns, row):
            value = cell.get("value") if isinstance(cell, dict) else cell
            if isinstance(cell, dict) and cell.get("type") == "null":
                value = None
            record[name] = value
        out.append(record)
    return out


def query(sql: str, args: list | None = None) -> list[dict]:
    return rows_of(execute([sql], [args or []])[0])


def table(rows: list[dict], empty: str) -> None:
    if not rows:
        print(f"  {empty}")
        return
    headers = list(rows[0].keys())
    widths = [max(len(h), max((len(str(r.get(h) or "—")) for r in rows), default=0)) for h in headers]
    print("  " + "  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("  " + "  ".join("-" * w for w in widths))
    for row in rows:
        print("  " + "  ".join(str(row.get(h) or "—").ljust(w) for h, w in zip(headers, widths)))


def emit(rows: list[dict], args, empty: str) -> int:
    if getattr(args, "json", False):
        print(json.dumps(rows, indent=2))
    else:
        table(rows, empty)
    return 0


# ---------------------------------------------------------------- migrations

LEDGER_DDL = (
    "CREATE TABLE IF NOT EXISTS schema_migrations (filename TEXT PRIMARY KEY, checksum TEXT NOT NULL, "
    "applied_at TEXT NOT NULL, statements INTEGER NOT NULL)"
)


def split_statements(sql: str) -> list[str]:
    out = []
    for chunk in re.split(r";\s*$", sql, flags=re.M):
        cleaned = re.sub(r"^\s*--.*$", "", chunk, flags=re.M).strip()
        if cleaned:
            out.append(cleaned)
    return out


def cmd_migrate(args) -> int:
    folder = site_repo() / "database"
    files = sorted(p for p in folder.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files:
        raise SystemExit(f"no migrations in {folder}")
    execute([LEDGER_DDL])
    applied = {r["filename"]: r["checksum"] for r in query("SELECT filename, checksum FROM schema_migrations")}
    done = []
    for path in files:
        raw = path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        prior = applied.get(path.name)
        if prior == checksum:
            continue
        if prior and prior != checksum:
            raise SystemExit(f"{path.name} was edited after being applied (checksum mismatch). Write a NEW migration.")
        statements = split_statements(raw.decode("utf-8"))
        execute(statements)
        execute(
            ["INSERT INTO schema_migrations (filename, checksum, applied_at, statements) VALUES (?, ?, ?, ?)"],
            [[path.name, checksum, datetime.datetime.now(datetime.timezone.utc).isoformat(), len(statements)]],
        )
        done.append(f"{path.name} ({len(statements)} statements)")
    print("applied: " + ", ".join(done) if done else "up to date")
    return 0


def cmd_tables(args) -> int:
    return emit(query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"), args, "no tables")


def cmd_invite(args) -> int:
    code = secrets.token_urlsafe(24)
    digest = hashlib.sha256(code.encode()).hexdigest()
    execute(
        ["INSERT INTO admin_invites (invite_hash, expires_at) VALUES (?, datetime('now', '+1 day'))"],
        [[digest]],
    )
    origin = load_env().get("OASIS_STORE__APP_URL", "https://oasis-store.oasisaisolutions.workers.dev").rstrip("/")
    print(f"{origin}/admin/invite/{code}")
    print("(valid 24h, single use — creates the OWNER account)")
    return 0


def cmd_orders(args) -> int:
    return emit(
        query(
            "SELECT number, kind, purchase_mode, units, amount_total_cents, payment_status, fulfillment_status, "
            f"tracking_number, email, substr(created_at,1,16) AS created FROM orders WHERE payment_status != 'created' "
            f"ORDER BY created_at DESC LIMIT {int(args.limit)}"
        ),
        args,
        "no orders",
    )


def cmd_subs(args) -> int:
    return emit(
        query(
            "SELECT stripe_subscription_id, email, status, cancel_at_period_end, frequency_months, "
            "substr(current_period_end,1,10) AS period_end, paused_until, skip_next, cancellation_reason FROM subscriptions ORDER BY created_at DESC LIMIT 100"
        ),
        args,
        "no subscriptions",
    )


def cmd_queues(args) -> int:
    rows = [
        {"queue": "email_outbox queued", "n": query("SELECT COUNT(*) AS n FROM email_outbox WHERE status='queued'")[0]["n"]},
        {"queue": "email_outbox failed", "n": query("SELECT COUNT(*) AS n FROM email_outbox WHERE status='failed'")[0]["n"]},
        {"queue": "fulfillment queued/claimed", "n": query("SELECT COUNT(*) AS n FROM fulfillment_jobs WHERE state IN ('queued','claimed')")[0]["n"]},
        {"queue": "fulfillment needs_human", "n": query("SELECT COUNT(*) AS n FROM fulfillment_jobs WHERE state='needs_human'")[0]["n"]},
        {"queue": "agent_actions pending", "n": query("SELECT COUNT(*) AS n FROM agent_actions WHERE state='pending'")[0]["n"]},
        {"queue": "support_threads open", "n": query("SELECT COUNT(*) AS n FROM support_threads WHERE status IN ('open','pending_approval','escalated')")[0]["n"]},
    ]
    return emit(rows, args, "")


def cmd_seed_demo(args) -> int:
    """Run the app's own seed (scripts/seed-demo.ts) against the live DB, credentials injected.

    One source of truth for the demo content: the TypeScript seed the local-dev
    path already uses. This verb only supplies the Turso credentials the TS
    script cannot read on this machine (they live in the agents env store).
    """
    import os
    import subprocess

    sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))
    from wrangler_tool import _npx  # noqa: E402

    env = load_env()
    child = {**os.environ, URL_KEY: env[URL_KEY], TOKEN_KEY: env.get(TOKEN_KEY, "")}
    proc = subprocess.run([_npx(), "tsx", "scripts/seed-demo.ts"], cwd=str(site_repo()), env=child,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (proc.stdout + proc.stderr).strip()
    print(out[-800:] if out else "(no output)")
    return proc.returncode


def cmd_set_status(args) -> int:
    if args.status not in ("draft", "unlisted", "live", "retired"):
        raise SystemExit("status must be draft|unlisted|live|retired")
    execute(
        ["UPDATE products SET status = ?, updated_at = ? WHERE slug = ?"],
        [[args.status, datetime.datetime.now(datetime.timezone.utc).isoformat(), args.slug]],
    )
    print(f"{args.slug} → {args.status} (catalog cache refreshes within 30s)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    p = sub.add_parser("tables"); p.add_argument("--json", action="store_true")
    sub.add_parser("invite")
    sub.add_parser("seed-demo")
    p = sub.add_parser("orders"); p.add_argument("--limit", default=20); p.add_argument("--json", action="store_true")
    p = sub.add_parser("subs"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("queues"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("set-status"); p.add_argument("--slug", required=True); p.add_argument("--status", required=True)
    args = parser.parse_args(argv)
    return {
        "migrate": cmd_migrate, "tables": cmd_tables, "invite": cmd_invite, "orders": cmd_orders,
        "subs": cmd_subs, "queues": cmd_queues, "set-status": cmd_set_status, "seed-demo": cmd_seed_demo,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
