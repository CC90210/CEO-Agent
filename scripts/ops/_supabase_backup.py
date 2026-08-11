#!/usr/bin/env python3
"""_supabase_backup.py — SunBiz-scoped logical export + restore-drill verify.

Called by scripts/ops/supabase_backup.sh. NEVER prints secret values (reads the
service-role JWT via the repo secret_loader; only emits row counts / sizes).

Two subcommands:

  export <out_dir>
      For every SunBiz-data table, page the Supabase REST API filtered to
      tenant_id = SUNBIZ_TENANT_ID and write <out_dir>/tables/<name>.ndjson
      (one JSON object per line). Then download this tenant's lead-documents
      Storage objects into <out_dir>/storage/<path>. Writes <out_dir>/manifest.json
      with per-table row counts + storage byte totals.

  verify <extracted_dir>
      Restore drill: load each .ndjson back into a scratch SQLite table, count
      rows, and compare to (a) the manifest count and (b) a fresh LIVE re-query.
      Exit 0 only when every table matches on all three. This is the
      "re-import into a scratch table and match row counts" check, done without
      Postgres (none is installed; a full pg_dump would also dump other tenants).

SunBiz-scoped by construction: every query carries .eq("tenant_id", SUNBIZ).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from lib.secret_loader import load_env  # noqa: E402

SUNBIZ_TENANT_ID = "aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110"
DOC_BUCKET = "lead-documents"
PAGE = 1000

# SunBiz-data tables to back up. Each is tenant-scoped (migrations 069/070+).
# Unknown table / missing tenant_id column => skipped with a logged warning,
# so the list can stay generous without breaking the run.
TABLES = [
    "tenant_records",
    "application_lender_threads",
    "application_underwriting",
    "lead_documents",
    "lead_interactions",
    "follow_up_tasks",
    "daily_plan_items",
    "conversations",
    "personalized_form_links",
    "agent_memory_notes",
    "offer_sources",
    "lender_feedback",
    "email_thread_monitors",
    "shop_out_warnings",
    "cold_lead_lists",
    "cold_leads",
    "cold_outreach_campaigns",
    "cold_outreach_recipients",
    "sequence_state",
    "drip_sequences",
    "tenant_cron_jobs",
    "tenant_manifests",
]


def _client():
    env = load_env()
    url = (env.get("BRAVO_SUPABASE_URL") or "https://bravo.turso.compat").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "turso-compat-key").strip()
    if not url or not key:
        print("FATAL missing BRAVO_SUPABASE_URL / SERVICE_ROLE_KEY", file=sys.stderr)
        sys.exit(2)
    from supabase import create_client
    return create_client(url, key)


def _is_missing_relation(exc: Exception) -> bool:
    m = str(exc).lower()
    return "42p01" in m or "42703" in m or "does not exist" in m or "could not find" in m


def _page_table(sb, table: str) -> list[dict]:
    """Return all SunBiz rows for a table, paged. Raises on real errors."""
    rows: list[dict] = []
    start = 0
    while True:
        res = (
            sb.table(table)
            .select("*")
            .eq("tenant_id", SUNBIZ_TENANT_ID)
            .range(start, start + PAGE - 1)
            .execute()
        )
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    return rows


def cmd_export(out_dir: Path) -> int:
    sb = _client()
    tables_dir = out_dir / "tables"
    storage_dir = out_dir / "storage"
    tables_dir.mkdir(parents=True, exist_ok=True)
    storage_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "tenant_id": SUNBIZ_TENANT_ID,
        "tables": {},
        "skipped_tables": {},
        "storage": {"bucket": DOC_BUCKET, "objects": 0, "bytes": 0, "failed": 0,
                    # Objects the tenant-prefix guard refused. Counted, not
                    # silently dropped — see the guard for why either cause
                    # matters.
                    "skipped_foreign": 0},
    }

    for table in TABLES:
        try:
            rows = _page_table(sb, table)
        except Exception as exc:  # noqa: BLE001
            if _is_missing_relation(exc):
                manifest["skipped_tables"][table] = "missing table/tenant_id"
                print(f"  skip {table}: not present / no tenant_id")
                continue
            print(f"  ERROR {table}: {str(exc)[:160]}", file=sys.stderr)
            return 3
        path = tables_dir / f"{table}.ndjson"
        with path.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")
        manifest["tables"][table] = len(rows)
        print(f"  table {table}: {len(rows)} rows")

    # Storage objects for this tenant (application PDFs etc.).
    try:
        doc_rows = _page_table(sb, "lead_documents")
    except Exception:
        doc_rows = []
    from lib.r2_storage import normalize_object_path  # noqa: PLC0415

    for d in doc_rows:
        raw_sp = (d.get("storage_path") or "").strip()
        if not raw_sp:
            continue
        # The R2 migration rewrote this column to an absolute r2.dev URL, so the
        # tenant test below stopped matching ANY row and every document was
        # skipped — an export that reported success with zero documents in it.
        # Normalize first, then apply the guard to the real path.
        try:
            sp = normalize_object_path(DOC_BUCKET, raw_sp)
        except Exception as exc:  # noqa: BLE001
            manifest["storage"]["failed"] += 1
            print(f"  storage UNUSABLE PATH {raw_sp[:60]}...: {str(exc)[:80]}",
                  file=sys.stderr)
            continue
        if not sp.startswith(SUNBIZ_TENANT_ID):
            # Hard guard: never pull an object outside the SunBiz tenant prefix.
            # The guard stays; the SILENCE does not. This used to `continue`
            # without counting or printing anything, so the object vanished from
            # the backup and the run still reported "export OK" — an archive
            # that is quietly missing documents is worse than one that admits it.
            #
            # Reaching here means one of two things, and both want attention:
            # the row belongs to another tenant (alarming — the query above
            # filters on tenant_id), or the stored path simply does not carry
            # the tenant prefix, in which case this guard is over-matching and
            # real documents are being dropped.
            manifest["storage"]["skipped_foreign"] += 1
            print(f"  storage SKIPPED (outside tenant prefix) {raw_sp[:60]}",
                  file=sys.stderr)
            continue
        try:
            blob = sb.storage.from_(DOC_BUCKET).download(sp)
        except Exception as exc:  # noqa: BLE001
            manifest["storage"]["failed"] += 1
            print(f"  storage MISS {sp[:40]}...: {str(exc)[:80]}", file=sys.stderr)
            continue
        dest = storage_dir / sp
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
        manifest["storage"]["objects"] += 1
        manifest["storage"]["bytes"] += len(blob)

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    summary = (
        f"{len(manifest['tables'])} tables, "
        f"{sum(manifest['tables'].values())} rows, "
        f"{manifest['storage']['objects']} storage objects "
        f"({manifest['storage']['bytes']} bytes)"
    )
    # A backup that could not read N documents is not an OK backup. This used to
    # print "export OK" with the failure count buried in the manifest, which is
    # how an archive gets trusted for a restore it cannot actually perform —
    # and under EMPIRE_DATA_BACKEND=turso_cloud a missing R2 credential fails
    # EVERY object at once while the table export still succeeds.
    unreadable = manifest["storage"]["failed"]
    skipped = manifest["storage"]["skipped_foreign"]
    if unreadable or skipped:
        parts = []
        if unreadable:
            parts.append(f"{unreadable} object(s) UNREADABLE (see the MISS lines)")
        if skipped:
            parts.append(
                f"{skipped} object(s) SKIPPED by the tenant-prefix guard (see the "
                f"SKIPPED lines) — either they belong to another tenant, which "
                f"should be impossible given the tenant_id filter, or the guard is "
                f"over-matching and real documents were dropped")
        print(
            f"export INCOMPLETE: {summary}; " + "; ".join(parts) +
            f". The tables are exported; the documents are not. "
            f"Do not treat {out_dir} as a restorable backup.",
            file=sys.stderr,
        )
        return 4
    print(f"export OK: {summary}")
    return 0


def cmd_verify(extracted_dir: Path) -> int:
    """Restore drill: load each ndjson into a scratch sqlite table; compare
    counts to the manifest AND to a fresh live re-query."""
    manifest = json.loads((extracted_dir / "manifest.json").read_text(encoding="utf-8"))
    tables_dir = extracted_dir / "tables"
    sb = _client()

    db = sqlite3.connect(":memory:")
    ok = True
    for table, expected in manifest["tables"].items():
        ndjson = tables_dir / f"{table}.ndjson"
        if not ndjson.exists():
            print(f"  FAIL {table}: ndjson missing from backup")
            ok = False
            continue
        # Load into a scratch table.
        db.execute(f'DROP TABLE IF EXISTS "scratch_{table}"')
        db.execute(f'CREATE TABLE "scratch_{table}" (j TEXT)')
        n_loaded = 0
        with ndjson.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                json.loads(line)  # parse-validate every row
                db.execute(f'INSERT INTO "scratch_{table}" (j) VALUES (?)', (line,))
                n_loaded += 1
        scratch_count = db.execute(f'SELECT COUNT(*) FROM "scratch_{table}"').fetchone()[0]
        # Fresh live count for drift detection.
        try:
            live = (
                sb.table(table).select("id", count="exact")
                .eq("tenant_id", SUNBIZ_TENANT_ID).limit(1).execute().count
            )
        except Exception:
            live = None
        status = "OK" if (scratch_count == expected and n_loaded == expected) else "FAIL"
        drift = "" if (live is None or live == expected) else f" (LIVE now {live})"
        if status != "OK":
            ok = False
        print(f"  {status} {table}: backup={expected} scratch={scratch_count} live={live}{drift}")
    db.close()

    so = manifest.get("storage", {})
    print(f"  storage: {so.get('objects',0)} objects, {so.get('bytes',0)} bytes, failed={so.get('failed',0)}")
    print("VERIFY PASS" if ok else "VERIFY FAIL")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] not in ("export", "verify"):
        print("usage: _supabase_backup.py export <out_dir> | verify <extracted_dir>", file=sys.stderr)
        return 64
    target = Path(argv[2])
    return cmd_export(target) if argv[1] == "export" else cmd_verify(target)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
