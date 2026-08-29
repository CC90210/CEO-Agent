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
  python scripts/core/event_router.py suppressed            # open suppression windows

Defaults are tuned for a single CC machine. Multi-machine deployments
should run the router on ONE host only — duplicate cursors would each
emit the same event to side-effects.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# sys.path setup MUST happen before importing anything under `lib.*` — otherwise
# the auto-added scripts/core/ on sys.path[0] doesn't expose lib/, the first
# `from lib.X import Y` fails, and Python's import-state cache makes every
# subsequent `from lib.Y import Z` fail too (the silent "Supabase client
# unavailable" bug debugged 2026-06-06).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

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


def _env_int(name: str, default: int) -> int:
    """Operator tunable. A typo must be loud, not silently reinterpreted — a
    mis-set budget changes what the log shows and nothing else would say so."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        sys.stderr.write(f"[event_router] {name}={raw!r} is not an integer; "
                         f"using {default}\n")
        _slog.error("bad_tunable", name=name, value=str(raw)[:80], using=default)
        return default


STATE_DIR = PROJECT_ROOT / "state"
LOG_PATH = STATE_DIR / "event_router.log"
CURSOR_PATH = STATE_DIR / "event_router.cursor"
DEFAULT_BATCH = 50

# ---- Repeat suppression -----------------------------------------------------
#
# Measured against the live bus 2026-08-29: 104,680 of 118,541 agent_events rows
# (88%) are TEXTTORRENT_UNMAPPED_DID, and 2,547 of the 2,560 lines then in
# state/event_router.log (99.5%) were that one warning. Behind those 104,680
# rows sit exactly 12 distinct (tenant_id, destination_last4) DIDs: one inbound
# SMS to a number with no tenant mapping, re-reported per message by a producer
# outside this repo (SunBiz/TextTorrent, see scripts/core/event_retention.py).
# Mapping the DIDs is a SunBiz handoff. What the router owes the operator
# meanwhile is a tail a human can still read.
#
# So the first SUPPRESS_BUDGET occurrences of a key inside a window log
# normally, the rest are counted, and the count is emitted as a rollup line when
# the window closes. Nothing vanishes: the canonical row stays in agent_events
# either way, and a suppressed run always ends in a line that names its size.
SUPPRESS_STATE_PATH = STATE_DIR / "event_router.suppress.json"
SUPPRESS_WINDOW_SEC = _env_int("EMPIRE_ROUTER_SUPPRESS_WINDOW_SEC", 3600)
# Two budgets, because the two cases are genuinely different.
#
# An event type listed in IDENTITY_FIELDS has been measured as a recurring
# per-identity CONDITION — the same fact restated once per inbound message. The
# second report of it carries no information the first did not, so one line per
# identity per window is the entire signal. With 12 DIDs that is 12 lines plus
# 12 rollups an hour, against roughly 15 real events an hour on the rest of the
# bus: a log a human can actually read. A laxer 20 would leave 240 flood lines
# an hour still burying everything else, which is not a fix.
SUPPRESS_BUDGET_RECURRING = _env_int("EMPIRE_ROUTER_SUPPRESS_BUDGET_RECURRING", 1)
# Everything else is presumed distinct per occurrence — a lead opening a mail is
# not a restatement of the previous lead opening one — so this is a burst
# ceiling, not a dedup. Per-hour rates over the bus's whole history: every type
# other than the flood sits at p50 1-10/hr, and only BRAVO_EMAIL_OPENED ever
# brushes 20 (107/hr, in 1 of its 948 active hours). So in practice this fires
# only on a genuinely new flood — and even then the rollup names what it held.
SUPPRESS_BUDGET_DEFAULT = _env_int("EMPIRE_ROUTER_SUPPRESS_BUDGET", 20)
# An unmapped-DID producer is finite (12 identities today), but a future producer
# could mint a fresh identity per event. Cap the tracked set so this daemon's
# footprint stays bounded on a machine that also runs everything else.
SUPPRESS_MAX_KEYS = _env_int("EMPIRE_ROUTER_SUPPRESS_MAX_KEYS", 2000)
ROLLUP_EVENT_TYPE = "ROUTER_SUPPRESSION_SUMMARY"
# event_bus.py:166 accepts info/warn/error/critical. An error storm is exactly
# what rate limiting is for, but a critical is rare by construction and its one
# line is the whole point of it — never withhold one.
NEVER_SUPPRESS_SEVERITY = frozenset({"critical"})

# Which payload fields identify "the same recurring problem" for an event type.
# Verified against live rows 2026-08-29: a TEXTTORRENT_UNMAPPED_DID payload is
# {tenant_id, destination_last4, provider_message_id}, and provider_message_id
# is a per-message fingerprint — unique on every single event. Keying on the
# whole payload would therefore suppress precisely nothing.
# Event types absent from this map fall back to (event_type, source_agent),
# which still rate-limits an unknown future flood without this file guessing at
# a payload shape nobody has looked at yet.
IDENTITY_FIELDS: dict[str, tuple[str, ...]] = {
    "TEXTTORRENT_UNMAPPED_DID": ("tenant_id", "destination_last4"),
}

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _client():
    """Service-role Supabase client. Returns None on any failure.

    Each return-None path emits both a stderr breadcrumb (for `pm2 logs`
    tails) AND a structured-log error event (for queryable post-mortems
    via state/logs/event_router.log). The dual-write matches the
    `tick_failed` pattern in loop().
    """
    def _fail(step: str, err: str) -> None:
        sys.stderr.write(f"[event_router/_client] {step}: {err}\n")
        _slog.error("client_unavailable", step=step, error=err[:200])

    try:
        from lib.secret_loader import load_env
    except Exception as e:
        _fail("secret_loader_import", str(e))
        return None
    try:
        env = load_env()
    except Exception as e:
        _fail("load_env", f"{type(e).__name__}: {e}")
        return None
    url = (env.get("BRAVO_SUPABASE_URL") or "https://bravo.turso.compat").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "turso-compat-key").strip()
    if not url or not key:
        _fail("env_missing", "BRAVO_SUPABASE_URL or _SERVICE_ROLE_KEY missing/empty")
        return None
    try:
        from supabase import create_client
    except ImportError as e:
        _fail("supabase_import", str(e))
        return None
    try:
        return create_client(url, key)
    except Exception as e:
        _fail("create_client", f"{type(e).__name__}: {e}")
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
    return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")


def _write_cursor(ts: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CURSOR_PATH.write_text(ts, encoding="utf-8")


def _payload_dict(event: dict) -> dict:
    """agent_events.payload as a dict — producers hand it over as JSON text or
    as a decoded object depending on the driver, so both shapes arrive here."""
    payload = event.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {"_raw": payload[:300]}
    if not isinstance(payload, dict):
        payload = {"_value": str(payload)[:300]}
    return payload


def _project(event: dict, payload: dict | None = None) -> dict:
    """Translate a raw agent_events row into the dashboard's feed shape.

    Drops noisy fields (idempotency_key, retry_count, consumed_by) and clips
    payload preview so a single event line stays scannable.
    """
    if payload is None:
        payload = _payload_dict(event)

    # destination_last4 earns its place here because without it the flood's log
    # line reads `preview: "—"` — 2,547 warnings that never once said WHICH
    # number was unmapped, which is the only fact the operator needs to fix it.
    preview_keys = ("note", "preview", "agent", "kind", "lead_id",
                    "channel", "intent", "client", "platform", "post_url",
                    "amount_cad", "amount_usd", "net_mrr_usd", "v6_mode",
                    "session_id", "invoice_id", "destination_last4")
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


def _parse_ts(raw) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _suppress_key(event: dict, payload: dict) -> str:
    """Stable identity of the recurring condition this event reports."""
    event_type = str(event.get("event_type") or "unknown")
    fields = IDENTITY_FIELDS.get(event_type)
    if not fields:
        source = str(event.get("source_agent") or event.get("publisher_agent") or "unknown")
        return f"{event_type}|src={source}"
    parts = []
    for field in fields:
        value = payload.get(field)
        parts.append(f"{field}={value if value not in (None, '') else '-'}")
    return "|".join([event_type, *parts])


def _budget_for(event_type: str) -> int:
    return (SUPPRESS_BUDGET_RECURRING if event_type in IDENTITY_FIELDS
            else SUPPRESS_BUDGET_DEFAULT)


def _load_suppress_state() -> dict:
    """Per-key counters, keyed by _suppress_key.

    Persisted rather than held in memory because PM2 restarts this daemon and
    `once` runs as a fresh process every invocation — an in-memory counter would
    re-log the whole flood from scratch on each start, which is the bug.
    """
    if not SUPPRESS_STATE_PATH.exists():
        return {}
    try:
        raw = json.loads(SUPPRESS_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        # Loud, then continue. A corrupt counter file must not take the whole
        # observability tail down with it, but it must never read as "nothing
        # was suppressed" either — hence both channels before the reset.
        sys.stderr.write(f"[event_router] suppression state unreadable ({e}); starting fresh\n")
        _slog.error("suppress_state_unreadable", path=str(SUPPRESS_STATE_PATH),
                    error=f"{type(e).__name__}: {e}"[:200])
        return {}
    if not isinstance(raw, dict) or not isinstance(raw.get("keys"), dict):
        sys.stderr.write("[event_router] suppression state has unexpected shape; starting fresh\n")
        _slog.error("suppress_state_bad_shape", path=str(SUPPRESS_STATE_PATH),
                    got=type(raw).__name__)
        return {}
    # Per-entry shape check, not just the container's: this file is plain JSON in
    # state/ and gets hand-inspected. One non-dict entry would raise inside the
    # row loop, where loop()'s broad handler would turn it into a router that
    # ticks forever and routes nothing.
    keys = {k: v for k, v in raw["keys"].items() if isinstance(v, dict)}
    if len(keys) != len(raw["keys"]):
        dropped = len(raw["keys"]) - len(keys)
        sys.stderr.write(f"[event_router] dropped {dropped} malformed suppression entr"
                         f"{'y' if dropped == 1 else 'ies'}\n")
        _slog.error("suppress_state_entry_dropped", path=str(SUPPRESS_STATE_PATH),
                    dropped=dropped)
    return keys


def _save_suppress_state(keys: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SUPPRESS_STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"version": 1, "keys": keys}, default=str),
                   encoding="utf-8")
    # Atomic: a crash mid-write must not leave a truncated counter file that the
    # next start reads as "starting fresh" and then re-floods behind.
    tmp.replace(SUPPRESS_STATE_PATH)


def _emit_rollup(key: str, entry: dict, now: datetime) -> None:
    """The line that makes suppression honest: how many were withheld, for what,
    over what span. Shares the projected shape so `tail` renders it for free."""
    withheld = int(entry.get("suppressed") or 0)
    since = entry.get("window_started_at") or "?"
    last = entry.get("last_seen_at") or "?"
    stamp = now.isoformat(timespec="seconds")
    _log_jsonl({
        "id":                None,
        "event_type":        ROLLUP_EVENT_TYPE,
        "source_agent":      "event_router",
        "target_agent":      "broadcast",
        "severity":          "warn",
        "published_at":      stamp,
        "created_at":        stamp,
        "status":            "rollup",
        "preview":           f"{withheld} suppressed for {key} since {since} (last seen {last})",
        "suppressed":        withheld,
        "suppressed_key":    key,
        "window_started_at": since,
        "last_seen_at":      last,
    })


def _sweep_suppress_windows(keys: dict, now: datetime) -> int:
    """Close every expired window, emitting its rollup on the way out.

    Runs on EVERY tick, including empty ones and ticks where the DB is
    unreachable. If it only ran when a key was seen again, a flood that stopped
    would carry its withheld count to the grave — the exact failure this whole
    mechanism exists to prevent.
    """
    cutoff = now - timedelta(seconds=SUPPRESS_WINDOW_SEC)
    closed = 0
    for key in list(keys):
        entry = keys[key]
        started = _parse_ts(entry.get("window_started_at"))
        # An unparseable window start counts as expired: rolling it up now
        # reports the count, where keeping it would pin the window open forever.
        if started is None or started <= cutoff:
            if int(entry.get("suppressed") or 0) > 0:
                _emit_rollup(key, entry, now)
            del keys[key]
            closed += 1
    if len(keys) > SUPPRESS_MAX_KEYS:
        stale_first = sorted(keys.items(), key=lambda kv: str(kv[1].get("last_seen_at") or ""))
        for key, entry in stale_first[: len(keys) - SUPPRESS_MAX_KEYS]:
            if int(entry.get("suppressed") or 0) > 0:
                _emit_rollup(key, entry, now)
            del keys[key]
            closed += 1
    return closed


def _admit(keys: dict, key: str, event_type: str, severity: str, now: datetime) -> bool:
    """True if this occurrence gets its own log line.

    A key with no open window ALWAYS logs. That is what keeps a genuinely new
    unmapped DID visible the instant it appears, however loud its neighbours are.
    """
    if severity in NEVER_SUPPRESS_SEVERITY:
        return True
    stamp = now.isoformat(timespec="seconds")
    entry = keys.get(key)
    if entry is None:
        keys[key] = {"window_started_at": stamp, "last_seen_at": stamp,
                     "logged": 1, "suppressed": 0}
        return True
    entry["last_seen_at"] = stamp
    if int(entry.get("logged") or 0) < _budget_for(event_type):
        entry["logged"] = int(entry.get("logged") or 0) + 1
        return True
    entry["suppressed"] = int(entry.get("suppressed") or 0) + 1
    return False


def tick(verbose: bool = False) -> int:
    """One poll cycle. Returns count of events routed.

    Every row still advances the cursor and still counts as routed — suppression
    governs only how many of them get their own line in the tail.
    """
    now = datetime.now(timezone.utc)
    suppress = _load_suppress_state()
    # Sweep first, before anything that can fail: a closed window's rollup is
    # owed to the operator even on a tick with no rows and even while the DB is
    # unreachable, which is exactly when a flood tends to stop.
    dirty = _sweep_suppress_windows(suppress, now) > 0

    client = _client()
    if client is None:
        if dirty:
            _save_suppress_state(suppress)
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
        if dirty:
            _save_suppress_state(suppress)
        sys.stderr.write(f"[event_router] fetch error: {e}\n")
        return 0

    rows = res.data or []
    if not rows:
        if dirty:
            _save_suppress_state(suppress)
        if verbose:
            sys.stderr.write(".")
            sys.stderr.flush()
        return 0

    routed = 0
    withheld = 0
    latest = cursor
    for ev in rows:
        payload = _payload_dict(ev)
        projected = _project(ev, payload)
        if _admit(suppress, _suppress_key(ev, payload),
                  projected["event_type"], projected["severity"], now):
            _log_jsonl(projected)
            if verbose:
                print(f"  → {projected['event_type']:35s} src={projected['source_agent']:8s} "
                      f"tgt={projected['target_agent']:10s} {projected['preview']}",
                      flush=True)
        else:
            withheld += 1
        ts = ev.get("created_at") or ""
        if ts > latest:
            latest = ts
        routed += 1

    _save_suppress_state(suppress)
    if verbose and withheld:
        sys.stderr.write(f"[event_router] {withheld} line(s) withheld this tick "
                         f"(see `suppressed` for open windows)\n")
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


def suppressed() -> int:
    """What is being withheld right now, and how much of it.

    These counters are the operator's answer to "is the tail quiet because
    nothing is happening, or because the router is holding a flood back?".
    """
    keys = _load_suppress_state()
    if not keys:
        print("(no open suppression windows)")
        return 0
    print(f"budget per {SUPPRESS_WINDOW_SEC}s window: "
          f"{SUPPRESS_BUDGET_RECURRING} line(s) per declared-recurring key, "
          f"{SUPPRESS_BUDGET_DEFAULT} for everything else")
    print(f"{'key':<62} {'logged':>6} {'withheld':>9}  window opened")
    for key, entry in sorted(keys.items(),
                             key=lambda kv: -int(kv[1].get("suppressed") or 0)):
        print(f"{key[:62]:<62} {int(entry.get('logged') or 0):>6} "
              f"{int(entry.get('suppressed') or 0):>9}  "
              f"{entry.get('window_started_at', '?')}")
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

    sp = sub.add_parser("suppressed",
                        help="Show open suppression windows and withheld counts")
    sp.set_defaults(func=lambda a: suppressed())

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
