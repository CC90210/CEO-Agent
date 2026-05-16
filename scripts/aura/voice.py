"""Aura's voice — ElevenLabs TTS with the tone settings tuned for her.

Single TTS entry point so the voice ID resolution + Opus encoding + tone
settings live in one place. Future Aura cron scripts (evening wind-down,
midweek pulse, etc.) call synthesize() — they don't re-implement the
ElevenLabs request shape.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# ElevenLabs' "Rachel" — the safe-bet female voice that ships with every
# account. Used until CC sets ELEVENLABS_AURA_VOICE_ID to his custom
# Aura voice from his ElevenLabs library.
AURA_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

ELEVENLABS_MODEL = "eleven_turbo_v2_5"

# Opus-in-OGG is what Telegram sendVoice expects. 48kHz / 64kbps fits
# well under Telegram's 1MB voice note ceiling for ~30-60s clips.
ELEVENLABS_OUTPUT_FORMAT = "opus_48000_64"

# Tone settings tuned for Aura — confident + intimate. Low stability so
# the voice has personality variation across days; high similarity so it
# stays recognizably her.
AURA_VOICE_SETTINGS = {
    "stability": 0.40,
    "similarity_boost": 0.85,
    "style": 0.55,
    "use_speaker_boost": True,
}


def _resolve_voice_id() -> str:
    """ELEVENLABS_AURA_VOICE_ID env var if set, otherwise the default."""
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root / "scripts"))
    from lib.secret_loader import load_env  # noqa: E402
    env = load_env()
    return (env.get("ELEVENLABS_AURA_VOICE_ID")
            or os.environ.get("ELEVENLABS_AURA_VOICE_ID", "")
            or AURA_DEFAULT_VOICE_ID).strip()


def _load_api_key() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root / "scripts"))
    from lib.secret_loader import load_env  # noqa: E402
    env = load_env()
    key = (env.get("ELEVENLABS_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY missing")
    return key


def synthesize(text: str) -> bytes:
    """Convert text to Aura-voice Opus audio. Returns raw bytes suitable
    for Telegram sendVoice."""
    api_key = _load_api_key()
    voice_id = _resolve_voice_id()
    url = (
        f"https://api.elevenlabs.io/v1/text-to-speech/{urllib.parse.quote(voice_id)}"
        f"?output_format={ELEVENLABS_OUTPUT_FORMAT}"
    )
    body = json.dumps({
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": AURA_VOICE_SETTINGS,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "xi-api-key": api_key,
            "content-type": "application/json",
            "accept": "audio/ogg",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return resp.read()
