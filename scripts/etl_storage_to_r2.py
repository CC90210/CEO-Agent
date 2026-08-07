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

import requests

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
        # NOT properties.image_url — that column does not exist. It was added
        # here from intuition and caught by verifying the list against
        # PRAGMA table_info. A pointer column that is not real makes the rewrite
        # cover less than it reports, which is exactly what the census prevents.
    ],
    "nostalgic": [
        {"table": "dj_profiles", "column": "profile_image_url", "kind": "url"},
    ],
    "breeze": [],
    "oasis": [],
}


# The agents env names these differently from the canonical R2 docs. Accept
# both rather than making the operator rename working credentials.
KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "R2_ACCESS_KEY_ID": ("cloudflare_Access_Key_ID", "CLOUDFLARE_ACCESS_KEY_ID"),
    "R2_SECRET_ACCESS_KEY": ("cloudflare_Secret_Access_Key",
                             "CLOUDFLARE_SECRET_ACCESS_KEY"),
    "CLOUDFLARE_API_TOKEN": ("cloudflare_API_Token", "Cloudflare_token"),
}

# Private by default. Of the 4,118 migrated objects, 4,113 came from buckets
# Supabase marked private — 4,088 of them merchant bank statements — so this
# bucket must never be handed a public domain. Only the handful of genuinely
# public prefixes are mirrored into DEFAULT_PUBLIC_BUCKET; see
# scripts/r2_split_public_bucket.py.
DEFAULT_BUCKET = "oasis-storage"
DEFAULT_PUBLIC_BUCKET = "oasis-public"

# Which Supabase buckets were PUBLIC, read from storage.buckets.public in each
# live project (2026-08-07) rather than guessed.
#
# The canonical copy lives here because three things depend on agreeing about
# it: this ETL, r2_split_public_bucket.py, and supabase_cancellation_gate.py.
# If they ever disagree, the gate either demands that bank statements be
# world-readable or waves through an object nobody can load — so there is one
# list, and anything absent from it is treated as PRIVATE.
PUBLIC_PREFIXES_DEFAULT = frozenset({
    "tenant-assets",                  # bravo
    "avatars",                        # nostalgic
    "application-documents",          # propflow
    "application-screening-reports",  # propflow
    "documents",                      # propflow
    "logos",                          # propflow
    "media",                          # propflow
    "properties",                     # propflow
    "property-photos",                # propflow
})


def _env() -> dict:
    return load_env()


def _lookup(env: dict, key: str) -> str | None:
    for name in (key, *KEY_ALIASES.get(key, ())):
        v = env.get(name) or os.environ.get(name)
        if v:
            return v
    return None


def _derive_account_id(api_token: str) -> str | None:
    """The account id is a lookup, not something to ask an operator to paste."""
    hdr = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    try:
        r = requests.get("https://api.cloudflare.com/client/v4/accounts",
                         headers=hdr, timeout=30)
        if r.status_code == 200:
            for a in r.json().get("result") or []:
                return a["id"]
        # A zone-scoped token cannot list accounts, but every zone names one.
        r = requests.get("https://api.cloudflare.com/client/v4/zones",
                         headers=hdr, timeout=30)
        if r.status_code == 200:
            for z in r.json().get("result") or []:
                if (z.get("account") or {}).get("id"):
                    return z["account"]["id"]
    except requests.RequestException:
        return None
    return None


def _creds(env: dict) -> tuple[dict, list[str]]:
    """Resolve R2 credentials, deriving everything that can be derived.

    Only the S3 key pair is genuinely secret and operator-supplied. The account
    id, bucket name and public URL are all discoverable through the Cloudflare
    API, so requiring them by hand just adds three ways for a cutover to stall
    on a typo.
    """
    have: dict[str, str] = {}
    missing: list[str] = []

    for k in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        v = _lookup(env, k)
        if v:
            have[k] = v
        else:
            missing.append(k)

    api_token = _lookup(env, "CLOUDFLARE_API_TOKEN")
    if api_token:
        have["CLOUDFLARE_API_TOKEN"] = api_token

    acct = _lookup(env, "CLOUDFLARE_ACCOUNT_ID")
    if not acct and api_token:
        acct = _derive_account_id(api_token)
    if acct:
        have["CLOUDFLARE_ACCOUNT_ID"] = acct
    else:
        missing.append("CLOUDFLARE_ACCOUNT_ID")

    have["R2_BUCKET"] = _lookup(env, "R2_BUCKET") or DEFAULT_BUCKET
    have["R2_PUBLIC_BUCKET"] = _lookup(env, "R2_PUBLIC_BUCKET") or DEFAULT_PUBLIC_BUCKET

    base = _lookup(env, "R2_PUBLIC_BASE_URL")
    if base:
        have["R2_PUBLIC_BASE_URL"] = base.rstrip("/")
    # Otherwise it is resolved by provision_r2(), which has to create the bucket
    # first — a managed r2.dev domain cannot exist before its bucket does.

    return have, missing


def provision_r2(creds: dict) -> list[str]:
    """Create the buckets and resolve the public URL. Returns progress notes.

    Split from _creds because the steps are ordered: a managed domain is a
    property of an existing bucket.

    TWO buckets, not one. Supabase carries a public/private flag per bucket, and
    of the 4,118 migrated objects 4,113 came from PRIVATE ones — 4,088 of those
    are merchant bank statements. An earlier version of this function enabled
    the r2.dev domain on whatever R2_BUCKET pointed at, so simply re-running it
    kept switching public access back on over the statements. The public URL now
    only ever comes from the public bucket, and the private bucket is never
    handed a domain.
    """
    notes: list[str] = []
    if "CLOUDFLARE_ACCOUNT_ID" not in creds or "R2_ACCESS_KEY_ID" not in creds:
        return notes
    _created, msg = ensure_bucket(creds)
    notes.append(msg)

    token = creds.get("CLOUDFLARE_API_TOKEN")
    if token:
        # Belt and braces: assert the private bucket has no public domain on
        # every run, so a stray dashboard click or an older build cannot leave
        # one enabled unnoticed.
        disabled = _ensure_no_public_domain(
            creds["CLOUDFLARE_ACCOUNT_ID"], creds["R2_BUCKET"], token)
        if disabled:
            notes.append(f"disabled a public domain found on the PRIVATE bucket "
                         f"{creds['R2_BUCKET']}")

    if "R2_PUBLIC_BASE_URL" not in creds and token:
        base = _managed_public_url(creds["CLOUDFLARE_ACCOUNT_ID"],
                                   creds["R2_PUBLIC_BUCKET"], token)
        if base:
            creds["R2_PUBLIC_BASE_URL"] = base.rstrip("/")
            notes.append(f"public base url ({creds['R2_PUBLIC_BUCKET']}): "
                         f"{creds['R2_PUBLIC_BASE_URL']}")
        else:
            notes.append("public base url: could not enable the managed r2.dev "
                         "domain — set R2_PUBLIC_BASE_URL explicitly")
    return notes


def _ensure_no_public_domain(acct: str, bucket: str, api_token: str) -> bool:
    """Turn off the managed r2.dev domain on a bucket. True if one was on."""
    hdr = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    url = (f"https://api.cloudflare.com/client/v4/accounts/{acct}"
           f"/r2/buckets/{bucket}/domains/managed")
    try:
        r = requests.get(url, headers=hdr, timeout=30)
        if r.status_code != 200:
            return False
        if not (r.json().get("result") or {}).get("enabled"):
            return False
        requests.put(url, headers=hdr, json={"enabled": False}, timeout=30)
        return True
    except requests.RequestException:
        return False


def resolve_r2(env: dict) -> tuple[dict, list[str], list[str]]:
    """Full resolution: credentials, bucket, public URL. (creds, missing, notes)"""
    creds, missing = _creds(env)
    notes = provision_r2(creds) if not missing else []
    if "R2_PUBLIC_BASE_URL" not in creds:
        missing = [*missing, "R2_PUBLIC_BASE_URL"]
    return creds, missing, notes


def _managed_public_url(acct: str, bucket: str, api_token: str) -> str | None:
    """The bucket's r2.dev domain, turning it on if it is not already."""
    hdr = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    url = (f"https://api.cloudflare.com/client/v4/accounts/{acct}"
           f"/r2/buckets/{bucket}/domains/managed")
    try:
        r = requests.get(url, headers=hdr, timeout=30)
        if r.status_code == 200:
            res = r.json().get("result") or {}
            if res.get("enabled") and res.get("domain"):
                return f"https://{res['domain']}"
            r = requests.put(url, headers=hdr, json={"enabled": True}, timeout=30)
            if r.status_code in (200, 201):
                res = r.json().get("result") or {}
                if res.get("domain"):
                    return f"https://{res['domain']}"
    except requests.RequestException:
        return None
    return None


def ensure_bucket(creds: dict) -> tuple[bool, str]:
    """Create the bucket if it is absent. Returns (created, message)."""
    s3 = _client(creds)
    bucket = creds["R2_BUCKET"]
    try:
        s3.head_bucket(Bucket=bucket)
        return False, f"bucket {bucket}: already present"
    except Exception:
        pass
    try:
        s3.create_bucket(Bucket=bucket)
        return True, f"bucket {bucket}: created"
    except Exception as exc:
        return False, f"bucket {bucket}: could not create — {str(exc)[:160]}"


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
    creds, missing, notes = resolve_r2(env)
    print("R2 credentials:")
    for k in REQUIRED_KEYS:
        how = ""
        if k in creds and not _lookup(env, k):
            how = "  (derived)"
        print(f"  {k:26} {'present' if k in creds else 'MISSING'}{how}")
    for n in notes:
        print(f"  {n}")
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

    # Validate the pointer list against the live schema BEFORE touching anything.
    # A stale entry used to be swallowed at INFO level, which meant the rewrite
    # quietly covered fewer columns than it claimed — the schema drifts, the
    # report still says success, and nobody finds out until a link 404s.
    bad: list[str] = []
    for spec in POINTER_COLUMNS.get(project, []):
        cols = [r[1] for r in db.execute(
            f'PRAGMA table_info("{spec["table"]}")').fetchall()]
        if not cols:
            bad.append(f'{spec["table"]} (table absent)')
        elif spec["column"] not in cols:
            bad.append(f'{spec["table"]}.{spec["column"]} (column absent)')
        elif "id" not in cols:
            bad.append(f'{spec["table"]} has no id column — the UPDATE keys on id')
    if bad:
        raise SystemExit(
            f"POINTER_COLUMNS is stale for {project}; refusing to rewrite:\n  "
            + "\n  ".join(bad)
            + "\nFix the list in etl_storage_to_r2.py, then re-run.")

    planned = 0
    for spec in POINTER_COLUMNS.get(project, []):
        t, col, kind = spec["table"], spec["column"], spec["kind"]
        rows = db.execute(
            f'SELECT id, "{col}" FROM "{t}" WHERE "{col}" IS NOT NULL '
            f'AND trim("{col}") <> \'\'').fetchall()
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
    creds, missing, notes = resolve_r2(env)
    for n in notes:
        print(f"r2: {n}")
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
