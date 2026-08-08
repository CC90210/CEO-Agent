#!/usr/bin/env python3
"""Write the VPS's Turso credentials to a file for scp, and fingerprint them.

WHY. Moving these by copy-paste has now failed twice, in two different ways.
The token is a 348-character JWT that terminals wrap and editors truncate; and
the second attempt did not truncate anything, it filled the canonical names with
two DIFFERENT keys that already existed on the box —
TURSO_OASIS_PLATFORM_URL (another database) and TURSO_API_KEY (another
product's token). Both attempts produced the same opaque 401.

A file removes both failure modes: nothing to wrap, nothing to pick the wrong
line from. The fingerprints let the far side confirm arrival BEFORE anything is
restarted.

    python scripts/turso_vps_bundle.py            # write it, print fingerprints
    python scripts/turso_vps_bundle.py --show-only  # fingerprints, write nothing

The file holds real secrets. It is written 0600, outside the repo, and the
script prints the command to delete it once the transfer is done.
"""
from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from lib import secret_loader  # noqa: E402

# One definition of "how a credential is fingerprinted", shared with the tool
# the VPS runs. Two copies could disagree about the digest length and produce
# two values that look different for no reason — on the one comparison this
# whole transfer depends on.
from turso_cred_fingerprint import fingerprint  # noqa: E402

# The VPS runs SunBiz + the dashboard-email and extraction daemons. Every table
# they touch lives in the bravo database, so it needs the unprefixed pair and
# nothing else — more credentials on a box that cannot use them is only more
# exposure.
KEYS = ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN")

OUT = Path.home() / "turso_vps_credentials.env"


def verify_bundle(path: Path) -> tuple[bool, str]:
    """Parse the file the way the far side will, then actually connect.

    Parsing goes through secret_loader's own `_parse_env` rather than a
    hand-rolled reader. A first draft here rejected quoted and
    whitespace-padded values — but the real loader STRIPS both, so those files
    would have worked and this would have told CC not to send them. A verifier
    that is stricter than the thing it models produces false alarms; one that is
    looser misses real breakage. The only way to be neither is to use the same
    parser.

    What remains is the check that matters: open a connection with the parsed
    values. Line count and value length were the checks last time, and shape is
    exactly what looked fine on the VPS while the credentials were wrong.
    """
    # Private by name, deliberately shared here: duplicating env-parsing
    # semantics is the specific defect this function exists to catch.
    from lib.secret_loader import _parse_env  # noqa: PLC0415

    pairs = _parse_env(path.read_text(encoding="utf-8"))

    url, token = pairs.get("TURSO_DATABASE_URL"), pairs.get("TURSO_AUTH_TOKEN")
    if not (url and token):
        have = ", ".join(sorted(pairs)) or "nothing"
        return False, f"the bundle is missing one of the two keys (has: {have})"
    try:
        import libsql  # noqa: PLC0415

        conn = libsql.connect(database=url, auth_token=token)
        conn.execute("SELECT 1").fetchall()
        n = conn.execute("select count(*) from tenant_records").fetchall()[0][0]
        # tenant_records is a bravo table. Reading it proves this is the right
        # DATABASE, not merely a database that accepted the token — which is the
        # distinction the oasis-URL mix-up turned on: those credentials were
        # internally consistent, just for the wrong product.
        return True, f"connected; tenant_records has {n} rows (bravo confirmed)"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:160]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show-only", action="store_true",
                    help="print fingerprints without writing the file")
    args = ap.parse_args()

    secret_loader.reset_cache()
    env = secret_loader.load_env()

    missing = [k for k in KEYS if not env.get(k)]
    if missing:
        print(f"ERROR: not in the agents env: {', '.join(missing)}", file=sys.stderr)
        return 2

    print("Fingerprints — the far side must match these EXACTLY:\n")
    print(f"  {'key':<22} {'len':>5}  sha256[:16]")
    print("  " + "-" * 46)
    for k in KEYS:
        v = env[k]
        print(f"  {k:<22} {len(v):>5}  {fingerprint(v)}")

    if args.show_only:
        return 0

    body = "".join(f"{k}={env[k]}\n" for k in KEYS)
    OUT.write_text(body, encoding="utf-8")
    try:
        os.chmod(OUT, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass  # Windows ACLs differ; the file still lands outside the repo

    print(f"\nwrote {OUT}  ({len(KEYS)} lines, mode 600)")

    # Prove the file works before anyone is told to send it. Shape checks are
    # what passed on the VPS twice while the credentials were wrong.
    ok, detail = verify_bundle(OUT)
    print(f"\nverify: {'OK' if ok else 'FAILED'} — {detail}")
    if not ok:
        print("\nDO NOT SEND THIS FILE. It does not authenticate.", file=sys.stderr)
        return 1

    print("\nTransfer, then delete:")
    print(f"  scp \"{OUT}\" <user>@<vps>:/srv/sunbiz/ceo-agent/turso_vps_credentials.env")
    print(f"  del \"{OUT}\"        # PowerShell:  Remove-Item \"{OUT}\"")
    print("\nOn the VPS, merge it in (replaces any existing values for these two "
          "keys, leaves everything else alone):")
    print("""
  cd /srv/sunbiz/ceo-agent
  cp .env.agents .env.agents.bak.$(date +%s)
  grep -v -E '^(TURSO_DATABASE_URL|TURSO_AUTH_TOKEN)=' .env.agents > .env.agents.new
  cat turso_vps_credentials.env >> .env.agents.new
  mv .env.agents.new .env.agents
  chmod 600 .env.agents
  shred -u turso_vps_credentials.env 2>/dev/null || rm -f turso_vps_credentials.env
""")
    print("Then re-run step 1 of the cutover — the fingerprints must match the "
          "table above before anything is restarted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
