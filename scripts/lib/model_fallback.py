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
import os
import sys
import time
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

    # ── Tier 2: OpenCode CLI (free model) ─────────────────────────────────
    fallback_model = model_for_task(task_type)
    sys.stderr.write(
        f"[model_fallback] Claude CLI returned None after {elapsed_claude}s — "
        f"falling back to OpenCode ({fallback_model}) for agent={agent_name}, "
        f"task_type={task_type}\n"
    )

    start_fb = time.perf_counter()
    result = _safe_call(
        run_opencode_cli,
        prompt,
        system=system,
        model=fallback_model,
        timeout=fallback_timeout,
        cwd=cwd,
        task_type=task_type,
    )
    elapsed_opencode = round(time.perf_counter() - start_fb, 1)

    if result is not None:
        sys.stderr.write(
            f"[model_fallback] OpenCode fallback SUCCESS ({fallback_model}) "
            f"in {elapsed_opencode}s\n"
        )
        _log_telemetry(agent_name, fallback_model, task_type, elapsed_opencode)
        return result

    # ── Tier 2b: Try the secondary free model ─────────────────────────────
    _, secondary = TIER_MODELS.get(task_type, TIER_MODELS["default"])
    if secondary != fallback_model:
        sys.stderr.write(
            f"[model_fallback] Primary fallback failed — trying secondary: "
            f"{secondary}\n"
        )
        start_sec = time.perf_counter()
        result = _safe_call(
            run_opencode_cli,
            prompt,
            system=system,
            model=secondary,
            timeout=fallback_timeout,
            cwd=cwd,
            task_type=task_type,
        )
        elapsed_sec = round(time.perf_counter() - start_sec, 1)
        if result is not None:
            sys.stderr.write(
                f"[model_fallback] Secondary fallback SUCCESS ({secondary}) "
                f"in {elapsed_sec}s\n"
            )
            return result

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
