#!/usr/bin/env python3
"""provision_maven_telegram.py -- give Maven the Telegram recipient it has never had.

WHY THIS EXISTS (2026-08-21)
    Maven's notify.py resolves a bot TOKEN fine but had no RECIPIENT, so every alert it
    "sent" for weeks resolved to zero chat ids and went nowhere -- silently, because
    notify() returns False for both "suppressed" and "failed". The value it needs already
    exists in Bravo's credential file; Maven cannot copy it across because secret_guard
    blocks an LLM from reading .env* by design, and that guard should stay exactly as it is.

    So the copy happens HERE, in a script, where the value moves machine-to-machine
    without ever entering an agent's context window. Nothing in this file prints the
    secret: the report is presence, recipient COUNT, and a short sha256 fingerprint that
    lets you confirm both repos hold the SAME value without revealing what it is.

WHY A SCRIPT AND NOT A ONE-OFF EDIT
    scripts/build_maven_env.py REGENERATES Maven's credential file from a hardcoded key
    list and writes it whole. It has no Telegram keys in that list, so a hand-added line
    would be erased the next time anyone ran it -- an action with no inverse, discovered
    only when alerts went quiet again. This script is re-runnable and idempotent, and the
    matching key list in build_maven_env.py is fixed in the same change.

CROSS-REPO CONTRACT
    MAVEN_TELEGRAM_ALLOWED_USERS is the exact key Bravo's notify.py AGENT_TOKEN_KEYS
    looks up when routing content / instagram / outreach alerts to Maven's bridge
    (scripts/notify.py:424), and the first key Maven's own _resolve_chat_ids reads
    (CMO-Agent/scripts/notify.py:119). Renaming either side silently breaks the routing.

Verbs::

    python scripts/provision_maven_telegram.py --check    # report only, write nothing
    python scripts/provision_maven_telegram.py            # provision (idempotent)
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from lib import secret_loader  # noqa: E402
from sibling_repos import SIBLING_REPOS  # noqa: E402

SOURCE_KEY = "TELEGRAM_ALLOWED_USERS"
TARGET_KEY = "MAVEN_TELEGRAM_ALLOWED_USERS"
MAVEN_ENV = SIBLING_REPOS["maven"] / ".env.agents"

SECTION_HEADER = "# --- Telegram bridge (recipient shared with Bravo) "


def fingerprint(value: str) -> str:
    """First 8 hex of sha256 -- enough to prove two files hold the same value,
    useless for recovering it."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def describe(value: str) -> str:
    ids = [c.strip() for c in value.split(",") if c.strip()]
    return f"{len(ids)} recipient(s), fingerprint {fingerprint(value)}"


def parse_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="report current state and exit without writing")
    a = ap.parse_args()

    try:
        source = (secret_loader.get(SOURCE_KEY) or "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not load {SOURCE_KEY} from Bravo: {exc}", file=sys.stderr)
        return 2

    if not source:
        print(f"ERROR: {SOURCE_KEY} is empty in Bravo's credential file -- "
              f"there is nothing to copy. Set it there first.", file=sys.stderr)
        return 2

    print(f"bravo   {SOURCE_KEY}: {describe(source)}")

    if not MAVEN_ENV.exists():
        print(f"ERROR: Maven credential file not found at {MAVEN_ENV}", file=sys.stderr)
        return 2

    existing = parse_env(MAVEN_ENV)
    current = (existing.get(TARGET_KEY) or "").strip()

    if current:
        print(f"maven   {TARGET_KEY}: {describe(current)}")
        if current == source:
            print("\nAlready provisioned and matching -- nothing to do.")
            return 0
        if a.check:
            print("\nDIVERGED: Maven holds a different value than Bravo. "
                  "Re-run without --check to overwrite.")
            return 1
    else:
        print(f"maven   {TARGET_KEY}: MISSING")
        if a.check:
            print("\nNOT PROVISIONED. Re-run without --check to fix.")
            return 1

    text = MAVEN_ENV.read_text(encoding="utf-8")
    backup = MAVEN_ENV.parent / ".env.agents.bak.pre_telegram"
    backup.write_text(text, encoding="utf-8")
    print(f"\nBackup: {backup.name}")

    if current:
        # Replace the existing assignment in place, preserving file order.
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{TARGET_KEY}="):
                lines[i] = f"{TARGET_KEY}={source}"
                break
        new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
        action = "updated"
    else:
        sep = "" if text.endswith("\n") else "\n"
        new_text = (
            f"{text}{sep}\n"
            f"{SECTION_HEADER}{'-' * max(0, 71 - len(SECTION_HEADER))}\n"
            f"# Set by scripts/provision_maven_telegram.py (Bravo). Same value as Bravo's\n"
            f"# {SOURCE_KEY}. Without it, every Maven alert resolves to zero\n"
            f"# recipients and is dropped silently.\n"
            f"{TARGET_KEY}={source}\n"
        )
        action = "added"

    MAVEN_ENV.write_text(new_text, encoding="utf-8")

    verify = (parse_env(MAVEN_ENV).get(TARGET_KEY) or "").strip()
    if verify != source:
        print("ERROR: post-write verification FAILED -- value did not persist.",
              file=sys.stderr)
        return 2

    print(f"{action.upper()}: {TARGET_KEY} -> {describe(verify)}")
    print("Verified by re-reading the file. Fingerprints above should match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
