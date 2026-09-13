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

Claude Spillover (fixture v3, 2026-09-12): build_claude_spawn_env also strips
the `lane_env_strip` vars inherited from the parent before applying extras, and
is_subscription_limit() is the narrow usage-limit predicate. Both come from the
same fixture and are parity-tested against scripts/lib/claude_auth.py and the
Node port.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Optional


# Signals for "subscription failed, fall over to the free tier", the spillover
# lane vars, and the narrow subscription-limit signals.
#
# Loaded from config/claude_auth_signals.json — the SAME file
# scripts/lib/claude_auth.py and scripts/c_suite_context.js read.
# scripts/tests/test_claude_auth_parity.py fails if the three disagree.
# This file used to carry its own hand-copied alternation; it had drifted
# narrower than the Node one and missed "hit your … limit" entirely.
try:
    from lib.claude_auth import (  # type: ignore
        AUTH_FAIL_SIGNALS as _SIGNALS,
        LANE_ENV_VARS,
        SUBSCRIPTION_LIMIT_SIGNALS as _SUBSCRIPTION_LIMIT_SIGNALS,
    )
except Exception:  # noqa: BLE001 — bravo_cli is importable without scripts/ on sys.path
    import json as _json

    _SIGNALS_PATH = Path(__file__).resolve().parents[1] / "config" / "claude_auth_signals.json"

    def _fixture_list(key: str, fallback: list) -> list:
        # Same contract as lib.claude_auth._load_fixture_list: never raises
        # (the bridge imports this at startup), never silent.
        try:
            values = _json.loads(_SIGNALS_PATH.read_text(encoding="utf-8")).get(key)
            if isinstance(values, list) and values:
                return [str(v) for v in values]
            problem = f"has no non-empty {key!r} list"
        except Exception as e:  # noqa: BLE001
            problem = f"is unreadable ({type(e).__name__})"
        sys.stderr.write(f"[_claude_auth] {_SIGNALS_PATH} {problem}; using the inline fallback\n")
        return list(fallback)

    # Widest-signals last resort: assume quota, take the free tier.
    _SIGNALS = _fixture_list("signals", [
        "authentication_error", "OAuth token has expired", "Invalid API key",
        "usage limit", "rate limit", "quota exceeded", "reached your.*limit",
        "hit your.*limit", "session limit", "weekly limit", "limit reached",
        "credit balance is too low", "out of credits",
        r"(?:status|code|error|HTTP)\W{0,12}(?:401|403|429|529)\b",
    ])
    # The FULL lane list, never a subset: a missing name is a route into the
    # spillover proxy.
    LANE_ENV_VARS = tuple(_fixture_list("lane_env_strip", [
        "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL",
        "ANTHROPIC_SMALL_FAST_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "ANTHROPIC_DEFAULT_FABLE_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL",
        "ANTHROPIC_CUSTOM_HEADERS", "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_CODE_AUTO_COMPACT_WINDOW", "CLAUDE_CODE_MAX_CONTEXT_TOKENS",
        "BRAVO_CLAUDE_LANE",
    ]))
    _SUBSCRIPTION_LIMIT_SIGNALS = _fixture_list("subscription_limit_signals", [
        r"hit your (?:(?:session|weekly|daily|opus|sonnet|usage|5[- ]?hour|five[- ]hour)\s+)?limit",
        r"reached your (?:(?:session|weekly|daily|opus|sonnet|usage|5[- ]?hour|five[- ]hour)\s+)?limit",
        r"exhausted your (?:(?:session|weekly|daily|usage|5[- ]?hour|five[- ]hour)\s+)?(?:limit|quota|usage)",
        r"(?:usage|session|weekly|opus|sonnet|5[- ]?hour|five[- ]hour)\s+limit\s+(?:has been\s+|was\s+)?reached",
        r"your limit will reset",
        "you(?:'ve|’ve| have) used all (?:of )?your "
        r"(?:(?:session|weekly|daily|opus|sonnet|5[- ]?hour)\s+)?(?:usage|limit|quota|messages)",
    ])

_AUTH_FAIL_PATTERN = re.compile("|".join(f"(?:{s})" for s in _SIGNALS), re.IGNORECASE)
_SUBSCRIPTION_LIMIT_PATTERN = re.compile(
    "|".join(f"(?:{s})" for s in _SUBSCRIPTION_LIMIT_SIGNALS), re.IGNORECASE)


def strip_lane_env(env: dict) -> dict:
    """Remove every LANE_ENV_VARS name from `env`, in place, and return it.

    Case-insensitive because Windows env names are: `Anthropic_Base_Url` in a
    copied env dict still reaches the child claude.exe as ANTHROPIC_BASE_URL."""
    lane = {name.upper() for name in LANE_ENV_VARS}
    for key in [k for k in env if k.upper() in lane]:
        del env[key]
    return env


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

    The spillover lane vars come off the INHERITED base before extras apply,
    so nothing leaks in from the parent while a caller can still set one on
    purpose.

    Returns:
        A dict suitable for subprocess.Popen's env= argument.
    """
    env = strip_lane_env(dict(base if base is not None else os.environ))
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


def is_subscription_limit(text: Optional[str]) -> bool:
    """True when `text` says the SUBSCRIPTION usage limit is spent — the narrow,
    verb-anchored predicate (see lib.claude_auth.is_subscription_limit)."""
    if not text:
        return False
    return bool(_SUBSCRIPTION_LIMIT_PATTERN.search(text))


def check_claude_auth_paths(home: Optional[str] = None, env: Optional[dict] = None) -> dict:
    """Inspect the local machine for OAuth credentials + API key fallback.

    Used by startup health checks. Storage varies by OS:
      - Linux/Windows: ~/.claude/.credentials.json
      - macOS 2.x: macOS Keychain (service="Claude Code-credentials"),
        with ~/.claude/.credentials.json absent. We check both so the
        dashboard's "is the CLI signed in?" indicator works regardless
        of where Claude actually stored the token.

    Returns:
        {
            "has_oauth": bool,
            "oauth_path": str | None,  # file path OR "keychain:..." marker
            "has_api_key": bool,
            "claude_dir": str,
        }
    """
    import subprocess  # local import — only needed in this function

    home_dir = home or os.environ.get("HOME") or os.environ.get("USERPROFILE") or ""
    claude_dir = Path(home_dir) / ".claude"
    # File-based path (Linux + Windows + legacy Mac installs).
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

    # macOS Keychain probe. Claude Code 2.x stores the OAuth token in
    # the user's login keychain under service="Claude Code-credentials".
    # `security find-generic-password -s "Claude Code-credentials" -w`
    # returns the secret on stdout if present; we don't WANT the secret,
    # just exit code 0 vs non-zero. `-g` mode would log to syslog so we
    # use `-w` with stdout redirected to /dev/null. 1s timeout because
    # Keychain probes occasionally prompt if ACLs aren't set right.
    if not oauth_path and os.uname().sysname == "Darwin":
        try:
            proc = subprocess.run(
                ["security", "find-generic-password", "-s", "Claude Code-credentials"],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
            if proc.returncode == 0:
                oauth_path = "keychain:Claude Code-credentials"
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    api_key = (env or os.environ).get("ANTHROPIC_API_KEY", "")
    return {
        "has_oauth": bool(oauth_path),
        "oauth_path": oauth_path,
        "has_api_key": bool(api_key),
        "claude_dir": str(claude_dir),
    }
