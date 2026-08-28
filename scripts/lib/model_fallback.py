"""model_fallback.py — unified smart model executor (Claude CLI → OpenCode CLI).

SINGLE ENTRY POINT for any automation that needs a model call. Tries the
Claude subscription CLI first (run_claude_cli). On failure — quota reached,
auth error, CLI missing, timeout — automatically falls back to OpenCode CLI
with the appropriate free model tier.

USAGE:
    from lib.model_fallback import run_smart_cli

    # For IG DM Closer (sales closing — needs big model):
    reply = run_smart_cli(prompt, system=persona, task_type="closing")

    # For Telegram bridge (general reasoning):
    reply = run_smart_cli(prompt, system=persona, task_type="reasoning")

    # For extraction consumer (fast classification):
    reply = run_smart_cli(prompt, system=persona, task_type="fast")

The function returns the model's text, or None if BOTH tiers fail. Callers
should handle None the same way they handled run_claude_cli returning None —
degrade gracefully, never crash.

TELEMETRY: Every fallback event is logged to stderr with a [model_fallback]
prefix so PM2 logs / SESSION_LOG captures the event.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.claude_cli import run_claude_cli  # noqa: E402
from lib.opencode_cli import run_opencode_cli, model_for_task, TIER_MODELS  # noqa: E402


# ── CLI alias → model mapping (for Claude tier) ─────────────────────────────
# Matches claude_cli.py's convention: callers pass "sonnet" / "haiku" / "opus".
_CLAUDE_ALIAS_DEFAULT = "sonnet"


def _prompt_fingerprint(prompt: str) -> str:
    """Privacy-safe prompt identifier for logs: sha256 prefix + length.
    Never log raw prompt content (lead DMs / inbound email are PII)."""
    return f"sha256:{hashlib.sha256(prompt.encode('utf-8', 'replace')).hexdigest()[:12]} len={len(prompt)}"


def _safe_call(fn, *args, **kwargs) -> Optional[str]:
    """Run a tier function, converting ANY exception into None + stderr note.

    Contract: run_smart_cli NEVER raises. The tier functions already catch
    Timeout/OSError internally; this guards against anything unexpected
    upstream of the spawn (env building, path resolution, etc.)."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 — deliberate total swallow by design
        sys.stderr.write(
            f"[model_fallback] tier {getattr(fn, '__name__', fn)} raised "
            f"{type(e).__name__}: {e} — treating as None\n")
        return None


# ── Fallback-tier health ─────────────────────────────────────────────────────
# On-disk, because the callers that matter are short-lived cron processes: the
# inbound sweep runs every 5 minutes and exits, so an in-process record would be
# discarded between exactly the ticks it needs to inform.
#
# NOT derived from _log_telemetry below: that appends prose to SESSION_LOG.md,
# which is an auto-generated file guarded against hand-edits and is not a
# queryable store. Health needs a real one, and this is the smallest possible.
TIER_HEALTH_PATH = PROJECT_ROOT / "state" / "model_tier_health.json"

# Consecutive failures before a model is moved to the back of the queue. Three
# tolerates a transient blip; the 2026-08-26 incident was a model failing every
# single call for hours.
TIER_DEMOTE_AFTER = 3

# How long a demotion holds before the model is probed again. Without an expiry
# a demotion is permanent in practice — see _order_by_health for why. 30 minutes
# is long enough to ride out the kind of outage that caused the demotion, short
# enough that a recovered model returns to first place within a few sweeps.
DEMOTE_TTL_SEC = 1800


def _read_tier_health() -> dict:
    """Never raises. Corrupt/missing state means "no opinion", which restores
    the declared order — the behaviour that shipped before this existed."""
    try:
        if TIER_HEALTH_PATH.exists():
            data = json.loads(TIER_HEALTH_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:  # noqa: BLE001 - advisory data, fail open
        pass
    return {}


def _record_tier_health(task_type: str, model: str, *, ok: bool) -> None:
    """Update the consecutive-failure counter for one (task_type, model)."""
    try:
        data = _read_tier_health()
        key = f"{task_type}:{model}"
        entry = data.get(key) or {}
        if ok:
            entry["consecutive_fail"] = 0
            entry["last_ok"] = datetime.now(timezone.utc).isoformat()
        else:
            entry["consecutive_fail"] = int(entry.get("consecutive_fail", 0)) + 1
            entry["last_fail"] = datetime.now(timezone.utc).isoformat()
        data[key] = entry
        TIER_HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = TIER_HEALTH_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, TIER_HEALTH_PATH)
    except Exception:  # noqa: BLE001 - must never break a model call
        pass


def _order_by_health(task_type: str, candidates: list[str]) -> list[str]:
    """Stable order: healthy models keep their declared position, models over
    the demotion threshold move to the back. Never drops a candidate.

    A DEMOTION EXPIRES. Codex's adversarial review caught that the first draft
    could not recover: run_smart_cli returns on the first candidate that
    succeeds, so once a model is behind a working one it is never called again,
    never records a success, and its consecutive_fail never resets — a single
    transient outage would have re-ordered that task type permanently, until
    someone deleted the state file by hand.

    The first draft's test "passed" because it called _record_tier_health(ok=True)
    directly. That proved the reset mechanism worked while proving nothing about
    whether any real code path could reach it. Time-based expiry is what makes
    the recovery reachable without a success: after DEMOTE_TTL_SEC the model is
    simply eligible again and gets probed on the next call.
    """
    data = _read_tier_health()
    now = datetime.now(timezone.utc)

    def demoted(m: str) -> int:
        entry = data.get(f"{task_type}:{m}") or {}
        try:
            if int(entry.get("consecutive_fail", 0)) < TIER_DEMOTE_AFTER:
                return 0
        except (TypeError, ValueError):
            return 0
        last_fail = entry.get("last_fail")
        if not last_fail:
            return 1
        try:
            age = (now - datetime.fromisoformat(str(last_fail))).total_seconds()
        except (TypeError, ValueError):
            return 0  # unparseable timestamp — do not hold a demotion on it
        return 1 if age < DEMOTE_TTL_SEC else 0

    return sorted(candidates, key=demoted)


def _log_telemetry(agent_name: str, fallback_model: str, task_type: str, elapsed: float) -> None:
    """Best-effort logging of fallback events to memory/SESSION_LOG.md."""
    try:
        log_file = PROJECT_ROOT / "memory" / "SESSION_LOG.md"
        if log_file.is_file():
            entry = f"- [{time.strftime('%Y-%m-%d %H:%M:%S')}] MODEL FALLBACK: agent={agent_name} model={fallback_model} task_type={task_type} latency={elapsed}s\n"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(entry)
    except Exception:  # noqa: BLE001
        pass  # Never break caller on telemetry log failure


def run_smart_cli(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: str = "sonnet",
    timeout: int = 90,
    cwd: Optional[Path] = None,
    task_type: str = "default",
    fallback_timeout: int = 120,
    agent_name: str = "bravo",
) -> Optional[str]:
    """Try Claude CLI first; fall back to OpenCode CLI on failure.

    Parameters
    ----------
    prompt : str
        The user/task prompt.
    system : str, optional
        System prompt / persona instructions.
    model : str
        Claude CLI alias ("sonnet", "haiku", "opus"). Ignored for fallback.
    timeout : int
        Timeout for the Claude CLI call (seconds).
    cwd : Path, optional
        Working directory for the subprocess.
    task_type : str
        One of "reasoning", "closing", "fast", "classify", "default".
        Determines which free model is used on fallback.
    fallback_timeout : int
        Timeout for the OpenCode CLI fallback call (seconds).
    agent_name : str
        Agent identity for telemetry logging.

    Returns
    -------
    str or None
        Model output text, or None if both tiers fail.
    """
    # ── Tier 1: Claude CLI (subscription OAuth) ───────────────────────────
    start = time.perf_counter()
    result = _safe_call(
        run_claude_cli, prompt, system=system, model=model, timeout=timeout, cwd=cwd
    )
    elapsed_claude = round(time.perf_counter() - start, 1)

    if result is not None:
        return result

    # ── Tier 2: OpenCode CLI (free models), ordered by recent health ──────
    # WHY THE ORDERING (2026-08-28): the declared primary/secondary order was
    # static, so a fallback model that had been timing out all day was still
    # tried FIRST, every time, for the full fallback_timeout. Measured on
    # 2026-08-26: claude 31.9s -> nemotron 120s TIMEOUT -> mimo 20.6s SUCCESS =
    # 172.5s for one classification, against the inbound sweep's 300s wall. The
    # sweep died mid-mailbox because two thirds of its budget went to a tier
    # already known to be dead.
    #
    # Health is advisory and self-healing: a demoted model is moved to the BACK
    # of the queue, never removed, so it returns to first place on its next
    # success. With no history the order is exactly the declared one.
    primary = model_for_task(task_type)
    _, secondary = TIER_MODELS.get(task_type, TIER_MODELS["default"])
    candidates = [primary] + ([secondary] if secondary != primary else [])
    ordered = _order_by_health(task_type, candidates)

    if ordered != candidates:
        sys.stderr.write(
            f"[model_fallback] health reorder for task_type={task_type}: "
            f"{candidates} -> {ordered}\n")

    sys.stderr.write(
        f"[model_fallback] Claude CLI returned None after {elapsed_claude}s — "
        f"falling back to OpenCode ({ordered[0]}) for agent={agent_name}, "
        f"task_type={task_type}\n"
    )

    for candidate in ordered:
        start_fb = time.perf_counter()
        result = _safe_call(
            run_opencode_cli,
            prompt,
            system=system,
            model=candidate,
            timeout=fallback_timeout,
            cwd=cwd,
            task_type=task_type,
        )
        elapsed_fb = round(time.perf_counter() - start_fb, 1)

        if result is not None:
            sys.stderr.write(
                f"[model_fallback] OpenCode fallback SUCCESS ({candidate}) "
                f"in {elapsed_fb}s\n"
            )
            _record_tier_health(task_type, candidate, ok=True)
            _log_telemetry(agent_name, candidate, task_type, elapsed_fb)
            return result

        sys.stderr.write(
            f"[model_fallback] fallback {candidate} failed after {elapsed_fb}s\n")
        _record_tier_health(task_type, candidate, ok=False)

    # ── Both tiers exhausted ──────────────────────────────────────────────
    sys.stderr.write(
        f"[model_fallback] ALL TIERS EXHAUSTED — Claude + OpenCode both "
        f"returned None for agent={agent_name}. Prompt {_prompt_fingerprint(prompt)}\n"
    )
    return None


def is_fallback_available() -> bool:
    """Quick check: is the OpenCode CLI even installed?"""
    from lib.opencode_cli import resolve_opencode_bin
    return resolve_opencode_bin() is not None


# ── CLI self-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test model_fallback.py")
    parser.add_argument("--force-fallback", action="store_true",
                        help="Skip Claude CLI to test OpenCode fallback directly")
    parser.add_argument("--task-type", default="default",
                        choices=list(TIER_MODELS.keys()))
    parser.add_argument("prompt", nargs="?", default="Reply with PONG.")
    args = parser.parse_args()

    if args.force_fallback:
        print("[model_fallback] --force-fallback: skipping Claude CLI, testing OpenCode directly")
        result = run_opencode_cli(
            args.prompt, task_type=args.task_type, timeout=60
        )
    else:
        result = run_smart_cli(
            args.prompt, task_type=args.task_type, timeout=30, fallback_timeout=60
        )

    if result:
        print(f"[model_fallback] SUCCESS: {result[:300]}")
    else:
        print("[model_fallback] FAILED: returned None")
        sys.exit(1)
