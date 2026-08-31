"""The Vercel exit gate's exemption lists must stay accountable.

vercel_exit_report.py carries three dicts that each stop something holding a
gate closed:

    KNOWN_BROKEN      pre-existing failures      (fleet health)
    KNOWN_INCOMPLETE  knowingly-incomplete apps  (data plane)
    OPERATOR_ACCEPTED decisions CC has made      (Vercel residency)

Every one of them says, in its own comment, that it needs a reason and a removal
condition "or this becomes a place to hide real breakage". That was true and
enforced by nothing — and the gate they weaken is the one that authorises
deleting production deployments.

What this can enforce mechanically:
  * every entry carries a substantive reason, not a shrug,
  * every dict documents how its entries get REMOVED,
  * an operator decision is dated, so a stale one is visible rather than
    inherited forever.

What it cannot: whether an exemption is still TRUE. That needs the live checks
the gate itself runs. So this prints the full inventory every run — an exemption
you can see is one somebody might delete.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "scripts" / "vercel_exit_report.py"

_spec = importlib.util.spec_from_file_location("vercel_exit_report", SRC)
mod = importlib.util.module_from_spec(_spec)
sys.modules["vercel_exit_report"] = mod
try:
    _spec.loader.exec_module(mod)
except SystemExit:
    pass

MIN_REASON = 20
DICTS = ("KNOWN_BROKEN", "KNOWN_INCOMPLETE", "OPERATOR_ACCEPTED")
# An operator decision without a date cannot be aged out by a later reader.
DATED = ("OPERATOR_ACCEPTED",)
DATE_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")


def main() -> int:
    bad = 0
    source = SRC.read_text(encoding="utf-8")

    for name in DICTS:
        d = getattr(mod, name, None)
        if d is None:
            print(f"  FAIL    {name}: not defined — did it get renamed?")
            bad += 1
            continue

        # The dict must document its own exit route, in the comment block above
        # it. Matched case-insensitively: the requirement is that a removal
        # condition is WRITTEN DOWN, not that it is shouted.
        block = source.split(f"{name}")[0][-1600:].lower()
        if "remove when" not in block and "removal condition" not in block:
            print(f"  FAIL    {name}: no documented removal condition near its definition")
            bad += 1

        if not d:
            print(f"  OK      {name}: empty (nothing exempted)")
            continue

        for key, reason in sorted(d.items()):
            problems = []
            if not isinstance(reason, str) or len(reason.strip()) < MIN_REASON:
                problems.append(f"reason under {MIN_REASON} chars")
            if name in DATED and not DATE_RE.search(reason or ""):
                problems.append("operator decision carries no date")
            if problems:
                print(f"  FAIL    {name}[{key}]: {'; '.join(problems)}")
                bad += 1
            else:
                print(f"  OK      {name}[{key}]")

    # Inventory, always. Exemptions accumulate silently; printing them is the
    # cheapest defence against that.
    total = sum(len(getattr(mod, n, {}) or {}) for n in DICTS)
    print(f"\n  exemptions in force: {total}")
    for name in DICTS:
        for key, reason in sorted((getattr(mod, name, {}) or {}).items()):
            print(f"    {name:18} {key:26} {reason[:70]}")

    print("\ntest_exit_gate_exemptions:", "OK" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
