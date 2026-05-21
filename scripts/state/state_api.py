"""V6.0 read-only state API — FastAPI service consumed by the Command Center.

This module is a thin composition layer. It does NOT query the state DB
directly — `state_manager.status()` is the single source of truth for that.
It does NOT query the FTS index directly — `memory_retriever.status()` owns
that. This service's actual job is:

  - HTTP transport over the canonical helpers
  - Tailing the guard JSONL audit logs (the one piece of data not in any DB)
  - Composing all of the above into a single dashboard payload

If you find yourself writing a SELECT here, stop — extend `state_manager.py`
or `memory_retriever.py` and call it from here.

Endpoints:
  GET /health     → 200 ok (liveness, no auth required)
  GET /status     → V6.0 system overview (db + index + guards)
  GET /guards     → just the guard tail summaries
  GET /retrieval  → memory_retriever.py status

Run locally:
    uvicorn state_api:app --host 0.0.0.0 --port 8500
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import state_manager        # noqa: E402  — single source of truth for state DB
import memory_retriever     # noqa: E402  — single source of truth for FTS index
from lib.hook_runtime import mode_from_env, state_log_path  # noqa: E402
from lib.rate_limiter import RateLimiter  # noqa: E402

# V6.8.3 rate limiter — token bucket per client IP. 20 req/s steady-state,
# burst up to 60. Tuned for a dashboard polling every 5s plus normal API use.
_LIMITER = RateLimiter(rate=20, burst=60, name="state-api")

# Map dashboard guard names → env vars. Defaults match the Phase 1 safe-mode.
HOOK_MODE_ENV = {
    "exec_guard":   ("EMPIRE_HOOK_EXEC_GUARD",   "report"),
    "secret_guard": ("EMPIRE_HOOK_SECRET_GUARD", "report"),
    "state_guard":  ("EMPIRE_HOOK_STATE_GUARD",  "off"),
}

# Logs we tail for the dashboard. secret_access has no enforcement mode
# (it's an access ledger, not a guard) so it skips the mode lookup.
GUARD_LOGS = {
    "exec_guard":     state_log_path("exec_guard"),
    "secret_guard":   state_log_path("secret_guard"),
    "state_guard":    state_log_path("state_guard"),
    "secret_access":  state_log_path("secret_access"),
}

app = FastAPI(title="Bravo V6.0 State API", version="6.8.3")


@app.middleware("http")
async def _rate_limit(request: Request, call_next):
    # /health is exempt — never throttle the liveness probe.
    if request.url.path == "/health":
        return await call_next(request)
    client_id = (request.client.host if request.client else "unknown")
    decision = _LIMITER.check(client_id)
    if not decision.allowed:
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limited", "retry_after": int(round(decision.retry_after))},
            headers=decision.as_headers(),
        )
    response = await call_next(request)
    for k, v in decision.as_headers().items():
        response.headers.setdefault(k, v)
    return response


# ── Helpers ──────────────────────────────────────────────────────────────

def _tail_jsonl(path: Path, n: int = 500) -> list[dict[str, Any]]:
    """Cheap reverse-read of the last `n` JSONL records. Tolerates malformed lines.

    The guard logs grow slowly (one line per blocked op), so reading the tail
    256KB and parsing is plenty for dashboard summaries.
    """
    import json
    if not path.exists():
        return []
    try:
        with path.open("rb") as fh:
            try:
                fh.seek(0, 2)
                size = fh.tell()
                read = min(size, 256 * 1024)
                fh.seek(size - read)
                tail_bytes = fh.read(read)
            except OSError:
                fh.seek(0)
                tail_bytes = fh.read()
        lines = tail_bytes.decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for raw in lines[-n:]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except Exception:
            continue
    return out


def _summarize_guard(name: str, log_path: Path) -> dict[str, Any]:
    rows = _tail_jsonl(log_path)
    blocked = [r for r in rows if r.get("decision") == "blocked"]
    would_block = [r for r in rows if r.get("decision") == "would-block"]
    by_layer: dict[str, int] = {}
    for r in blocked + would_block:
        layer = r.get("layer", "?")
        by_layer[layer] = by_layer.get(layer, 0) + 1
    last = rows[-1] if rows else None
    summary: dict[str, Any] = {
        "exists": log_path.exists(),
        "tail_count": len(rows),
        "blocked_count": len(blocked),
        "would_block_count": len(would_block),
        "by_layer": by_layer,
        "last_event_ts": last.get("ts") if last else None,
        "last_decision": last.get("decision") if last else None,
    }
    if name in HOOK_MODE_ENV:
        env_name, default = HOOK_MODE_ENV[name]
        summary["mode"] = mode_from_env(env_name, default=default)
    return summary


# ── Endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> JSONResponse:
    """Liveness + lightweight readiness probe.

    Returns 200 with `status: healthy` when all sub-checks pass, 200 with
    `status: degraded` when something secondary (memory index, disk space)
    is unhealthy, and 503 when the primary state DB is unreachable.
    """
    import shutil as _shutil

    checks: dict[str, dict[str, Any]] = {}

    # State DB
    try:
        db_status = state_manager.status()
        checks["database"] = {"status": "ok", "v6_mode": db_status.get("v6_mode", "?")}
    except Exception as exc:  # noqa: BLE001
        checks["database"] = {"status": "down", "error": type(exc).__name__}

    # Memory index
    try:
        idx_status = memory_retriever.status()
        chunks = idx_status.get("chunk_count", idx_status.get("chunks", 0))
        checks["memory_index"] = {"status": "ok" if chunks else "warn", "chunks": chunks}
    except Exception as exc:  # noqa: BLE001
        checks["memory_index"] = {"status": "warn", "error": type(exc).__name__}

    # Disk space (state/ dir)
    try:
        usage = _shutil.disk_usage(str(PROJECT_ROOT / "state"))
        free_gb = round(usage.free / (1024 ** 3), 1)
        pct_used = round((usage.used / usage.total) * 100, 1) if usage.total else 0
        checks["disk_space"] = {
            "status": "ok" if pct_used < 80 else "warn",
            "free_gb": free_gb,
            "pct_used": pct_used,
        }
    except OSError as exc:
        checks["disk_space"] = {"status": "warn", "error": str(exc)}

    primary_down = checks["database"]["status"] == "down"
    any_degraded = any(c["status"] not in ("ok",) for c in checks.values())
    overall = "down" if primary_down else ("degraded" if any_degraded else "healthy")
    status_code = 503 if primary_down else 200

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "version": app.version,
            "checks": checks,
        },
    )


@app.get("/status")
def status() -> JSONResponse:
    """Dashboard-shaped overview composed from canonical helpers."""
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "v6_mode": os.environ.get("EMPIRE_V6_MODE", "off").lower(),
        "deploy_target": os.environ.get("EMPIRE_DEPLOY_TARGET", "unknown"),
        "state_db": state_manager.status(),
        "index_db": memory_retriever.status(),
        "guards": {name: _summarize_guard(name, path) for name, path in GUARD_LOGS.items()},
    }
    return JSONResponse(content=payload)


@app.get("/guards")
def guards() -> dict[str, Any]:
    """Just the guard tails — cheaper poll for the dashboard."""
    return {name: _summarize_guard(name, path) for name, path in GUARD_LOGS.items()}


@app.get("/retrieval")
def retrieval() -> dict[str, Any]:
    """Memory retriever index health — pure delegation."""
    return memory_retriever.status()
