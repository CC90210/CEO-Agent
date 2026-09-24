"""Unified subscription model runner: Claude first, Codex second.

OpenCode's free tier is only usable inside an OpenCode session and therefore is
not a valid unattended fallback.  This module uses two independently billed
subscriptions and never inherits metered ``*_API_KEY`` credentials into Codex.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.claude_cli import run_claude_cli  # noqa: E402
from lib.codex_cli import is_codex_authenticated, run_codex_cli  # noqa: E402


def _prompt_fingerprint(prompt: str) -> str:
    digest = hashlib.sha256(prompt.encode("utf-8", "replace")).hexdigest()[:12]
    return f"sha256:{digest} len={len(prompt)}"


def _safe_call(fn, *args, **kwargs) -> Optional[str]:
    """A failed provider never crashes its automation caller."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - provider boundary
        sys.stderr.write(
            f"[model_fallback] tier {getattr(fn, '__name__', fn)} raised "
            f"{type(exc).__name__}; treating as unavailable\n"
        )
        return None


def _log_telemetry(agent_name: str, task_type: str, elapsed: float) -> None:
    try:
        log_file = PROJECT_ROOT / "memory" / "SESSION_LOG.md"
        if log_file.is_file():
            entry = (
                f"- [{time.strftime('%Y-%m-%d %H:%M:%S')}] MODEL FALLBACK: "
                f"agent={agent_name} model=codex-subscription "
                f"task_type={task_type} latency={elapsed}s\n"
            )
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(entry)
    except OSError:
        pass


def run_smart_cli(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: str = "sonnet",
    timeout: int = 90,
    cwd: Optional[Path] = None,
    task_type: str = "default",
    fallback_timeout: int = 180,
    agent_name: str = "bravo",
    operator_trusted: bool = False,
) -> Optional[str]:
    """Return Claude output, then Codex output, or ``None``.

    Codex currently has no true text-only/no-tools CLI mode. Its read-only
    sandbox still permits shell and absolute file reads, so attacker-controlled
    email, DM, lead, and scraped text must stop after the tool-denied Claude
    tier. Only callers that independently authenticated the operator may set
    ``operator_trusted=True``.
    """
    start = time.perf_counter()
    result = _safe_call(
        run_claude_cli,
        prompt,
        system=system,
        model=model,
        timeout=timeout,
        cwd=cwd,
    )
    claude_elapsed = round(time.perf_counter() - start, 1)
    if result is not None:
        return result

    if not operator_trusted:
        sys.stderr.write(
            f"[model_fallback] Claude unavailable after {claude_elapsed}s; "
            "Codex skipped because payload is not operator-authenticated\n"
        )
        return None

    sys.stderr.write(
        f"[model_fallback] Claude unavailable after {claude_elapsed}s; "
        f"using Codex subscription for agent={agent_name}, task_type={task_type}\n"
    )
    start = time.perf_counter()
    result = _safe_call(
        run_codex_cli,
        prompt,
        system=system,
        timeout=fallback_timeout,
        cwd=cwd,
        sandbox="read-only",
        respect_rules=False,
        operator_trusted=True,
    )
    elapsed = round(time.perf_counter() - start, 1)
    if result is not None:
        sys.stderr.write(f"[model_fallback] Codex fallback SUCCESS in {elapsed}s\n")
        _log_telemetry(agent_name, task_type, elapsed)
        return result

    sys.stderr.write(
        f"[model_fallback] ALL SUBSCRIPTIONS EXHAUSTED for agent={agent_name}; "
        f"prompt {_prompt_fingerprint(prompt)}\n"
    )
    return None


def is_fallback_available() -> bool:
    """Whether the second subscription is installed *and* authenticated."""
    return is_codex_authenticated()


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Run the subscription model ladder")
    parser.add_argument("--force-fallback", action="store_true",
                        help="Skip Claude and invoke Codex directly")
    parser.add_argument("--stdin", action="store_true",
                        help="Read the prompt from stdin (required for private data)")
    parser.add_argument("--workspace-write", action="store_true",
                        help="Allow Codex writes inside the selected workspace")
    parser.add_argument("--respect-rules", action="store_true",
                        help="Load repository AGENTS instructions")
    parser.add_argument(
        "--operator-trusted",
        action="store_true",
        help="Assert the prompt came from an authenticated operator, not inbound data",
    )
    parser.add_argument("--cwd", default=str(PROJECT_ROOT))
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--task-type", default="default")
    parser.add_argument("prompt", nargs="?", default=None)
    args = parser.parse_args()

    if args.stdin:
        prompt = sys.stdin.read()
    else:
        prompt = args.prompt or "Reply with PONG."
    if not prompt.strip():
        sys.stderr.write("[model_fallback] empty prompt\n")
        return 2

    root = Path(args.cwd).resolve()
    if args.force_fallback:
        if not args.operator_trusted:
            sys.stderr.write(
                "[model_fallback] refusing tool-capable Codex for an "
                "unauthenticated payload; pass --operator-trusted only after "
                "verifying operator provenance\n"
            )
            return 2
        result = run_codex_cli(
            prompt,
            timeout=args.timeout,
            cwd=root,
            sandbox="workspace-write" if args.workspace_write else "read-only",
            respect_rules=args.respect_rules,
            operator_trusted=True,
        )
    else:
        result = run_smart_cli(
            prompt,
            timeout=args.timeout,
            fallback_timeout=args.timeout,
            cwd=root,
            task_type=args.task_type,
            operator_trusted=args.operator_trusted,
        )
    if not result:
        return 1
    sys.stdout.write(result)
    if not result.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
