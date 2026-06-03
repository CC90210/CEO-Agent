#!/usr/bin/env python3
"""set_secret.py — safely set keys in .env.agents without an editor.

Why this exists: editing .env.agents in nano over an unstable SSH session
kept failing (nano dumped to .env.agents.save instead of saving). This tool
upserts one key at a time:

  * the value is read with getpass — it is NEVER echoed to the screen,
    NEVER stored in shell history, and NEVER passed as a command argument.
  * existing keys are replaced in place (no duplicate lines); new keys are
    appended. Every other line, comment, and ordering is preserved.
  * the write is atomic (temp file + os.replace) and the result is chmod 600.
  * a one-time timestamped backup is made on first run.

Usage (run it in YOUR terminal, not through the chat):

    cd /srv/sunbiz/ceo-agent
    .venv/bin/python scripts/set_secret.py

It loops: type a KEY name, then paste/type its value (hidden). Blank key = done.
"""
from __future__ import annotations

import getpass
import os
import sys
import time
from pathlib import Path

ENV_PATH = Path("/srv/sunbiz/ceo-agent/.env.agents").resolve()


def _load_lines() -> list[str]:
    if not ENV_PATH.exists():
        return []
    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def _upsert(lines: list[str], key: str, value: str) -> tuple[list[str], str]:
    """Replace the first `KEY=...` line, else append. Returns (lines, action)."""
    prefix = key + "="
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith(prefix) and not ln.lstrip().startswith("#"):
            lines[i] = f"{key}={value}"
            return lines, "updated"
    lines.append(f"{key}={value}")
    return lines, "added"


def _atomic_write(lines: list[str]) -> None:
    tmp = ENV_PATH.with_suffix(ENV_PATH.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, ENV_PATH)
    os.chmod(ENV_PATH, 0o600)


def main() -> int:
    if not ENV_PATH.exists():
        print(f"refusing: {ENV_PATH} does not exist", file=sys.stderr)
        return 1

    # One-time backup per run so a fat-finger is always recoverable.
    backup = ENV_PATH.with_name(f".env.agents.bak.setsecret.{int(time.time())}")
    backup.write_text(ENV_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    os.chmod(backup, 0o600)
    print(f"backup written: {backup.name}")
    print("Enter keys to set. Blank key name = finish.\n")

    lines = _load_lines()
    changed = 0
    while True:
        try:
            key = input("KEY (blank to finish): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not key:
            break
        if "=" in key or " " in key:
            print("  ! key must be a bare name like GMAIL_USER (no '=' or spaces)\n")
            continue
        value = getpass.getpass(f"  value for {key} (hidden): ").strip()
        if value == "":
            print(f"  (skipped {key}: empty value)\n")
            continue
        lines, action = _upsert(lines, key, value)
        changed += 1
        # Confirm WITHOUT revealing the value — show only its length.
        print(f"  {action} {key}  (len={len(value)})\n")

    if changed == 0:
        print("no changes made.")
        backup.unlink(missing_ok=True)
        return 0

    _atomic_write(lines)
    print(f"\nsaved {changed} key(s) to {ENV_PATH} (mode 600).")
    print("Verify with the doctor — it never prints values:")
    print("  cd /srv/sunbiz/sunbiz-agent && .venv/bin/python scripts/doctor.py --json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
