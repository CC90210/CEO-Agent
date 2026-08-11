#!/usr/bin/env python3
"""Split the migrated objects into a private and a public R2 bucket.

WHY
    Supabase carries a public/private flag PER BUCKET. The migration flattened
    all 13 of them into one R2 bucket, which forces a single answer for objects
    with two very different sensitivities:

        private : lead-documents (4,088 merchant bank statements),
                  chat-attachments, marketing-media, merchant-documents
        public  : tenant-assets, avatars, and PropFlow's seven image buckets

    Turning on the r2.dev domain to serve a property photo would have published
    the bank statements at a guessable URL. (Checked: enabling the managed
    domain did NOT actually serve them — an unauthenticated fetch still 403'd —
    but relying on that is not a security posture.)

WHAT
    oasis-storage  stays private; served only through signed URLs.
    oasis-public   new, r2.dev enabled; holds copies of the public prefixes.

    Objects are copied server-side (S3 CopyObject), so nothing is re-uploaded
    and the originals stay put — the private bucket remains the complete
    archive.

    python scripts/r2_split_public_bucket.py --plan
    python scripts/r2_split_public_bucket.py --apply
    python scripts/r2_split_public_bucket.py --verify
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

import importlib.util  # noqa: E402

import requests  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "etl", REPO / "scripts" / "etl_storage_to_r2.py")
etl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(etl)

PUBLIC_BUCKET = etl.DEFAULT_PUBLIC_BUCKET

# One canonical list, defined in etl_storage_to_r2.py. Copying it here is how
# the split and the cancellation gate would come to disagree about which
# objects are allowed to be world-readable.
PUBLIC_PREFIXES = sorted(etl.PUBLIC_PREFIXES_DEFAULT)

CF_API = "https://api.cloudflare.com/client/v4"


def _cf(method: str, path: str, token: str, **kw):
    return requests.request(method, f"{CF_API}{path}",
                            headers={"Authorization": f"Bearer {token}",
                                     "Content-Type": "application/json"},
                            timeout=45, **kw)


def _iter_keys(s3, bucket: str, prefix: str):
    tok = None
    while True:
        kw = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
        if tok:
            kw["ContinuationToken"] = tok
        r = s3.list_objects_v2(**kw)
        for o in r.get("Contents", []):
            yield o["Key"], o["Size"]
        if not r.get("IsTruncated"):
            return
        tok = r.get("NextContinuationToken")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    if not (args.plan or args.apply or args.verify):
        args.plan = True

    creds, missing, _notes = etl.resolve_r2(etl._env())
    if missing:
        print(f"ERROR: R2 not resolvable: {', '.join(missing)}", file=sys.stderr)
        return 2
    acct = creds["CLOUDFLARE_ACCOUNT_ID"]
    api_token = creds.get("CLOUDFLARE_API_TOKEN")
    private_bucket = creds["R2_BUCKET"]
    s3 = etl._client(creds)

    counts: dict[str, tuple[int, int]] = {}
    for p in PUBLIC_PREFIXES:
        n = size = 0
        for _k, sz in _iter_keys(s3, private_bucket, f"{p}/"):
            n += 1
            size += sz
        counts[p] = (n, size)

    total = sum(n for n, _ in counts.values())
    print(f"private bucket : {private_bucket}")
    print(f"public bucket  : {PUBLIC_BUCKET}")
    print(f"\npublic-prefixed objects to copy: {total}")
    for p, (n, size) in counts.items():
        if n:
            print(f"    {p:<32} {n:>5} objects  {size / 1e6:>8.2f} MB")
    empties = [p for p, (n, _) in counts.items() if not n]
    if empties:
        print(f"    (no objects under: {', '.join(empties)})")

    if args.plan and not (args.apply or args.verify):
        return 0

    if args.apply:
        print(f"\ncreating {PUBLIC_BUCKET} ...")
        try:
            s3.head_bucket(Bucket=PUBLIC_BUCKET)
            print("    already present")
        except Exception:
            s3.create_bucket(Bucket=PUBLIC_BUCKET)
            print("    created")

        copied = failed = 0
        for p in PUBLIC_PREFIXES:
            for key, _sz in _iter_keys(s3, private_bucket, f"{p}/"):
                try:
                    s3.copy_object(Bucket=PUBLIC_BUCKET, Key=key,
                                   CopySource={"Bucket": private_bucket, "Key": key})
                    copied += 1
                except Exception as exc:
                    failed += 1
                    print(f"    FAILED {key}: {str(exc)[:120]}")
        print(f"    copied {copied}, failed {failed}")

        if api_token:
            url = (f"/accounts/{acct}/r2/buckets/{PUBLIC_BUCKET}/domains/managed")
            r = _cf("PUT", url, api_token, json={"enabled": True})
            dom = (r.json().get("result") or {}).get("domain")
            print(f"    r2.dev on {PUBLIC_BUCKET}: HTTP {r.status_code} domain={dom}")

            # And make certain the PRIVATE bucket has no public domain.
            pv = _cf("GET", f"/accounts/{acct}/r2/buckets/{private_bucket}"
                            f"/domains/managed", api_token)
            en = (pv.json().get("result") or {}).get("enabled")
            print(f"    r2.dev on {private_bucket}: enabled={en}"
                  f"{'  <-- MUST BE FALSE' if en else '  (correct)'}")

    if args.verify:
        print("\n=== verification ===")
        fails = 0

        def check(label, ok, detail=""):
            nonlocal fails
            if not ok:
                fails += 1
            print(f"  {'PASS' if ok else 'FAIL'}  {label}"
                  f"{('  — ' + detail) if detail else ''}")

        # Object parity for every public prefix.
        for p in PUBLIC_PREFIXES:
            src = {k for k, _ in _iter_keys(s3, private_bucket, f"{p}/")}
            if not src:
                continue
            dst = {k for k, _ in _iter_keys(s3, PUBLIC_BUCKET, f"{p}/")}
            check(f"{p}: all objects copied", src <= dst,
                  f"{len(src - dst)} missing" if src - dst else f"{len(src)} objects")

        # No private prefix leaked into the public bucket.
        leaked = []
        for p in ("lead-documents", "chat-attachments", "marketing-media",
                  "merchant-documents"):
            got = list(_iter_keys(s3, PUBLIC_BUCKET, f"{p}/"))
            if got:
                leaked.append(f"{p} ({len(got)})")
        check("no private prefix present in the public bucket", not leaked,
              ", ".join(leaked))

        if api_token:
            pub = _cf("GET", f"/accounts/{acct}/r2/buckets/{PUBLIC_BUCKET}"
                             f"/domains/managed", api_token).json().get("result") or {}
            priv = _cf("GET", f"/accounts/{acct}/r2/buckets/{private_bucket}"
                              f"/domains/managed", api_token).json().get("result") or {}
            check("private bucket has NO public domain", not priv.get("enabled"))
            check("public bucket has a public domain", bool(pub.get("enabled")),
                  str(pub.get("domain")))

            # The decisive test: fetch one of each with no credentials.
            def fetch(domain, key):
                try:
                    req = urllib.request.Request(f"https://{domain}/{key}",
                                                 headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                    with urllib.request.urlopen(req, timeout=25) as r:
                        return r.status, len(r.read(64))
                except Exception as e:
                    return getattr(e, "code", None), str(e)[:70]

            if pub.get("domain"):
                sample = next((k for p in PUBLIC_PREFIXES
                               for k, _ in _iter_keys(s3, PUBLIC_BUCKET, f"{p}/")), None)
                if sample:
                    st, info = fetch(pub["domain"], sample)
                    check("a PUBLIC object is readable without credentials",
                          st == 200, f"HTTP {st} {info}")
                priv_sample = next(
                    (k for k, _ in _iter_keys(s3, private_bucket, "lead-documents/")),
                    None)
                if priv_sample:
                    st, info = fetch(pub["domain"], priv_sample)
                    check("a PRIVATE object is NOT readable on the public domain",
                          st != 200, f"HTTP {st}")

        print(f"\n{'SPLIT VERIFIED' if not fails else f'{fails} CHECK(S) FAILED'}")
        return 1 if fails else 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
