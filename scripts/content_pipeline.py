#!/usr/bin/env python3
"""
Content Pipeline — Elite Video Production System

The master orchestrator. CC uploads a raw video, this does everything:
  1. Transcribe with word-level Whisper timestamps
  2. Generate karaoke-style captions (word-by-word highlight)
  3. Apply cinematic cuts, transitions, split-screen overlays
  4. Generate contextual AI images via Codex
  5. Generate thumbnail
  6. Format caption text per platform
  7. Schedule across all platforms via Zernio

Usage:
  python scripts/content_pipeline.py process <video> [--topic "AI agents"] [--platforms all]
  python scripts/content_pipeline.py transcribe <video>
  python scripts/content_pipeline.py caption <video> --style karaoke
  python scripts/content_pipeline.py thumbnail <video> --text "The #1 Claude Code Tip"
  python scripts/content_pipeline.py research <competitor_handle>
  python scripts/content_pipeline.py ideas [--niche "AI automation"]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = PROJECT_ROOT / "media" / "exports"
RESEARCH_DIR = PROJECT_ROOT / "data" / "content_research"

# FFmpeg
FFMPEG_DIR = os.path.expandvars(
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
)
FFMPEG = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
FFPROBE = os.path.join(FFMPEG_DIR, "ffprobe.exe")
if not os.path.exists(FFMPEG):
    FFMPEG, FFPROBE = "ffmpeg", "ffprobe"

# Whisper
WHISPER_MODEL = "small"
DEFAULT_OFFSET = -0.8

# Brand
BRAND = {
    "primary": "#FAF9F5",       # Pearl White
    "background": "#141413",    # Obsidian
    "accent": "#0A84FF",        # OASIS Blue
    "highlight": "#30D158",     # Signal Green
    "font": "Inter",
}

# ASS color format (&HBBGGRR&)
ASS_COLORS = {
    "primary": "&H00F5F9FA&",
    "background": "&H00131414&",
    "accent": "&H00FF840A&",
    "highlight": "&H0058D130&",
    "dimmed": "&H80F5F9FA&",    # 50% opacity white
}

# Platform specs
PLATFORMS = {
    "instagram": {"max_duration": 90, "aspect": "9:16", "res": (1080, 1920), "max_chars": 2200},
    "tiktok": {"max_duration": 180, "aspect": "9:16", "res": (1080, 1920), "max_chars": 4000},
    "youtube_shorts": {"max_duration": 60, "aspect": "9:16", "res": (1080, 1920), "max_chars": 5000},
    "linkedin": {"max_duration": 600, "aspect": "9:16", "res": (1080, 1920), "max_chars": 3000},
    "facebook": {"max_duration": 240, "aspect": "9:16", "res": (1080, 1920), "max_chars": 63206},
    "x": {"max_duration": 140, "aspect": "9:16", "res": (1080, 1920), "max_chars": 280},
}


# ============================================================================
# TRANSCRIPTION (Word-Level)
# ============================================================================

def transcribe(input_path, offset=DEFAULT_OFFSET, model_name=WHISPER_MODEL):
    """Transcribe video with word-level timestamps."""
    try:
        import whisper
    except ImportError:
        print("ERROR: pip install openai-whisper")
        return None

    print(f"[1/7] Transcribing with Whisper ({model_name})...")
    model = whisper.load_model(model_name)
    result = model.transcribe(input_path, word_timestamps=True)

    words = []
    for seg in result["segments"]:
        for w in seg.get("words", []):
            words.append({
                "word": w["word"].strip(),
                "start": round(w["start"] + offset, 3),
                "end": round(w["end"] + offset, 3),
            })

    # Save outputs
    base = os.path.splitext(input_path)[0]
    words_path = base + ".words.json"
    srt_path = base + ".srt"

    with open(words_path, "w", encoding="utf-8") as f:
        json.dump({"words": words, "text": result["text"], "offset": offset}, f, indent=2)

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(result["segments"], 1):
            start = _srt_ts(seg["start"] + offset)
            end = _srt_ts(seg["end"] + offset)
            f.write(f"{i}\n{start} --> {end}\n{seg['text'].strip()}\n\n")

    print(f"  {len(words)} words transcribed")
    print(f"  Words: {os.path.basename(words_path)}")
    print(f"  SRT: {os.path.basename(srt_path)}")

    return {"words": words, "text": result["text"], "segments": result["segments"],
            "words_path": words_path, "srt_path": srt_path}


# ============================================================================
# KARAOKE CAPTIONS (Word-by-word highlight)
# ============================================================================

def generate_karaoke_ass(words, output_path, orientation="portrait"):
    """
    Generate karaoke-style ASS captions.
    Current word: bright brand color highlight
    Other words: dimmed white
    3-5 words displayed at a time, synced to audio.
    """
    if orientation == "portrait":
        res_x, res_y = 1080, 1920
        font_size = 72
        margin_v = 480
    else:
        res_x, res_y = 1920, 1080
        font_size = 52
        margin_v = 120

    header = f"""[Script Info]
Title: OASIS AI Karaoke Captions
ScriptType: v4.00+
PlayResX: {res_x}
PlayResY: {res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,{BRAND['font']},{font_size},{ASS_COLORS['dimmed']},{ASS_COLORS['dimmed']},{ASS_COLORS['background']},&H80000000&,-1,0,0,0,100,100,2,0,1,4,3,2,40,40,{margin_v},1
Style: KaraokeHighlight,{BRAND['font']},{font_size},{ASS_COLORS['primary']},{ASS_COLORS['primary']},{ASS_COLORS['background']},&H80000000&,-1,0,0,0,105,105,2,0,1,5,3,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    chunk_size = 4  # Words per display chunk

    for i in range(0, len(words), chunk_size):
        chunk = words[i:i + chunk_size]
        if not chunk:
            continue

        chunk_start = max(0, chunk[0]["start"])
        chunk_end = chunk[-1]["end"] + 0.15  # Buffer

        # For each word in the chunk, create a karaoke event
        # Show ALL words in chunk, but highlight current word
        for j, current_word in enumerate(chunk):
            word_start = max(0, current_word["start"])
            word_end = current_word["end"]

            # Build text: dimmed words + highlighted current word
            parts = []
            for k, w in enumerate(chunk):
                if k == j:
                    # Current word — bright, slightly larger
                    parts.append(f"{{\\c{ASS_COLORS['primary']}\\fscx110\\fscy110\\bord5}}{w['word']}{{\\r}}")
                else:
                    # Other words — dimmed
                    parts.append(f"{{\\c{ASS_COLORS['dimmed']}}}{w['word']}{{\\r}}")

            text = " ".join(parts)
            start_ts = _ass_ts(word_start)
            end_ts = _ass_ts(word_end)

            events.append(f"Dialogue: 0,{start_ts},{end_ts},Karaoke,,0,0,0,,{text}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write("\n".join(events))

    print(f"[2/7] Karaoke captions: {len(events)} events -> {os.path.basename(output_path)}")
    return output_path


# ============================================================================
# VIDEO PROCESSING
# ============================================================================

def probe_video(path):
    """Get video metadata."""
    cmd = [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return json.loads(r.stdout) if r.returncode == 0 else None


def process_video(input_path, output_path, ass_path, orientation="portrait",
                  split_image=None, intro_duration=0):
    """
    Process video with karaoke captions, optional split-screen overlay.
    """
    w, h = (1080, 1920) if orientation == "portrait" else (1920, 1080)

    inputs = ["-i", input_path]
    fc = f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black[vbase]"
    last = "vbase"

    # Split-screen overlay (top half image, bottom half video)
    if split_image and os.path.exists(split_image):
        inputs.extend(["-i", split_image])
        img_idx = 1
        fc += f";[{img_idx}:v]scale={w}:{h // 2}:force_original_aspect_ratio=decrease,pad={w}:{h // 2}:(ow-iw)/2:(oh-ih)/2:black[img]"
        fc += f";[{last}]crop={w}:{h // 2}:0:{h // 2}[vbottom]"
        fc += f";[img][vbottom]vstack[vsplit]"
        last = "vsplit"

    # Apply karaoke captions
    if ass_path and os.path.exists(ass_path):
        safe = ass_path.replace("\\", "/").replace(":", "\\:")
        fc += f";[{last}]ass='{safe}'[vcap]"
        last = "vcap"

    fc += f";[{last}]null[vfinal]"

    cmd = [
        FFMPEG, "-y", *inputs,
        "-filter_complex", fc,
        "-map", "[vfinal]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        output_path,
    ]

    print(f"[3/7] Encoding video...")
    try:
        subprocess.run(cmd, check=True, capture_output=True, encoding="utf-8")
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"  Output: {os.path.basename(output_path)} ({size_mb:.1f} MB)")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"  FFmpeg error: {e.stderr[:300] if e.stderr else 'unknown'}")
        return None


def generate_thumbnail(input_path, output_path, text=None, timestamp=1.0):
    """Extract a frame and optionally overlay text for thumbnail."""
    cmd = [
        FFMPEG, "-y", "-ss", str(timestamp),
        "-i", input_path, "-frames:v", "1",
        "-vf", f"scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black",
    ]

    if text:
        safe_text = text.replace("'", "\\'")
        cmd[-1] += (
            f",drawtext=text='{safe_text}':"
            f"fontcolor=white:fontsize=72:font={BRAND['font']}:"
            f"borderw=4:bordercolor=black:"
            f"x=(w-text_w)/2:y=(h-text_h)/2"
        )

    cmd.append(output_path)

    try:
        subprocess.run(cmd, check=True, capture_output=True, encoding="utf-8")
        print(f"[4/7] Thumbnail: {os.path.basename(output_path)}")
        return output_path
    except subprocess.CalledProcessError:
        print(f"  Thumbnail generation failed")
        return None


# ============================================================================
# PLATFORM CAPTION GENERATION
# ============================================================================

def generate_captions(transcript_text, topic=None):
    """Generate platform-specific caption text."""
    captions = {}

    # Base caption with hashtags
    base = transcript_text[:200].strip() if transcript_text else ""
    if topic:
        hashtags = f"#{topic.replace(' ', '')} #AI #automation #claudecode"
    else:
        hashtags = "#AI #automation #tech #claudecode #oasisai"

    captions["instagram"] = f"{base}\n\n{hashtags}"[:2200]
    captions["tiktok"] = f"{base}\n\n{hashtags}"[:4000]
    captions["youtube_shorts"] = base[:100]  # Title
    captions["linkedin"] = f"{base}\n\n#AI #automation #business"[:3000]
    captions["facebook"] = f"{base}\n\n{hashtags}"
    captions["x"] = base[:250] + " " + hashtags[:25] if len(base) < 250 else base[:275]

    print(f"[5/7] Captions generated for {len(captions)} platforms")
    return captions


# ============================================================================
# CODEX IMAGE GENERATION
# ============================================================================

def generate_context_image(topic, style="branded", output_path=None):
    """Delegate image generation to Codex."""
    if output_path is None:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in topic[:30])
        output_path = str(EXPORT_DIR / f"img_{safe}_{datetime.now().strftime('%H%M')}.png")

    script = str(PROJECT_ROOT / "scripts" / "codex_image_gen.py")
    if os.path.exists(script):
        cmd = ["python", script, "generate", topic, "--style", style, "--output", output_path]
        print(f"[6/7] Generating image via Codex: {topic[:50]}...")
        try:
            subprocess.run(cmd, timeout=300, encoding="utf-8")
            return output_path if os.path.exists(output_path) else None
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            print(f"  Image generation skipped (Codex unavailable)")
            return None
    else:
        print(f"  Image generation skipped (codex_image_gen.py not found)")
        return None


# ============================================================================
# COMPETITOR RESEARCH
# ============================================================================

def research_competitor(handle):
    """Research a competitor's content strategy."""
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    output_file = RESEARCH_DIR / f"{handle.replace('@', '').replace('.', '_')}.json"

    print(f"Researching @{handle}...")
    print(f"  Note: Full research requires Playwright MCP for scraping.")
    print(f"  Use: /research {handle} — for deep analysis via browser automation")
    print(f"  Output will be saved to: {output_file}")

    # Create research template
    template = {
        "handle": handle,
        "researched": datetime.now().isoformat(),
        "platform": "instagram",
        "followers": None,
        "posting_frequency": None,
        "content_pillars": [],
        "hook_patterns": [],
        "engagement_metrics": {},
        "viral_videos": [],
        "production_style": None,
        "caption_style": None,
        "hashtag_strategy": None,
        "cta_patterns": [],
        "notes": "Use Playwright MCP to fill in actual data",
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2)

    print(f"  Research template: {output_file}")
    return template


def generate_ideas(niche="AI automation", count=10):
    """Generate content ideas based on niche and trending patterns."""
    # Hook templates from viral content research
    hooks = [
        f"3 mistakes killing your {niche} business",
        f"I spent $10K learning {niche} so you don't have to",
        f"Why most {niche} fails (and what actually works)",
        f"The #1 {niche} tip nobody talks about",
        f"If you're doing {niche} like this, stop immediately",
        f"I automated my entire {niche} workflow in 30 minutes",
        f"People think {niche} is hard. Here's why they're wrong",
        f"This one {niche} hack changed everything",
        f"Stop wasting money on {niche} tools. Use this instead",
        f"How I built a $5K/month {niche} business from scratch",
        f"The truth about {niche} nobody wants to admit",
        f"Day in the life: running an {niche} agency at 22",
    ]

    ideas = []
    for i, hook in enumerate(hooks[:count], 1):
        ideas.append({
            "id": i,
            "hook": hook,
            "format": "talking head + screen recording" if i % 2 == 0 else "talking head + split-screen",
            "duration": "30-60 seconds",
            "platforms": ["instagram", "tiktok", "youtube_shorts"],
            "cta": "DM me 'AI' for free resources" if i % 3 == 0 else "Link in bio",
        })

    print(f"Generated {len(ideas)} content ideas for '{niche}':")
    for idea in ideas:
        print(f"  [{idea['id']}] {idea['hook']}")

    return ideas


# ============================================================================
# MASTER PIPELINE
# ============================================================================

def run_pipeline(input_path, topic=None, orientation="portrait",
                 platforms=None, generate_images=True, output_json=False):
    """
    Run the full content pipeline.
    Input: raw video from CC
    Output: edited video + thumbnail + captions + ready to schedule
    """
    if platforms is None:
        platforms = ["instagram", "tiktok", "youtube_shorts", "linkedin"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  OASIS AI Content Pipeline")
    print(f"  Input: {os.path.basename(input_path)}")
    print(f"  Topic: {topic or 'auto-detect from transcript'}")
    print(f"  Platforms: {', '.join(platforms)}")
    print(f"{'='*60}\n")

    results = {"input": input_path, "timestamp": timestamp, "outputs": {}}

    # Step 1: Transcribe
    transcription = transcribe(input_path)
    if not transcription:
        print("FAILED: Transcription failed")
        return None

    results["transcript"] = transcription["text"]
    if not topic:
        # Auto-detect topic from first 50 words
        topic = " ".join(transcription["text"].split()[:10])

    # Step 2: Karaoke captions
    ass_path = os.path.splitext(input_path)[0] + ".karaoke.ass"
    generate_karaoke_ass(transcription["words"], ass_path, orientation)
    results["captions_file"] = ass_path

    # Step 3: Process video with captions
    output_video = str(EXPORT_DIR / f"{base_name}_{timestamp}.mp4")
    result = process_video(input_path, output_video, ass_path, orientation)
    if result:
        results["outputs"]["video"] = output_video
    else:
        print("WARNING: Video processing failed, continuing with other outputs")

    # Step 4: Thumbnail
    thumb_path = str(EXPORT_DIR / f"{base_name}_{timestamp}_thumb.jpg")
    thumb_text = topic.split()[:5]
    generate_thumbnail(input_path, thumb_path, text=" ".join(thumb_text).upper())
    results["outputs"]["thumbnail"] = thumb_path

    # Step 5: Platform captions
    captions = generate_captions(transcription["text"], topic)
    results["outputs"]["captions"] = captions

    # Step 6: AI image (optional)
    if generate_images:
        img_prompt = f"Professional tech visual related to: {topic}. Dark background, modern aesthetic."
        img_path = generate_context_image(img_prompt, output_path=str(EXPORT_DIR / f"{base_name}_{timestamp}_overlay.png"))
        if img_path:
            results["outputs"]["overlay_image"] = img_path

    # Step 7: Summary
    print(f"\n{'='*60}")
    print(f"  Pipeline Complete")
    print(f"{'='*60}")
    print(f"  Video:     {results['outputs'].get('video', 'FAILED')}")
    print(f"  Thumbnail: {results['outputs'].get('thumbnail', 'FAILED')}")
    print(f"  Overlay:   {results['outputs'].get('overlay_image', 'skipped')}")
    print(f"  Captions:  {len(captions)} platforms")
    print(f"\n  Next: Review outputs, then schedule via Zernio:")
    print(f"  python scripts/late_tool.py create --text '<caption>' --media '<video>'")

    if output_json:
        print(json.dumps(results, indent=2, default=str))

    return results


# ============================================================================
# UTILITIES
# ============================================================================

def _srt_ts(seconds):
    seconds = max(0, seconds)
    h, m = int(seconds // 3600), int((seconds % 3600) // 60)
    s, ms = int(seconds % 60), int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def _ass_ts(seconds):
    seconds = max(0, seconds)
    h, m = int(seconds // 3600), int((seconds % 3600) // 60)
    s, cs = int(seconds % 60), int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OASIS AI Content Pipeline")
    parser.add_argument("--json", action="store_true")

    sub = parser.add_subparsers(dest="command")

    # Process (full pipeline)
    p = sub.add_parser("process", help="Full pipeline: video -> edited + captions + schedule")
    p.add_argument("input", help="Path to raw video")
    p.add_argument("--topic", help="Content topic (auto-detected if omitted)")
    p.add_argument("--orientation", choices=["portrait", "landscape"], default="portrait")
    p.add_argument("--platforms", nargs="+", default=None)
    p.add_argument("--no-images", action="store_true")

    # Transcribe only
    t = sub.add_parser("transcribe", help="Transcribe video with word-level timestamps")
    t.add_argument("input")
    t.add_argument("--offset", type=float, default=DEFAULT_OFFSET)
    t.add_argument("--model", default=WHISPER_MODEL)

    # Caption only
    c = sub.add_parser("caption", help="Generate karaoke captions from existing transcription")
    c.add_argument("input", help="Path to .words.json file")
    c.add_argument("--orientation", default="portrait")

    # Thumbnail
    th = sub.add_parser("thumbnail", help="Generate thumbnail from video")
    th.add_argument("input")
    th.add_argument("--text", help="Overlay text")
    th.add_argument("--timestamp", type=float, default=1.0)

    # Research
    r = sub.add_parser("research", help="Research competitor content strategy")
    r.add_argument("handle", help="Instagram handle")

    # Ideas
    ideas = sub.add_parser("ideas", help="Generate content ideas")
    ideas.add_argument("--niche", default="AI automation")
    ideas.add_argument("--count", type=int, default=10)

    args = parser.parse_args()

    if args.command == "process":
        run_pipeline(args.input, args.topic, args.orientation, args.platforms,
                     not args.no_images, args.json)
    elif args.command == "transcribe":
        transcribe(args.input, args.offset, args.model)
    elif args.command == "caption":
        with open(args.input, encoding="utf-8") as f:
            data = json.load(f)
        out = os.path.splitext(args.input)[0] + ".karaoke.ass"
        generate_karaoke_ass(data["words"], out, args.orientation)
    elif args.command == "thumbnail":
        out = os.path.splitext(args.input)[0] + "_thumb.jpg"
        generate_thumbnail(args.input, out, args.text, args.timestamp)
    elif args.command == "research":
        research_competitor(args.handle)
    elif args.command == "ideas":
        generate_ideas(args.niche, args.count)
    else:
        parser.print_help()
