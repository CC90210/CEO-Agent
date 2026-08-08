"""Empire data-backend switch — Supabase to Turso for the Python harness.

Python imports `sitecustomize` automatically at interpreter start, which is the
only place that runs before all 49 harness modules bind `create_client` via
`from supabase import create_client`. So the swap has to happen here, not in
application code.

When EMPIRE_DATA_BACKEND=turso_cloud, supabase.create_client is replaced with
the Turso compat client. Any other value (or none): this file does nothing.
Rollback is unsetting the env var.

TWO THINGS THIS FIXES, both of which made the switch a no-op off this machine:

1. PATH RESOLUTION WAS WINDOWS-ONLY.
   The previous version did `Path(__file__).resolve().parents[3] / "scripts"`.
   Windows venvs are `.venv/Lib/site-packages/`, so parents[3] is the repo root
   — correct. POSIX venvs are `.venv/lib/pythonX.Y/site-packages/`, one level
   deeper, so parents[3] is `.venv` and the import fails. On the VPS the switch
   therefore never applied. It now WALKS UP looking for the repo, so the layout
   does not matter.

2. FAILURE WAS INVISIBLE.
   It printed to stderr and continued on Supabase. A PM2 daemon discards
   stderr, so "the operator asked for Turso and silently got Supabase" produced
   no signal anywhere — which is precisely the state that keeps a cancelled
   database load-bearing. It still must never break interpreter start (every
   recovery tool is a Python process too), so instead of raising it records a
   durable marker at state/turso_switch_failed.json that the cancellation gate
   and harness health check can read.

   Set EMPIRE_TURSO_PATCH_REQUIRED=1 to make it hard-fail instead. Daemons that
   must never quietly fall back should set it.

DEPLOYMENT: this file is TRACKED. `python scripts/install_python_switch.py`
copies it into the active venv's site-packages on either platform. The previous
copy existed only inside .venv on one machine and was in no repo.
"""
import os
import sys


def _install() -> None:
    from pathlib import Path

    # Walk up from this file until the repo shows itself. Independent of venv
    # layout, and of how deep site-packages happens to be.
    marker = Path("scripts") / "lib" / "turso_supabase_compat.py"
    here = Path(__file__).resolve()
    root = None
    for parent in here.parents:
        if (parent / marker).exists():
            root = parent
            break
    if root is None:
        # Fall back to an explicit override before giving up, so an unusual
        # deployment can still be told where the repo is.
        env_root = os.environ.get("EMPIRE_REPO_ROOT")
        if env_root and (Path(env_root) / marker).exists():
            root = Path(env_root)
    if root is None:
        raise RuntimeError(
            f"could not locate the repo from {here} — no ancestor contains "
            f"{marker}. Set EMPIRE_REPO_ROOT.")

    scripts = str(root / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)

    import supabase as _supabase_mod  # noqa: PLC0415
    from lib.turso_supabase_compat import create_client as _turso_create  # noqa: PLC0415

    _supabase_mod.create_client = _turso_create
    # postgrest-py's Client symbol stays importable; only the factory swaps.


def _record_failure(exc: Exception) -> None:
    """Leave a durable trace. stderr alone is invisible under a daemon."""
    print(f"[sitecustomize] Turso backend patch FAILED — Supabase client left "
          f"in place: {exc}", file=sys.stderr)
    try:
        import json
        import socket
        from datetime import datetime, timezone
        from pathlib import Path

        for parent in Path(__file__).resolve().parents:
            if (parent / "scripts" / "lib" / "turso_supabase_compat.py").exists():
                out = parent / "state" / "turso_switch_failed.json"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps({
                    "at": datetime.now(timezone.utc).isoformat(),
                    "host": socket.gethostname(),
                    "python": sys.executable,
                    "error": str(exc),
                    "effect": "EMPIRE_DATA_BACKEND=turso_cloud was requested but "
                              "the Supabase client was NOT swapped — this process "
                              "is still writing to Supabase.",
                }, indent=2), encoding="utf-8")
                return
    except Exception:  # noqa: BLE001 — recording must never break startup
        pass


if os.environ.get("EMPIRE_DATA_BACKEND") == "turso_cloud":
    try:
        _install()
    except Exception as exc:  # noqa: BLE001 — NEVER break interpreter start
        _record_failure(exc)
        if os.environ.get("EMPIRE_TURSO_PATCH_REQUIRED") == "1":
            # Opt-in hard failure for daemons that must not fall back silently.
            raise
