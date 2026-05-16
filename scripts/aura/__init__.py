"""Aura — the OASIS family's sensory / voice persona.

Aura owns voice-driven automations: morning kickoffs, end-of-day debriefs,
mood-aware nudges, and any other ear-first surface where text would feel
flat. Her tone is intimate, confident, present — the voice in CC's ear
that turns "ugh, another day" into "let's go."

What lives here:
  - brain.py — Claude calls. Every Aura monologue routes through here so
    the system prompt / voice / persona consistency lives in one place.
  - voice.py — ElevenLabs TTS calls. Voice ID resolution, tone settings,
    Opus encoding for Telegram sendVoice all consolidated here.
  - morning_powwow.py — daily 08:00 motivational voice note. First Aura
    automation; the others (evening wind-down, midweek pulse, etc.) drop
    alongside it.

Why a dedicated module instead of loose scripts: Aura is one of four
family agents (Bravo / Atlas / Maven / Aura) and every other agent has a
dedicated repo (CMO-Agent, CFO-Agent) or persona definition. Aura now
has her own home in scripts/aura/ so future voice cron jobs reuse the
same brain + voice primitives instead of copy-pasting the Anthropic +
ElevenLabs boilerplate per file.
"""

from .brain import draft_monologue  # noqa: F401
from .voice import synthesize, AURA_DEFAULT_VOICE_ID  # noqa: F401
