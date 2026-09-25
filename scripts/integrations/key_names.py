"""List the NAMES (never values) of env-store keys matching a pattern.

    python scripts/integrations/key_names.py wise
    python scripts/integrations/key_names.py stripe --store atlas

Answers "is a key for X present, and under what name?" without anyone reading
the store. `--store atlas` looks in CFO-Agent's store (Atlas's keys).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.env_store import key_names  # noqa: E402
from lib.secret_loader import ENV_FILE  # noqa: E402

STORES = {"bravo": ENV_FILE, "atlas": Path("C:/Users/User/APPS/CFO-Agent/.env.agents")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pattern", help="case-insensitive regex matched against key names")
    ap.add_argument("--store", choices=sorted(STORES), default="bravo")
    args = ap.parse_args()
    path = STORES[args.store]
    if not path.exists():
        print(f"{args.store}: store not found")
        return 1
    rx = re.compile(args.pattern, re.IGNORECASE)
    names = sorted(n for n in key_names(path.read_text(encoding="utf-8")) if rx.search(n))
    print(f"{args.store}: {len(names)} key name(s) matching /{args.pattern}/i")
    for n in names:
        print(f"  {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
