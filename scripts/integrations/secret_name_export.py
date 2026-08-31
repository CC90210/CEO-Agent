"""secret_name_export.py — export KEY NAMES ONLY from the agents store.

Exists so a semantic matcher can reason about naming without any value ever
leaving the store. Key NAMES are not secrets; values are, and none are read
into the output, printed, or returned.

The mechanical matcher (`secret_fuzzy_match.py`) scores token overlap, so a key
renamed to something with no shared tokens — `BREEZE_ENCRYPTION_KEY` stored as
`CREDPORT_AES_KEY`, say — scores zero and reads as "absent". That is a limit of
the method, not a fact about the file, and claiming "absent under any name" on
mechanical evidence alone overstates it. This export is what lets a semantic
pass check the same question properly.

    python scripts/integrations/secret_name_export.py            # summary
    python scripts/integrations/secret_name_export.py --json     # names as JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CAPABILITY_META = {
    "category": "release.cloudflare",
    "lifecycle": "active",
    "risk": "read_only",
    "triggers": ["export env key names", "list secret names for matching"],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": False},
}

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / ".env.agents"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    populated: list[str] = []
    gaps: list[str] = []
    for raw in STORE.read_text(encoding="utf-8", errors="replace").splitlines():
        s = raw.strip()
        if s.startswith("# FILL ") and "=" in s:
            gaps.append(s[len("# FILL "):].split("=", 1)[0].strip())
            continue
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        if k.strip() and v.strip():
            populated.append(k.strip())

    if args.json:
        json.dump({"populated": sorted(populated), "gaps": sorted(gaps)},
                  sys.stdout, indent=1)
        return 0
    print(f"populated key names: {len(populated)}")
    print(f"outstanding gap names: {len(gaps)}")
    print("(names only — no value is read into this output)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
