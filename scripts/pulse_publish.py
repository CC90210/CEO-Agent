"""
pulse_publish.py — Atomic, schema-validated writer for Bravo's ceo_pulse.json.

This is the only blessed path to update data/pulse/ceo_pulse.json. Direct
file edits are forbidden (per brain/AGENT_ORCHESTRATION.md § Pulse Protocol).

Why a script and not just an edit:
  1. Atomic write (write-to-temp + rename) — readers never see partial JSON
  2. Schema validation — catches missing fields before publish
  3. Stamps `updated_at` automatically — never stale on republish
  4. Optional inbox notification — pings Atlas + Maven when material fields change

Usage:
  # Refresh from CLI (recommended for CC tonight):
  python scripts/pulse_publish.py refresh \\
    --net-mrr 3322 \\
    --priority "Diversify revenue — close 2 new retainer clients before May 15" \\
    --top-client-pct 84

  # Validate current pulse without writing:
  python scripts/pulse_publish.py validate

  # Show current pulse with freshness:
  python scripts/pulse_publish.py status [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
PULSE_PATH = REPO_ROOT / "data" / "pulse" / "ceo_pulse.json"
SCHEMA_VERSION = "0.3.0"

REQUIRED_TOP_LEVEL = {"agent", "version", "updated_at", "status", "revenue", "strategy"}
REQUIRED_REVENUE = {"net_mrr_usd", "target_mrr_usd", "gap_usd", "active_clients"}
REQUIRED_STRATEGY = {"current_focus", "top_priority_this_week"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_pulse() -> dict[str, Any] | None:
    if not PULSE_PATH.exists():
        return None
    try:
        return json.loads(PULSE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def validate(payload: dict[str, Any]) -> list[str]:
    """Return list of validation errors. Empty list = valid."""
    errors: list[str] = []
    missing_top = REQUIRED_TOP_LEVEL - set(payload.keys())
    if missing_top:
        errors.append(f"missing top-level fields: {sorted(missing_top)}")
    revenue = payload.get("revenue", {})
    if isinstance(revenue, dict):
        missing_rev = REQUIRED_REVENUE - set(revenue.keys())
        if missing_rev:
            errors.append(f"missing revenue fields: {sorted(missing_rev)}")
        if revenue.get("net_mrr_usd") is not None and not isinstance(revenue["net_mrr_usd"], (int, float)):
            errors.append("revenue.net_mrr_usd must be a number")
    else:
        errors.append("revenue must be an object")
    strategy = payload.get("strategy", {})
    if isinstance(strategy, dict):
        missing_strat = REQUIRED_STRATEGY - set(strategy.keys())
        if missing_strat:
            errors.append(f"missing strategy fields: {sorted(missing_strat)}")
    else:
        errors.append("strategy must be an object")
    if "updated_at" in payload:
        try:
            ts = payload["updated_at"]
            if isinstance(ts, str):
                normalized = ts[:-1] + "+00:00" if ts.endswith("Z") else ts
                datetime.fromisoformat(normalized)
        except (ValueError, TypeError):
            errors.append("updated_at must be ISO 8601")
    return errors


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _v6_telemetry() -> dict[str, Any]:
    """Best-effort snapshot of Bravo's V6.0 surface for cross-agent visibility.

    Stamped into ceo_pulse.json so Atlas / Maven / Aura / Hermes can tell at
    a glance whether Bravo is on V5.5 or V6.0 and how healthy the new
    substrate is. Read-only — never raises. Unknown to V5.5-era siblings;
    they ignore it (JSON additive).
    """
    out: dict[str, Any] = {
        "mode": os.environ.get("EMPIRE_V6_MODE", "off").lower(),
        "hook_modes": {
            "secret_guard": os.environ.get("EMPIRE_HOOK_SECRET_GUARD", "report").lower(),
            "exec_guard":   os.environ.get("EMPIRE_HOOK_EXEC_GUARD",   "report").lower(),
            "state_guard":  os.environ.get("EMPIRE_HOOK_STATE_GUARD",  "off").lower(),
        },
    }
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import state_manager as _sm  # type: ignore
        s = _sm.status()
        if s.get("exists"):
            out["state_db"] = {
                "session_log_count":  s.get("session_log_count", 0),
                "transaction_count":  s.get("transaction_count", 0),
                "size_kb":            s.get("size_kb"),
                "last_heartbeat":     (s.get("agents") or [{}])[0].get("last_heartbeat"),
            }
        else:
            out["state_db"] = {"exists": False}
    except Exception:
        out["state_db"] = {"unreachable": True}
    try:
        import memory_retriever as _mr  # type: ignore
        r = _mr.status()
        out["fts5"] = {
            "sources":      r.get("sources"),
            "chunks":       r.get("chunks"),
            "last_indexed": r.get("last_indexed"),
            "size_kb":      r.get("size_kb"),
        }
    except Exception:
        out["fts5"] = {"unreachable": True}
    return out


# ── mechanical refresh ───────────────────────────────────────────────────────
# Split the pulse by WHO CAN HONESTLY AUTHOR EACH PART.
#
# Atlas pages CC when this file is >14d old, and on 2026-08-03 it was 15d old and
# right: nothing had ever scheduled a producer. The obvious fix — cron `refresh`
# nightly — is the wrong one. cmd_refresh() merges over the existing file and
# stamps updated_at=now, so a bare scheduled refresh would present 15-day-old
# strategy and directives as current. That converts a true "drifting" signal into
# a false "fresh" one, which is strictly worse than the alert.
#
# So: a cron may write only what a machine can KNOW (sibling pulse ages, V6
# telemetry, the commit log). Judgment — strategy, directives, blockers,
# client_health — is written by Bravo at session end, and revenue belongs to Atlas
# and is never written here at all. The mechanical pass records its own freshness
# in `mechanical_as_of` and leaves `updated_at` exactly where judgment left it.

SIBLING_PULSES = {
    "atlas": Path("C:/Users/User/APPS/CFO-Agent/data/pulse/cfo_pulse.json"),
    "maven": Path("C:/Users/User/CMO-Agent/data/pulse/cmo_pulse.json"),
    "aura": Path("C:/Users/User/APPS/Aura-Home-Agent/data/pulse/aura_pulse.json"),
}


def _pulse_age_hours(path: Path) -> float | None:
    """Hours since a sibling last published, or None if it never has / is unreadable.

    None is DATA, not an error — a sibling being dark is exactly what a CEO pulse
    should record. Only Bravo's own inputs failing is a reason to abort.
    """
    try:
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        ts = raw.get("updated_at")
        if not isinstance(ts, str):
            return None
        normalized = ts[:-1] + "+00:00" if ts.endswith("Z") else ts
        then = datetime.fromisoformat(normalized)
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - then).total_seconds() / 3600, 1)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _recent_commits(since_iso: str | None, limit: int = 15) -> list[str]:
    """Commit subjects since the last judgment write. Raises on failure.

    Deliberately NOT written into `recent_shipped`: that field holds hand-authored
    prose about what actually shipped, and a commit subject is a different kind of
    claim. Overwriting judgment prose with machine output would be the same lie in
    a smaller box. This lands in its own key and leaves `recent_shipped` alone.
    """
    cmd = ["git", "log", f"--max-count={limit}", "--pretty=format:%h %s"]
    if since_iso:
        cmd.insert(2, f"--since={since_iso}")
    try:
        from _subprocess_helpers import WINDOWLESS_FLAGS  # type: ignore
    except ImportError:
        WINDOWLESS_FLAGS = 0
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                          cwd=str(REPO_ROOT), encoding="utf-8", errors="replace",
                          creationflags=WINDOWLESS_FLAGS)
    if proc.returncode != 0:
        raise RuntimeError(f"git log failed (exit {proc.returncode}): "
                           f"{(proc.stderr or '').strip()[:200]}")
    return [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]


def cmd_autorefresh(args: argparse.Namespace) -> int:
    """Refresh ONLY the mechanically-knowable sections. Never moves updated_at."""
    existing = _read_pulse()
    if existing is None:
        print(f"ERROR: no pulse at {PULSE_PATH} — run `pulse_publish.py refresh` "
              f"first; autorefresh updates an existing pulse, it does not seed one.",
              file=sys.stderr)
        return 2

    try:
        commits = _recent_commits(existing.get("updated_at"))
    except Exception as exc:  # noqa: BLE001 — fail closed, never stamp a fake
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Refusing to write: a mechanical refresh that silently skips its own "
              "source is how a stale pulse starts looking fresh.", file=sys.stderr)
        return 1

    payload = dict(existing)
    payload["v6"] = _v6_telemetry()

    state = dict(existing.get("agent_system_state", {}))
    atlas_age = _pulse_age_hours(SIBLING_PULSES["atlas"])
    maven_age = _pulse_age_hours(SIBLING_PULSES["maven"])
    state["atlas_last_known_pulse_age_hours"] = atlas_age
    state["maven_last_known_pulse_age_hours"] = maven_age
    state["aura_pulse_exists"] = SIBLING_PULSES["aura"].exists()
    payload["agent_system_state"] = state

    payload["recent_commits"] = commits
    payload["mechanical_as_of"] = _now_iso()

    errors = validate(payload)
    if errors:
        print("VALIDATION FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps(payload, indent=2, default=str))
        print("\n(dry-run — pulse not written)", file=sys.stderr)
        return 0

    _atomic_write(PULSE_PATH, payload)

    judgment_age = _pulse_age_hours(PULSE_PATH.parent / PULSE_PATH.name) or 0
    print(f"OK — mechanical sections refreshed at {payload['mechanical_as_of']}")
    print(f"  commits since last judgment: {len(commits)}")
    print(f"  atlas pulse age: {atlas_age}h | maven: {maven_age}h | "
          f"aura exists: {state['aura_pulse_exists']}")
    print(f"  updated_at UNCHANGED: {payload.get('updated_at')}")
    if judgment_age > 24 * 7:
        print(f"  NOTE: judgment fields are {judgment_age / 24:.0f}d old. Strategy, "
              f"directives and blockers need a session-end write — "
              f"`pulse_publish.py refresh --priority ... --focus ...`.", file=sys.stderr)
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    existing = _read_pulse() or {}
    payload = dict(existing)
    payload["agent"] = "Bravo (CEO)"
    payload["version"] = SCHEMA_VERSION
    payload["updated_at"] = _now_iso()
    payload["status"] = args.status or existing.get("status", "ACTIVE")
    if args.session_note:
        payload["session_note"] = args.session_note
    # V6.0 telemetry stamp — siblings that read ceo_pulse.json see Bravo's
    # state DB / FTS5 / hook modes alongside the revenue & strategy fields.
    payload["v6"] = _v6_telemetry()

    revenue = dict(existing.get("revenue", {}))
    if args.net_mrr is not None:
        revenue["net_mrr_usd"] = args.net_mrr
        revenue["target_mrr_usd"] = revenue.get("target_mrr_usd", 5000)
        revenue["gap_usd"] = max(0, revenue["target_mrr_usd"] - args.net_mrr)
    if args.top_client_pct is not None:
        revenue["top_client_concentration_pct"] = args.top_client_pct
    if args.active_clients is not None:
        revenue["active_clients"] = args.active_clients
    revenue.setdefault("net_mrr_usd", existing.get("revenue", {}).get("net_mrr_usd", 0))
    revenue.setdefault("target_mrr_usd", 5000)
    revenue.setdefault("gap_usd", 5000 - revenue.get("net_mrr_usd", 0))
    revenue.setdefault("active_clients", existing.get("revenue", {}).get("active_clients", 0))
    payload["revenue"] = revenue

    strategy = dict(existing.get("strategy", {}))
    if args.priority:
        strategy["top_priority_this_week"] = args.priority
        strategy.setdefault("current_focus", args.priority)
    if args.focus:
        strategy["current_focus"] = args.focus
    strategy.setdefault("current_focus", existing.get("strategy", {}).get("current_focus", ""))
    strategy.setdefault("top_priority_this_week", existing.get("strategy", {}).get("top_priority_this_week", ""))
    payload["strategy"] = strategy

    errors = validate(payload)
    if errors:
        print("VALIDATION FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps(payload, indent=2, default=str))
        print("\n(dry-run — pulse not written)", file=sys.stderr)
        return 0

    _atomic_write(PULSE_PATH, payload)
    print(f"OK — ceo_pulse refreshed at {payload['updated_at']}")
    print(f"  net_mrr_usd:    ${revenue['net_mrr_usd']:,}")
    print(f"  gap_usd:        ${revenue['gap_usd']:,}")
    print(f"  priority:       {strategy['top_priority_this_week']}")

    # V6 BUILD 3 — emit a cross-agent event so Atlas/Maven/Aura wake on
    # pulse refresh instead of polling. Best-effort; never breaks the publish.
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        # Lazy import: event_bus pulls the heavyweight supabase client; the
        # refresh path is the only place pulse_publish needs it.
        from event_bus import publish as _bus_publish  # type: ignore[import-not-found]
        _bus_publish(
            "BRAVO_PULSE_REFRESHED",
            {
                "updated_at": payload["updated_at"],
                "net_mrr_usd": revenue.get("net_mrr_usd"),
                "gap_usd": revenue.get("gap_usd"),
                "v6_mode": (payload.get("v6") or {}).get("mode", "off"),
            },
            source="bravo",
            target=None,  # broadcast
        )
    except Exception:  # noqa: BLE001
        pass
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    payload = _read_pulse()
    if payload is None:
        print(f"ERROR — pulse not readable at {PULSE_PATH}", file=sys.stderr)
        return 2
    errors = validate(payload)
    if args.json:
        print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
    else:
        if errors:
            print("INVALID:")
            for e in errors:
                print(f"  - {e}")
        else:
            print("VALID")
    return 0 if not errors else 1


def cmd_status(args: argparse.Namespace) -> int:
    payload = _read_pulse()
    if payload is None:
        print(f"ERROR — pulse not readable at {PULSE_PATH}", file=sys.stderr)
        return 2
    updated = payload.get("updated_at", "?")
    age_hours: float | None = None
    try:
        ts = updated[:-1] + "+00:00" if isinstance(updated, str) and updated.endswith("Z") else updated
        dt = datetime.fromisoformat(ts) if isinstance(ts, str) else None
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except (ValueError, TypeError):
        pass
    summary = {
        "updated_at": updated,
        "age_hours": round(age_hours, 1) if age_hours is not None else None,
        "freshness": (
            "FRESH" if age_hours is not None and age_hours < 24
            else "AGING" if age_hours is not None and age_hours < 168
            else "STALE" if age_hours is not None
            else "UNKNOWN"
        ),
        "net_mrr_usd": payload.get("revenue", {}).get("net_mrr_usd"),
        "gap_usd": payload.get("revenue", {}).get("gap_usd"),
        "priority": payload.get("strategy", {}).get("top_priority_this_week"),
    }
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        print(f"updated_at:  {summary['updated_at']}")
        print(f"age_hours:   {summary['age_hours']}")
        print(f"freshness:   {summary['freshness']}")
        print(f"net_mrr_usd: ${summary['net_mrr_usd']}")
        print(f"gap_usd:     ${summary['gap_usd']}")
        print(f"priority:    {summary['priority']}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Bravo ceo_pulse atomic publisher.")
    sub = p.add_subparsers(dest="command", required=True)

    pr = sub.add_parser("refresh", help="Update ceo_pulse with new values")
    pr.add_argument("--net-mrr", type=float, default=None, help="Current net MRR (USD)")
    # '%%' not '%': argparse runs help strings through %-formatting, so a bare
    # '% of' was read as the '%o' conversion and `refresh --help` died with
    # "TypeError: %o format: an integer is required, not dict". The publisher
    # was unusable via its own help, which is part of why the pulse went 13
    # days without a refresh.
    pr.add_argument("--top-client-pct", type=float, default=None, help="Top-client concentration %% of MRR")
    pr.add_argument("--active-clients", type=int, default=None)
    pr.add_argument("--priority", type=str, default=None, help="This week's #1 priority")
    pr.add_argument("--focus", type=str, default=None, help="Current strategic focus")
    pr.add_argument("--status", type=str, default=None, help="ACTIVE | PAUSED | ESCALATED")
    pr.add_argument("--session-note", type=str, default=None)
    pr.add_argument("--dry-run", action="store_true")

    pa = sub.add_parser(
        "autorefresh",
        help="Refresh only machine-knowable sections (sibling pulse ages, V6 "
             "telemetry, commit log). Never moves updated_at — judgment stays "
             "as stale as it actually is.")
    pa.add_argument("--dry-run", action="store_true")

    pv = sub.add_parser("validate", help="Validate current pulse against schema")
    pv.add_argument("--json", action="store_true")

    ps = sub.add_parser("status", help="Show current pulse summary + freshness")
    ps.add_argument("--json", action="store_true")

    args = p.parse_args()
    handlers = {"refresh": cmd_refresh, "autorefresh": cmd_autorefresh,
                "validate": cmd_validate, "status": cmd_status}
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
