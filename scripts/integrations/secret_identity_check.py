"""Answer "are these two keys the same credential?" without revealing either.

This question kept coming up during the Cloudflare migration and there was no
way to ask it. Twice it mattered:

  * a fuzzy matcher scored GOOGLE_CLIENT_ID against GOOGLE_CLIENT_SECRET at 1.00
    and proposed writing one into the other,
  * adversarial verification refuted GOOGLE_CLIENT_ID <- GWS_CLIENT_ID on the
    grounds that the app deliberately keeps TWO Google OAuth clients — a
    rep-facing WEB client with an https redirect URI, and a headless desktop
    client for the shared calendar. One cannot be both. If those two slots ever
    end up holding the SAME value, consent breaks in production and presents as
    a permissions bug rather than a config error.

So: compare by SHA-256 prefix. Equality and difference are both reportable; the
values never enter anyone's context. Assertions are the point — this is meant to
run in a pre-deploy gate, not to be eyeballed.

    python scripts/integrations/secret_identity_check.py --same A B
    python scripts/integrations/secret_identity_check.py --distinct A B
    python scripts/integrations/secret_identity_check.py --show A B C
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

CAPABILITY_META = {
    "category": "release.cloudflare",
    "lifecycle": "active",
    "risk": "read_only",
    "triggers": ["are these two secrets the same value",
                 "check two env keys hold different credentials",
                 "verify oauth client slots are distinct"],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": False},
}

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from lib.env_store import parse_text as _populated, digest as _digest  # noqa: E402

STORE = ROOT / ".env.agents"


def _describe(v: str) -> str:
    """Shape only — enough to spot a mis-typed slot, never enough to reuse."""
    if v.startswith(("http://", "https://")):
        return f"url({len(v)})"
    if "@" in v and " " not in v:
        return f"email({len(v)})"
    if v.endswith(".apps.googleusercontent.com"):
        return f"google-oauth-client-id({len(v)})"
    if v.startswith("GOCSPX-"):
        return f"google-oauth-client-secret({len(v)})"
    if v.startswith("eyJ") and v.count(".") == 2:
        return f"jwt({len(v)})"
    return f"opaque({len(v)})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--same", nargs=2, metavar=("A", "B"),
                    help="assert the two keys hold the SAME value")
    ap.add_argument("--distinct", nargs=2, metavar=("A", "B"),
                    help="assert the two keys hold DIFFERENT values")
    ap.add_argument("--show", nargs="+", metavar="KEY",
                    help="print digest + shape for each key")
    a = ap.parse_args()
    if not (a.same or a.distinct or a.show):
        ap.error("give --same, --distinct, or --show")

    pop = _populated(STORE.read_text(encoding="utf-8"))
    rc = 0

    def fetch(k: str) -> str | None:
        v = pop.get(k)
        if v is None:
            print(f"  ABSENT   {k}")
        return v

    for k in a.show or []:
        v = fetch(k)
        if v is not None:
            print(f"  {k:56} sha256:{_digest(v)}  {_describe(v)}")
        else:
            rc = 1

    if a.distinct:
        x, y = a.distinct
        vx, vy = fetch(x), fetch(y)
        if vx is None or vy is None:
            return 1
        if vx == vy:
            # Not a warning. Two slots the codebase keeps apart on purpose now
            # hold one credential, and the failure it causes is a login error
            # nobody will trace back to here.
            print(f"  FAIL     {x}\n           and {y}\n"
                  f"           hold the SAME value (sha256:{_digest(vx)}). "
                  f"These are required to be different credentials.")
            rc = 1
        else:
            print(f"  OK       {x} (sha256:{_digest(vx)}, {_describe(vx)})\n"
                  f"           differs from {y} (sha256:{_digest(vy)}, {_describe(vy)})")

    if a.same:
        x, y = a.same
        vx, vy = fetch(x), fetch(y)
        if vx is None or vy is None:
            return 1
        if vx != vy:
            print(f"  FAIL     {x} (sha256:{_digest(vx)}) != {y} (sha256:{_digest(vy)})")
            rc = 1
        else:
            print(f"  OK       {x} and {y} hold the same value (sha256:{_digest(vx)})")

    return rc


if __name__ == "__main__":
    sys.exit(main())
