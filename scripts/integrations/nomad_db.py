#!/usr/bin/env python
"""Operate on the nomad-store Turso database (migrations, invites, ops reads).

    python scripts/integrations/nomad_db.py migrate            # apply every database/*.sql not yet in the ledger
    python scripts/integrations/nomad_db.py tables
    python scripts/integrations/nomad_db.py invite             # mint a 24h admin invite link (prints the URL)
    python scripts/integrations/nomad_db.py orders  [--limit 20] [--json]
    python scripts/integrations/nomad_db.py subs    [--json]
    python scripts/integrations/nomad_db.py queues  [--json]   # outbox / fulfilment / pending approvals
    python scripts/integrations/nomad_db.py set-status --slug <slug> --status draft|unlisted|live|retired

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

APP_SLUG = "nomad-store"
URL_KEY = "NOMAD_TURSO_DATABASE_URL"
TOKEN_KEY = "NOMAD_TURSO_AUTH_TOKEN"


def site_repo() -> Path:
    return app_dir(APP_SLUG)


def _endpoint_and_token() -> tuple[str, str | None]:
    env = load_env()
    url = env.get(URL_KEY)
    if not url:
        raise SystemExit(f"{URL_KEY} is not set in the agents env store (run turso_admin.py create --db nomad-store --write-env)")
    return url.replace("libsql://", "https://").rstrip("/") + "/v2/pipeline", env.get(TOKEN_KEY)


def execute(statements: list[str], args_per: list[list] | None = None) -> list[dict]:
    endpoint, token = _endpoint_and_token()
    reqs = []
    for i, s in enumerate(statements):
        stmt: dict = {"sql": s}
        if args_per and args_per[i]:
            stmt["args"] = [{"type": "text", "value": str(v)} if v is not None else {"type": "null"} for v in args_per[i]]
        reqs.append({"type": "execute", "stmt": stmt})
    reqs.append({"type": "close"})
    req = urllib.request.Request(
        endpoint,
        data=json.dumps({"requests": reqs}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "nomad-db/1.0"},
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
    origin = load_env().get("NOMAD_STORE__APP_URL", "https://nomad-store.oasisaisolutions.workers.dev").rstrip("/")
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
    """Seed one complete demo product (draft) so the storefront can be reviewed. Idempotent on slug."""
    import uuid

    slug = "demo-product"
    if query("SELECT id FROM products WHERE slug = ?", [slug]):
        print(f"demo product exists: /p/{slug}")
        return 0
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    pid = "prd_" + uuid.uuid4().hex[:21]
    sections = [
        ("benefits", {"heading": "Built for the daily ritual", "items": [
            {"title": "Small-batch, every month", "body": "Made in small runs and shipped fresh on your schedule, so what arrives is what it should be."},
            {"title": "One less thing to remember", "body": "You'll never run out again. It shows up before you need it, and you can skip a month in two taps."},
            {"title": "Stop whenever", "body": "Pause, skip, change frequency or cancel from your account. No calls, no forms, no guilt."}]}),
        ("how_it_works", {"heading": "How it works", "steps": [
            {"title": "Pick your plan", "body": "One, two or three — subscribe and save, or buy once."},
            {"title": "We ship it", "body": "Leaves a US warehouse within 1–3 business days with tracking."},
            {"title": "Adjust anytime", "body": "Skip, pause, change frequency, cancel — all from your account."}]}),
        ("comparison", {"heading": "Why people switch", "usLabel": "Here", "themLabel": "Elsewhere", "rows": [
            {"label": "Delivery", "us": "Monthly, free", "them": "Reorder manually"},
            {"label": "Guarantee", "us": "30 days, no return", "them": "Restocking fees"},
            {"label": "Cancel", "us": "Two taps", "them": "Phone during business hours"}]}),
        ("specs", {"heading": "What's in the box", "rows": [{"label": "Quantity", "value": "1 unit (30-day supply)"}, {"label": "Ships from", "value": "United States"}]}),
        ("guarantee", {"heading": "Love it or we make it right", "body": ""}),
        ("reviews", {"heading": "What customers say"}),
        ("faq", {"heading": "Questions", "items": [
            {"q": "How does the subscription work?", "a": "You're charged today and then the same amount monthly until you cancel. Subscribers get the lower price and free shipping."},
            {"q": "How do I cancel?", "a": "From your account in two taps, or reply 'cancel' to any email from us. No fees, no minimum term."},
            {"q": "When will it arrive?", "a": "Orders leave within 1–3 business days and typically arrive in 3–8. You get a tracking link by email."}]}),
        ("cta", {"heading": "Ready when you are", "body": "Start with one. Pause or cancel any time."}),
    ]
    tiers = [(1, "Starter", None, 3900, None, 3100, 0), (2, "Most popular", "Most popular", 6900, 7800, 5500, 1), (3, "Best value", "Save 25%", 8900, 11700, 7100, 0)]
    stmts = ["INSERT INTO products (id, slug, status, name, tagline, hero_headline, hero_subhead, hero_bullets_json, unit_label, supplier_json, created_at, updated_at) VALUES (?, ?, 'draft', ?, ?, ?, ?, ?, 'bag', ?, ?, ?)"]
    argv = [[pid, slug, "Demo Product", "A month of something good, on repeat.", "The one you'll actually keep using.",
             "A demo landing page showing every section, tier and the subscribe-and-save offer. Replace this copy with the real product.",
             json.dumps(["Ships free on subscription", "30-day guarantee, no return needed", "Pause or cancel in two taps"]),
             json.dumps({"adapter": "manual", "warehouse": "US"}), now, now]]
    for i, (t, data) in enumerate(sections):
        stmts.append("INSERT INTO product_sections (id, product_id, position, type, enabled, data_json, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)")
        argv.append(["sec_" + uuid.uuid4().hex[:21], pid, i, t, json.dumps(data), now])
    for i, (units, label, badge, one, cmp, sub, dflt) in enumerate(tiers):
        stmts.append("INSERT INTO product_tiers (id, product_id, position, units, label, badge, onetime_cents, compare_at_cents, subscribe_cents, is_default, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
        argv.append(["tier_" + uuid.uuid4().hex[:21], pid, i, units, label, badge, one, cmp, sub, dflt, now])
    for author, rating, title, body in [("Maya", 5, "Exactly what it says.", "Second month in and it just shows up. Skipped one when I was travelling — took two taps."), ("Daniel", 4, "Good, honest product.", "Quality is consistent. Wish the box were smaller, but that's a nitpick."), ("Priya", 5, "Cancelled and came back.", "Cancelled after month one because I overbought, resubscribed a month later. No drama either way.")]:
        stmts.append("INSERT INTO reviews (id, product_id, author, rating, title, body, verified, incentivized, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 'approved', ?)")
        argv.append(["rev_" + uuid.uuid4().hex[:21], pid, author, rating, title, body, now])
    execute(stmts, argv)
    print(f"seeded demo product {pid} at /p/{slug} (draft). Demo reviews are unverified placeholders — delete before launch.")
    return 0


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
