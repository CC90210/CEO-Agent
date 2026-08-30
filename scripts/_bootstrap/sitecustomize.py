"""Empire data-backend switch — Supabase to Turso for the Python harness.

Python imports `sitecustomize` automatically at interpreter start, which is the
only place that runs before all 49 harness modules bind `create_client` via
`from supabase import create_client`. So the swap has to happen here, not in
application code.

Defaults to EMPIRE_DATA_BACKEND=turso_cloud when unset (post-Supabase
decommissioning). The only direct-Supabase escape hatch is the deliberately
verbose emergency mode EMPIRE_DATA_BACKEND=legacy_supabase_rollback. Old or
unknown backend names are rejected so a stale setting cannot silently select
the retired data plane.

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
   database load-bearing. Failure now records a durable marker at
   state/turso_switch_failed.json AND stops interpreter startup.

   This module is imported from a .pth file. Python's .pth loader catches
   ordinary Exception subclasses, so RuntimeError would still continue startup.
   The fail-closed path deliberately raises SystemExit (a BaseException) after
   recording the marker. Only explicit legacy_supabase_rollback skips the patch.

DEPLOYMENT: this file is TRACKED. `python scripts/install_python_switch.py`
copies it into the active venv's site-packages on either platform. The previous
copy existed only inside .venv on one machine and was in no repo.
"""
import os
import sys
from typing import NoReturn


TURSO_BACKEND = "turso_cloud"
LEGACY_SUPABASE_ROLLBACK_BACKEND = "legacy_supabase_rollback"
_ALLOWED_BACKENDS = {TURSO_BACKEND, LEGACY_SUPABASE_ROLLBACK_BACKEND}


def _find_root():
    """Locate the repo whose shim THIS PROCESS should use.

    Resolution order matters enormously, because one interpreter can serve
    several sibling agents. Bravo, Atlas (CFO-Agent) and Maven (CMO-Agent) each
    ship their own REGULAR `scripts/lib` package. Python binds a regular package
    to exactly one directory, so whichever repo lands on sys.path first owns
    `lib` for the whole process — and every sibling's lib.* module becomes
    invisible.

    2026-08-08: pointing EMPIRE_REPO_ROOT at Bravo to flip atlas-scheduler put
    Bravo's scripts/ first and Atlas crash-looped on
    `ModuleNotFoundError: lib.schedule_helpers`. It had been up 29h.

    So the SCRIPT BEING RUN wins. Each pm2 app runs its own repo's script, so
    each process resolves to its own repo, loads its own lib, and no sibling is
    shadowed. EMPIRE_REPO_ROOT drops to last resort: it is a global answer to a
    per-process question, which is exactly why it was the wrong first choice.
    """
    from pathlib import Path

    marker = Path("scripts") / "lib" / "turso_supabase_compat.py"

    def walk(start):
        try:
            start = Path(start).resolve()
        except Exception:  # noqa: BLE001
            return None
        for parent in (start, *start.parents):
            if (parent / marker).exists():
                return parent
        return None

    # 1. The script this interpreter was invoked with. Most specific, and the
    #    only candidate that is correct when siblings share an interpreter.
    argv0 = sys.argv[0] if sys.argv and sys.argv[0] else ""
    if argv0:
        root = walk(argv0)
        if root:
            return root

    # 2. Working directory — covers `python -m package` where argv[0] is not a
    #    path. pm2 sets cwd per app, so this is still per-process.
    root = walk(Path.cwd())
    if root:
        return root

    # 3. This file's own location — correct for a per-venv install, where
    #    site-packages sits inside the repo's .venv.
    root = walk(__file__)
    if root:
        return root

    # 4. Explicit override, LAST. Global, so it cannot distinguish siblings.
    env_root = os.environ.get("EMPIRE_REPO_ROOT")
    if env_root:
        from pathlib import Path as _P

        if (_P(env_root) / marker).exists():
            return _P(env_root)
    return None


def _install() -> None:
    root = _find_root()
    if root is None:
        raise RuntimeError(
            "could not locate a repo containing scripts/lib/"
            "turso_supabase_compat.py from the running script, the working "
            "directory, this file, or EMPIRE_REPO_ROOT. Copy the shim into "
            "this repo rather than pointing at a sibling's — a sibling's "
            "scripts/ on sys.path shadows this repo's own lib package.")

    scripts = str(root / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)

    import supabase as _supabase_mod  # noqa: PLC0415
    from lib.turso_supabase_compat import create_client as _turso_create  # noqa: PLC0415

    _supabase_mod.create_client = _turso_create
    # postgrest-py's Client symbol stays importable; only the factory swaps.


def _record_failure(exc: Exception) -> None:
    """Leave a durable trace. stderr alone is invisible under a daemon."""
    print(f"[sitecustomize] data-backend activation FAILED — startup blocked: "
          f"{exc}", file=sys.stderr)
    # Installer/health probes deliberately exercise rejected and broken modes.
    # Their subprocess failure is the evidence; writing the production marker
    # would turn a successful negative test into a false live incident.
    if os.environ.get("EMPIRE_TURSO_SWITCH_PROBE") == "1":
        return
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
                    "effect": "The requested data-backend mode could not be "
                              "activated. Process startup was blocked; no "
                              "automatic fallback to Supabase was allowed.",
                }, indent=2), encoding="utf-8")
                return
    except Exception:  # noqa: BLE001 — recording must never break startup
        pass


def _requested_backend() -> str:
    """Return the one validated startup mode; unset means Turso."""
    backend = os.environ.get("EMPIRE_DATA_BACKEND", "").strip().lower()
    backend = backend or TURSO_BACKEND
    if backend not in _ALLOWED_BACKENDS:
        allowed = ", ".join(sorted(_ALLOWED_BACKENDS))
        raise RuntimeError(
            f"invalid EMPIRE_DATA_BACKEND={backend!r}; allowed values: {allowed}. "
            "Direct Supabase is available only through the explicit emergency "
            f"mode {LEGACY_SUPABASE_ROLLBACK_BACKEND!r}.")
    return backend


def _stop_startup(exc: Exception) -> NoReturn:
    """Record the fault, then escape the .pth loader's Exception catch."""
    _record_failure(exc)
    raise SystemExit(
        "[sitecustomize] startup blocked: Turso is the required data backend "
        f"and no silent Supabase fallback is permitted ({exc})") from exc


def _activate() -> str:
    """Install Turso by default or enter the one explicit rollback mode."""
    try:
        backend = _requested_backend()
    except Exception as exc:  # noqa: BLE001 — configuration errors fail closed
        _stop_startup(exc)

    if backend == LEGACY_SUPABASE_ROLLBACK_BACKEND:
        return backend

    try:
        _install()
    except Exception as exc:  # noqa: BLE001 — patch failures fail closed
        _stop_startup(exc)
    return backend


_ACTIVE_BACKEND = _activate()
