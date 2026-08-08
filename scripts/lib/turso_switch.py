"""Is the Supabase->Turso data-plane switch actually live on an interpreter?

Three callers need this answer and each had its own copy: the installer
(scripts/install_python_switch.py), the machine-parity check
(scripts/machine_parity.py), and the cancellation gate
(scripts/supabase_cancellation_gate.py). All three shelled out with the same
env, compared against the same hardcoded module name, and would have drifted
independently — which matters more than usual here, because this is the check
that decides whether it is safe to cancel a database.

The question is deliberately answered by ASKING AN INTERPRETER rather than by
looking for the file. The switch is a sitecustomize.py in site-packages, so it
can be present but stale, present but shadowed by another sitecustomize earlier
on sys.path, or present but unable to import its dependencies. Every one of
those looks identical on disk and behaves like "not installed" at runtime.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

#: What `supabase.create_client.__module__` reads as once the swap has happened.
COMPAT_MODULE = "lib.turso_supabase_compat"

#: Dropped by sitecustomize when it tried to patch and could not. stderr is
#: discarded under PM2, so this file is the only durable trace.
FAILURE_MARKER = Path(__file__).resolve().parents[2] / "state" / "turso_switch_failed.json"

_PROBE = "import supabase;print(getattr(supabase.create_client,'__module__','?'))"


@dataclass(frozen=True)
class SwitchStatus:
    active: bool
    module: str
    error: str = ""

    @property
    def detail(self) -> str:
        if self.active:
            return f"installed; create_client -> {self.module}"
        if self.error:
            return self.error[:120]
        return f"create_client -> {self.module or 'no output'} (Supabase, not Turso)"


def probe(interpreter: str | None = None, timeout: int = 60) -> SwitchStatus:
    """Run the probe under EMPIRE_DATA_BACKEND=turso_cloud and report.

    The env var is forced on purpose: the caller wants to know whether the
    switch WOULD engage, not whether this shell happens to have it set.
    """
    interp = interpreter or sys.executable
    if not interp:
        return SwitchStatus(False, "", "no python interpreter available")
    try:
        proc = subprocess.run(
            [interp, "-c", _PROBE],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
            env={**os.environ, "EMPIRE_DATA_BACKEND": "turso_cloud"},
        )
    except Exception as exc:  # noqa: BLE001 — a probe must not raise on callers
        return SwitchStatus(False, "", str(exc))
    module = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
    if module == COMPAT_MODULE:
        return SwitchStatus(True, module)
    err = (proc.stderr or "").strip().splitlines()[-1:] or [""]
    return SwitchStatus(False, module, err[0] if not module else "")


def failure_record() -> dict | None:
    """The marker a failed patch left behind, if any."""
    if not FAILURE_MARKER.exists():
        return None
    try:
        import json

        return json.loads(FAILURE_MARKER.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"error": "marker exists but is unreadable", "at": "?", "host": "?"}
