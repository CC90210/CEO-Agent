#!/usr/bin/env python3
"""
Voice Note Transcriber — converts audio to text using OpenAI Whisper (local).
Used by the Telegram bridge to process voice messages.

Usage:
  python scripts/transcribe.py --file /path/to/audio.ogg
  python scripts/transcribe.py --file /path/to/audio.ogg --model tiny  (faster, less accurate)

Output: JSON with transcription text.
"""

import argparse
import json
import os
import subprocess
import sys
import time

FFMPEG = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Microsoft", "WinGet", "Packages",
    "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe",
    "ffmpeg-8.0.1-full_build", "bin", "ffmpeg.exe"
)
if not os.path.exists(FFMPEG):
    FFMPEG = "ffmpeg"

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def main():
    parser = argparse.ArgumentParser(description="Transcribe audio to text")
    parser.add_argument("--file", required=True, help="Path to audio file (OGG, MP3, WAV, etc.)")
    parser.add_argument("--model", default="base", help="Whisper model: tiny, base, small, medium (default: base)")
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(json.dumps({"ok": False, "error": f"File not found: {args.file}"}))
        sys.exit(1)

    # Step 1: Convert to WAV using FFmpeg (Whisper works best with WAV)
    wav_path = args.file.rsplit(".", 1)[0] + ".wav"
    try:
        subprocess.run(
            [FFMPEG, "-i", args.file, "-ar", "16000", "-ac", "1", "-y", wav_path],
            capture_output=True, timeout=30,
            creationflags=CREATE_NO_WINDOW
        )
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"FFmpeg conversion failed: {e}"}))
        sys.exit(1)

    if not os.path.isfile(wav_path):
        print(json.dumps({"ok": False, "error": "FFmpeg produced no output"}))
        sys.exit(1)

    # Step 2: Transcribe with Whisper
    try:
        import whisper
        start = time.time()
        model = whisper.load_model(args.model)
        result = model.transcribe(wav_path, language="en")
        elapsed = round(time.time() - start, 1)

        text = result.get("text", "").strip()
        print(json.dumps({
            "ok": True,
            "text": text,
            "model": args.model,
            "duration_s": elapsed,
        }))
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Whisper failed: {e}"}))
        sys.exit(1)
    finally:
        # Clean up WAV
        try:
            os.remove(wav_path)
        except Exception:
            pass


if __name__ == "__main__":
    main()
