"""send_guards.py — pluggable safety guards for the outbound send chokepoint.

Four universal guards that wrap every outbound send across every tenant:

  1. HALT flag                — global kill switch (state/HALT.flag).
                                Operator panic button: a single touch
                                stops EVERY outbound send across every
                                tenant. Stays active until the operator
                                deletes the file.

  2. Quiet window             — optional per-tenant outbound blackout
                                window. Configured via
                                tenants.custom_fields.quiet_window
                                (start/end weekday + hour/minute + tz).
                                Default is None — no window unless a
                                tenant explicitly configures one. Tenant
                                runtimes ship their own quiet-window
                                constants if they want a code-side
                                default (e.g., SunBiz-Agent/scripts/
                                integrations/sunbiz_guards.py).

  3. Opt-out enforcement      — tenant_records (entity_type='lead')
                                marked status='opted_out' OR
                                tt_leads.status='opted_out' (legacy)
                                NEVER receive another outbound. Hard
                                block regardless of channel.

  4. AI rate cap              — global 60-per-minute ceiling on
                                Anthropic Haiku invocations across the
                                whole agent stack. Prevents a runaway
                                loop from burning the API budget.

Each guard is a pure function that returns a structured GuardResult so
the caller (send_gateway.can_act() typically) can short-circuit with a
clear reason. They're side-effect-free EXCEPT acquire_ai_rate_slot()
which atomically increments a counter file.

  --- Integration with send_gateway.py ---

At the top of `can_act()` in send_gateway.py — BEFORE the cooldown +
daily-cap chokepoints — add:

    from send_guards import check_all_guards
    guard_result = check_all_guards(
        db=db,
        lead_id=lead_id,
        channel=channel,
        tenant_id=tenant_id,
        state_dir=PROJECT_ROOT / "state",
    )
    if not guard_result.allowed:
        return {
            "allow": False,
            "reason": guard_result.reason,
            "blocked_by": guard_result.blocked_by,
        }

  --- Threading & atomicity ---

The AI rate counter uses fcntl on POSIX (Mac, Linux, VPS). On Windows
the daemon stack doesn't run multi-process so no lock is taken — single
writer is the only writer. If the SunBiz-Agent daemons later run multi-
process on Windows, swap fcntl for msvcrt.locking.

  --- Bypass mechanism ---

`check_all_guards(force=True)` skips every guard. Reserved for the
manual operator override path — Telegram /force-send. Use sparingly.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

# ─────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────

DEFAULT_AI_RATE_WINDOW_SECONDS = 60
DEFAULT_AI_RATE_MAX_CALLS = 60

# No universal default quiet window. Tenants opt in by writing a window
# dict to tenants.custom_fields.quiet_window in the form:
#   {"tz": "America/New_York",
#    "start_weekday": 4, "start_hour": 18, "start_minute": 0,
#    "end_weekday":   5, "end_hour":   20, "end_minute":   30}
# Tenant-specific defaults live in the tenant's own runtime (for example
# SunBiz-Agent/scripts/integrations/sunbiz_guards.py defines the SunBiz
# Friday/Saturday window).
DEFAULT_QUIET_WINDOW: Optional[dict[str, Any]] = None

# ─────────────────────────────────────────────────────────────────────
# Result type
# ─────────────────────────────────────────────────────────────────────


@dataclass
class GuardResult:
    """One pass result. allowed=True OR a structured block reason."""

    allowed: bool
    blocked_by: Optional[str] = None  # 'halt' | 'quiet_window' | 'opted_out' | 'ai_rate_cap'
    reason: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────
# Guard 1 — HALT flag
# ─────────────────────────────────────────────────────────────────────


def is_halt_active(state_dir: Path) -> tuple[bool, Optional[str]]:
    """Returns (is_halted, reason_text). state/HALT.flag is the panic
    button — its mere existence stops every outbound across every tenant.
    Optional content of the file is surfaced as the reason text so the
    operator can leave themselves a note about why."""
    halt_path = state_dir / "HALT.flag"
    if not halt_path.exists():
        return False, None
    try:
        body = halt_path.read_text(encoding="utf-8", errors="replace").strip()
        return True, body or "halt flag present (no note)"
    except OSError:
        # If we can't read it, treat presence as halted. Fail-closed.
        return True, "halt flag present (unreadable)"


def check_halt(state_dir: Path) -> GuardResult:
    halted, reason = is_halt_active(state_dir)
    if not halted:
        return GuardResult(allowed=True)
    return GuardResult(
        allowed=False,
        blocked_by="halt",
        reason=f"HALT flag active: {reason}",
        metadata={"halt_path": str(state_dir / "HALT.flag")},
    )


# ─────────────────────────────────────────────────────────────────────
# Guard 2 — quiet window (per-tenant outbound blackout)
# ─────────────────────────────────────────────────────────────────────


def is_within_quiet_window(
    now: Optional[datetime] = None,
    window: Optional[dict[str, Any]] = None,
) -> bool:
    """Returns True when `now` falls inside the quiet window.

    Window dict shape:
        {"tz": "America/New_York",
         "start_weekday": 4, "start_hour": 18, "start_minute": 0,
         "end_weekday":   5, "end_hour":   20, "end_minute":   30}

    Weekdays are 0=Mon ... 6=Sun. start/end may span midnight (e.g.,
    start=Fri 22:00, end=Sat 02:00 wraps through the date change).
    """
    w = window if window is not None else DEFAULT_QUIET_WINDOW
    if w is None:
        return False
    tz = ZoneInfo(w.get("tz", "America/New_York"))
    if now is None:
        now = datetime.now(timezone.utc)
    local = now.astimezone(tz)

    # Compute the start + end timestamps of THIS week's window. We pick
    # the most recent Mon-of-week and offset to start_weekday + end_weekday.
    monday = (local - timedelta(days=local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start = monday + timedelta(
        days=int(w["start_weekday"]),
        hours=int(w["start_hour"]),
        minutes=int(w["start_minute"]),
    )
    end = monday + timedelta(
        days=int(w["end_weekday"]),
        hours=int(w["end_hour"]),
        minutes=int(w["end_minute"]),
    )

    # If end <= start (e.g. window spans Sunday into Monday), assume
    # the operator meant "next week's same weekday" and bump end forward.
    if end <= start:
        end = end + timedelta(days=7)

    return start <= local <= end


def resolve_tenant_quiet_window(
    db: Any, tenant_id: Optional[str]
) -> Optional[dict[str, Any]]:
    """Pull custom_fields.quiet_window from the tenants row. Returns None
    when no tenant override exists and no module-level DEFAULT_QUIET_WINDOW
    is set, in which case check_shabbat is a no-op for that tenant. Tenant
    runtimes override DEFAULT_QUIET_WINDOW from their own module if they
    want a code-side default."""
    if not tenant_id or db is None:
        return DEFAULT_QUIET_WINDOW
    try:
        res = db.table("tenants").select("custom_fields").eq("id", tenant_id).maybe_single().execute()
        cf = (res.data or {}).get("custom_fields") or {}
        w = cf.get("quiet_window")
        if isinstance(w, dict) and "tz" in w:
            if DEFAULT_QUIET_WINDOW is None:
                return dict(w)
            merged = dict(DEFAULT_QUIET_WINDOW)
            merged.update(w)
            return merged
    except Exception:
        pass
    return DEFAULT_QUIET_WINDOW


def check_quiet_window(
    db: Any,
    tenant_id: Optional[str],
    channel: str,
    now: Optional[datetime] = None,
) -> GuardResult:
    """Block outbound merchant / lender comms during the quiet window.
    Internal channels (telegram alerts to the operator) are NOT blocked
    — those are the operator's own incoming surface."""
    if channel == "telegram":
        return GuardResult(allowed=True)  # internal operator alert, never blocked
    window = resolve_tenant_quiet_window(db, tenant_id)
    if window is None:
        return GuardResult(allowed=True)
    if is_within_quiet_window(now=now, window=window):
        return GuardResult(
            allowed=False,
            blocked_by="quiet_window",
            reason=f"quiet window active ({window.get('tz', 'tenant')}), retry after window close",
            metadata={"window": window},
        )
    return GuardResult(allowed=True)


# ─────────────────────────────────────────────────────────────────────
# Guard 3 — opt-out
# ─────────────────────────────────────────────────────────────────────


def is_opted_out(db: Any, lead_id: Optional[str]) -> bool:
    """Returns True when the lead has status='opted_out' on the tenant_records
    row OR the legacy tt_leads row. Either source wins — once a merchant
    opts out, no other path opens them back up except a direct DB UPDATE.

    Returns False when there's no DB connection or no lead_id (those paths
    are handled higher up — sends without a lead_id go through different
    guards). FAIL-CLOSED here would block legitimate broadcast sends that
    aren't lead-attached, so we fail-open and rely on the upstream code
    paths having lead_id always when it matters.
    """
    if not lead_id or db is None:
        return False
    # Check tenant_records (the canonical store).
    try:
        res = (
            db.table("tenant_records")
            .select("data")
            .eq("id", lead_id)
            .maybe_single()
            .execute()
        )
        d = (res.data or {}).get("data") or {}
        if d.get("status") == "opted_out":
            return True
    except Exception:
        pass
    # Legacy tt_leads check (some daemons still write there).
    try:
        res = (
            db.table("tt_leads")
            .select("status")
            .eq("id", lead_id)
            .maybe_single()
            .execute()
        )
        if (res.data or {}).get("status") == "opted_out":
            return True
    except Exception:
        pass
    return False


def check_opt_out(db: Any, lead_id: Optional[str]) -> GuardResult:
    if is_opted_out(db, lead_id):
        return GuardResult(
            allowed=False,
            blocked_by="opted_out",
            reason="lead is opted out — outbound permanently blocked",
            metadata={"lead_id": lead_id},
        )
    return GuardResult(allowed=True)


# ─────────────────────────────────────────────────────────────────────
# Guard 4 — AI rate cap (global, sliding window)
# ─────────────────────────────────────────────────────────────────────


def _ai_rate_state_path(state_dir: Path) -> Path:
    return state_dir / "ai_rate.json"


def acquire_ai_rate_slot(
    state_dir: Path,
    max_calls: int = DEFAULT_AI_RATE_MAX_CALLS,
    window_seconds: int = DEFAULT_AI_RATE_WINDOW_SECONDS,
    now: Optional[float] = None,
) -> bool:
    """Atomic sliding-window counter. Returns True when a slot was
    acquired (caller may proceed with the AI call), False when the
    window is saturated.

    Storage: state/ai_rate.json — JSON array of unix timestamps within
    the window. Read-modify-write under an fcntl exclusive lock so
    concurrent daemons can't double-spend slots.

    Falls back to allow=True on any file/lock error (fail-OPEN on rate
    limit because false-positives block real work; the safety net is
    Anthropic's own per-key rate limit which kicks in upstream).
    """
    now = now if now is not None else time.time()
    state_path = _ai_rate_state_path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)

    # POSIX fcntl path — Mac, Linux, VPS. Windows daemons run single-
    # process so we skip the lock there.
    try:
        import fcntl  # type: ignore
        f = open(state_path, "a+")
        try:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            body = f.read()
            try:
                stamps = json.loads(body) if body else []
                if not isinstance(stamps, list):
                    stamps = []
            except json.JSONDecodeError:
                stamps = []
            cutoff = now - window_seconds
            stamps = [t for t in stamps if isinstance(t, (int, float)) and t > cutoff]
            if len(stamps) >= max_calls:
                # Saturated. Don't increment; deny the slot.
                f.seek(0)
                f.truncate()
                f.write(json.dumps(stamps))
                return False
            stamps.append(now)
            f.seek(0)
            f.truncate()
            f.write(json.dumps(stamps))
            return True
        finally:
            try:
                fcntl.flock(f, fcntl.LOCK_UN)
            except Exception:
                pass
            f.close()
    except ImportError:
        # Windows path — single-writer assumption.
        try:
            stamps: list[float] = []
            if state_path.exists():
                stamps = json.loads(state_path.read_text() or "[]")
                if not isinstance(stamps, list):
                    stamps = []
            cutoff = now - window_seconds
            stamps = [t for t in stamps if isinstance(t, (int, float)) and t > cutoff]
            if len(stamps) >= max_calls:
                state_path.write_text(json.dumps(stamps))
                return False
            stamps.append(now)
            state_path.write_text(json.dumps(stamps))
            return True
        except Exception:
            return True  # fail-open
    except Exception:
        return True  # fail-open on any unexpected error


def check_ai_rate(state_dir: Path) -> GuardResult:
    """Calling-pattern wrapper. Acquires a slot if available — note this
    has a side effect (consumes a slot). Send-gateway callers should
    call this AFTER all other guards pass so they don't burn the slot
    on a send that's about to be blocked for some other reason."""
    if acquire_ai_rate_slot(state_dir):
        return GuardResult(allowed=True)
    return GuardResult(
        allowed=False,
        blocked_by="ai_rate_cap",
        reason=f"AI rate cap hit ({DEFAULT_AI_RATE_MAX_CALLS} calls / {DEFAULT_AI_RATE_WINDOW_SECONDS}s window)",
    )


# ─────────────────────────────────────────────────────────────────────
# Aggregator
# ─────────────────────────────────────────────────────────────────────


def check_all_guards(
    db: Any,
    lead_id: Optional[str],
    channel: str,
    tenant_id: Optional[str],
    state_dir: Path,
    skip_ai_rate: bool = False,
    force: bool = False,
    now: Optional[datetime] = None,
) -> GuardResult:
    """The chokepoint. Returns the FIRST blocking guard's result, or
    allowed=True. Order is by cheapest-to-check first so we short-circuit
    on the obvious cases (HALT, opt-out) before the more expensive
    Shabbat/AI-rate checks.

    Args:
        db:          Supabase client (service-role).
        lead_id:     Lead UUID; required for opt-out check.
        channel:     'sms' | 'email' | 'telegram'. Telegram is exempt
                     from the quiet-window guard.
        tenant_id:   Tenant UUID; used to resolve per-tenant quiet window.
        state_dir:   PROJECT_ROOT / 'state' typically.
        skip_ai_rate: True for non-AI sends (templated outbound that
                     doesn't burn an LLM call).
        force:       Operator override (Telegram /force-send). Skips all
                     guards. Logged but not blocked.
    """
    if force:
        return GuardResult(allowed=True, metadata={"forced": True})

    # 1. HALT (cheapest — file existence check)
    r = check_halt(state_dir)
    if not r.allowed:
        return r

    # 2. Opt-out (one DB call)
    r = check_opt_out(db, lead_id)
    if not r.allowed:
        return r

    # 3. Quiet window (one DB call + datetime math)
    r = check_quiet_window(db, tenant_id, channel, now=now)
    if not r.allowed:
        return r

    # 4. AI rate cap (only when the send burns an LLM call)
    if not skip_ai_rate:
        r = check_ai_rate(state_dir)
        if not r.allowed:
            return r

    return GuardResult(allowed=True)


# ─────────────────────────────────────────────────────────────────────
# CLI — for operator inspection / testing
# ─────────────────────────────────────────────────────────────────────


def _cli() -> int:
    import argparse

    p = argparse.ArgumentParser(prog="send_guards", description="Inspect outbound safety guards.")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="Print which guards would block right now (no DB).")
    p_status.add_argument("--state-dir", type=Path, default=Path(__file__).resolve().parent.parent.parent / "state")
    p_status.add_argument("--tz", type=str, default=None, help="Override tz check, e.g. America/New_York")

    p_halt_on = sub.add_parser("halt", help="Activate HALT flag with optional note.")
    p_halt_on.add_argument("--note", type=str, default="manual halt")
    p_halt_on.add_argument("--state-dir", type=Path, default=Path(__file__).resolve().parent.parent.parent / "state")

    p_halt_off = sub.add_parser("resume", help="Clear HALT flag.")
    p_halt_off.add_argument("--state-dir", type=Path, default=Path(__file__).resolve().parent.parent.parent / "state")

    args = p.parse_args()

    if args.cmd == "status":
        halted, reason = is_halt_active(args.state_dir)
        print(f"HALT:        {'ON' if halted else 'off'} {f'({reason})' if reason else ''}")
        if DEFAULT_QUIET_WINDOW is None:
            print("Quiet win:   no module-level default (per-tenant via tenants.custom_fields.quiet_window)")
        else:
            in_window = is_within_quiet_window()
            print(f"Quiet win:   {'WITHIN window' if in_window else 'outside window'} (module default)")
        rate_path = _ai_rate_state_path(args.state_dir)
        if rate_path.exists():
            try:
                stamps = json.loads(rate_path.read_text() or "[]")
                recent = [t for t in stamps if t > time.time() - DEFAULT_AI_RATE_WINDOW_SECONDS]
                print(f"AI rate: {len(recent)} / {DEFAULT_AI_RATE_MAX_CALLS} in last {DEFAULT_AI_RATE_WINDOW_SECONDS}s")
            except Exception:
                print("AI rate: (counter file unreadable)")
        else:
            print(f"AI rate: 0 / {DEFAULT_AI_RATE_MAX_CALLS} in last {DEFAULT_AI_RATE_WINDOW_SECONDS}s (no counter yet)")
        return 0

    if args.cmd == "halt":
        args.state_dir.mkdir(parents=True, exist_ok=True)
        (args.state_dir / "HALT.flag").write_text(args.note + "\n", encoding="utf-8")
        print(f"HALT activated. Outbound sends are now blocked across every tenant.")
        print(f"To resume: python {__file__} resume")
        return 0

    if args.cmd == "resume":
        path = args.state_dir / "HALT.flag"
        if path.exists():
            path.unlink()
            print("HALT cleared. Outbound resumes.")
        else:
            print("No HALT flag was active.")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
