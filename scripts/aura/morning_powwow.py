"""Morning Pow Wow Call — Aura's daily 08:00 voice note.

First of Aura's voice automations. Drafts a ~120-word motivational/flirty
monologue, renders it in her voice, ships it as a Telegram voice note.

CLI:
  python scripts/aura/morning_powwow.py             # generate + send
  python scripts/aura/morning_powwow.py --dry-run   # generate, save locally, no send
  python scripts/aura/morning_powwow.py --text-only # print text, skip TTS + send

Cron: SEED_JOBS entry at 0 8 * * * with action_type=morning_powwow.
Cost: ~$0.02/day.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from aura.brain import draft_monologue  # noqa: E402
from aura.voice import synthesize  # noqa: E402
from notify import notify_voice  # noqa: E402


def _occasion_prompt() -> str:
    """Today's user-message for Aura's brain. The persona + universal
    rules live in aura/brain.py; this is the per-call context."""
    today = datetime.now().strftime("%A, %B %#d" if sys.platform == "win32" else "%A, %B %-d")
    return (
        f"Today is {today}. Write today's morning pow wow for CC — ~120 words.\n\n"
        f"Beats to hit, in order:\n"
        f"  1. High-energy hook in one short sentence. NOT 'Good morning.'\n"
        f"  2. One concrete focus for the day — pick from his operator life: closing leads, "
        f"shipping the next agent build, hitting the gym, content drop, getting paid. "
        f"Specific, not vague self-help.\n"
        f"  3. One flirty / playful line — confident, not desperate. He's the prize.\n"
        f"  4. Closing rallying line. Punchy. End with 'Let's go, baby.' or a sharper kicker."
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true",
                   help="Generate text + audio, save locally, skip Telegram send")
    p.add_argument("--text-only", action="store_true",
                   help="Print the monologue, skip TTS + send")
    args = p.parse_args(argv)

    # 1. Draft.
    try:
        text = draft_monologue(_occasion_prompt())
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[powwow] draft failed: {e}\n")
        return 2

    print("--- pow wow text ---")
    print(text)
    print("--- /text ---")
    if args.text_only:
        return 0

    # 2. Voice.
    try:
        audio_bytes = synthesize(text)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[powwow] tts failed: {e}\n")
        return 3

    # 3. Ship (or save for dry-run inspection).
    tmp_dir = PROJECT_ROOT / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="powwow_", suffix=".ogg", dir=str(tmp_dir))
    os.close(fd)
    out_path = Path(tmp_path)
    out_path.write_bytes(audio_bytes)

    if args.dry_run:
        print(f"DRY: saved {len(audio_bytes)} bytes to {out_path}")
        return 0

    ok = notify_voice(audio_bytes, filename="powwow.ogg", mime="audio/ogg")
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
