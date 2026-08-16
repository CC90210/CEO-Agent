"""
Bravo V6.0 — Webhook Listener (FastAPI)

Single public entrypoint on the VPS for:
  - Stripe webhooks  (subscription lifecycle, invoice events)
  - N8N inbound     (form submissions, classifier outputs)
  - Telegram updates (if we migrate off long-polling)

All real work gets handed to the event bus — the webhook handler writes one
agent_events row and returns 200 immediately. Consumers elsewhere pick it up.

Run locally (from project root):
    cd scripts && uvicorn webhook_listener:app --reload --port 8000

Run in prod (see infra/docker-compose.yml — working_dir: /app/scripts):
    uvicorn webhook_listener:app --host 0.0.0.0 --port 8000 \
        --proxy-headers --forwarded-allow-ips='*'

Endpoints:
    GET  /healthz                    → "ok"
    POST /webhooks/stripe            → Stripe signature-verified events
    POST /webhooks/n8n/{hook}        → catch-all N8N forwards
    POST /webhooks/telegram          → Telegram update passthrough
    GET  /stats                      → per-hook counters (internal)

Security:
  - Stripe signature verified via STRIPE_WEBHOOK_SECRET in .env.agents
  - N8N routes require a static header X-Bravo-Token matching WEBHOOK_N8N_TOKEN
  - Telegram routes verify secret_token per Telegram's setWebhook payload
  - No secrets are logged. Bodies are hashed (sha256) for dedup.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    from fastapi import FastAPI, HTTPException, Request, status
    from fastapi.responses import JSONResponse, PlainTextResponse
except ImportError as e:  # pragma: no cover — import error surfaces on `pip install`
    raise RuntimeError(
        "fastapi+uvicorn required for webhook_listener. "
        "Install via: pip install fastapi uvicorn[standard]"
    ) from e

from event_bus import publish as bus_publish  # noqa: E402

# V6.8.3 structured logging — JSON-shaped error/state events go to
# state/logs/{module}.log alongside stderr. Falls back to a stub on
# import error so this daemon never fails just because the lib isn't
# on sys.path (dev environments, ad-hoc subprocess invocations).
try:
    from lib.structured_log import get_logger  # type: ignore
    _slog = get_logger("webhook_listener")
except Exception:
    class _StubSlog:
        def info(self, *_a, **_k): pass
        def warn(self, *_a, **_k): pass
        def error(self, *_a, **_k): pass
        def critical(self, *_a, **_k): pass
    _slog = _StubSlog()


# V6.8.3 rate limiter — webhooks are public, so the bucket is more permissive
# than state_api but still capped. Stripe sends bursts of related events; n8n
# may retry on transient 5xx. 60 req/s steady-state, burst to 120.
try:
    from lib.rate_limiter import RateLimiter  # type: ignore
    _LIMITER = RateLimiter(rate=60, burst=120, name="webhook-listener")
except ImportError:
    _LIMITER = None  # rate-limiting disabled if lib/ unavailable (dev env)

# ---- Env ------------------------------------------------------------------

def _load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env.agents"
    if not env_path.exists():
        return {}
    env: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = _load_env()
STRIPE_WEBHOOK_SECRET = ENV.get("STRIPE_WEBHOOK_SECRET", "")
WEBHOOK_N8N_TOKEN = ENV.get("WEBHOOK_N8N_TOKEN", "")
TELEGRAM_SECRET_TOKEN = ENV.get("TELEGRAM_WEBHOOK_SECRET", "")

# In-memory counters for /stats (durability not required — Supabase agent_events
# is the real ledger).
_COUNTERS: dict[str, int] = {"stripe": 0, "n8n": 0, "telegram": 0, "rejected": 0}


app = FastAPI(title="Bravo Webhook Listener", version="6.8.3", docs_url=None, redoc_url=None)


@app.middleware("http")
async def _rate_limit(request: Request, call_next):
    # /healthz and /health are exempt — never throttle liveness probes.
    if request.url.path in ("/healthz", "/health"):
        return await call_next(request)
    if _LIMITER is None:
        return await call_next(request)
    client_id = (request.client.host if request.client else "unknown")
    decision = _LIMITER.check(client_id)
    if not decision.allowed:
        # V6.8.3: structured-log every 429 so abusive clients show up in
        # state/logs/webhook_listener.log for the error_knowledge_pipeline.
        _slog.warn("rate_limited", client_id=client_id, path=request.url.path,
                   retry_after=round(decision.retry_after, 2))
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limited", "retry_after": int(round(decision.retry_after))},
            headers=decision.as_headers(),
        )
    response = await call_next(request)
    for k, v in decision.as_headers().items():
        response.headers.setdefault(k, v)
    return response


# ---- Helpers --------------------------------------------------------------

def _verify_stripe_sig(payload: bytes, sig_header: str, secret: str,
                      tolerance_seconds: int = 300) -> bool:
    """Minimal Stripe signature verification without pulling the stripe SDK
    into the webhook image. Public algorithm — Stripe documents it."""
    if not sig_header or not secret:
        return False
    parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
    ts = parts.get("t")
    v1 = parts.get("v1")
    if not ts or not v1:
        return False
    try:
        if abs(time.time() - int(ts)) > tolerance_seconds:
            return False
    except ValueError:
        return False
    signed_payload = f"{ts}.".encode() + payload
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)


def _body_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:16]


# ---- Routes ---------------------------------------------------------------

@app.get("/healthz", include_in_schema=False)
async def healthz() -> PlainTextResponse:
    return PlainTextResponse("ok", status_code=200)


@app.get("/health", include_in_schema=False)
async def health() -> JSONResponse:
    """V6.8.3 enriched health endpoint — same shape as state_api /health so
    `verify_deploy` + the dashboard can poll both with one schema."""
    from datetime import datetime, timezone
    checks: dict[str, dict[str, Any]] = {
        "secrets": {
            "status": "ok" if STRIPE_WEBHOOK_SECRET and (WEBHOOK_N8N_TOKEN or TELEGRAM_SECRET_TOKEN) else "warn",
            "stripe_secret": bool(STRIPE_WEBHOOK_SECRET),
            "n8n_token": bool(WEBHOOK_N8N_TOKEN),
            "telegram_token": bool(TELEGRAM_SECRET_TOKEN),
        },
        "counters": {"status": "ok", **dict(_COUNTERS)},
    }
    any_degraded = any(c["status"] not in ("ok",) for c in checks.values())
    return JSONResponse(
        status_code=200,
        content={
            "status": "degraded" if any_degraded else "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "version": app.version,
            "checks": checks,
        },
    )


@app.get("/stats", include_in_schema=False)
async def stats() -> dict[str, Any]:
    return {"counters": dict(_COUNTERS), "as_of": time.time()}


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request) -> JSONResponse:
    raw = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    if not _verify_stripe_sig(raw, sig, STRIPE_WEBHOOK_SECRET):
        _COUNTERS["rejected"] += 1
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad signature")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        _COUNTERS["rejected"] += 1
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad json")

    event_type = f"stripe.{payload.get('type', 'unknown')}"
    idem = f"stripe:{payload.get('id', _body_hash(raw))}"
    result = bus_publish(
        event_type=event_type,
        payload=payload,
        source="webhook_stripe",
        severity="info",
        idempotency_key=idem,
    )
    _COUNTERS["stripe"] += 1
    return JSONResponse({"status": "accepted", "bus": result.get("status")})


@app.post("/webhooks/n8n/{hook}")
async def n8n_webhook(hook: str, request: Request) -> JSONResponse:
    token = request.headers.get("X-Bravo-Token", "")
    if not WEBHOOK_N8N_TOKEN or not hmac.compare_digest(token, WEBHOOK_N8N_TOKEN):
        _COUNTERS["rejected"] += 1
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad token")
    raw = await request.body()
    try:
        payload: Any = json.loads(raw.decode("utf-8")) if raw else {}
    except json.JSONDecodeError:
        payload = {"raw": raw.decode("utf-8", errors="replace")}
    result = bus_publish(
        event_type=f"n8n.{hook}",
        payload={"hook": hook, "body": payload},
        source="webhook_n8n",
        severity="info",
        idempotency_key=f"n8n:{hook}:{_body_hash(raw)}",
    )
    _COUNTERS["n8n"] += 1
    return JSONResponse({"status": "accepted", "bus": result.get("status")})


@app.post("/webhooks/telegram")
async def telegram_webhook(request: Request) -> JSONResponse:
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    # Fail CLOSED when the token is unconfigured. This previously read
    # `if TELEGRAM_SECRET_TOKEN and not hmac.compare_digest(...)`, so an unset
    # TELEGRAM_WEBHOOK_SECRET made the whole condition false and every unverified
    # update was accepted and published onto the agent event bus — the check was
    # present in review and absent in any environment where the var was never set.
    # Both siblings in this file already fail closed: the n8n gate below at
    # `not WEBHOOK_N8N_TOKEN or not hmac.compare_digest(...)` and
    # `_verify_stripe_sig`'s `if not sig_header or not secret: return False`.
    # Telegram was the only one of the three that did not. (2026-08-15, point 16.)
    if not TELEGRAM_SECRET_TOKEN or not hmac.compare_digest(secret, TELEGRAM_SECRET_TOKEN):
        _COUNTERS["rejected"] += 1
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad secret")
    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        _COUNTERS["rejected"] += 1
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad json")
    update_id = payload.get("update_id")
    result = bus_publish(
        event_type="telegram.update",
        payload=payload,
        source="webhook_telegram",
        severity="info",
        idempotency_key=f"tg:{update_id}" if update_id else None,
    )
    _COUNTERS["telegram"] += 1
    return JSONResponse({"status": "accepted", "bus": result.get("status")})


# ---- Entrypoint ------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run("webhook_listener:app", host="0.0.0.0", port=8000, reload=False)
