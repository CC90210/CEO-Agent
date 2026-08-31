"""Regression: origin attribution, the call that gates the Vercel exit.

`origin_of` decides whether a hostname counts as migrated. It got this wrong
once already and the exit gate reported two remaining Vercel hostnames when
there were five. The two cases that matter are both counter-intuitive:

  * A response can carry BOTH `cf-ray` and `x-vercel-id` — Cloudflare fronted it,
    Vercel produced the body. Reading `cf-ray` first calls that migrated. It is
    not: cancel the Vercel account and the page dies.
  * A redirect is a response somebody serves. Following it attributes the hop to
    the destination's host, which is how `www.breezeadvance.credit` — a 307
    served BY VERCEL to an apex that is on Workers — read as migrated.

Header dicts are built by hand rather than over the network so this stays a unit
test: it must fail on a logic regression, not on someone's wifi.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "http_probe", ROOT / "scripts" / "lib" / "http_probe.py")
hp = importlib.util.module_from_spec(_spec)
# Register BEFORE exec_module: @dataclass resolves its own module out of
# sys.modules while the class body runs, and blows up with an unhelpful
# AttributeError on NoneType if the module is not there yet.
sys.modules["http_probe"] = hp
_spec.loader.exec_module(hp)

CASES = [
    # (label, headers, expected origin)
    ("plain Cloudflare Worker",
     {"cf-ray": "abc123-YYZ", "server": "cloudflare"}, hp.WORKERS),

    ("plain Vercel",
     {"server": "Vercel", "x-vercel-id": "yul1::abc"}, hp.VERCEL),

    # THE ONE THAT CAUSED THE UNDERCOUNT. Cloudflare-proxied, Vercel-served.
    # cf-ray is present and truthful; it just answers a different question.
    ("Cloudflare in front of a live Vercel origin",
     {"cf-ray": "abc123-YYZ", "server": "cloudflare", "x-vercel-id": "yul1::xyz"},
     hp.VERCEL),

    ("Vercel identified by server header alone",
     {"server": "Vercel"}, hp.VERCEL),

    ("header casing must not matter",
     {"X-Vercel-Id": "yul1::abc"}, hp.VERCEL),

    ("neither marker",
     {"server": "nginx"}, hp.UNKNOWN),

    ("no headers at all",
     {}, hp.UNKNOWN),
]


def main() -> int:
    bad = 0
    for label, headers, expected in CASES:
        got = hp.origin_of(headers)
        ok = got == expected
        bad += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {got:12} expected={expected:12} {label}")

    # A probe that could not reach the host must never be attributed to an
    # origin — "unreachable" and "not on Vercel" are different answers, and
    # conflating them would let a down host read as migrated.
    p = hp.Probe("https://x.invalid/", None, {}, error="URLError: nope")
    ok = p.origin == hp.UNREACHABLE and not p.ok
    bad += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  {p.origin:12} expected={hp.UNREACHABLE:12} "
          f"errored probe is never attributed an origin")

    # follow=False is the default, and that default is load-bearing.
    import inspect
    sig = inspect.signature(hp.probe)
    ok = sig.parameters["follow"].default is False
    bad += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  follow default is False "
          f"(a redirect is served by someone; following it hides who)")

    print("\ntest_http_probe:", "OK" if not bad else f"{bad} FAILED")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
