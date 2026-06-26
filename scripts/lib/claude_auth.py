"""Claude Code CLI auth-priority helpers (Bravo Python port).

Behaviorally identical to scripts/c_suite_context.js (Node) and
APPS/CFO-Agent/cfo/claude_auth.py (Atlas). Bravo daemons that spawn the
`claude` CLI as a subprocess (e.g. extraction_consumer.py) use these so the
CLI authenticates with CC's Claude Code SUBSCRIPTION (OAuth) instead of the
metered ANTHROPIC_API_KEY.

Auth priority:
  1. Claude Code subscription OAuth (free under CC's plan, registered by
     `claude setup-token`, stored at ~/.claude/.credentials.json)
  2. ANTHROPIC_API_KEY (paid metered, fallback only)

CROSS-LANGUAGE SYNC (CRITICAL): keep the _AUTH_FAIL_PATTERN + OAuth path
detection behaviorally identical to scripts/c_suite_context.js and
CFO-Agent/cfo/claude_auth.py. Diverge only in language idiom, never behavior.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Mapping, Optional


# Matches BOTH auth errors and quota/rate-limit errors. Same regex as
# c_suite_context.js / CFO claude_auth.py — kept in sync deliberately.
_AUTH_FAIL_PATTERN = re.compile(
    r"authentication_error|"
    r"OAuth token has expired|"
    r"401|"
    r"Invalid API key|"
    r"Please obtain a new token|"
    r"usage limit|"
    r"rate limit|"
    r"quota exceeded|"
    r"reached your.*limit|"
    r"429",
    re.IGNORECASE,
)


def build_claude_spawn_env(
    force_api_key: bool = False,
    base: Optional[Mapping[str, str]] = None,
    extras: Optional[Mapping[str, str]] = None,
) -> dict[str, str]:
    """Child-process env that respects subscription-first auth.

    Default (force_api_key=False): strips ANTHROPIC_API_KEY so the claude CLI
    falls through to the OAuth subscription token. Pass force_api_key=True on the
    retry path to enable the paid API-key fallback.
    """
    if base is None:
        base = os.environ
    env: dict[str, str] = dict(base)
    if extras:
        env.update(extras)
    if not force_api_key:
        env.pop("ANTHROPIC_API_KEY", None)
    return env


def is_claude_auth_or_quota_failure(raw_output: str, exit_code: int) -> bool:
    """True when the CLI failed in a way the caller should retry on the API-key
    fallback path (auth error OR quota/rate-limit)."""
    if exit_code == 0:
        return False
    if not raw_output:
        return False
    return bool(_AUTH_FAIL_PATTERN.search(raw_output))


def check_claude_auth_paths(
    home: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    """Detect which auth paths are usable: {hasOAuth, oauthPath, hasApiKey, claudeDir}."""
    if env is None:
        env = os.environ
    if home is None:
        home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or ""

    claude_dir = Path(home) / ".claude"
    candidates = [claude_dir / ".credentials.json", claude_dir / "credentials.json"]
    oauth_path: Optional[str] = None
    for candidate in candidates:
        try:
            if candidate.stat().st_size > 0:
                oauth_path = str(candidate)
                break
        except (FileNotFoundError, OSError):
            continue

    api_key = env.get("ANTHROPIC_API_KEY") or ""
    return {
        "hasOAuth": oauth_path is not None,
        "oauthPath": oauth_path,
        "hasApiKey": bool(api_key),
        "claudeDir": str(claude_dir),
    }
