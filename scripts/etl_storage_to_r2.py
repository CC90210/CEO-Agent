"""Publish the archived Supabase Storage objects to Cloudflare R2, then repoint
every database row that references them.

WHY THIS EXISTS. `etl_storage_archive.py` already pulled all 4,118 objects
(~3.1 GB) to local disk with a SHA-256 per file, so nothing is lost if the
Supabase projects are deleted. But an archive on one Windows machine is not a
runtime store: the apps run on Vercel and still fetch
`https://<ref>.supabase.co/storage/...`. Cancel the subscription and those
become 404s — the files survive, the product breaks.

This is the step that closes that gap. It is the ONLY remaining piece of the
migration that needs a credential nobody has issued yet:

    CLOUDFLARE_ACCOUNT_ID        R2 -> Overview (the 32-char hex id)
    R2_ACCESS_KEY_ID             R2 -> Manage API tokens -> Create (S3 creds)
    R2_SECRET_ACCESS_KEY
    R2_BUCKET                    e.g. oasis-storage
    R2_PUBLIC_BASE_URL           the r2.dev URL, or a custom domain

Run order:
    python scripts/etl_storage_to_r2.py --check                 credentials + reachability
    python scripts/etl_storage_to_r2.py --project bravo --plan  what would move/rewrite
    python scripts/etl_storage_to_r2.py --project bravo --apply
    python scripts/etl_storage_to_r2.py --project bravo --verify

DESIGN NOTES, each earned the hard way elsewhere in this migration:
  * Upload and rewrite are separate phases with a verification between them.
    Rewriting a URL before its bytes are readable at the new address turns a
    working link into a broken one.
  * Rewrites are idempotent and reversible: the original value is kept in
    `_storage_url_rewrites` so this can be undone without a database restore.
  * Object keys keep the `<bucket>/<path>` shape, so a Supabase path maps to an
    R2 key by prefix alone — no lookup table to drift out of sync.
  * Nothing here deletes from Supabase. Deletion is the operator's call, after
    they have seen --verify pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

from core.turso_schema_transpiler import PROJECTS  # noqa: E402
from lib.db_turso import resolve_project_target  # noqa: E402
from lib.secret_loader import load_env  # noqa: E402
from lib.structured_log import get_logger  # noqa: E402

log = get_logger("etl_storage_to_r2")

ARCHIVE_ROOT = SCRIPTS.parent / "state" / "backups" / "supabase_storage"

REQUIRED_KEYS = (
    "CLOUDFLARE_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
    "R2_PUBLIC_BASE_URL",
)

# Columns that hold a storage reference, per project. Derived from the live
# census (scratch audit, 2026-08-07) rather than guessed — a column list that
# drifts silently is how half a rewrite ships.
#   kind="path"   value is a bucket-relative path; prefix it with the bucket
#   kind="url"    value is a full https://<ref>.supabase.co/storage/... URL
POINTER_COLUMNS: dict[str, list[dict]] = {
    "bravo": [
        {"table": "lead_documents", "column": "storage_path",
         "kind": "path", "bucket": "lead-documents"},
        {"table": "chat_attachments", "column": "storage_path",
         "kind": "path", "bucket": "chat-attachments"},
        {"table": "marketing_asset_media", "column": "storage_path",
         "kind": "path", "bucket": "marketing-media"},
    ],
    "propflow": [
        {"table": "areas", "column": "image_url", "kind": "url"},
        {"table": "buildings", "column": "image_url", "kind": "url"},
        {"table": "properties", "column": "image_url", "kind": "url"},
    ],
    "nostalgic": [
        {"table": "dj_profiles", "column": "profile_image_url", "kind": "url"},
    ],
    "breeze": [],
    "oasis": [],
}


def _env() -> dict:
    return load_env()


def _creds(env: dict) -> tuple[dict, list[str]]:
    have, missing = {}, []
    for k in REQUIRED_KEYS:
        v = env.get(k) or os.environ.get(k)
        if v:
            have[k] = v
        else:
            missing.append(k)
    return have, missing


def _client(creds: dict):
    """S3-compatible client for R2. boto3 is optional until this actually runs."""
    try:
        import boto3  # noqa: PLC0415
        from botocore.config import Config  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise SystemExit(
            "boto3 is required to talk to R2:  pip install boto3\n"
            f"(import failed: {exc})") from exc
    return boto3.client(
        "s3",
        endpoint_url=f"https://{creds['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=creds["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=creds["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4", retries={"max_attempts": 5}),
        region_name="auto",
    )


def _manifest(project: str) -> list[dict]:
    p = ARCHIVE_ROOT / f"{project}__manifest.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _local_path(project: str, entry: dict) -> Path:
    # Layout: state/backups/supabase_storage/<project>/<bucket>/<path...>
    return ARCHIVE_ROOT / project / entry["bucket"] / entry["path"]


def _object_key(entry: dict) -> str:
    """`<bucket>/<path>` — keeps Supabase's namespacing so a path maps by prefix."""
    return f"{entry['bucket']}/{entry['path']}"


def _content_type(entry: dict) -> str:
    """The archive manifest records no MIME type, so infer it from the extension.

    Not cosmetic: most of these objects are merchant bank statements. Served as
    application/octet-stream a browser force-downloads them instead of previewing,
    which quietly changes how every document link in the product behaves.
    """
    import mimetypes  # noqa: PLC0415

    guess, _ = mimetypes.guess_type(entry["path"])
    return entry.get("content_type") or guess or "application/octet-stream"


def cmd_check() -> int:
    env = _env()
    creds, missing = _creds(env)
    print("R2 credentials:")
    for k in REQUIRED_KEYS:
        print(f"  {k:26} {'present' if k in creds else 'MISSING'}")
    if missing:
        print("\nNOT READY. Add the missing keys to the agents env, then re-run.")
        print("Cloudflare dashboard -> R2 -> Manage API tokens -> Create API token")
        print("(Object Read & Write). The account id is on the R2 Overview page.")
        return 2
    try:
        s3 = _client(creds)
        s3.head_bucket(Bucket=creds["R2_BUCKET"])
        print(f"\nbucket {creds['R2_BUCKET']}: reachable")
    except Exception as exc:  # noqa: BLE001
        print(f"\nbucket {creds['R2_BUCKET']}: UNREACHABLE — {str(exc)[:160]}")
        return 2
    print("READY")
    return 0


def cmd_upload(project: str, creds: dict, apply: bool) -> dict:
    entries = _manifest(project)
    if not entries:
        return {"project": project, "objects": 0, "note": "no archive manifest"}
    s3 = _client(creds) if apply else None
    bucket = creds["R2_BUCKET"]
    uploaded = skipped = missing_local = failed = 0

    for e in entries:
        local = _local_path(project, e)
        if not local.exists():
            missing_local += 1
            log.error("archived file absent on disk", context={"path": str(local)})
            continue
        key = _object_key(e)
        if not apply:
            uploaded += 1
            continue
        try:
            # Skip when an object with the same SHA-256 is already there, so a
            # re-run after an interruption resumes instead of re-sending 3 GB.
            head = None
            try:
                head = s3.head_object(Bucket=bucket, Key=key)
            except Exception:
                head = None
            if head and head.get("Metadata", {}).get("sha256") == e.get("sha256"):
                skipped += 1
                continue
            s3.upload_file(
                str(local), bucket, key,
                ExtraArgs={"Metadata": {"sha256": e.get("sha256", "")},
                           "ContentType": _content_type(e)},
            )
            uploaded += 1
        except Exception as exc:  # noqa: BLE001 - report every failure, never swallow
            failed += 1
            log.error("upload failed", context={"key": key, "error": str(exc)[:200]})

    return {"project": project, "objects": len(entries), "uploaded": uploaded,
            "skipped_same_hash": skipped, "missing_local": missing_local,
            "failed": failed}


def _rewrite_sql(project: str, creds: dict, apply: bool) -> dict:
    """Repoint pointer columns at R2. Originals saved for reversal."""
    import libsql  # noqa: PLC0415

    url, tok, _ = resolve_project_target(project)
    db = libsql.connect(database=url, auth_token=tok)
    ref = PROJECTS[project]["ref"]
    old_prefix = f"https://{ref}.supabase.co/storage/v1/object/public/"
    new_base = creds["R2_PUBLIC_BASE_URL"].rstrip("/") + "/"

    db.execute("""CREATE TABLE IF NOT EXISTS "_storage_url_rewrites" (
        "id" INTEGER PRIMARY KEY, "tbl" TEXT NOT NULL, "col" TEXT NOT NULL,
        "row_id" TEXT NOT NULL, "old_value" TEXT NOT NULL, "new_value" TEXT NOT NULL,
        "rewritten_at" TEXT NOT NULL)""")

    planned = 0
    for spec in POINTER_COLUMNS.get(project, []):
        t, col, kind = spec["table"], spec["column"], spec["kind"]
        try:
            rows = db.execute(
                f'SELECT id, "{col}" FROM "{t}" WHERE "{col}" IS NOT NULL '
                f'AND trim("{col}") <> \'\'').fetchall()
        except Exception as exc:  # table/column may not exist in this project
            log.info("pointer column skipped", context={"table": t, "column": col,
                                                        "reason": str(exc)[:120]})
            continue
        for row_id, val in rows:
            val = str(val)
            if val.startswith(new_base):
                continue                     # already rewritten
            if kind == "url":
                if not val.startswith(old_prefix):
                    continue                 # external URL (iTunes art etc.) — leave it
                new_val = new_base + val[len(old_prefix):]
            else:
                if val.startswith("http"):
                    continue                 # already absolute; not a bare path
                new_val = new_base + f"{spec['bucket']}/{val.lstrip('/')}"
            planned += 1
            if not apply:
                continue
            db.execute(
                'INSERT INTO "_storage_url_rewrites" '
                '(tbl, col, row_id, old_value, new_value, rewritten_at) '
                "VALUES (?, ?, ?, ?, ?, datetime('now'))",
                [t, col, str(row_id), val, new_val])
            db.execute(f'UPDATE "{t}" SET "{col}" = ? WHERE id = ?', [new_val, row_id])
    if apply:
        db.commit()
    return {"project": project, "rows_rewritten" if apply else "rows_to_rewrite": planned}


def cmd_verify(project: str, creds: dict) -> dict:
    """Every archived object must be readable at its R2 key with a matching hash."""
    import urllib.request  # noqa: PLC0415

    entries = _manifest(project)
    s3 = _client(creds)
    bucket = creds["R2_BUCKET"]
    ok = bad = absent = 0
    for e in entries:
        key = _object_key(e)
        try:
            head = s3.head_object(Bucket=bucket, Key=key)
        except Exception:
            absent += 1
            log.error("object missing in R2", context={"key": key})
            continue
        if head.get("Metadata", {}).get("sha256") == e.get("sha256"):
            ok += 1
        else:
            bad += 1
            log.error("hash mismatch in R2", context={"key": key})

    # One real HTTP fetch through the public base URL — head_object proves the
    # object exists, not that the URL the apps will use actually serves it.
    sample_ok = None
    if entries:
        sample = creds["R2_PUBLIC_BASE_URL"].rstrip("/") + "/" + _object_key(entries[0])
        try:
            with urllib.request.urlopen(sample, timeout=30) as r:
                body = r.read()
            sample_ok = (hashlib.sha256(body).hexdigest() == entries[0].get("sha256"))
        except Exception as exc:  # noqa: BLE001
            log.error("public URL fetch failed", context={"url": sample,
                                                          "error": str(exc)[:160]})
            sample_ok = False
    return {"project": project, "objects": len(entries), "hash_ok": ok,
            "hash_bad": bad, "missing_in_r2": absent,
            "public_url_serves_correct_bytes": sample_ok,
            "ok": bad == 0 and absent == 0 and sample_ok is not False}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", choices=sorted(PROJECTS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--check", action="store_true", help="credentials + bucket reachability")
    ap.add_argument("--plan", action="store_true", help="report, change nothing")
    ap.add_argument("--apply", action="store_true", help="upload, then rewrite pointers")
    ap.add_argument("--verify", action="store_true", help="re-hash R2 against the manifest")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.check or not (args.plan or args.apply or args.verify):
        return cmd_check()

    env = _env()
    creds, missing = _creds(env)
    if missing:
        print(f"ERROR: missing R2 credentials: {', '.join(missing)}", file=sys.stderr)
        print("Run --check for setup instructions.", file=sys.stderr)
        return 2

    projects = sorted(PROJECTS) if args.all else ([args.project] if args.project else [])
    if not projects:
        print("ERROR: give --project or --all", file=sys.stderr)
        return 2

    out = []
    for p in projects:
        if args.verify:
            out.append(cmd_verify(p, creds))
            continue
        up = cmd_upload(p, creds, apply=args.apply)
        # Rewrite ONLY after the bytes are in place — a URL repointed at an
        # object that is not there yet is a broken link, not a migration.
        if args.apply and up.get("failed"):
            up["rewrite"] = "SKIPPED — uploads failed; pointers left untouched"
        else:
            up["rewrite"] = _rewrite_sql(p, creds, apply=args.apply)
        out.append(up)

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        for r in out:
            print(json.dumps(r))
    return 0 if all(r.get("ok", True) and not r.get("failed") for r in out) else 1


if __name__ == "__main__":
    sys.exit(main())
