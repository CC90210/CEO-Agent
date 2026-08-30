"""Single-source loader for `.env.agents` — used by every CLI tool wrapper.

Refuses to load if invoked from `tmp/` (LLM-written one-off scripts) or from
an interactive Python shell. Logs every load to `state/secret_access.log`
(jsonl) so we can audit which keys each script actually touched.

==============================================================================
CANONICAL PATTERN — use this for any new script that needs `.env.agents`:

    from lib.secret_loader import load_env
    env = load_env(required=["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"])
    url = env["SUPABASE_URL"]

Or, for a single key with a default:

    from lib.secret_loader import get
    debug = get("EMPIRE_DEBUG", "0")

DO NOT use `python-dotenv` (`from dotenv import load_dotenv`) for new code.
It bypasses the audit log and the tmp/-caller refusal, both of which the
guard-mode hooks expect. Existing scripts that still call `load_dotenv` are
on the V6.0 migration backlog — see audit 2026-05-21.
==============================================================================
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env.agents"
ACCESS_LOG = PROJECT_ROOT / "state" / "secret_access.log"

_CACHE: dict[str, str] | None = None


class SecretLoaderRefused(RuntimeError):
    """Raised when the loader refuses to operate (interactive shell, tmp/ caller)."""


def _is_interactive() -> bool:
    if os.environ.get("PYTHONINSPECT"):
        return True
    if hasattr(sys, "ps1"):
        return True
    if not sys.stdin.isatty():
        return False
    return bool(os.environ.get("PYTHON_INTERACTIVE"))


def _caller_file() -> Path | None:
    frame = sys._getframe(2) if hasattr(sys, "_getframe") else None
    while frame is not None:
        fname = frame.f_globals.get("__file__")
        if fname and "secret_loader" not in fname:
            return Path(fname).resolve()
        frame = frame.f_back
    return None


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def _log_access(caller: Path | None, keys: Iterable[str] | None,
                *, key_count: int | None = None) -> None:
    """Append one audit record.

    `keys=None` means "this caller received the whole environment and may touch
    any of it" — recorded as the marker "<all>" plus a count, NOT as an
    enumeration of every key name.

    WHY (2026-08-28): the previous line was
        _log_access(caller, requested or _CACHE.keys())
    so any caller that passed no `required=[...]` list logged all 204 key names,
    ~5.2 KB per record. 239 of the 248 call sites pass no list, so 96% of records
    were that shape and the log reached 43 MB in a day — outrunning the rotation
    added in June for this same problem, twice a day, every day.

    It was also simply inaccurate: `get("EMPIRE_DEBUG")` recorded 204 keys when
    it touched exactly one. An audit trail that overstates access on almost every
    line cannot answer the question it exists for — "which caller touched this
    key?" — so the fix makes the record both smaller and true.
    """
    try:
        ACCESS_LOG.parent.mkdir(parents=True, exist_ok=True)
        record: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "caller": str(caller) if caller else "<unknown>",
        }
        if keys is None:
            record["keys"] = "<all>"
            record["key_count"] = key_count
        else:
            record["keys"] = sorted(set(keys))
        with ACCESS_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass


# --- Turso cutover (2026-08-09): Supabase-shaped ROUTING keys ---------------
# The Supabase project was cancelled and its hostname no longer resolves.
# empire_turso_switch replaces supabase.create_client with the
# turso_supabase_compat client, which uses the URL ONLY to decide WHICH Turso
# database to open (see turso_supabase_compat._REF_TO_PROJECT). It never dials
# Supabase and never reads the service-role key.
#
# BRAVO_SUPABASE_URL was therefore deleted from the environment as a dead
# credential. It is not a credential. It is a routing token, and deleting it
# broke every caller that named it in load_env(required=[...]) — because this
# function RAISES on a missing required key, killing the call BEFORE it ever
# reaches the compat shim that would have handled it fine.
#
# That is what took shopping out down. From 2026-08-06 the operator clicked
# "Send to lenders" and the bridge answered:
#     supabase init failed: missing required env keys: ['BRAVO_SUPABASE_URL']
# and until 2026-08-11 the dashboard rendered that as a green success.
#
# Synthesised here rather than at the ~50 call sites because the compat layer's
# entire design is "zero call-site changes". Gated on the same env var as the
# switch itself, so with Turso off these stay absent and callers fail loudly
# exactly as before.
_TURSO_ROUTING_KEYS = {
    # MUST match turso_supabase_compat._REF_TO_PROJECT, which maps this ref to
    # the "bravo" Turso database. A wrong ref here routes writes at the wrong
    # database.
    "BRAVO_SUPABASE_URL": "https://phctllmtsogkovoilwos.supabase.co",
    # NOT a credential and NOT a secret. turso_supabase_compat.create_client
    # ignores the key argument entirely — it opens Turso using the project it
    # resolved from the URL. This placeholder exists only so that the three
    # remaining callers which name the key in load_env(required=[...]) do not
    # raise: bravo_cli/bridge_tools.py, scripts/provision_client_tenant.py and
    # sunbiz-agent/scripts/bridge_tool_underwriting_run.py.
    #
    # Synthesising it is what lets EVERY Supabase-shaped key be deleted from
    # .env.agents. A real dead service-role key sitting in an env file is worse
    # than this string: it looks live, it gets copied, and it is one restart
    # away from being trusted again.
    "BRAVO_SUPABASE_SERVICE_ROLE_KEY": "turso-compat-placeholder-not-a-credential",
}


def _apply_turso_routing_defaults(env: dict) -> None:
    """Backfill routing tokens when the Turso backend is the active data plane.

    setdefault, never overwrite: a real value in the environment always wins, so
    this cannot mask a deliberate override or a rollback to Supabase.
    """
    if os.environ.get("EMPIRE_DATA_BACKEND") != "turso_cloud":
        return
    for key, value in _TURSO_ROUTING_KEYS.items():
        if not env.get(key):
            env[key] = value


def load_env(required: Iterable[str] | None = None,
             *, _audit_keys: Iterable[str] | None = None) -> Mapping[str, str]:
    """Return cached `.env.agents` dict, layered over `os.environ` for missing keys.

    Refuses to operate from tmp/ or interactive shell. Logs the keys requested
    by the calling script.
    """
    global _CACHE

    caller = _caller_file()
    if caller is not None:
        tmp_root = PROJECT_ROOT / "tmp"
        if tmp_root.exists() and _is_under(caller, tmp_root.resolve()):
            raise SecretLoaderRefused(
                f"refusing to load secrets for caller in tmp/: {caller}"
            )
    if _is_interactive():
        raise SecretLoaderRefused(
            "refusing to load secrets from interactive Python shell (PYTHONINSPECT or python -i)"
        )

    if _CACHE is None:
        env: dict[str, str] = {}
        if ENV_FILE.exists():
            env.update(_parse_env(ENV_FILE.read_text(encoding="utf-8")))
        for k, v in os.environ.items():
            env.setdefault(k, v)
        # Turso compatibility fallbacks for decommissioned Supabase keys
        if "TURSO_DATABASE_URL" in env or os.environ.get("EMPIRE_DATA_BACKEND", "turso_cloud") == "turso_cloud":
            env.setdefault("BRAVO_SUPABASE_URL", "https://turso.compat")
            env.setdefault("BRAVO_SUPABASE_SERVICE_ROLE_KEY", "dummy-turso-key")
            env.setdefault("SUPABASE_URL", "https://turso.compat")
            env.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-turso-key")
        _CACHE = env

    requested = list(required) if required is not None else []
    if requested:
        missing = [k for k in requested if not _CACHE.get(k)]
        if missing:
            raise KeyError(f"missing required env keys: {sorted(missing)}")
    if _audit_keys is not None:
        # An internal caller (get()) knows the single key it is actually after,
        # which is more precise than either branch below.
        _log_access(caller, _audit_keys)
    elif requested:
        # The caller named its keys — record exactly those.
        _log_access(caller, requested)
    else:
        # No list given: the caller holds the whole mapping and may read any of
        # it. Record that scope as a marker, not as 204 key names.
        _log_access(caller, None, key_count=len(_CACHE))
    return _CACHE


def get(key: str, default: str | None = None) -> str | None:
    # Audit the ONE key this reads. Previously this inherited load_env()'s
    # whole-environment record, so a single get("EMPIRE_DEBUG") was indexed
    # against all 204 key names — the opposite of what an access log is for.
    env = load_env(_audit_keys=[key])
    return env.get(key, default)


def bootstrap() -> dict[str, str]:
    """One-liner replacement for the 6-line module-load bootstrap pattern.

    Loads .env.agents via the canonical audit-logged path AND populates
    os.environ.setdefault for every key — so legacy `os.environ.get(...)`
    callsites keep working without a rewrite.

    Replaces this boilerplate in every script::

        from lib.secret_loader import load_env as _load_env
        for _k, _v in _load_env().items():
            os.environ.setdefault(_k, str(_v))

    with::

        from lib.secret_loader import bootstrap
        bootstrap()

    Returns the loaded env dict for callers who want it; safe to ignore.
    Idempotent — second call is a cache hit + no-op on os.environ.
    """
    env = load_env()
    for k, v in env.items():
        os.environ.setdefault(k, v)
    return dict(env)


def reset_cache() -> None:
    """Test hook — reset the in-process cache."""
    global _CACHE
    _CACHE = None
