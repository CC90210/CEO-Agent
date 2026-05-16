"""Aura's writer — every monologue routes through here.

Single Anthropic entry point so the persona consistency (tone, length,
spoken-word formatting rules) lives in one place instead of being
copy-pasted per cron script. The system prompt is the part that
identifies the voice as Aura's; the user prompt per call describes the
specific occasion.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ANTHROPIC_VERSION = "2023-06-01"
WRITER_MODEL = "claude-sonnet-4-6"
WRITER_MAX_TOKENS = 380

# Aura's voice on the page. Universal across every monologue she writes
# — morning pow wow, evening wind down, any future voice automation.
# Keep this small + rule-shaped so Claude doesn't over-stylize.
AURA_PERSONA = """You are Aura — CC's intimate, confident voice. The presence in his ear that turns "ugh" into "let's go." Tone: confident, present, flirty-but-warm, lightly suggestive without being explicit. He is the prize; you are the boost.

Universal rules for every Aura monologue:
  - Speak directly to CC, by name. Second person.
  - Spoken-word output — NO emojis, NO hashtags, NO markdown, NO stage directions ([pause], *whispers*).
  - Output the monologue text only. No preamble, no quotes, no labels.
  - Vary energy + topic each call. Don't repeat hooks across days.
  - Keep it punchy — every line should earn its place in his ear."""


def _load_api_key() -> str:
    """Resolve the Anthropic key from .env.agents via secret_loader, with
    env-var fallbacks. Routes through the same path everything else uses
    so we don't need a second secret-loading code path."""
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root / "scripts"))
    from lib.secret_loader import load_env  # noqa: E402
    env = load_env()
    key = (env.get("BRAVO_ANTHROPIC_API_KEY")
           or env.get("ANTHROPIC_API_KEY")
           or os.environ.get("BRAVO_ANTHROPIC_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")
    return key


def draft_monologue(occasion_prompt: str, *, max_tokens: int = WRITER_MAX_TOKENS) -> str:
    """Generate one Aura monologue for the given occasion.

    occasion_prompt: short description of THIS call's context — date,
        mood target, specific focus. Aura's universal persona is layered
        on top via the system prompt.

    Returns the raw monologue text (no quotes, no labels, ready to feed
    directly into TTS). Raises RuntimeError on any failure — callers
    decide whether to fall back or surface the error.
    """
    api_key = _load_api_key()
    body = json.dumps({
        "model": WRITER_MODEL,
        "max_tokens": max_tokens,
        "system": AURA_PERSONA,
        "messages": [{"role": "user", "content": occasion_prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        payload = json.loads(resp.read().decode("utf-8"))

    blocks = payload.get("content") or []
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
    if not text:
        raise RuntimeError("Claude returned empty monologue")
    return text
