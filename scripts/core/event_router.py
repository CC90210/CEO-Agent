"""V6 Apex Phase 3 — cross-agent event-bus router daemon.

Watches the Supabase `agent_events` substrate and writes a sanitized
operations log to `state/event_router.log` (jsonl) so the dashboard's
/feed page has a single, low-latency surface for live activity.

Why a router on top of event_bus.subscribe()?
  - subscribe() dispatches on event_type → exact handler. It's optimized
    for per-agent business logic (Atlas reacts to BUDGET_LOCKED, Maven
    reacts to POST_COMPLETE, etc).
  - The router is the OBSERVABILITY layer — it sees every event regardless
    of target_agent, projects it to a uniform shape, and emits it to:
      1. state/event_router.log (jsonl)            — local audit tail
      2. agent_events (no-op; already there)       — Supabase canonical
      3. (future) per-event side-effects: Slack pings, dashboard websocket
         pushes, metric counters.

Read model:
  Tracks the highest `created_at` already routed in state/event_router.cursor.
  Each tick fetches rows WHERE created_at > cursor ORDER BY created_at ASC LIMIT N.
  This deliberately doesn't claim_events / ack_event — that's the per-agent
  consumer path. The router is read-only and lossless: it sees every row
  exactly once based on its local cursor.

CLI:
  python scripts/core/event_router.py once                  # single tick, exit
  python scripts/core/event_router.py loop --interval 3     # poll forever
  python scripts/core/event_router.py tail                  # print latest 20 to stdout

Defaults are tuned for a single CC machine. Multi-machine deployments
should run the router on ONE host only — duplicate cursors would each
emit the same event to side-effects.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# V6.8.3 structured logging — JSON-shaped error/state events go to
# state/logs/{module}.log alongside stderr. Falls back to a stub on
# import error so this daemon never fails just because the lib isn't
# on sys.path (dev environments, ad-hoc subprocess invocations).
try:
    from lib.structured_log import get_logger  # type: ignore
    _slog = get_logger("event_router")
except Exception:
    class _StubSlog:
        def info(self, *_a, **_k): pass
        def warn(self, *_a, **_k): pass
        def error(self, *_a, **_k): pass
        def critical(self, *_a, **_k): pass
    _slog = _StubSlog()


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

STATE_DIR = PROJECT_ROOT / "state"
LOG_PATH = STATE_DIR / "event_router.log"
CURSOR_PATH = STATE_DIR / "event_router.cursor"
DEFAULT_BATCH = 50

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _client():
    """Service-role Supabase client. Returns None on any failure."""
    try:
        from lib.secret_loader import load_env
    except Exception:
        return None
    try:
        env = load_env()
    except Exception:
        return None
    url = (env.get("BRAVO_SUPABASE_URL") or "").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return None
    try:
        from supabase import create_client
    except ImportError:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None


def _read_cursor() -> str:
    """ISO timestamp of the last routed event, or 1 hour ago on cold start.
    1h instead of all-time so we don't flood the log on first run."""
    if CURSOR_PATH.exists():
        try:
            text = CURSOR_PATH.read_text(encoding="utf-8").strip()
            if text:
                return text
        except OSError:
            pass
    # Cold start: 1 hour back. Tunable.
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")


def _write_cursor(ts: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CURSOR_PATH.write_text(ts, encoding="utf-8")


def _project(event: dict) -> dict:
    """Translate a raw agent_events row into the dashboard's feed shape.

    Drops noisy fields (idempotency_key, retry_count, consumed_by) and clips
    payload preview so a single event line stays scannable.
    """
    payload = event.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {"_raw": payload[:300]}
    if not isinstance(payload, dict):
        payload = {"_value": str(payload)[:300]}

    preview_keys = ("note", "preview", "agent", "kind", "lead_id",
                    "channel", "intent", "client", "platform", "post_url",
                    "amount_cad", "amount_usd", "net_mrr_usd", "v6_mode",
                    "session_id", "invoice_id")
    preview_pairs = []
    for k in preview_keys:
        if k in payload and payload[k] not in (None, ""):
            v = payload[k]
            if isinstance(v, (dict, list)):
                v = json.dumps(v)[:80]
            preview_pairs.append(f"{k}={str(v)[:80]}")
    preview = " ".join(preview_pairs) or "—"

    return {
        "id":            event.get("id"),
        "event_type":    event.get("event_type"),
        "source_agent":  event.get("source_agent") or event.get("publisher_agent") or "unknown",
        "target_agent":  event.get("target_agent") or "broadcast",
        "severity":      event.get("severity") or "info",
        "published_at":  event.get("published_at") or event.get("created_at"),
        "created_at":    event.get("created_at"),
        "status":        event.get("status") or "pending",
        "preview":       preview,
    }


def _log_jsonl(payload: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, default=str, ensure_ascii=False)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def tick(verbose: bool = False) -> int:
    """One poll cycle. Returns count of events routed."""
    client = _client()
    if client is None:
        if verbose:
            sys.stderr.write("[event_router] Supabase client unavailable; skipping tick\n")
        return 0

    cursor = _read_cursor()
    try:
        res = (
            client.table("agent_events")
            .select(
                "id, event_type, source_agent, publisher_agent, target_agent, "
                "severity, payload, published_at, created_at, status",
            )
            .gt("created_at", cursor)
            .order("created_at", desc=False)
            .limit(DEFAULT_BATCH)
            .execute()
        )
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[event_router] fetch error: {e}\n")
        return 0

    rows = res.data or []
    if not rows:
        if verbose:
            sys.stderr.write(".")
            sys.stderr.flush()
        return 0

    routed = 0
    latest = cursor
    for ev in rows:
        projected = _project(ev)
        _log_jsonl(projected)
        if verbose:
            print(f"  → {projected['event_type']:35s} src={projected['source_agent']:8s} "
                  f"tgt={projected['target_agent']:10s} {projected['preview']}",
                  flush=True)
        ts = ev.get("created_at") or ""
        if ts > latest:
            latest = ts
        routed += 1

    _write_cursor(latest)
    return routed


def loop(interval: int, verbose: bool) -> int:
    print(f"[event_router] polling every {interval}s — Ctrl-C to stop", flush=True)
    print(f"  log:    {LOG_PATH}", flush=True)
    print(f"  cursor: {_read_cursor()}", flush=True)
    total = 0
    # Round 3 R3-11: rate-limited crash alerts to CC's Telegram.
    crash_window_start = 0.0
    crash_window_count = 0
    try:
        while True:
            try:
                n = tick(verbose=verbose)
                total += n
                if n and not verbose:
                    print(f"[+{n}] routed (running total {total})", flush=True)
            except KeyboardInterrupt:
                raise
            except Exception as e:  # noqa: BLE001
                # V6.8.3: stderr print stays for live `pm2 logs` tails;
                # structured_log captures the same event for queryable
                # post-mortems in state/logs/event_router.log.
                print(f"\n[tick error] {e}", flush=True)
                _slog.error("tick_failed", error_type=type(e).__name__,
                            error=str(e)[:200], total_routed=total)
                now = time.time()
                if now - crash_window_start > 600:
                    crash_window_start = now
                    crash_window_count = 0
                if crash_window_count < 2:
                    crash_window_count += 1
                    try:
                        from notify import notify_daemon_crash  # type: ignore
                        notify_daemon_crash("event-router", str(e))
                    except Exception:
                        pass
            time.sleep(max(1, interval))
    except KeyboardInterrupt:
        print(f"\n[event_router] stopped. {total} event(s) routed total.")
        return 0


def tail(count: int) -> int:
    """Print the last N lines from the router log."""
    if not LOG_PATH.exists():
        print("(log empty — router has not ticked yet)")
        return 0
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        print(f"ERROR reading log: {e}", file=sys.stderr)
        return 1
    for line in lines[-count:]:
        try:
            ev = json.loads(line)
            print(f"{ev.get('created_at','—'):30s} {ev.get('event_type','—'):35s} "
                  f"src={ev.get('source_agent','—')} tgt={ev.get('target_agent','—')} "
                  f"{ev.get('preview','')}")
        except Exception:
            print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V6 Apex event-bus router")
    sub = p.add_subparsers(dest="command", required=True)

    once = sub.add_parser("once", help="Route any new events once, exit")
    once.add_argument("--verbose", action="store_true")
    once.set_defaults(func=lambda a: 0 if tick(verbose=a.verbose) >= 0 else 1)

    lp = sub.add_parser("loop", help="Poll continuously")
    lp.add_argument("--interval", type=int, default=3)
    lp.add_argument("--verbose", action="store_true")
    lp.set_defaults(func=lambda a: loop(a.interval, a.verbose))

    tl = sub.add_parser("tail", help="Print the last N events from the router log")
    tl.add_argument("--count", type=int, default=20)
    tl.set_defaults(func=lambda a: tail(a.count))

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
