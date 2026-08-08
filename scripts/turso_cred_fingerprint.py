#!/usr/bin/env python3
"""Fingerprint the Turso credentials so two machines can be compared safely.

WHY. Transferring a Turso auth token by copy-paste is error-prone: it is a
~200-character JWT, terminals wrap it, and a truncated paste produces a value
that LOOKS present and fails with "invalid JWT token: can't be decoded with any
of the existing keys" — which reads like a wrong/expired credential rather than
a damaged one.

Run this on both machines and compare. It prints length + a truncated SHA-256,
never the value, so the output is safe to read aloud or paste into chat.

    python scripts/turso_cred_fingerprint.py            # fingerprint only
    python scripts/turso_cred_fingerprint.py --probe    # also open a connection

--probe is the real test: a fingerprint match proves the transfer was clean, and
the probe proves the credential itself works against the live database.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

from lib import secret_loader  # noqa: E402

KEYS = ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN")


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true",
                    help="also open a real connection and run SELECT 1")
    args = ap.parse_args()

    secret_loader.reset_cache()
    env = secret_loader.load_env()

    print(f"{'key':<24} {'len':>5}  {'sha256[:16]':<16}  shape")
    print("-" * 64)
    missing = []
    for k in KEYS:
        v = env.get(k)
        if not v:
            missing.append(k)
            print(f"{k:<24} {'--':>5}  {'MISSING':<16}")
            continue
        # Shape is diagnostic without being sensitive: a JWT has two dots, and a
        # truncated paste usually loses the signature segment.
        if k.endswith("TOKEN"):
            segs = v.count(".") + 1
            shape = f"{segs} JWT segment(s)" + ("" if segs == 3 else "  <-- expected 3")
        else:
            shape = "libsql://…" if v.startswith("libsql://") else f"starts {v[:8]!r}"
        print(f"{k:<24} {len(v):>5}  {fingerprint(v):<16}  {shape}")

    if missing:
        print(f"\nMISSING: {', '.join(missing)}")
        return 2

    print("\nCompare BOTH the length and the hash against the other machine.")
    print("A different hash with the same length means the value was replaced;")
    print("a shorter length means the paste was truncated.")

    if not args.probe:
        return 0

    print("\n--- live probe ---")
    try:
        import libsql

        conn = libsql.connect(database=env["TURSO_DATABASE_URL"],
                              auth_token=env["TURSO_AUTH_TOKEN"])
        one = conn.execute("SELECT 1").fetchall()[0][0]
        tables = conn.execute(
            "select count(*) from sqlite_master where type='table'").fetchall()[0][0]
        print(f"  SELECT 1 -> {one}")
        print(f"  tables visible: {tables}")
        print("  CREDENTIAL WORKS")
        return 0
    except Exception as exc:
        msg = str(exc)
        print(f"  FAILED: {msg[:200]}")
        if "invalid JWT" in msg or "401" in msg:
            print("  -> the database rejected this token. Either it was damaged in "
                  "transfer (compare the hash above) or it is not a token for this "
                  "database.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
