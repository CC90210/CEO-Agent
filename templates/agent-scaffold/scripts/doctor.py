#!/usr/bin/env python3
"""{{AGENT_NAME}} doctor — quick diagnostic on a forged agent."""
from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path

if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    print(f"{{AGENT_NAME}} doctor  —  {ROOT}")
    print()
    # 1. Self-audit
    code = subprocess.call([sys.executable, str(ROOT / "scripts" / "self_audit.py")])
    print()
    # 2. Git status if this is a repo
    if (ROOT / ".git").exists():
        subprocess.call(["git", "status", "--short"], cwd=str(ROOT))
    return code


if __name__ == "__main__":
    sys.exit(main())
