"""Claude Code subscription-first auth helpers.

Port of scripts/c_suite_context.js:95-165 — the auth-priority pattern the
Telegram bridge has been using since V15.8 (2026-04-27). Same shape, same
regex, same semantics, just Python so the dashboard bridge (warm pool +
bridge_chat_server) can use it without crossing the Node/Python boundary.

CROSS-LANGUAGE SYNC (CRITICAL):
This file MUST stay behaviorally identical to:
  scripts/c_suite_context.js (Node — Telegram + Bravo CLI tools)
  APPS/CFO-Agent/cfo/claude_auth.py (Python — Atlas's bridge)
The three live in separate repos but share one regex and one auth-priority
rule. If Anthropic changes the auth-failure or quota-error patterns, all
three implementations update in lockstep.

Auth priority (the rule):
  - Default: subscription-first. Spawn `claude` with ANTHROPIC_API_KEY stripped
    from the env so the CLI falls through to the OAuth token from
    `claude setup-token` (CC's Claude.ai Pro subscription).
  - On retry after auth/quota failure: spawn with ANTHROPIC_API_KEY restored,
    paying per-token from console.anthropic.com.

This is CC's billing model: free under Pro until the 5-hour rolling window
caps, then paid metered API. Never the other way around.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional


# Single-source regex for "subscription failed, fall over to API key" signals.
# Covers auth-token expiry, invalid keys, usage caps, rate limits, and HTTP
# 401/429 responses. Matches both stderr text and structured JSON error events
# claude emits during streaming.
_AUTH_FAIL_PATTERN = re.compile(
    r"authentication_error"
    r"|OAuth token has expired"
    r"|401"
    r"|Invalid API key"
    r"|Please obtain a new token"
    r"|usage limit"
    r"|rate limit"
    r"|quota exceeded"
    r"|reached your.*limit"
    r"|429",
    re.IGNORECASE,
)


def build_claude_spawn_env(
    *,
    force_api_key: bool = False,
    base: Optional[dict] = None,
    extras: Optional[dict] = None,
) -> dict:
    """Build a child-process env that respects subscription-first auth.

    Args:
        force_api_key: True on the paid-fallback retry path. False (default)
            spawns subscription-first.
        base: starting env (default os.environ).
        extras: additional env keys to merge on top (e.g. CI=true).

    Returns:
        A dict suitable for subprocess.Popen's env= argument.
    """
    env = dict(base if base is not None else os.environ)
    if extras:
        env.update(extras)
    if not force_api_key:
        # Strip the key so claude CLI uses the OAuth token (subscription).
        # Removing absent keys is a no-op; safe either way.
        env.pop("ANTHROPIC_API_KEY", None)
    return env


def is_claude_auth_or_quota_failure(raw_output: str, exit_code: Optional[int]) -> bool:
    """Detect "subscription failed, try API key" signals from claude CLI output.

    Matches stderr+stdout against _AUTH_FAIL_PATTERN. Returns False on a
    clean exit (exit_code == 0) regardless of output — claude succeeded,
    no retry needed.

    Note: exit_code can be None when the process is still running OR was
    killed by signal. We treat None as "the process died unexpectedly"
    and pattern-match the output to decide if it was auth/quota related.
    """
    if exit_code == 0:
        return False
    if not raw_output:
        return False
    return bool(_AUTH_FAIL_PATTERN.search(raw_output))


def check_claude_auth_paths(home: Optional[str] = None, env: Optional[dict] = None) -> dict:
    """Inspect the local machine for OAuth credentials + API key fallback.

    Used by startup health checks. The OAuth file lives at
    ~/.claude/.credentials.json on Mac + Windows + Linux. Returns:
        {
            "has_oauth": bool,
            "oauth_path": str | None,
            "has_api_key": bool,
            "claude_dir": str,
        }
    """
    home_dir = home or os.environ.get("HOME") or os.environ.get("USERPROFILE") or ""
    claude_dir = Path(home_dir) / ".claude"
    # Real path is .credentials.json (leading dot). Keep the legacy candidate
    # as a fallback in case the storage layout changes.
    candidates = [
        claude_dir / ".credentials.json",
        claude_dir / "credentials.json",
    ]
    oauth_path: Optional[str] = None
    for p in candidates:
        try:
            if p.stat().st_size > 0:
                oauth_path = str(p)
                break
        except OSError:
            continue
    api_key = (env or os.environ).get("ANTHROPIC_API_KEY", "")
    return {
        "has_oauth": bool(oauth_path),
        "oauth_path": oauth_path,
        "has_api_key": bool(api_key),
        "claude_dir": str(claude_dir),
    }
