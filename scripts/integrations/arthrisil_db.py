#!/usr/bin/env python
"""Operate on the Arthrisil Turso database (leads, orders, subscriptions).

    python scripts/integrations/arthrisil_db.py migrate database/0004_subscriptions.sql
    python scripts/integrations/arthrisil_db.py tables
    python scripts/integrations/arthrisil_db.py orders   [--limit 20] [--json]
    python scripts/integrations/arthrisil_db.py subs     [--json]
    python scripts/integrations/arthrisil_db.py churn    [--json]

WHY THIS EXISTS. Migrations 0003 and 0004 were applied by a throwaway script in
a temp directory — which worked, and then would have evaporated, leaving the
repo with no runnable way to apply a migration. The site's own
`scripts/migrate.ts` reads `.env.local`, which is the LOCAL DEV path and is not
populated on this machine; the credentials live in the agents env store. So the
ops path belongs here, committed, next to the Stripe provisioner.

`churn` exists for the opposite reason. 0004 added a retention worklist —
subscriptions cancelling inside their paid period that have not yet been offered
anything — behind a partial index. A table nobody can read is a table that is
not really there, and the whole point of recording a cancellation is to be able
to act on it before the period ends.

Credentials load through lib.secret_loader and are sent only as an Authorization
header. Nothing here prints a token.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.secret_loader import load_env  # noqa: E402

SITE_REPO = Path(r"C:\Users\User\APPS\arthrisil-website")


def _endpoint_and_token() -> tuple[str, str | None]:
    env = load_env()
    url = env.get("ARTHRISIL_TURSO_DATABASE_URL")
    if not url:
        raise SystemExit("ARTHRISIL_TURSO_DATABASE_URL is not set in the agents env store")
    endpoint = url.replace("libsql://", "https://").rstrip("/") + "/v2/pipeline"
    return endpoint, env.get("ARTHRISIL_TURSO_AUTH_TOKEN")


def execute(statements: list[str]) -> list[dict]:
    """Run statements in order over Turso's HTTP pipeline API."""
    endpoint, token = _endpoint_and_token()
    payload = {"requests": [{"type": "execute", "stmt": {"sql": s}} for s in statements]}
    payload["requests"].append({"type": "close"})
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "arthrisil-db/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            body = json.load(response)
    except urllib.error.HTTPError as err:
        raise SystemExit(
            f"HTTP {err.code} from Turso: {err.read().decode('utf-8', 'replace')[:600]}"
        ) from None

    results = body.get("results", [])
    for statement, result in zip(statements, results):
        error = (result.get("error") or {}).get("message") or (
            (result.get("response") or {}).get("error") or {}
        ).get("message")
        if error:
            raise SystemExit(f"SQL failed:\n  {re.sub(r'\\s+', ' ', statement)[:120]}\n  {error}")
    return results


def rows_of(result: dict) -> list[dict]:
    """Turso's pipeline result -> list of dicts, decoding its typed cells."""
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


def query(sql: str) -> list[dict]:
    return rows_of(execute([sql])[0])


def table(rows: list[dict], empty: str) -> None:
    if not rows:
        print(f"  {empty}")
        return
    headers = list(rows[0].keys())
    widths = [
        max(len(h), max((len(str(r.get(h) or "—")) for r in rows), default=0))
        for h in headers
    ]
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


# -------------------------------------------------------------------- commands

LEDGER_DDL = (
    'CREATE TABLE IF NOT EXISTS "schema_migrations" ('
    '"filename" TEXT PRIMARY KEY, "checksum" TEXT NOT NULL, '
    '"applied_at" TEXT NOT NULL, "statements" INTEGER NOT NULL)'
)


def cmd_migrate(args) -> int:
    path = Path(args.file)
    if not path.is_absolute():
        path = SITE_REPO / path
    if not path.exists():
        raise SystemExit(f"not found: {path}")

    # The database already keeps a ledger — 0001 and 0002 are in it with a
    # SHA256 of the file's raw bytes. Applying a migration without recording it
    # leaves the ledger claiming a schema that is not what is deployed, which is
    # worse than having no ledger: the next person trusts it. (0003 and 0004
    # were applied by a throwaway script and went unrecorded; running them
    # through here backfills them, since every statement is IF NOT EXISTS.)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    execute([LEDGER_DDL])
    recorded = query(
        "SELECT checksum, applied_at, statements FROM schema_migrations "
        f"WHERE filename = '{path.name}'"
    )
    if recorded:
        previous = recorded[0]
        if previous["checksum"] == checksum:
            print(f"{path.name} already applied {previous['applied_at']} "
                  f"({previous['statements']} statements) — nothing to do.")
            return 0
        raise SystemExit(
            f"{path.name} is in the ledger with a DIFFERENT checksum.\n"
            f"  applied : {previous['checksum']} at {previous['applied_at']}\n"
            f"  on disk : {checksum}\n"
            "The file changed after it was applied, so what ran and what this file "
            "now says are not the same thing. Write a NEW migration rather than "
            "editing an applied one."
        )

    text = path.read_text(encoding="utf-8")
    # Split on end-of-line semicolons and strip comment lines. Sufficient for the
    # DDL in this repo (no triggers, no BEGIN...END); it is not a SQL parser and
    # does not pretend to be.
    statements = [
        s
        for s in (
            re.sub(r"^\s*--.*$", "", part, flags=re.M).strip()
            for part in re.split(r";\s*$", text, flags=re.M)
        )
        if s
    ]
    print(f"file  : {path.name}")
    print(f"stmts : {len(statements)}\n")
    execute(statements)
    for statement in statements:
        print(f"  ok  {re.sub(r'\\s+', ' ', statement)[:70]}")

    applied_at = (
        datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    )
    execute([
        "INSERT INTO schema_migrations (filename, checksum, applied_at, statements) "
        f"VALUES ('{path.name}', '{checksum}', '{applied_at}', {len(statements)})"
    ])
    print(f"\nApplied and recorded: {path.name}  {checksum[:12]}…  {applied_at}")
    return 0


def cmd_tables(args) -> int:
    rows = query(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return emit(rows, args, "no tables")


def cmd_orders(args) -> int:
    rows = query(
        "SELECT created_at, plan, quantity, amount_total_cents, currency, "
        "       email, payment_status "
        f"FROM arthrisil_orders ORDER BY created_at DESC LIMIT {int(args.limit)}"
    )
    return emit(rows, args, "no orders yet")


def cmd_subs(args) -> int:
    rows = query(
        "SELECT status, cancel_at_period_end, COUNT(*) AS n "
        "FROM arthrisil_subscriptions GROUP BY status, cancel_at_period_end "
        "ORDER BY n DESC"
    )
    return emit(rows, args, "no subscriptions yet")


def cmd_churn(args) -> int:
    """The retention worklist: cancelling, still paid up, not yet offered anything.

    This is the query the partial index in 0004 exists for. Every row is a
    customer who can still be kept — once their current_period_end passes, they
    are gone and this is just a report.
    """
    rows = query(
        "SELECT stripe_subscription_id, email, canceled_at, current_period_end, "
        "       cancellation_reason, cancellation_comment "
        "FROM arthrisil_subscriptions "
        "WHERE cancel_at_period_end = 1 AND retention_offer_sent_at IS NULL "
        "ORDER BY current_period_end ASC"
    )
    if not getattr(args, "json", False) and rows:
        print(f"{len(rows)} subscription(s) cancelling with no retention offer sent:\n")
    return emit(rows, args, "nobody is mid-cancellation — nothing to win back")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    migrate = sub.add_parser("migrate", parents=[common], help="apply a .sql file")
    migrate.add_argument("file", help="path, absolute or relative to the site repo")

    sub.add_parser("tables", parents=[common], help="list tables")
    orders = sub.add_parser("orders", parents=[common], help="recent orders")
    orders.add_argument("--limit", default=20)
    sub.add_parser("subs", parents=[common], help="subscription counts by status")
    sub.add_parser("churn", parents=[common], help="retention worklist")

    args = parser.parse_args()
    return {
        "migrate": cmd_migrate,
        "tables": cmd_tables,
        "orders": cmd_orders,
        "subs": cmd_subs,
        "churn": cmd_churn,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
