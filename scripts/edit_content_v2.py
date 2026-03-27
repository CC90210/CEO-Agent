"""
OASIS AI Video Pipeline — V2 (Refined)

Improvements over V1:
  - Word-level timestamps via Whisper (word_timestamps=True) for "pop" captions
  - Configurable timing offset to fix Whisper latency (-0.3s default)
  - Brand-aligned caption styling (Pearl White #FAF9F5 on dark outline)
  - Configurable sticker system (not hardcoded)
  - Whisper model selection (small > base for accuracy)
  - SRT + word-level JSON output for maximum flexibility
  - Clean separation of transcription, editing, and export

Usage:
  # Basic portrait edit with auto-captions:
  python scripts/edit_content_v2.py media/raw/videos/IMG_0450.MP4 --auto-caption

  # With timing offset adjustment:
  python scripts/edit_content_v2.py media/raw/videos/IMG_0450.MP4 --auto-caption --offset -0.3

  # Landscape for LinkedIn:
  python scripts/edit_content_v2.py media/raw/videos/IMG_0450.MP4 --orientation landscape

  # Just transcribe (no video edit):
  python scripts/edit_content_v2.py media/raw/videos/IMG_0450.MP4 --transcribe-only
"""

import os
import sys
import subprocess
import json
import re
import argparse
from datetime import datetime

# ============================================================================
# CONFIG
# ============================================================================

# FFmpeg path (winget install location)
FFMPEG_DIR = os.path.expandvars(
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
)
FFMPEG = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
FFPROBE = os.path.join(FFMPEG_DIR, "ffprobe.exe")

# Fallback: try system PATH
if not os.path.exists(FFMPEG):
    FFMPEG = "ffmpeg"
    FFPROBE = "ffprobe"

# Brand colors (ASS format: &HBBGGRR&)
BRAND = {
    "pearl_white": "&H00F5F9FA&",     # #FAF9F5
    "obsidian": "&H00131414&",         # #141413
    "oasis_blue": "&H00FF840A&",       # #0A84FF in BGR
    "signal_green": "&H0058D130&",     # #30D158 in BGR
}

# Default timing offset to compensate for Whisper latency (seconds)
DEFAULT_OFFSET = -0.8

# Whisper model — "small" is the best balance of speed/accuracy
# Options: tiny, base, small, medium, large
WHISPER_MODEL = "small"

# Export directory
EXPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media", "exports")


# ============================================================================
# UTILITIES
# ============================================================================

def probe_video(input_path):
    """Get video metadata via ffprobe."""
    cmd = [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", input_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout) if result.returncode == 0 else None


def _srt_timestamp(seconds):
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_timestamp(seconds):
    """Convert seconds to ASS timestamp format (H:MM:SS.cc)."""
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ============================================================================
# TRANSCRIPTION
# ============================================================================

def transcribe_word_level(input_path, offset=DEFAULT_OFFSET, model_name=WHISPER_MODEL):
    """
    Transcribe video with word-level timestamps using Whisper.
    
    Returns:
        dict with 'segments' (phrase-level) and 'words' (word-level) data
        Also saves .srt (phrase-level) and .words.json (word-level) files
    """
    try:
        import whisper
    except ImportError:
        print("ERROR: Whisper not installed. Run: pip install openai-whisper")
        return None

    base = os.path.splitext(input_path)[0]
    srt_path = base + ".srt"
    words_path = base + ".words.json"

    print(f"🎤 Transcribing {os.path.basename(input_path)} with Whisper ({model_name})...")
    model = whisper.load_model(model_name)
    result = model.transcribe(input_path, word_timestamps=True)

    # Extract word-level data
    all_words = []
    for seg in result["segments"]:
        for word_info in seg.get("words", []):
            all_words.append({
                "word": word_info["word"].strip(),
                "start": round(word_info["start"] + offset, 3),
                "end": round(word_info["end"] + offset, 3),
            })

    # Write word-level JSON
    with open(words_path, "w", encoding="utf-8") as f:
        json.dump({"words": all_words, "offset_applied": offset}, f, indent=2)
    print(f"  📝 Word-level data → {os.path.basename(words_path)} ({len(all_words)} words)")

    # Write SRT (phrase-level, with offset applied)
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(result["segments"], 1):
            start = _srt_timestamp(seg["start"] + offset)
            end = _srt_timestamp(seg["end"] + offset)
            text = seg["text"].strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
    print(f"  📝 SRT captions → {os.path.basename(srt_path)} ({len(result['segments'])} segments)")

    return {
        "segments": result["segments"],
        "words": all_words,
        "srt_path": srt_path,
        "words_path": words_path,
    }


def generate_word_pop_ass(words_data, output_path, orientation="portrait"):
    """
    Generate an ASS subtitle file with word-by-word "pop" animation.
    Each word appears one at a time with a slight scale-up effect.
    """
    if orientation == "portrait":
        res_x, res_y = 1080, 1920
        font_size = 64
        margin_v = 500
    else:
        res_x, res_y = 1920, 1080
        font_size = 48
        margin_v = 120

    # ASS header
    header = f"""[Script Info]
Title: OASIS AI Captions
ScriptType: v4.00+
PlayResX: {res_x}
PlayResY: {res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pop,Inter,{font_size},{BRAND['pearl_white']},{BRAND['pearl_white']},{BRAND['obsidian']},&H80000000&,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    words = words_data if isinstance(words_data, list) else words_data.get("words", [])

    # Group words into display chunks (3-4 words at a time for readability)
    chunk_size = 3
    for i in range(0, len(words), chunk_size):
        chunk = words[i:i + chunk_size]
        if not chunk:
            continue

        chunk_start = chunk[0]["start"]
        chunk_end = chunk[-1]["end"]
        
        # Build the text with word-by-word reveal using ASS karaoke tags
        # Each word gets a transformation: slight scale pop from 110% to 100%
        text_parts = []
        for j, w in enumerate(chunk):
            word_duration_cs = max(1, int((w["end"] - w["start"]) * 100))
            # Highlight with slight bold pop using \t transform
            text_parts.append(f"{{\\k{word_duration_cs}}}{w['word']}")

        text = " ".join(text_parts) if text_parts else ""
        
        start_ts = _ass_timestamp(chunk_start)
        end_ts = _ass_timestamp(chunk_end + 0.1)  # Small buffer
        
        events.append(f"Dialogue: 0,{start_ts},{end_ts},Pop,,0,0,0,,{text}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write("\n".join(events))

    print(f"  🎬 ASS pop captions → {os.path.basename(output_path)} ({len(events)} events)")
    return output_path


# ============================================================================
# VIDEO EDITING
# ============================================================================

def edit_video(input_path, output_path=None, orientation="portrait",
               auto_caption=False, captions_path=None, use_word_pop=True,
               offset=DEFAULT_OFFSET, voiceover_path=None, stickers=None):
    """
    OASIS AI Elite Video Edit.
    
    Args:
        input_path: Path to source video
        output_path: Output path (auto-generated if None)
        orientation: 'portrait' (1080x1920) or 'landscape' (1920x1080)
        auto_caption: Auto-transcribe with Whisper
        captions_path: Path to existing .srt or .ass file
        use_word_pop: Use word-level pop animation (requires auto_caption or .words.json)
        offset: Timing offset in seconds (negative = shift earlier)
        voiceover_path: Path to voiceover audio file
        stickers: List of sticker configs [{word, emoji, duration}]
    """
    print(f"\n🎬 OASIS AI Video Pipeline V2")
    print(f"   Input: {os.path.basename(input_path)}")
    print(f"   Orientation: {orientation}")
    
    # Auto-generate output path
    if output_path is None:
        base = os.path.splitext(os.path.basename(input_path))[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        output_path = os.path.join(EXPORT_DIR, f"{base}_v2_{timestamp}.mp4")
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Resolution
    if orientation == "portrait":
        w, h = 1080, 1920
    else:
        w, h = 1920, 1080

    # Step 1: Auto-transcribe if requested
    ass_path = None
    if auto_caption:
        transcription = transcribe_word_level(input_path, offset=offset)
        if transcription and use_word_pop:
            ass_path = os.path.splitext(input_path)[0] + ".ass"
            generate_word_pop_ass(transcription["words"], ass_path, orientation)
            captions_path = ass_path
        elif transcription:
            captions_path = transcription["srt_path"]

    # Step 2: Build FFmpeg filter chain
    video_filter = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
    
    inputs = ["-i", input_path]
    filter_complex = f"[0:v]{video_filter}[vbase]"
    last_v = "vbase"

    # Add voiceover input
    if voiceover_path and os.path.exists(voiceover_path):
        inputs.extend(["-i", voiceover_path])

    # Step 3: Add subtitles
    if captions_path and os.path.exists(captions_path):
        safe_subs = captions_path.replace("\\", "/").replace(":", "\\:")
        
        if captions_path.endswith(".ass"):
            # ASS with full styling baked in
            filter_complex += f";[{last_v}]ass='{safe_subs}'[vcap]"
        else:
            # SRT with forced brand styling
            font_size = 64 if orientation == "portrait" else 48
            margin_v = 450 if orientation == "portrait" else 100
            filter_complex += (
                f";[{last_v}]subtitles='{safe_subs}':"
                f"force_style='Alignment=2,FontSize={font_size},MarginV={margin_v},"
                f"PlayResX={w},PlayResY={h},"
                f"FontName=Inter,"
                f"PrimaryColour={BRAND['pearl_white']},OutlineColour={BRAND['obsidian']},"
                f"BorderStyle=1,Outline=4,Shadow=2,Bold=1'[vcap]"
            )
        last_v = "vcap"

    # Step 4: Add contextual stickers (if provided)
    if stickers and captions_path:
        srt_to_search = captions_path
        if captions_path.endswith(".ass"):
            # Try to find the .srt version
            srt_alt = captions_path.replace(".ass", ".srt")
            if os.path.exists(srt_alt):
                srt_to_search = srt_alt
        
        if os.path.exists(srt_to_search):
            with open(srt_to_search, "r", encoding="utf-8") as f:
                srt_content = f.read()
            
            for s in stickers:
                match = re.search(
                    rf"(\d{{2}}:\d{{2}}:\d{{2}},\d{{3}}) --> (\d{{2}}:\d{{2}}:\d{{2}},\d{{3}})\n.*{s['word']}",
                    srt_content, re.IGNORECASE
                )
                if match:
                    start_str = match.group(1).replace(",", ".")
                    parts = start_str.split(':')
                    start_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                    end_sec = start_sec + s.get("duration", 2)
                    
                    x = 800 if orientation == "portrait" else 1500
                    y = 350
                    tag = re.sub(r'\W', '', s['word'])
                    filter_complex += (
                        f";[{last_v}]drawtext=text='{s['emoji']}':"
                        f"fontcolor=white:fontsize=100:x={x}:y={y}:"
                        f"enable='between(t,{start_sec},{end_sec})'[v{tag}]"
                    )
                    last_v = f"v{tag}"

    # Finalize filter
    filter_complex += f";[{last_v}]null[vfinal]"

    # Step 5: Build command
    command = [
        FFMPEG, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vfinal]",
    ]

    # Audio mapping
    if voiceover_path and os.path.exists(voiceover_path):
        command.extend(["-map", "1:a"])
    else:
        command.extend(["-map", "0:a?"])

    command.extend([
        "-c:v", "libx264",
        "-preset", "medium",        # Better quality than superfast
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-movflags", "+faststart",   # Optimize for web streaming
        output_path,
    ])

    # Step 6: Execute
    print(f"\n🔨 Encoding...")
    try:
        subprocess.run(command, check=True, capture_output=True)
        print(f"✅ SUCCESS → {output_path}")

        info = probe_video(output_path)
        if info:
            for s in info.get("streams", []):
                if s.get("codec_type") == "video":
                    print(f"   Resolution: {s['width']}x{s['height']}")
                    duration = info['format'].get('duration', 'unknown')
                    print(f"   Duration: {duration}s")
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"   File size: {size_mb:.1f} MB")
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg failed!")
        print(f"   stderr: {e.stderr.decode()[:500] if e.stderr else 'none'}")
        return None

    return output_path


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OASIS AI Video Pipeline V2")
    parser.add_argument("input", help="Path to input video file")
    parser.add_argument("-o", "--output", help="Output path (auto-generated if omitted)")
    parser.add_argument("--orientation", choices=["portrait", "landscape"], default="portrait")
    parser.add_argument("--auto-caption", action="store_true", help="Auto-transcribe with Whisper")
    parser.add_argument("--captions", help="Path to existing .srt or .ass file")
    parser.add_argument("--no-word-pop", action="store_true", help="Disable word-level pop animation")
    parser.add_argument("--offset", type=float, default=DEFAULT_OFFSET,
                        help=f"Timing offset in seconds (default: {DEFAULT_OFFSET})")
    parser.add_argument("--voiceover", help="Path to voiceover audio")
    parser.add_argument("--transcribe-only", action="store_true", help="Only transcribe, don't edit video")
    parser.add_argument("--model", default=WHISPER_MODEL, 
                        choices=["tiny", "base", "small", "medium", "large"],
                        help=f"Whisper model (default: {WHISPER_MODEL})")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ File not found: {args.input}")
        sys.exit(1)

    if args.transcribe_only:
        transcribe_word_level(args.input, offset=args.offset, model_name=args.model)
    else:
        edit_video(
            input_path=args.input,
            output_path=args.output,
            orientation=args.orientation,
            auto_caption=args.auto_caption,
            captions_path=args.captions,
            use_word_pop=not args.no_word_pop,
            offset=args.offset,
            voiceover_path=args.voiceover,
        )
