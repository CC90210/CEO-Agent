import argparse
import os
import subprocess
import json
import re
import sys

# FFmpeg path (winget install location)
FFMPEG_DIR = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin")
FFMPEG = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
FFPROBE = os.path.join(FFMPEG_DIR, "ffprobe.exe")

# Fallback: try system PATH
if not os.path.exists(FFMPEG):
    FFMPEG = "ffmpeg"
    FFPROBE = "ffprobe"

# Brand colors
PRIMARY_COLOR = "&H00F5F9FA&"   # #faf9f5 in BGR
OUTLINE_COLOR = "&H00131414&"   # #141413 in BGR


def probe_video(input_path):
    """Get video metadata via ffprobe."""
    cmd = [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", input_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout) if result.returncode == 0 else None


def transcribe_audio(input_path, output_srt=None):
    """Auto-transcribe video audio to SRT using Whisper."""
    try:
        import whisper
    except ImportError:
        print("Whisper not installed. Run: pip install openai-whisper")
        return None

    if output_srt is None:
        base = os.path.splitext(input_path)[0]
        output_srt = base + ".srt"

    print(f"Transcribing {input_path}...")
    model = whisper.load_model("base")
    result = model.transcribe(input_path)

    # Write SRT
    with open(output_srt, "w", encoding="utf-8") as f:
        for i, seg in enumerate(result["segments"], 1):
            start = _format_timestamp(seg["start"])
            end = _format_timestamp(seg["end"])
            text = seg["text"].strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")

    print(f"Transcription saved to {output_srt}")
    return output_srt


def _format_timestamp(seconds):
    """Convert seconds to SRT timestamp format."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_voiceover(text, output_path, voice="Adam"):
    """Generate voiceover using ElevenLabs API."""
    try:
        from elevenlabs import ElevenLabs
    except ImportError:
        print("ElevenLabs not installed. Run: pip install elevenlabs")
        return None

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        # Fall back to .env.agents
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env.agents")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("ELEVENLABS_API_KEY="):
                        api_key = line.split("=", 1)[1].strip()
                        break
    if not api_key:
        print("ELEVENLABS_API_KEY not found in environment or .env.agents", file=sys.stderr)
        return None

    client = ElevenLabs(api_key=api_key)
    audio = client.text_to_speech.convert(
        text=text,
        voice_id=voice,
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
    )

    with open(output_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)

    print(f"Voiceover saved to {output_path}")
    return output_path


def edit_video(input_path, output_path, overlays=None, captions_path=None,
               orientation="portrait", auto_caption=False, voiceover_path=None):
    """
    Elite Bravo Video Edit:
    - Portrait (1080x1920) or Landscape (1920x1080)
    - Branded captions (#faf9f5 primary, #141413 outline)
    - Image overlays with timing
    - Audio normalization
    - Auto-transcription via Whisper
    - Voiceover mixing via ElevenLabs
    """
    print(f"Starting ELITE EDIT on {input_path}...")

    # Auto-transcribe if requested
    if auto_caption and not captions_path:
        captions_path = transcribe_audio(input_path)

    # Resolution based on orientation
    if orientation == "portrait":
        w, h = 1080, 1920
    else:
        w, h = 1920, 1080

    video_filter = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"

    inputs = ["-i", input_path]
    filter_complex = f"[0:v]{video_filter}[vbase]"
    last_v = "vbase"
    # Add voiceover as additional input
    if voiceover_path and os.path.exists(voiceover_path):
        inputs.extend(["-i", voiceover_path])
        audio_input_idx = len(inputs) // 2  # track which input is the voiceover

    # Add overlays
    if overlays:
        overlay_start_idx = len(inputs) // 2
        for i, overlay in enumerate(overlays):
            inputs.extend(["-i", overlay["path"]])
            idx = overlay_start_idx + i
            ov_name = f"ov{i}"
            ov_width = overlay.get("width", 400)
            filter_complex += f";[{idx}:v]scale={ov_width}:-1[ovscaled{i}]"
            filter_complex += f";[{last_v}][ovscaled{i}]overlay={overlay['x']}:{overlay['y']}:enable='between(t,{overlay['start']},{overlay['end']})'[{ov_name}]"
            last_v = ov_name

    # Add subtitles
    if captions_path and os.path.exists(captions_path):
        safe_subs = captions_path.replace("\\", "/").replace(":", "\\:")
        font_size = 64 if orientation == "portrait" else 48
        margin_v = 450 if orientation == "portrait" else 100
        # Color: &H<Alpha><Blue><Green><Red>&
        YELLOW = "0000FFFF" # BGR
        WHITE = "00FFFFFF"
        filter_complex += (
            f";[{last_v}]subtitles='{safe_subs}':"
            f"force_style='Alignment=2,FontSize={font_size},MarginV={margin_v},"
            f"PlayResX={w},PlayResY={h},"
            f"PrimaryColour=&H{YELLOW}&,OutlineColour=&H00000000&,"
            f"BorderStyle=1,Outline=4,Shadow=0,Bold=1'[vcap]"
        )
        last_v = "vcap"

    # Creative "Contextual Stickers" Pass (FFmpeg Emojis)
    stickers = [
        {"word": "CLOG", "emoji": "🤖", "start_offset": 0, "duration": 2},
        {"word": "GEMINI", "emoji": "✨", "start_offset": 0, "duration": 2},
        {"word": "STRIPE", "emoji": "💰", "start_offset": 0, "duration": 2},
        {"word": "INVOICES", "emoji": "🧾", "start_offset": 0, "duration": 2},
        {"word": "CLI", "emoji": "💻", "start_offset": 0, "duration": 2},
        {"word": "HAIRLINE", "emoji": "👨‍🦲", "start_offset": 0, "duration": 3},
    ]

    if captions_path and os.path.exists(captions_path):
        with open(captions_path, "r", encoding="utf-8") as f:
            srt_content = f.read()
        
        for s in stickers:
            # Find timestamp for the word in SRT
            match = re.search(rf"(\d{{2}}:\d{{2}}:\d{{2}},\d{{3}}) --> (\d{{2}}:\d{{2}}:\d{{2}},\d{{3}})\n.*{s['word']}", srt_content, re.IGNORECASE)
            if match:
                start_str = match.group(1).replace(",", ".")
                # Convert SRT time to seconds for FFmpeg 'between'
                h, m, s_val = start_str.split(':')
                start_sec = int(h)*3600 + int(m)*60 + float(s_val)
                end_sec = start_sec + s.get("duration", 2)
                
                # Overlay large emoji in top-right or center-left
                x = 800 if orientation == "portrait" else 1500
                y = 400
                filter_complex += f";[{last_v}]drawtext=text='{s['emoji']}':fontcolor=white:fontsize=120:x={x}:y={y}:enable='between(t,{start_sec},{end_sec})'[v{s['word']}]"
                last_v = f"v{s['word']}"

    filter_complex += f";[{last_v}]null[vfinal]"
    last_v = "vfinal"

    # Build command
    command = [
        FFMPEG, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{last_v}]",
    ]

    # Audio mapping — mix voiceover with original if present
    if voiceover_path and os.path.exists(voiceover_path):
        command.extend(["-map", "1:a"])  # use voiceover audio
    else:
        command.extend(["-map", "0:a?"])  # original audio (optional)

    command.extend([
        "-c:v", "libx264",
        "-preset", "superfast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        output_path,
    ])

    try:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"ERROR: FFmpeg failed (exit {result.returncode}):", file=sys.stderr)
            print(result.stderr[-500:] if result.stderr else "No error output", file=sys.stderr)
            return
        print(f"SUCCESS: Elite export -> {output_path}")

        # Report specs
        info = probe_video(output_path)
        if info:
            for s in info.get("streams", []):
                if s.get("codec_type") == "video":
                    print(f"  Resolution: {s['width']}x{s['height']}")
                    print(f"  Duration: {info['format'].get('duration', 'unknown')}s")
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  File size: {size_mb:.1f} MB")
    except Exception as e:
        print(f"ERROR: FFmpeg failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Video pipeline — probe, transcribe, voiceover, edit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s probe media/raw/clip.mp4
  %(prog)s transcribe media/raw/clip.mp4
  %(prog)s voiceover "Your script text" media/raw/voiceover.mp3
  %(prog)s edit media/raw/clip.mp4 media/exports/out.mp4
  %(prog)s edit media/raw/clip.mp4 media/exports/out.mp4 --auto-caption --landscape
        """
    )
    sub = parser.add_subparsers(dest="command")

    # probe
    p_probe = sub.add_parser("probe", help="Get video metadata via ffprobe")
    p_probe.add_argument("input", help="Input video file")

    # transcribe
    p_trans = sub.add_parser("transcribe", help="Auto-transcribe audio to SRT via Whisper")
    p_trans.add_argument("input", help="Input video file")
    p_trans.add_argument("--output", help="Output SRT path (default: same name as input)")

    # voiceover
    p_voice = sub.add_parser("voiceover", help="Generate voiceover via ElevenLabs")
    p_voice.add_argument("text", help="Text to convert to speech")
    p_voice.add_argument("output", help="Output audio file path")
    p_voice.add_argument("--voice", default="Adam", help="ElevenLabs voice name")

    # edit
    p_edit = sub.add_parser("edit", help="Full video edit pipeline")
    p_edit.add_argument("input", help="Input video file")
    p_edit.add_argument("output", help="Output video file")
    p_edit.add_argument("--auto-caption", action="store_true", help="Auto-transcribe and add captions")
    p_edit.add_argument("--captions", help="Path to existing SRT file")
    p_edit.add_argument("--voiceover", help="Path to voiceover audio file")
    p_edit.add_argument("--landscape", action="store_true", help="Landscape (1920x1080) instead of portrait")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "probe":
        info = probe_video(args.input)
        if info:
            print(json.dumps(info, indent=2))
        else:
            print("ERROR: Could not probe video", file=sys.stderr)
            sys.exit(1)
    elif args.command == "transcribe":
        result = transcribe_audio(args.input, args.output)
        if not result:
            sys.exit(1)
    elif args.command == "voiceover":
        result = generate_voiceover(args.text, args.output, voice=args.voice)
        if not result:
            sys.exit(1)
    elif args.command == "edit":
        orientation = "landscape" if args.landscape else "portrait"
        edit_video(args.input, args.output,
                   captions_path=args.captions,
                   auto_caption=args.auto_caption,
                   voiceover_path=args.voiceover,
                   orientation=orientation)
