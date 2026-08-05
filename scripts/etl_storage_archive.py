"""Archive Supabase Storage buckets to local disk, with a verifiable manifest.

WHY LOCAL DISK. The census found 4,084 files / ~2.98 GB — overwhelmingly
bravo's lead-documents (4,067 files, 2.94 GB of merchant bank statements).
Putting 3 GB of blobs INSIDE Turso would eat most of the 5 GB free quota and
bloat every embedded replica; R2 is the right long-term home but the Cloudflare
token on this machine reaches no account. Losing the files to a Supabase
cancellation is the one unacceptable outcome — so archive locally FIRST, with
SHA-256 per file, and upload to R2 whenever those credentials exist. The
manifest also lands in the project's Turso database (_storage_archive_manifest)
so the file inventory survives even if this machine dies.

Layout:  state/backups/supabase_storage/<project>/<bucket>/<path...>
Manifest: same root, <project>__manifest.jsonl (path, size, sha256, archived_at)

The object list comes from storage.objects via the Management API (works for
every project); the BYTES come from the storage download API, which needs that
project's service-role key. Projects with a dead/absent key are reported as
BLOCKED per bucket, never silently skipped.

CLI:
  python scripts/etl_storage_archive.py --project bravo
  python scripts/etl_storage_archive.py --all
  python scripts/etl_storage_archive.py --verify --project bravo   # re-hash local files vs manifest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

import requests  # noqa: E402

from core.turso_schema_transpiler import PROJECTS as REFS, _mgmt_query  # noqa: E402
from etl_supabase_to_turso import PROJECTS as REST_KEYS  # noqa: E402
from lib.db_turso import TursoDB, resolve_project_target  # noqa: E402
from lib.secret_loader import load_env  # noqa: E402
from lib.structured_log import get_logger  # noqa: E402

log = get_logger("etl_storage_archive")

ARCHIVE_ROOT = PROJECT_ROOT / "state" / "backups" / "supabase_storage"
TIMEOUT_S = 120

MANIFEST_DDL = (
    'CREATE TABLE IF NOT EXISTS "_storage_archive_manifest" ('
    '"bucket" TEXT NOT NULL, "path" TEXT NOT NULL, "size" INTEGER, '
    '"sha256" TEXT, "archived_at" TEXT, "local_root" TEXT, '
    'PRIMARY KEY ("bucket", "path"))'
)


def list_objects(project: str, token: str) -> list[dict]:
    ref = REFS[project]["ref"]
    return _mgmt_query(ref, (
        "select bucket_id, name, (metadata->>'size')::bigint as size "
        "from storage.objects where metadata is not null order by bucket_id, name"
    ), token)


def download(url_base: str, key: str, bucket: str, path: str) -> bytes:
    r = requests.get(
        f"{url_base}/storage/v1/object/{bucket}/{path}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=TIMEOUT_S,
    )
    if r.status_code != 200:
        raise RuntimeError(f"{bucket}/{path}: HTTP {r.status_code} {r.text[:120]}")
    return r.content


def archive_project(project: str, mgmt_token: str, env: dict) -> dict:
    objs = list_objects(project, mgmt_token)
    if not objs:
        return {"project": project, "objects": 0, "status": "empty"}

    if project not in REST_KEYS:
        return {"project": project, "objects": len(objs),
                "status": "BLOCKED — no service key registered for storage download"}
    url_key, key_key = REST_KEYS[project]
    url, key = env.get(url_key), env.get(key_key)
    if not url or not key:
        return {"project": project, "objects": len(objs),
                "status": f"BLOCKED — {key_key} absent"}

    root = ARCHIVE_ROOT / project
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = ARCHIVE_ROOT / f"{project}__manifest.jsonl"
    done: set[tuple[str, str]] = set()
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                done.add((e["bucket"], e["path"]))

    copied = failed = skipped = 0
    bytes_copied = 0
    entries: list[dict] = []
    with manifest_path.open("a", encoding="utf-8") as mf:
        for o in objs:
            bucket, path = o["bucket_id"], o["name"]
            if (bucket, path) in done:
                skipped += 1
                continue
            try:
                blob = download(url.rstrip("/"), key, bucket, path)
            except Exception as exc:  # noqa: BLE001 - record, continue, report
                failed += 1
                log.error("download failed", project=project, bucket=bucket,
                          path=path, error=str(exc)[:200])
                continue
            target = root / bucket / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
            sha = hashlib.sha256(blob).hexdigest()
            entry = {"bucket": bucket, "path": path, "size": len(blob), "sha256": sha,
                     "archived_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            mf.write(json.dumps(entry) + "\n")
            entries.append(entry)
            copied += 1
            bytes_copied += len(blob)
            if copied % 200 == 0:
                log.info("archive progress", project=project, copied=copied,
                         of=len(objs), bytes=bytes_copied)

    # Mirror the manifest into the project's Turso DB so the inventory outlives
    # this machine. Bytes stay on disk; only metadata goes to Turso.
    try:
        turl, ttok, tmode = resolve_project_target(project)
        db = TursoDB(turl, ttok, tmode)
        db.execute(MANIFEST_DDL, allow_unscoped=True, reason="storage manifest DDL")
        for e in entries:
            db.execute(
                'INSERT OR REPLACE INTO "_storage_archive_manifest" '
                '(bucket, path, size, sha256, archived_at, local_root) VALUES (?,?,?,?,?,?)',
                [e["bucket"], e["path"], e["size"], e["sha256"], e["archived_at"], str(root)],
                allow_unscoped=True, reason="storage manifest — no tenant column")
        db.commit()
    except Exception as exc:  # noqa: BLE001
        log.error("manifest mirror to Turso failed (files are safe on disk)",
                  project=project, error=str(exc)[:200])

    return {"project": project, "objects": len(objs), "copied": copied,
            "skipped_already_archived": skipped, "failed": failed,
            "bytes": bytes_copied,
            "status": "ok" if failed == 0 else f"PARTIAL — {failed} failed"}


def verify_project(project: str) -> dict:
    manifest_path = ARCHIVE_ROOT / f"{project}__manifest.jsonl"
    if not manifest_path.exists():
        return {"project": project, "status": "no manifest"}
    ok = bad = missing = 0
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        f = ARCHIVE_ROOT / project / e["bucket"] / e["path"]
        if not f.exists():
            missing += 1
            continue
        if hashlib.sha256(f.read_bytes()).hexdigest() == e["sha256"]:
            ok += 1
        else:
            bad += 1
    return {"project": project, "hash_ok": ok, "hash_bad": bad, "missing": missing,
            "status": "ok" if bad == 0 and missing == 0 else "FAIL"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", choices=sorted(REFS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--verify", action="store_true", help="re-hash local archive vs manifest")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not args.project and not args.all:
        ap.error("give --project or --all")
    projects = sorted(REFS) if args.all else [args.project]

    results = []
    if args.verify:
        results = [verify_project(p) for p in projects]
    else:
        env = load_env()
        token = env.get("SUPABASE_ACCESS_TOKEN")
        if not token:
            print("ERROR: SUPABASE_ACCESS_TOKEN absent", file=sys.stderr)
            return 2
        for p in projects:
            try:
                results.append(archive_project(p, token, env))
            except Exception as exc:  # noqa: BLE001
                results.append({"project": p, "status": f"ERROR {str(exc)[:200]}"})

    failed = any("ok" not in str(r.get("status", "")) and r.get("status") != "empty"
                 for r in results)
    if args.json:
        print(json.dumps({"ok": not failed, "results": results}, indent=2))
    else:
        for r in results:
            print(f"  {r['project']}: " + json.dumps(
                {k: v for k, v in r.items() if k != "project"}))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
