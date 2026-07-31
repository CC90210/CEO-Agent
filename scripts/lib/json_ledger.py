"""json_ledger.py — the small on-disk JSON ledger idiom, in one place.

Several loops need to remember "have I already handled this?" across process
restarts: the inbound-email Message-ID ledger, the review-thread seen-set, the
review-harvest queue. Each is a dict persisted to tmp/, written atomically, and
capped so it cannot grow without bound.

email_engine keeps its own proven copy (_load/_save_processed_msgids) — it is
load-bearing on the CASL/idempotency path and not worth re-plumbing. This module
is the shared implementation for everything written since.

    from lib.json_ledger import load_ledger, save_ledger

    seen = load_ledger(PATH)
    seen[key] = now_iso
    save_ledger(PATH, seen, cap=5000)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_ledger(path: Path) -> dict[str, Any]:
    """Read a JSON dict ledger. Any problem returns {} — a ledger that fails to
    load must degrade to "nothing seen yet" (work gets redone, which is safe)
    rather than raising and taking the caller down with it."""
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:  # noqa: BLE001
        pass
    return {}


def save_ledger(path: Path, data: dict[str, Any], *, cap: int | None = None,
                indent: int | None = None) -> bool:
    """Persist atomically. Returns True on success.

    Atomic tmp+replace matters: these files are read by a fresh process every
    cron tick, and a torn write would look like a corrupt ledger and silently
    reset the loop's memory.

    `cap` keeps the most-recent N entries by stored value, which works because
    every caller stores an ISO timestamp. Callers whose values are not sortable
    should pass cap=None.
    """
    try:
        if cap is not None and len(data) > cap:
            data = dict(sorted(data.items(), key=lambda kv: str(kv[1]),
                               reverse=True)[:cap])
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=indent), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[json_ledger] could not persist {path.name}: {exc}")
        return False
