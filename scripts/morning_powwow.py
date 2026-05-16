"""Morning Pow Wow Call — daily 08:00 voice message to CC's Telegram.

Phase 10.2 of the OASIS HQ redesign. CC's first voice-driven automation.

What it does:
  1. Asks Claude Sonnet to draft a ~120-word morning pow wow — motivational,
     invigorating, inspiring with a flirty / "sexy-confident" tone. Personal,
     uses CC's name, leads with a single high-energy hook then lands a
     concrete focus for the day.
  2. Sends the text to ElevenLabs TTS as Aura's voice (configurable via
     ELEVENLABS_AURA_VOICE_ID env var; falls back to ElevenLabs' default
     "Rachel" voice 21m00Tcm4TlvDq8ikWAM until CC picks his own).
  3. Ships the resulting Opus-encoded audio as a Telegram voice note via
     sendVoice — plays inline in the chat like a real voicemail.

CLI:
  python scripts/morning_powwow.py             # generate + send
  python scripts/morning_powwow.py --dry-run   # generate text + audio, no Telegram send
  python scripts/morning_powwow.py --text-only # print the draft script, no TTS

Cron: registered in scripts/cron_engine.py SEED_JOBS at 0 8 * * * with
action_type=morning_powwow.

Cost: ~$0.02/day (Claude ~150 tokens + ElevenLabs ~150 chars of TTS).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ANTHROPIC_VERSION = "2023-06-01"
WRITER_MODEL = "claude-sonnet-4-6"
WRITER_MAX_TOKENS = 380

# Default ElevenLabs voice. "Rachel" is the safe-bet female voice that
# ships with every ElevenLabs account. Override via ELEVENLABS_AURA_VOICE_ID
# once CC picks a custom Aura voice from his library.
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
ELEVENLABS_MODEL = "eleven_turbo_v2_5"

# Opus-in-OGG is what Telegram sendVoice expects. 48kHz / 64kbps fits well
# under Telegram's 1MB voice note ceiling for ~30-60s clips.
ELEVENLABS_OUTPUT_FORMAT = "opus_48000_64"

SYSTEM_PROMPT = """You are Aura — CC's morning hype woman. Voice: confident, intimate, flirty-but-warm, lightly suggestive without being explicit. You're the voice in his ear at 8 a.m. that turns "ugh, another day" into "let's go."

Write a single ~120-word spoken-word monologue for one morning. Rules:
  - Speak directly to CC, by name. Second person.
  - Open with a high-energy hook in 1 short sentence. No "Good morning."
  - One concrete piece of focus / direction for the day — pick from the operator-life pool: closing leads, shipping the next agent build, hitting the gym, content drop, getting paid. Keep it specific, not vague self-help.
  - One flirty / playful line — confident, not desperate. He's the prize, you're the boost.
  - One closing rallying line that leaves him wanting to move.
  - NO emojis, NO hashtags, NO markdown. This will be read aloud by a voice model.
  - NO stage directions like *whispers* or [pause]. Just the words she'd say.
  - End with "Let's go, baby." or a similar variant — keep the kicker punchy.

Vary the energy + topic each day. Don't repeat hooks. Output the monologue text only — no preamble, no quotes, no labels."""


def _load_env() -> dict:
    from lib.secret_loader import load_env  # noqa: E402
    return load_env()


def _draft_powwow_text(env: dict) -> str:
    """Ask Claude for today's monologue. Returns the raw text."""
    api_key = (env.get("BRAVO_ANTHROPIC_API_KEY")
               or env.get("ANTHROPIC_API_KEY")
               or os.environ.get("BRAVO_ANTHROPIC_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    today = datetime.now().strftime("%A, %B %-d" if sys.platform != "win32" else "%A, %B %#d")
    user_prompt = (
        f"Today is {today}. Write today's morning pow wow for CC. "
        f"120 words. Confident, intimate, motivating. One concrete focus, one flirty line, "
        f"close with 'Let's go, baby.' (or a punchier variant if it lands better)."
    )

    body = json.dumps({
        "model": WRITER_MODEL,
        "max_tokens": WRITER_MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_prompt}],
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
        raise RuntimeError("Claude returned no text for the pow wow")
    return text


def _synthesize_voice(env: dict, text: str) -> bytes:
    """Convert text → Opus/OGG audio via ElevenLabs. Returns raw bytes."""
    api_key = (env.get("ELEVENLABS_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY missing")

    voice_id = (env.get("ELEVENLABS_AURA_VOICE_ID")
                or os.environ.get("ELEVENLABS_AURA_VOICE_ID", "")
                or DEFAULT_VOICE_ID).strip()

    url = (
        f"https://api.elevenlabs.io/v1/text-to-speech/{urllib.parse.quote(voice_id)}"
        f"?output_format={ELEVENLABS_OUTPUT_FORMAT}"
    )
    body = json.dumps({
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {
            # Settings tuned for the "intimate / flirty / confident" tone.
            # Stability slightly low so the voice has personality variation;
            # similarity high so it stays recognizably the chosen voice.
            "stability": 0.40,
            "similarity_boost": 0.85,
            "style": 0.55,
            "use_speaker_boost": True,
        },
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


def _send_voice_note(audio_path: Path) -> bool:
    """Ship the OGG/Opus voice note to Telegram. Delegates to the canonical
    notify_voice helper so the multipart + chat-id resolution lives in
    one place (scripts/notify.py)."""
    try:
        from notify import notify_voice  # type: ignore
    except ImportError:
        sys.stderr.write("[powwow] scripts/notify.py not on sys.path\n")
        return False
    audio_bytes = audio_path.read_bytes()
    return notify_voice(audio_bytes, filename="powwow.ogg", mime="audio/ogg")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true",
                   help="Generate text + audio, save locally, no Telegram send")
    p.add_argument("--text-only", action="store_true",
                   help="Print the generated monologue, skip TTS + send")
    p.add_argument("--save-to", type=str, default=None,
                   help="Write the OGG audio to this path (default: auto temp file)")
    args = p.parse_args(argv)

    env = _load_env()

    try:
        text = _draft_powwow_text(env)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[powwow] draft failed: {e}\n")
        return 2

    print("--- pow wow text ---")
    print(text)
    print("--- /text ---")

    if args.text_only:
        return 0

    try:
        audio_bytes = _synthesize_voice(env, text)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[powwow] tts failed: {e}\n")
        return 3

    if args.save_to:
        out_path = Path(args.save_to)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(audio_bytes)
        print(f"wrote: {out_path}")
    else:
        # Write to a temp file so Telegram upload has a real file handle.
        # Keep it under tmp/ so it doesn't clutter the root.
        tmp_dir = PROJECT_ROOT / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix="powwow_", suffix=".ogg", dir=str(tmp_dir))
        os.close(fd)
        out_path = Path(tmp_name)
        out_path.write_bytes(audio_bytes)

    if args.dry_run:
        print(f"DRY: saved {len(audio_bytes)} bytes to {out_path}, skipping Telegram send")
        return 0

    ok = _send_voice_note(out_path)
    if not args.save_to:
        # Auto-delete temp file after send.
        try:
            out_path.unlink()
        except OSError:
            pass

    if ok:
        print("sent: morning pow wow shipped to Telegram")
        return 0
    sys.stderr.write("[powwow] Telegram send failed\n")
    return 4


if __name__ == "__main__":
    sys.exit(main())
