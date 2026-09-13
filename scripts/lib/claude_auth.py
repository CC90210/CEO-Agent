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

CLAUDE SPILLOVER (fixture v3, 2026-09-12 — scripts/spillover/CONTRACT.md §13):
build_claude_spawn_env also strips the `lane_env_strip` vars (ANTHROPIC_BASE_URL,
CLAUDE_CODE_ENTRYPOINT, the model overrides, …) from the INHERITED env before the
caller's extras, so no child automation inherits a route into the local
spillover proxy or a model lane. is_subscription_limit() is the narrow,
verb-anchored "the subscription usage limit is spent" predicate behind
claude_cli's quota breaker. Both lists live in the same fixture.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional

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

# Last-resort inline copy of `lane_env_strip`. Unlike _FALLBACK_SIGNALS this is
# the FULL list, never a subset: a name missing here is a route into the
# spillover proxy on a partial deploy. test_claude_auth_parity.py runs every
# port with the fixture unreadable and fails if any lane var survives.
_FALLBACK_LANE_ENV_STRIP = [
    "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_FABLE_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL",
    "ANTHROPIC_CUSTOM_HEADERS", "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW", "CLAUDE_CODE_MAX_CONTEXT_TOKENS",
    "BRAVO_CLAUDE_LANE",
]

# Last-resort inline copy of `subscription_limit_signals`. A miss only costs
# latency (the breaker stays shut and the caller falls back anyway), but the
# parity test still holds this copy to the fixture's must_match/must_not_match.
_FALLBACK_SUBSCRIPTION_LIMIT_SIGNALS = [
    r"hit your (?:(?:session|weekly|daily|opus|sonnet|usage|5[- ]?hour|five[- ]hour)\s+)?limit",
    r"reached your (?:(?:session|weekly|daily|opus|sonnet|usage|5[- ]?hour|five[- ]hour)\s+)?limit",
    r"exhausted your (?:(?:session|weekly|daily|usage|5[- ]?hour|five[- ]hour)\s+)?(?:limit|quota|usage)",
    r"(?:usage|session|weekly|opus|sonnet|5[- ]?hour|five[- ]hour)\s+limit\s+(?:has been\s+|was\s+)?reached",
    r"your limit will reset",
    "you(?:'ve|’ve| have) used all (?:of )?your "
    r"(?:(?:session|weekly|daily|opus|sonnet|5[- ]?hour)\s+)?(?:usage|limit|quota|messages)",
]


def _load_fixture_list(key: str, fallback: list[str]) -> list[str]:
    """One list from the shared fixture, or `fallback` when it cannot be read.

    Never raises — daemons import this at startup — but never silent either: a
    degraded read goes to stderr, so the daemon's own log names it."""
    try:
        values = json.loads(SIGNALS_PATH.read_text(encoding="utf-8")).get(key)
        if isinstance(values, list) and values:
            return [str(v) for v in values]
        problem = f"has no non-empty {key!r} list"
    except Exception as e:  # noqa: BLE001 — see _FALLBACK_SIGNALS rationale above
        problem = f"is unreadable ({type(e).__name__})"
    sys.stderr.write(f"[claude_auth] {SIGNALS_PATH} {problem}; using the inline fallback\n")
    return list(fallback)


def _load_signals() -> list[str]:
    return _load_fixture_list("signals", _FALLBACK_SIGNALS)


AUTH_FAIL_SIGNALS: list[str] = _load_signals()
_AUTH_FAIL_PATTERN = re.compile("|".join(f"(?:{s})" for s in AUTH_FAIL_SIGNALS), re.IGNORECASE)

LANE_ENV_VARS: tuple[str, ...] = tuple(_load_fixture_list("lane_env_strip", _FALLBACK_LANE_ENV_STRIP))
SUBSCRIPTION_LIMIT_SIGNALS: list[str] = _load_fixture_list(
    "subscription_limit_signals", _FALLBACK_SUBSCRIPTION_LIMIT_SIGNALS)
_SUBSCRIPTION_LIMIT_PATTERN = re.compile(
    "|".join(f"(?:{s})" for s in SUBSCRIPTION_LIMIT_SIGNALS), re.IGNORECASE)


def strip_lane_env(env: MutableMapping[str, str]) -> MutableMapping[str, str]:
    """Remove every LANE_ENV_VARS name from `env`, in place, and return it.

    Case-insensitive on purpose: Windows env names are, so a copied env dict
    carrying `Anthropic_Base_Url` still reaches a child claude.exe as
    ANTHROPIC_BASE_URL."""
    lane = {name.upper() for name in LANE_ENV_VARS}
    for key in [k for k in env if k.upper() in lane]:
        del env[key]
    return env


def build_claude_spawn_env(
    force_api_key: bool = False,
    base: Optional[Mapping[str, str]] = None,
    extras: Optional[Mapping[str, str]] = None,
) -> dict[str, str]:
    """Child-process env that respects subscription-first auth.

    Default (force_api_key=False): strips ANTHROPIC_API_KEY so the claude CLI
    falls through to the OAuth subscription token. Pass force_api_key=True on the
    retry path to enable the paid API-key fallback.

    Order matters: the lane vars come off the INHERITED env first, then extras
    apply. A parent Claude Code session exports CLAUDE_CODE_ENTRYPOINT=cli and a
    shell can carry ANTHROPIC_BASE_URL — neither may leak into a child — while a
    caller can still set one deliberately (claude_cli sets
    ANTHROPIC_CUSTOM_HEADERS=X-Bravo-Lane: automation).
    """
    if base is None:
        base = os.environ
    env: dict[str, str] = dict(base)
    strip_lane_env(env)
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


def is_subscription_limit(text: Optional[str]) -> bool:
    """True when `text` is Claude saying the SUBSCRIPTION usage limit is spent
    (session / weekly / 5-hour), so every call fails until the reset.

    Deliberately narrower than is_claude_auth_or_quota_failure: it opens
    claude_cli's quota breaker, and a false positive parks the whole fleet on
    fallback models for the cooldown. Every signal is verb-anchored ("hit your …
    limit", "… limit reached"): "Approaching Opus usage limit" is only a warning
    and a per-minute rate limit clears in seconds. The fixture's
    subscription_limit_must_match / _must_not_match pin both sides."""
    if not text:
        return False
    return bool(_SUBSCRIPTION_LIMIT_PATTERN.search(text))


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
