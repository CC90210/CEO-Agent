"""Cloudflare R2 behind the shape of `supabase.storage`, for the Python harness.

WHY THIS EXISTS. The data plane already moved: `lib/turso_supabase_compat.py`
gives all 49 harness modules a Turso-backed `create_client`. But Turso is a
database, not an object store, so `.storage` was left as a `_Refuser` — correct
as a fail-closed default, wrong as a destination. Three runtime paths read bytes
out of Supabase Storage:

    integrations/send_gateway.py   shop-out attachments (the signed contract and
                                   the merchant's bank statements)
    integrations/extraction_consumer.py
                                   the SunBiz application PDF it extracts fields
                                   from
    ops/_supabase_backup.py        the SunBiz tenant export

Cancel Supabase with `.storage` still refusing and the first of those sends a
funder an email whose attachments are gone, the second marks every extraction
job failed, and the third writes a "backup" with no documents in it.

WHAT THIS IS. The same surface those callers already use, with supabase-py's
semantics rather than supabase-js's:

    storage.from_(bucket).download(path)                -> bytes  (RAISES on miss)
                         .upload(path, file, file_options)
                         .create_signed_url(path, expires_in)
                         .create_signed_upload_url(path)
                         .get_public_url(path)
                         .info(path)
                         .list(prefix, options)
                         .remove([paths])

supabase-py RAISES on a failed download (storage3.StorageException); supabase-js
returns `{data, error}`. This module follows PYTHON, because that is what the
call sites are written against — every one of them wraps the download in
`try/except` and treats an exception as the failure signal. Returning `None` or
`b""` here would turn a missing bank statement into a zero-byte attachment.

KEYS AND BUCKETS. One R2 bucket holds every Supabase bucket, namespaced by the
Supabase bucket name: `<supabase-bucket>/<path>` — the exact convention
`etl_storage_to_r2.py` uploaded 4,118 objects with, and the one
`lib/r2-storage.ts` writes new objects with in the four Next.js repos. So a
migrated object and a newly-written one land at the same key.

Reads and writes go to the PRIVATE bucket (oasis-storage), which holds every
object — `r2_split_public_bucket.py` COPIED the handful of public prefixes into
oasis-public and left the originals in place. Only `get_public_url` consults the
public bucket, and only for a prefix on the canonical public list; anything else
gets a short-lived presigned URL instead of a world-readable one. 4,088 of these
objects are merchant bank statements.

CREDENTIALS come from `etl_storage_to_r2._creds`, not from a fresh read of the
env here. The agents env spells the R2 key pair `cloudflare_Access_Key_ID` /
`cloudflare_Secret_Access_Key`, and that aliasing lives in one place. This
deliberately calls `_creds` rather than the `resolve_r2` wrapper: `resolve_r2`
also runs `provision_r2`, which creates buckets and toggles the managed r2.dev
domain over the Cloudflare API. That is a migration action. A cron job
downloading one PDF has no business creating buckets, and doing it on every
process start would put two API calls in front of every attachment read.
"""
from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.structured_log import get_logger  # noqa: E402

log = get_logger("r2_storage")


class R2StorageError(Exception):
    """Raised for every failure. Never returned as data, never swallowed."""


# --------------------------------------------------------------------------- etl reuse

_ETL = None


def _etl():
    """Load `scripts/etl_storage_to_r2.py` as a module (it is a top-level
    script, not a package member). Lazy so importing this file costs nothing
    until storage is actually touched — it pulls in requests, boto3's trust
    bootstrap and the Turso project table."""
    global _ETL
    if _ETL is None:
        path = _SCRIPTS / "etl_storage_to_r2.py"
        if not path.exists():
            raise R2StorageError(
                f"cannot resolve R2 credentials: {path} is missing — it owns the "
                f"aliased key names (cloudflare_Access_Key_ID etc.)")
        spec = importlib.util.spec_from_file_location("etl_storage_to_r2", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _ETL = mod
    return _ETL


_CREDS: dict | None = None


def _creds() -> dict:
    """Resolved once per process. Re-deriving the account id on every object is
    an HTTP round trip nobody asked for."""
    global _CREDS
    if _CREDS is not None:
        return _CREDS
    etl = _etl()
    env = etl.load_env()
    creds, missing = etl._creds(env)
    if missing:
        raise R2StorageError(
            "R2 is not configured — missing " + ", ".join(missing) + ". "
            "Supabase Storage is gone under EMPIRE_DATA_BACKEND=turso_cloud, so "
            "there is nowhere else to read these bytes from. Add the keys to the "
            "agents env and confirm with:  python scripts/etl_storage_to_r2.py --check")
    _CREDS = creds
    return creds


_PUBLIC_BASE: str | None = None


def _public_base() -> str:
    """The r2.dev (or custom) domain on the PUBLIC bucket.

    Split from `_creds` because it costs Cloudflare API calls: the managed
    domain is a property of the bucket, not an env var, so `_creds` leaves
    R2_PUBLIC_BASE_URL unset unless an operator pinned one and `resolve_r2` is
    what fills it in. Reaching for `resolve_r2` on every object read would put
    bucket provisioning in front of every attachment download; reaching for it
    only here means the private path stays a single GET and the public path
    still works. Found by a live probe — the first version read `_creds` alone
    and raised "R2_PUBLIC_BASE_URL is unset" on a fully provisioned account.
    """
    global _PUBLIC_BASE
    if _PUBLIC_BASE:
        return _PUBLIC_BASE
    etl = _etl()
    base = (_creds().get("R2_PUBLIC_BASE_URL")
            or etl._lookup(etl.load_env(), "R2_PUBLIC_BASE_URL"))
    if not base:
        creds, missing, _notes = etl.resolve_r2(etl.load_env())
        base = creds.get("R2_PUBLIC_BASE_URL")
        if not base:
            raise R2StorageError(
                "R2_PUBLIC_BASE_URL could not be resolved (missing: "
                + ", ".join(missing) + "). Run  python scripts/etl_storage_to_r2.py "
                "--check  to provision the r2.dev domain on the public bucket, or "
                "set R2_PUBLIC_BASE_URL explicitly.")
    _PUBLIC_BASE = str(base).rstrip("/")
    return _PUBLIC_BASE


_S3 = None


def _s3():
    global _S3
    if _S3 is None:
        try:
            _S3 = _etl()._client(_creds())
        except SystemExit as exc:  # etl exits on a missing boto3; not fatal here
            raise R2StorageError(str(exc)) from exc
    return _S3


def r2_configured() -> bool:
    """True when a read would succeed on credentials alone. Diagnostics only —
    no call path branches on this, because a False must fail loudly at the point
    of use rather than degrade into a send with no attachments."""
    try:
        _creds()
        return True
    except R2StorageError:
        return False


# --------------------------------------------------------------------------- helpers

def normalize_object_path(bucket: str, value: str) -> str:
    """Reduce a stored pointer to a bucket-relative path.

    Three forms are live in the database right now and all three mean the same
    object:

        tenant/doc.pdf                              bare path (the original)
        lead-documents/tenant/doc.pdf               bucket-prefixed
        https://<host>/lead-documents/tenant/doc.pdf   rewritten to an absolute URL

    The third exists because `etl_storage_to_r2.py --apply` repointed
    `lead_documents.storage_path` (it is in POINTER_COLUMNS) at the public base
    URL. All 3,406 of those rows now hold a URL on `pub-d5766….r2.dev` — the
    managed domain that was briefly enabled on the PRIVATE bucket before
    `_ensure_no_public_domain` turned it off. An unauthenticated GET of one
    returns 403, so as a URL it is dead; as a KEY it is perfectly valid, because
    the bytes never moved. This maps it back to the key and the caller reads it
    from the private bucket with credentials, the way a bank statement should be
    read anyway.

    A URL whose first path segment is NOT this bucket raises. Silently treating
    an arbitrary external URL as an object key would let a caller's payload
    address storage it never named.
    """
    raw = str(value or "").replace("\\", "/").strip()
    if not raw:
        raise R2StorageError("empty storage path")
    if raw.lower().startswith(("http://", "https://")):
        from urllib.parse import unquote, urlsplit  # noqa: PLC0415

        path = unquote(urlsplit(raw).path).lstrip("/")
        head = path.split("/", 1)
        if len(head) != 2 or head[0] != bucket:
            raise R2StorageError(
                f"{raw[:120]!r} is an absolute URL whose path does not start with "
                f"the {bucket!r} bucket — refusing to guess an object key from it.")
        return head[1]
    raw = raw.lstrip("/")
    if raw.startswith(f"{bucket}/"):
        return raw[len(bucket) + 1:]
    return raw


def _object_key(bucket: str, path: str) -> str:
    """`<supabase-bucket>/<path>` — the shape etl_storage_to_r2 uploaded with."""
    return f"{bucket}/{normalize_object_path(bucket, path)}"


def _public_prefixes() -> frozenset[str]:
    return _etl().PUBLIC_PREFIXES_DEFAULT


class _Resp(dict):
    """supabase-py's storage returns have drifted between dict and object across
    storage3 versions, and different call sites reach for different spellings.
    Supporting both costs one class and removes a whole family of AttributeError
    at the far end of a cutover."""

    def __getattr__(self, item: str) -> Any:
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc


def _to_bytes(file: Any) -> bytes:
    if isinstance(file, (bytes, bytearray, memoryview)):
        return bytes(file)
    if isinstance(file, Path):
        return file.read_bytes()
    if isinstance(file, str):
        # supabase-py treats a str as a path on disk, not as content. Matching
        # that matters: guessing "content" would upload the filename.
        p = Path(file)
        if p.exists():
            return p.read_bytes()
        raise R2StorageError(
            f"upload(file={file!r}) — supabase-py reads a str argument as a local "
            f"file path, and that path does not exist. Pass bytes for literal content.")
    if isinstance(file, io.IOBase) or hasattr(file, "read"):
        data = file.read()
        return data if isinstance(data, bytes) else str(data).encode("utf-8")
    raise R2StorageError(f"upload(): unsupported file type {type(file).__name__}")


def _opt(options: dict | None, *names: str, default: Any = None) -> Any:
    if not options:
        return default
    for n in names:
        if n in options:
            return options[n]
    return default


# --------------------------------------------------------------------------- bucket API

class R2Bucket:
    """One Supabase bucket's worth of objects, inside the single R2 bucket."""

    def __init__(self, bucket: str):
        self._bucket = bucket

    # -- reads

    def download(self, path: str, options: dict | None = None) -> bytes:
        """Object bytes. Raises R2StorageError if it is not there.

        The raise is the contract. Both production callers branch on the
        exception; a soft return would let a shop-out email leave with an empty
        attachment and no error anywhere."""
        key = _object_key(self._bucket, path)
        c = _creds()
        try:
            obj = _s3().get_object(Bucket=c["R2_BUCKET"], Key=key)
            body = obj["Body"].read()
        except Exception as exc:  # noqa: BLE001 — re-raised, never swallowed
            raise R2StorageError(
                f"R2 download failed for {key} in bucket {c['R2_BUCKET']}: "
                f"{str(exc)[:200]}") from exc
        if not body:
            # A zero-byte read is indistinguishable from a healthy one downstream,
            # so it is treated as the failure it almost certainly is.
            raise R2StorageError(f"R2 object {key} is empty (0 bytes)")
        return body

    def info(self, path: str) -> _Resp:
        """HEAD, for confirming an object exists and reading its real size
        without pulling a multi-megabyte statement back through the process."""
        key = _object_key(self._bucket, path)
        c = _creds()
        try:
            h = _s3().head_object(Bucket=c["R2_BUCKET"], Key=key)
        except Exception as exc:  # noqa: BLE001
            raise R2StorageError(f"R2 head failed for {key}: {str(exc)[:200]}") from exc
        ctype = h.get("ContentType") or "application/octet-stream"
        return _Resp({
            "name": str(path).rsplit("/", 1)[-1],
            "id": (h.get("ETag") or "").strip('"') or None,
            "size": int(h.get("ContentLength") or 0),
            "contentLength": int(h.get("ContentLength") or 0),
            "contentType": ctype,
            "mimetype": ctype,
            "lastModified": h["LastModified"].isoformat() if h.get("LastModified") else None,
            "etag": h.get("ETag"),
            "cacheControl": h.get("CacheControl"),
            "metadata": h.get("Metadata") or {},
        })

    def list(self, path: str | None = None, options: dict | None = None) -> list[dict]:
        """Objects directly under `path`. Non-recursive by default, like
        supabase-py, so a caller matching on an exact `name` behaves the same on
        both backends.

        `options={"recursive": True}` walks the whole prefix and returns FULL
        keys in `name`. Added because an orphan sweep is impossible without it:
        objects live at <tenant>/<asset_id>/<file>, the default list drops both
        nested keys and the sub-prefixes, so listing a tenant returned ZERO while
        73 objects sat underneath — a false negative that reads exactly like a
        clean bucket. publish_to_library's delete path already promises the bytes
        survive "so a sweep can find it"; this is what makes that true."""
        c = _creds()
        dir_ = (path or "").replace("\\", "/").strip("/")
        prefix = _object_key(self._bucket, f"{dir_}/" if dir_ else "")
        limit = int(_opt(options, "limit", default=1000) or 1000)
        search = _opt(options, "search")
        recursive = bool(_opt(options, "recursive", default=False))
        out: list[dict] = []
        token = None
        try:
            while True:
                kw: dict[str, Any] = {"Bucket": c["R2_BUCKET"], "Prefix": prefix,
                                      "MaxKeys": min(max(limit - len(out), 1), 1000)}
                if not recursive:
                    kw["Delimiter"] = "/"
                if token:
                    kw["ContinuationToken"] = token
                r = _s3().list_objects_v2(**kw)
                for o in r.get("Contents", []):
                    name = o["Key"][len(prefix):]
                    if not name:
                        continue
                    if "/" in name and not recursive:
                        continue
                    if search and search not in name:
                        continue
                    out.append({
                        "name": name,
                        "id": o["Key"],
                        "updated_at": o["LastModified"].isoformat() if o.get("LastModified") else None,
                        "metadata": {"size": int(o.get("Size") or 0),
                                     "eTag": o.get("ETag")},
                    })
                    if len(out) >= limit:
                        return out
                if not r.get("IsTruncated"):
                    return out
                token = r.get("NextContinuationToken")
        except Exception as exc:  # noqa: BLE001
            raise R2StorageError(
                f"R2 list failed for {prefix}: {str(exc)[:200]}") from exc

    # -- writes

    def upload(self, path: str, file: Any = None, file_options: dict | None = None,
               **kw: Any) -> _Resp:
        """PUT an object. `file` may be bytes, a Path, a local path str (as
        supabase-py reads it), or a file-like.

        `file_options` follows supabase-py: {"content-type": ..., "upsert":
        "true"/"false", "cache-control": ...}. upsert defaults to FALSE, and a
        collision raises rather than overwriting — S3 has no single-request
        if-none-match on R2, so it costs a HEAD, which is the correct price for
        not silently replacing a signed contract."""
        if file is None:
            file = kw.get("file")
        data = _to_bytes(file)
        key = _object_key(self._bucket, path)
        c = _creds()
        opts = file_options or kw.get("file_options") or {}
        upsert = str(_opt(opts, "upsert", "x-upsert", default="false")).lower() in ("1", "true", "yes")
        ctype = _opt(opts, "content-type", "contentType", "content_type",
                     default="application/octet-stream")
        cache = _opt(opts, "cache-control", "cacheControl", "cache_control")

        if not upsert:
            try:
                _s3().head_object(Bucket=c["R2_BUCKET"], Key=key)
            except Exception:  # noqa: BLE001 — absence is the expected case
                pass
            else:
                raise R2StorageError(
                    f"Duplicate: object already exists at {key}. Pass "
                    f'file_options={{"upsert": "true"}} to replace it.')

        put: dict[str, Any] = {"Bucket": c["R2_BUCKET"], "Key": key, "Body": data,
                               "ContentType": ctype}
        if cache:
            put["CacheControl"] = str(cache)
        try:
            _s3().put_object(**put)
        except Exception as exc:  # noqa: BLE001
            raise R2StorageError(f"R2 upload failed for {key}: {str(exc)[:200]}") from exc
        log.info("r2 upload", key=key, bytes=len(data))
        return _Resp({"path": str(path), "fullPath": key, "full_path": key,
                      "Key": key, "key": key})

    def remove(self, paths: list[str] | str) -> list[dict]:
        if isinstance(paths, str):
            paths = [paths]
        c = _creds()
        done: list[dict] = []
        for p in paths:
            key = _object_key(self._bucket, p)
            try:
                _s3().delete_object(Bucket=c["R2_BUCKET"], Key=key)
            except Exception as exc:  # noqa: BLE001
                raise R2StorageError(
                    f"R2 delete failed for {key}: {str(exc)[:200]}") from exc
            done.append({"name": p, "key": key})
        return done

    # -- URLs

    def create_signed_url(self, path: str, expires_in: int = 3600,
                          options: dict | None = None) -> _Resp:
        url = self._presign("get_object", path, expires_in)
        # Three spellings because storage3 changed its mind twice; call sites in
        # this fleet use signedURL and signed_url both.
        return _Resp({"signedURL": url, "signedUrl": url, "signed_url": url,
                      "path": str(path)})

    def create_signed_upload_url(self, path: str, expires_in: int = 900) -> _Resp:
        url = self._presign("put_object", path, expires_in)
        return _Resp({"signed_url": url, "signedUrl": url, "signedURL": url,
                      "token": url.split("?", 1)[-1], "path": str(path),
                      "key": _object_key(self._bucket, path)})

    def get_public_url(self, path: str, options: dict | None = None) -> str:
        """A durable public URL — but ONLY for a Supabase bucket that was public.

        Everything else gets a one-hour presigned URL instead. The public bucket
        carries an r2.dev domain; handing it a lead-documents key would publish a
        bank statement at a guessable address, which is the exact failure
        r2_split_public_bucket.py exists to prevent."""
        if self._bucket in _public_prefixes():
            return f"{_public_base()}/{_object_key(self._bucket, path)}"
        return self._presign("get_object", path, 3600)

    def _presign(self, op: str, path: str, expires_in: int) -> str:
        c = _creds()
        try:
            return _s3().generate_presigned_url(
                op,
                Params={"Bucket": c["R2_BUCKET"], "Key": _object_key(self._bucket, path)},
                ExpiresIn=int(expires_in),
            )
        except Exception as exc:  # noqa: BLE001
            raise R2StorageError(
                f"R2 presign ({op}) failed for {self._bucket}/{path}: "
                f"{str(exc)[:200]}") from exc


class R2Storage:
    """`supabase.storage`-shaped entry point."""

    def from_(self, bucket: str) -> R2Bucket:
        if not bucket or not isinstance(bucket, str):
            raise R2StorageError(f"storage.from_({bucket!r}) — bucket name required")
        return R2Bucket(bucket)

    # supabase-js spelling, in case a port copied it across
    def from_bucket(self, bucket: str) -> R2Bucket:
        return self.from_(bucket)

    def list_buckets(self):
        raise R2StorageError(
            "storage.list_buckets() has no R2 equivalent — every Supabase bucket "
            "is a key prefix inside one R2 bucket now. Enumerate with "
            "storage.from_('<bucket>').list().")

    def get_bucket(self, bucket: str):
        raise R2StorageError(
            "storage.get_bucket() has no R2 equivalent — buckets are key prefixes. "
            "Use storage.from_('<bucket>').info(<path>) for an object.")


def storage_surface() -> R2Storage:
    """The object `TursoSupabaseCompat.storage` is bound to.

    Constructing it does NOT touch credentials or the network: a process that
    never reads an object must not fail because R2 is unconfigured, and a
    process that does read one must fail at the read with a message naming the
    missing keys.
    """
    return R2Storage()


__all__ = ["R2Storage", "R2Bucket", "R2StorageError", "storage_surface",
           "r2_configured", "normalize_object_path"]
