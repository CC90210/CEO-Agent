"""sequence_runner.py — drip-campaign daemon (Phase 4.3 of SunBiz CRM).

Two concurrent responsibilities in one daemon (run in alternation each tick):

  1. ENROLLMENT — read new agent_events rows since the last cursor, match
     against drip_sequences trigger_event + trigger_filter, and insert
     sequence_state rows for matching (lead, sequence) pairs.

  2. EXECUTION — read sequence_state rows where status='scheduled' AND
     scheduled_for <= now(), fire the step's send via send_gateway.send,
     update status to 'sent' (or 'failed' on error), and enqueue the
     next step if any.

Architecture rationale:
  - One daemon, two loops (alternated in the same tick) so the operator
    only needs to keep one PM2 entry alive. PM2 entry: 'sequence-runner'
    in ecosystem.config.js.
  - Cursor-based enrollment so a daemon restart doesn't re-enroll leads
    that were already enrolled before the restart.
  - One sequence_state row per (lead, sequence, step) so the audit trail
    is durable and the operator can see exactly what fired when. Cancel-
    a-single-lead-mid-drip works by setting their status='cancelled'
    without touching the sequence definition.

Idempotency:
  - one_per_lead=true (default): before inserting a new sequence_state
    row, check for an active (scheduled / failed) row for the same
    (sequence_id, lead_id). If one exists, skip enrollment.
  - Each step row stores attempt_count + last_error so failed sends
    don't get retried infinitely. After MAX_ATTEMPTS the daemon marks
    the row 'failed' permanently and moves on.

Send path:
  - send_gateway.send is the universal outbound chokepoint. SMS uses
    channel='sms', email uses channel='email'. CASL / cooldown /
    daily-cap enforcement is automatic because that's where it lives.

CLI:
  python scripts/sequence_runner.py loop --interval 10
  python scripts/sequence_runner.py once
  python scripts/sequence_runner.py tail
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────────────
# State + config
# ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "state"
CURSOR_PATH = STATE_DIR / "sequence_runner.cursor"
LOG_PATH = STATE_DIR / "sequence_runner.log"

# Cap on retry attempts for a single sequence_state row. After this many
# failed sends we permanently mark the row 'failed' and stop trying.
MAX_ATTEMPTS = 5

# Backoff for retries — multiplicative, capped. attempt_count=1 means
# we've tried once and failed; next attempt waits BACKOFF_BASE_SECONDS
# before retrying.
BACKOFF_BASE_SECONDS = 60      # 1 min for attempt #2
BACKOFF_FACTOR = 3              # 3x growth -> 3m, 9m, 27m, 81m
BACKOFF_MAX_SECONDS = 6 * 3600  # cap at 6h


# ─────────────────────────────────────────────────────────────────────
# Supabase client (service-role)
# ─────────────────────────────────────────────────────────────────────


def _supabase():
    """Service-role Supabase client. Returns None on any failure."""
    try:
        from lib.secret_loader import load_env
    except Exception:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            from lib.secret_loader import load_env  # type: ignore
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


# ─────────────────────────────────────────────────────────────────────
# Cursor for enrollment loop
# ─────────────────────────────────────────────────────────────────────


def _read_cursor() -> str:
    """ISO timestamp of the last enrolled-from event, or 1 hour ago on
    cold start. The 1h floor prevents flooding sequence_state on first
    run after a long downtime — operators can re-enroll specific leads
    manually if needed."""
    if CURSOR_PATH.exists():
        try:
            text = CURSOR_PATH.read_text(encoding="utf-8").strip()
            if text:
                return text
        except OSError:
            pass
    return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")


def _write_cursor(ts: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CURSOR_PATH.write_text(ts, encoding="utf-8")


def _log(msg: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}\n"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass
    print(line.rstrip())


# ─────────────────────────────────────────────────────────────────────
# Mustache-style template rendering
#
# Mirrors apps/command-center/lib/drips/templates.ts. Cross-language
# sync — if the regex or default-value rule changes, update both.
#
# PARITY ASSERTION — every case below MUST behave identically in both
# implementations. The TS file has the same sample cases in its
# docstring. When changing either side, run through the list before
# shipping:
#
#   1. render_template("Hi {{lead.first_name}}", {"lead": {"first_name": "Jordan"}})
#        -> "Hi Jordan"
#   2. render_template("Hi {{lead.first_name}}", {"lead": {}})
#        -> "Hi "                                     (empty default)
#   3. render_template("Hi {{lead.first_name}}", {"lead": {}}, default="there")
#        -> "Hi there"
#   4. render_template("Hi {{ lead.first_name }}", {"lead": {"first_name": "X"}})
#        -> "Hi X"                                    (whitespace tolerated)
#   5. render_template("Bal: {{lead.monthly_revenue}}", {"lead": {"monthly_revenue": 25000}})
#        -> "Bal: 25000"                              (number coercion)
#   6. render_template("Toggle: {{lead.opted_in}}", {"lead": {"opted_in": False}})
#        -> "Toggle: False"                           (boolean coercion)
#   7. render_template("Tags: {{lead.tags}}", {"lead": {"tags": ["vip"]}})
#        -> 'Tags: ["vip"]'                            (JSON fallback)
#   8. render_template("Nope: {{unknown.path}}", {})
#        -> "Nope: "                                  (missing intermediate)
#
# Cases 5+6: Python `str(False)` -> "False", TS `String(false)` -> "false".
# This is the ONE intentional language divergence — operators see Python
# True/False on email but the rendered string only differs by case. Not
# worth a separate fix; flagged so a future reader doesn't "fix" the
# Python side to lowercase and break SunBiz operators' muscle memory.
# ─────────────────────────────────────────────────────────────────────


_TOKEN_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def _lookup(ctx: dict, path: str) -> Any:
    parts = path.split(".")
    cur: Any = ctx
    for p in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def render_template(template: str, ctx: dict, default: str = "") -> str:
    """Substitute {{path}} tokens. Missing values render as `default`."""
    def repl(m: re.Match) -> str:
        v = _lookup(ctx, m.group(1))
        if v is None:
            return default
        if isinstance(v, str):
            return v
        if isinstance(v, (int, float, bool)):
            return str(v)
        try:
            return json.dumps(v)
        except (TypeError, ValueError):
            return default
    return _TOKEN_RE.sub(repl, template)


# ─────────────────────────────────────────────────────────────────────
# Loop A: enrollment from agent_events
# ─────────────────────────────────────────────────────────────────────


def _filter_matches(trigger_filter: dict, payload: dict) -> bool:
    """Shallow equality on top-level keys. trigger_filter keys all must
    match the corresponding payload values."""
    if not trigger_filter:
        return True
    for k, v in trigger_filter.items():
        if payload.get(k) != v:
            return False
    return True


def _has_active_state(sb, sequence_id: str, lead_id: str) -> bool:
    """one_per_lead guard. Returns True if an active row already exists
    for this (sequence, lead) pair."""
    try:
        r = (
            sb.table("sequence_state")
            .select("id", count="exact")
            .eq("sequence_id", sequence_id)
            .eq("lead_id", lead_id)
            .in_("status", ["scheduled", "failed"])
            .limit(1)
            .execute()
        )
        return bool(r.data)
    except Exception:
        # Conservative: on a query failure, claim active so we don't
        # double-enroll. Operator can investigate via the daemon log.
        return True


def _enroll_step(sb, sequence: dict, lead_id: str, payload: dict, step_index: int) -> Optional[str]:
    """Insert a sequence_state row. Returns the new row id on success."""
    steps = sequence.get("steps") or []
    if step_index >= len(steps):
        return None
    step = steps[step_index]
    delay_minutes = max(0, int(step.get("delay_minutes") or 0))
    scheduled_for = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
    try:
        r = (
            sb.table("sequence_state")
            .insert(
                {
                    "sequence_id": sequence["id"],
                    "tenant_id": sequence["tenant_id"],
                    "lead_id": lead_id,
                    "step_index": step_index,
                    "scheduled_for": scheduled_for.isoformat(),
                    "status": "scheduled",
                    "context_snapshot": payload,
                }
            )
            .execute()
        )
        if r.data:
            return r.data[0]["id"]
    except Exception as e:
        _log(f"enroll insert failed seq={sequence.get('id')} lead={lead_id}: {e}")
    return None


def enrollment_tick(sb) -> int:
    """Read new agent_events since the cursor, enroll matching leads.
    Returns the number of enrollments inserted."""
    cursor = _read_cursor()
    try:
        events = (
            sb.table("agent_events")
            .select("id, event_type, published_at, payload")
            .gt("published_at", cursor)
            .order("published_at", desc=False)
            .limit(500)
            .execute()
        )
    except Exception as e:
        _log(f"enrollment: agent_events read failed: {e}")
        return 0
    rows = events.data or []
    if not rows:
        return 0

    enrolled = 0
    latest_ts = cursor
    for ev in rows:
        latest_ts = ev["published_at"]
        event_type = ev.get("event_type") or ""
        payload = ev.get("payload") or {}
        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            continue

        # Find active sequences for this tenant + event_type. Tenant
        # isolation is handled at the row level via tenant_id match —
        # not via RLS, since the daemon connects as service-role.
        try:
            seq_rows = (
                sb.table("drip_sequences")
                .select("id, tenant_id, name, trigger_event, trigger_filter, steps, one_per_lead")
                .eq("tenant_id", tenant_id)
                .eq("trigger_event", event_type)
                .eq("enabled", True)
                .execute()
            )
        except Exception as e:
            _log(f"enrollment: drip_sequences read failed tenant={tenant_id}: {e}")
            continue

        # Pick the lead_id from the payload (BRAVO_RECORD_STATUS_CHANGED
        # carries entity + record_id; we treat record_id as the lead_id
        # when entity=='lead'). Other entities don't enroll in lead-drips.
        lead_id = None
        if payload.get("entity") == "lead":
            lead_id = payload.get("record_id")
        if not lead_id:
            continue

        for seq in seq_rows.data or []:
            if not _filter_matches(seq.get("trigger_filter") or {}, payload):
                continue
            if seq.get("one_per_lead", True) and _has_active_state(sb, seq["id"], lead_id):
                continue
            if _enroll_step(sb, seq, lead_id, payload, 0):
                enrolled += 1
                _log(f"enroll seq={seq['id']} name='{seq.get('name')}' lead={lead_id}")

    _write_cursor(latest_ts)
    return enrolled


# ─────────────────────────────────────────────────────────────────────
# Loop B: execution of due rows
# ─────────────────────────────────────────────────────────────────────


def _backoff_seconds(attempt_count: int) -> int:
    """Multiplicative backoff. attempt_count is the number of PRIOR
    failures (so 0 = first attempt, no backoff yet)."""
    if attempt_count <= 0:
        return 0
    sec = BACKOFF_BASE_SECONDS * (BACKOFF_FACTOR ** (attempt_count - 1))
    return min(sec, BACKOFF_MAX_SECONDS)


def _build_context(sb, tenant_id: str, lead_id: str, payload: dict) -> dict:
    """Assemble the template context for a single send. Includes the
    lead row (joined from tenant_records) + the original triggering
    event payload. Future iterations can add lender / form / etc."""
    ctx: dict = {"event": payload}
    try:
        lead_row = (
            sb.table("tenant_records")
            .select("data")
            .eq("tenant_id", tenant_id)
            .eq("entity_type", "lead")
            .eq("id", lead_id)
            .maybeSingle()
            .execute()
        )
        if lead_row.data:
            ctx["lead"] = lead_row.data.get("data") or {}
    except Exception as e:
        _log(f"context: lead lookup failed lead={lead_id}: {e}")
        ctx["lead"] = {}
    return ctx


def _send_step(sb, state_row: dict, sequence: dict) -> dict:
    """Fire the actual send via send_gateway.send. Returns a structured
    result so the execution loop can branch on the five real outcomes
    instead of collapsing them into ok/fail:

      { "outcome": "sent",       "detail": "..." }
        Step shipped. Mark sent, enqueue next step.

      { "outcome": "cooldown",   "detail": "...", "retry_after_iso": "..." }
        send_gateway returned blocked because a per-lead/channel cooldown
        is still active. The reschedule honors `cooldown_until` from
        send_gateway rather than the exponential backoff — cooldown is a
        deterministic wait, not a flaky failure. attempt_count is NOT
        incremented so a sequence sitting in cooldown for 72h doesn't
        burn its 5 retry attempts.

      { "outcome": "suppressed", "detail": "..." }
        Lead opted out (STOP), CASL block, or other hard reject. Cancel
        the sequence_state row immediately — no retry will ever succeed.

      { "outcome": "permanent",  "detail": "..." }
        Configuration error (missing email/phone on file, unknown channel,
        step_index out of range, gateway import failure). Retry won't fix
        it; treat as permanent fail without burning the backoff budget.

      { "outcome": "error",      "detail": "..." }
        Transient failure (network blip, SMTP 5xx). Use the existing
        exponential-backoff retry path.

    This is the bug-fix for the prior collapsed ok/fail return: previously
    a lead in cooldown chewed through all 5 retry attempts in the
    backoff window and got permanently failed for a temporary wait.
    """
    try:
        # Import lazily — send_gateway pulls smtplib + supabase clients
        # of its own. Importing at module load time would slow the
        # daemon's cold start.
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from send_gateway import send  # type: ignore
    except Exception as e:
        return {"outcome": "permanent", "detail": f"send_gateway import failed: {e}"}

    steps = sequence.get("steps") or []
    step_index = state_row["step_index"]
    if step_index >= len(steps):
        return {
            "outcome": "permanent",
            "detail": f"step_index {step_index} out of range (steps={len(steps)})",
        }
    step = steps[step_index]
    channel = step.get("channel")
    body_template = step.get("body") or ""
    subject_template = step.get("subject") or ""

    ctx = _build_context(
        sb, state_row["tenant_id"], state_row["lead_id"], state_row.get("context_snapshot") or {}
    )
    body = render_template(body_template, ctx)
    subject = render_template(subject_template, ctx) if subject_template else None

    lead = ctx.get("lead") or {}
    to_email = lead.get("email")
    to_phone = lead.get("phone")

    if channel == "email" and not to_email:
        return {"outcome": "permanent", "detail": "lead has no email on file"}
    if channel == "sms" and not to_phone:
        return {"outcome": "permanent", "detail": "lead has no phone on file"}

    try:
        if channel == "email":
            res = send(
                channel="email",
                to_email=to_email,
                subject=subject or "(no subject)",
                body_text=body,
                lead_id=state_row["lead_id"],
                agent_source=f"sequence:{sequence.get('name') or sequence.get('id')}",
                brand="oasis",
                intent="commercial",
            )
        elif channel == "sms":
            res = send(
                channel="sms",
                to_phone=to_phone,
                body_text=body,
                lead_id=state_row["lead_id"],
                agent_source=f"sequence:{sequence.get('name') or sequence.get('id')}",
                brand="oasis",
                intent="commercial",
            )
        else:
            return {"outcome": "permanent", "detail": f"unknown channel '{channel}'"}
    except Exception as e:
        return {"outcome": "error", "detail": f"send_gateway raised: {e}"}

    status = res.get("status")
    reason = res.get("reason") or ""
    if status == "sent":
        return {"outcome": "sent", "detail": reason or "sent"}
    if status == "blocked":
        # send_gateway exposes cooldown_until ISO — use it for the
        # reschedule instead of synthetic backoff. If it's missing,
        # fall back to error-style backoff so we don't hot-spin on a
        # blocked-but-no-cooldown-stamp result.
        cooldown_until = res.get("cooldown_until")
        if cooldown_until:
            return {
                "outcome": "cooldown",
                "detail": f"blocked: {reason}",
                "retry_after_iso": cooldown_until,
            }
        return {"outcome": "error", "detail": f"blocked (no cooldown_until): {reason}"}
    if status == "suppressed":
        # CASL opt-out / hard reject. The retry button isn't going to
        # un-opt the lead out. Cancel cleanly.
        return {"outcome": "suppressed", "detail": f"suppressed: {reason}"}
    # dry_run / error / unknown — treat as transient.
    return {"outcome": "error", "detail": f"{status}: {reason}"}


def execution_tick(sb) -> int:
    """Poll due sequence_state rows, fire each, advance to the next
    step on success. Returns the number of rows processed."""
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        due = (
            sb.table("sequence_state")
            .select("*")
            .eq("status", "scheduled")
            .lte("scheduled_for", now_iso)
            .order("scheduled_for", desc=False)
            .limit(50)
            .execute()
        )
    except Exception as e:
        _log(f"execution: sequence_state read failed: {e}")
        return 0
    rows = due.data or []
    if not rows:
        return 0

    processed = 0
    for row in rows:
        try:
            seq_lookup = (
                sb.table("drip_sequences")
                .select("id, tenant_id, name, steps, enabled")
                .eq("id", row["sequence_id"])
                .maybeSingle()
                .execute()
            )
        except Exception as e:
            _log(f"execution: drip_sequences read failed id={row.get('sequence_id')}: {e}")
            continue
        if not seq_lookup.data:
            # Sequence deleted while a state row was scheduled. Cancel.
            sb.table("sequence_state").update({"status": "cancelled", "last_error": "sequence_deleted"}).eq("id", row["id"]).execute()
            continue
        sequence = seq_lookup.data

        if not sequence.get("enabled", True):
            # Operator disabled the sequence mid-flight. Honor: cancel.
            sb.table("sequence_state").update({"status": "cancelled", "last_error": "sequence_disabled"}).eq("id", row["id"]).execute()
            continue

        result = _send_step(sb, row, sequence)
        outcome = result.get("outcome")
        detail = (result.get("detail") or "")[:1000]
        now = datetime.now(timezone.utc).isoformat()
        prior_attempts = int(row.get("attempt_count") or 0)

        if outcome == "sent":
            try:
                sb.table("sequence_state").update({
                    "status": "sent",
                    "attempt_count": prior_attempts + 1,
                    "last_attempt_at": now,
                    "last_error": None,
                }).eq("id", row["id"]).execute()
            except Exception as e:
                _log(f"execution: status update failed row={row['id']}: {e}")
                continue
            _log(f"sent seq={sequence['id']} lead={row['lead_id']} step={row['step_index']}")
            steps = sequence.get("steps") or []
            next_idx = row["step_index"] + 1
            if next_idx < len(steps):
                _enroll_step(sb, sequence, row["lead_id"], row.get("context_snapshot") or {}, next_idx)

        elif outcome == "cooldown":
            # NOT a failure. Reschedule to fire shortly after cooldown_until
            # without incrementing attempt_count -- otherwise a 72h cooldown
            # would burn all 5 attempts in the backoff window and
            # permanently fail a perfectly healthy lead.
            retry_iso = result.get("retry_after_iso")
            try:
                next_scheduled = datetime.fromisoformat(
                    (retry_iso or "").replace("Z", "+00:00")
                ) + timedelta(minutes=1)
            except (ValueError, AttributeError):
                next_scheduled = datetime.now(timezone.utc) + timedelta(hours=1)
            try:
                sb.table("sequence_state").update({
                    "last_attempt_at": now,
                    "last_error": detail,
                    "scheduled_for": next_scheduled.isoformat(),
                }).eq("id", row["id"]).execute()
            except Exception:
                pass
            _log(f"cooldown seq={sequence['id']} lead={row['lead_id']} step={row['step_index']} until={next_scheduled.isoformat()}: {detail}")

        elif outcome == "suppressed":
            # CASL opt-out / hard block. Cancel; retry will never succeed.
            try:
                sb.table("sequence_state").update({
                    "status": "cancelled",
                    "attempt_count": prior_attempts + 1,
                    "last_attempt_at": now,
                    "last_error": detail,
                }).eq("id", row["id"]).execute()
            except Exception:
                pass
            _log(f"suppressed seq={sequence['id']} lead={row['lead_id']} step={row['step_index']}: {detail}")

        elif outcome == "permanent":
            # Config error (no email/phone, unknown channel, bad index).
            # Retry won't fix. Mark failed without burning the backoff budget.
            try:
                sb.table("sequence_state").update({
                    "status": "failed",
                    "attempt_count": prior_attempts + 1,
                    "last_attempt_at": now,
                    "last_error": detail,
                }).eq("id", row["id"]).execute()
            except Exception:
                pass
            _log(f"PERMANENT FAIL seq={sequence['id']} lead={row['lead_id']} step={row['step_index']}: {detail}")

        else:
            # outcome == "error" or unknown — transient. Apply the
            # existing exponential-backoff retry path.
            attempt_count = prior_attempts + 1
            if attempt_count >= MAX_ATTEMPTS:
                try:
                    sb.table("sequence_state").update({
                        "status": "failed",
                        "attempt_count": attempt_count,
                        "last_attempt_at": now,
                        "last_error": detail,
                    }).eq("id", row["id"]).execute()
                except Exception:
                    pass
                _log(f"FAIL seq={sequence['id']} lead={row['lead_id']} step={row['step_index']} attempts={attempt_count}: {detail}")
            else:
                backoff = _backoff_seconds(attempt_count)
                next_scheduled = (datetime.now(timezone.utc) + timedelta(seconds=backoff)).isoformat()
                try:
                    sb.table("sequence_state").update({
                        "attempt_count": attempt_count,
                        "last_attempt_at": now,
                        "last_error": detail,
                        "scheduled_for": next_scheduled,
                    }).eq("id", row["id"]).execute()
                except Exception:
                    pass
                _log(f"retry seq={sequence['id']} lead={row['lead_id']} step={row['step_index']} attempt={attempt_count} backoff={backoff}s: {detail}")
        processed += 1
    return processed


# ─────────────────────────────────────────────────────────────────────
# Daemon loop
# ─────────────────────────────────────────────────────────────────────


def tick() -> tuple[int, int]:
    """One iteration: enrollment + execution. Returns (enrolled, executed)."""
    sb = _supabase()
    if not sb:
        _log("supabase client unavailable — skipping tick")
        return 0, 0
    enrolled = enrollment_tick(sb)
    executed = execution_tick(sb)
    return enrolled, executed


def loop(interval: int) -> int:
    interval = max(1, int(interval))
    _log(f"sequence-runner up; tick interval = {interval}s")
    while True:
        try:
            tick()
        except Exception as e:
            _log(f"tick crashed: {e}")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            _log("sequence-runner shutting down (SIGINT)")
            return 0


def tail(count: int) -> int:
    if not LOG_PATH.exists():
        print("(no log yet)")
        return 0
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-count:]
    except OSError as e:
        print(f"read failed: {e}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Drip-campaign sequence runner")
    sub = p.add_subparsers(dest="command", required=True)

    once = sub.add_parser("once", help="Run one tick and exit")
    once.set_defaults(func=lambda _a: 0 if tick() else 0)

    lp = sub.add_parser("loop", help="Run continuously")
    lp.add_argument("--interval", type=int, default=10, help="seconds between ticks (default: 10)")
    lp.set_defaults(func=lambda a: loop(a.interval))

    tl = sub.add_parser("tail", help="Print the last N log lines")
    tl.add_argument("--count", type=int, default=50)
    tl.set_defaults(func=lambda a: tail(a.count))

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
