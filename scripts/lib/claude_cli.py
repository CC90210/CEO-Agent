"""claude_cli.py — one-shot local Claude CLI calls on CC's SUBSCRIPTION OAuth.

The fleet's ANTHROPIC_API_KEY is metered and currently out of credits, and CC's
iron rule bans API keys in automations ("CLI-only"). Every automation that needs
a model call — daily-brief narration, the sleep-agent memory consolidation,
future self-improving loops — routes through here instead of hitting
api.anthropic.com.

It spawns the local `claude` CLI with build_claude_spawn_env(force_api_key=False),
which STRIPS ANTHROPIC_API_KEY from the child env so the CLI authenticates with
CC's Claude Code subscription (OAuth token from `claude setup-token`). The boot
is lean and side-effect-free: no MCP servers, no slash commands, no
settings/CLAUDE.md/hooks (--setting-sources "").

Returns the model's text, or None on ANY failure (missing CLI, expired token,
timeout, non-zero exit) so callers degrade gracefully instead of crashing.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    from _subprocess_helpers import WINDOWLESS_FLAGS  # type: ignore
except Exception:  # pragma: no cover - fallback if helper moves
    WINDOWLESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)

from lib.claude_auth import build_claude_spawn_env  # noqa: E402


def resolve_claude_bin() -> Optional[str]:
    """Locate the claude CLI. shutil.which first; Windows npm-global /
    .local/bin fallbacks so a PYTHONW scheduler with a slim PATH still finds
    it (mirrors bravo_cli/warm_claude_pool)."""
    found = shutil.which("claude")
    if found:
        return found
    if os.name == "nt":
        for c in (Path.home() / ".local" / "bin" / "claude.exe",
                  Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd"):
            if c.is_file():
                return str(c)
    return None


def run_claude_cli(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: str = "sonnet",
    timeout: int = 90,
    cwd: Optional[Path] = None,
) -> Optional[str]:
    """One-shot `claude -p` on the subscription OAuth. Returns stdout text, or
    None on any failure.

    model: a CLI alias ("sonnet" | "haiku" | "opus") — always resolves,
      unlike a dated API model id.
    system: optional --append-system-prompt persona/instructions.
    """
    claude_bin = resolve_claude_bin()
    if not claude_bin:
        sys.stderr.write("[claude_cli] claude CLI not found on PATH\n")
        return None

    args = [claude_bin, "-p", prompt]
    if system:
        args += ["--append-system-prompt", system]
    args += [
        "--model", model,
        "--output-format", "text",
        # Pure text transform — deny ALL tools. Callers feed untrusted data
        # (lead notes, session logs) into the prompt, so a prompt-injection
        # payload must not be able to invoke Bash/Read/Write etc. An empty
        # allowlist = no tool is available (verified). Belt-and-suspenders with
        # the boot-strip flags below (no MCP servers, no slash commands, no
        # settings/CLAUDE.md/hooks). --no-session-persistence avoids writing
        # session state for these one-shot calls.
        "--allowed-tools", "",
        "--no-session-persistence",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--setting-sources", "",
    ]

    env = build_claude_spawn_env(force_api_key=False, extras={
        "CI": "true", "NONINTERACTIVE": "true", "NO_COLOR": "1",
        "FORCE_COLOR": "0", "PAGER": "cat",
        "CLAUDE_PROJECT_DIR": str(PROJECT_ROOT),
    })
    try:
        proc = subprocess.run(
            args, cwd=str(cwd or PROJECT_ROOT), capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
            creationflags=WINDOWLESS_FLAGS, env=env,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        sys.stderr.write(f"[claude_cli] spawn failed: {e}\n")
        return None
    if proc.returncode != 0:
        sys.stderr.write(
            f"[claude_cli] exit {proc.returncode}: {(proc.stderr or '').strip()[:300]}\n")
        return None
    return (proc.stdout or "").strip() or None
