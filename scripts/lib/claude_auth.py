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

CROSS-LANGUAGE SYNC: the signal list is NO LONGER hand-copied. It lives in
config/claude_auth_signals.json and every implementation loads it (Python here,
Node in scripts/c_suite_context.js). scripts/tests/test_claude_auth_parity.py
fails if any implementation disagrees with the fixture.

Why that changed (2026-09-03): four copies of this regex existed, each with a
comment saying "keep in lockstep". They drifted. The Node copy matched
"You've hit your session limit"; this Python copy did not — and this is the copy
guarding the SunBiz extraction daemon, so a rep's application drop died with
`cli_failed` and the free fallback never ran. A comment is not enforcement.

SCOPE OF THIS PREDICATE (read before relying on it): it is an OPTIMISATION, not
a safety gate. It answers "is retrying on the same subscription pointless?" —
nothing more. Callers MUST fall back to the free tier on ANY model failure, so
that a signal this list has never seen costs one wasted retry instead of the
whole feature. See model_fallback.run_smart_cli and extraction_consumer's tier
ladder for the shape that is safe.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Optional

# config/claude_auth_signals.json — canonical, shared with the Node port.
SIGNALS_PATH = Path(__file__).resolve().parents[2] / "config" / "claude_auth_signals.json"

# Last-resort inline copy. Used ONLY if the fixture file is unreadable (a
# partial VPS deploy, a truncated checkout). It is deliberately the widest
# signals rather than the old narrow set: if we cannot read the canon, the safe
# failure is "assume quota and take the free tier", never "assume a code bug and
# keep hammering a capped subscription".
_FALLBACK_SIGNALS = [
    "authentication_error", "OAuth token has expired", "Invalid API key",
    "usage limit", "rate limit", "quota exceeded", "reached your.*limit",
    "hit your.*limit", "session limit", "weekly limit", "limit reached",
    "credit balance is too low", "out of credits",
    r"(?:status|code|error|HTTP)\W{0,12}(?:401|403|429|529)\b",
]


def _load_signals() -> list[str]:
    try:
        data = json.loads(SIGNALS_PATH.read_text(encoding="utf-8"))
        signals = data.get("signals")
        if isinstance(signals, list) and signals:
            return [str(s) for s in signals]
    except Exception:  # noqa: BLE001 — see _FALLBACK_SIGNALS rationale above
        pass
    return list(_FALLBACK_SIGNALS)


AUTH_FAIL_SIGNALS: list[str] = _load_signals()
_AUTH_FAIL_PATTERN = re.compile("|".join(f"(?:{s})" for s in AUTH_FAIL_SIGNALS), re.IGNORECASE)


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
