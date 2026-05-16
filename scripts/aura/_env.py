"""Aura's env loader — single source of truth for sys.path + secret loading.

Both brain.py (Anthropic) and voice.py (ElevenLabs) need to resolve API
keys from .env.agents via scripts/lib/secret_loader.py. Without this
helper each module did its own sys.path.insert + load_env() — three
identical blocks across two files. Consolidated here so module init in
either file is a single import.

Cached: secret_loader caches in-process already, but we also short-circuit
the sys.path.insert so re-imports are free.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"

# Ensure scripts/ is importable so `from lib.secret_loader import load_env`
# works regardless of which directory the caller is in. Idempotent.
_scripts_str = str(_SCRIPTS_DIR)
if _scripts_str not in sys.path:
    sys.path.insert(0, _scripts_str)


@lru_cache(maxsize=1)
def env() -> dict:
    """Return the .env.agents dict. Cached after first load."""
    from lib.secret_loader import load_env  # noqa: E402
    return load_env()


def anthropic_key() -> str:
    """ANTHROPIC_API_KEY resolved from env (or process env as fallback)."""
    e = env()
    key = (e.get("BRAVO_ANTHROPIC_API_KEY")
           or e.get("ANTHROPIC_API_KEY")
           or os.environ.get("BRAVO_ANTHROPIC_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")
    return key


def elevenlabs_key() -> str:
    """ELEVENLABS_API_KEY resolved from env."""
    e = env()
    key = (e.get("ELEVENLABS_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY missing")
    return key


def aura_voice_id(default: str) -> str:
    """ELEVENLABS_AURA_VOICE_ID env var, or the supplied default."""
    e = env()
    return (e.get("ELEVENLABS_AURA_VOICE_ID")
            or os.environ.get("ELEVENLABS_AURA_VOICE_ID", "")
            or default).strip()
