"""
OASIS AI Video Pipeline -- V3 (Elite Production)

Upgrades over V2:
  - WhisperX forced alignment replaces openai-whisper (eliminates timing offset hack)
  - Audio enhancement pre-processing (noisereduce + pedalboard)
  - FFmpeg audio mastering chain (gate -> EQ -> compand -> loudnorm -14 LUFS)
  - Automatic silence/filler word removal via auto-editor
  - Color grading presets (teal_orange, editorial, warm, clean)
  - Cinematic effects (vignette, film grain, unsharp mask)
  - Brand-color word highlighting in captions (active word = OASIS Blue)
  - Falls back gracefully to openai-whisper if WhisperX not installed

Usage:
  # Full elite pipeline (enhance audio, transcribe, caption, grade, master):
  python scripts/edit_content_v2.py media/raw/video.mp4 --auto-caption --grade warm --master-audio

  # With silence removal:
  python scripts/edit_content_v2.py media/raw/video.mp4 --auto-caption --remove-silence

  # With filler word removal:
  python scripts/edit_content_v2.py media/raw/video.mp4 --auto-caption --remove-fillers

  # Color grade only (no captions):
  python scripts/edit_content_v2.py media/raw/video.mp4 --grade teal_orange

  # Just transcribe with WhisperX:
  python scripts/edit_content_v2.py media/raw/video.mp4 --transcribe-only

  # Legacy mode (V2 behavior):
  python scripts/edit_content_v2.py media/raw/video.mp4 --auto-caption --offset -0.8
"""

import os
import sys
import warnings
import subprocess
import json
import re

# Suppress non-critical torchcodec warning (pyannote optional dependency, not used by pipeline)
warnings.filterwarnings("ignore", message=".*torchcodec.*")
import argparse
import shutil
from datetime import datetime

# Windows symlink workaround for HuggingFace model cache
# (Windows requires Developer Mode for symlinks; this uses file copies instead)
if sys.platform == "win32":
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    try:
        import huggingface_hub.file_download as _hf_dl
        _orig_symlink = _hf_dl._create_symlink
        def _safe_symlink(src, dst, new_blob=False):
            try:
                _orig_symlink(src, dst, new_blob)
            except OSError:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.exists(dst):
                    os.remove(dst)
                shutil.copy2(src, dst)
        _hf_dl._create_symlink = _safe_symlink
    except ImportError:
        pass

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
    "dimmed_white": "&H80F5F9FA&",     # 50% opacity pearl white
}

# Whisper config
WHISPER_MODEL = "large-v3-turbo"  # Upgraded from "small"
WHISPER_FALLBACK_MODEL = "small"  # If WhisperX not available
DEFAULT_OFFSET = 0.0              # WhisperX alignment eliminates offset need

# Filler words to detect and optionally remove
FILLER_WORDS = {"um", "uh", "uhm", "erm", "ah", "like", "you know", "i mean", "sort of", "kind of"}

# Export directory
EXPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media", "exports")

# Color grade presets (FFmpeg filter strings)
COLOR_GRADES = {
    "teal_orange": (
        "curves=r='0/0 0.5/0.56 1/0.95':g='0/0 0.5/0.48 1/1':b='0/0.22 0.5/0.44 1/0.80',"
        "eq=saturation=0.80:contrast=1.05"
    ),
    "editorial": "eq=saturation=0.6:contrast=1.2:brightness=-0.02,curves=increase_contrast",
    "warm": (
        "curves=r='0/0 0.5/0.55 1/1':g='0/0 0.5/0.50 1/0.98':b='0/0 0.5/0.45 1/0.90',"
        "eq=saturation=1.05:contrast=1.02"
    ),
    "clean": "eq=saturation=0.95:contrast=1.03",
}

# Audio mastering chain (FFmpeg -af filter)
AUDIO_MASTER_CHAIN = (
    "agate=threshold=0.01:attack=80:release=840:makeup=1:ratio=3:knee=8,"
    "highpass=f=100:width_type=q:width=0.5,"
    "lowpass=f=10000,"
    "anequalizer=c0 f=250 w=100 g=2 t=1|c0 f=700 w=500 g=-5 t=1|c0 f=2000 w=1000 g=2 t=1,"
    "compand=attacks=0:points=-80/-900|-45/-15|-27/-9|0/-7|20/-7:gain=5,"
    "loudnorm=I=-14:TP=-1.0:LRA=11"
)


# ============================================================================
# UTILITIES
# ============================================================================

def probe_video(input_path):
    """Get video metadata via ffprobe."""
    cmd = [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", input_path]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
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
# AUDIO ENHANCEMENT (Pre-processing)
# ============================================================================

def enhance_audio(input_path, output_path=None):
    """
    Enhance audio quality using noisereduce + pedalboard.
    Transforms iPhone audio into broadcast-quality voice.
    Falls back to raw audio if libraries not installed.
    """
    if output_path is None:
        base = os.path.splitext(input_path)[0]
        output_path = base + "_enhanced.wav"

    # Extract audio first
    raw_wav = output_path + ".raw.wav"
    cmd = [FFMPEG, "-y", "-i", input_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", raw_wav]
    subprocess.run(cmd, capture_output=True, encoding="utf-8")

    enhanced = False

    try:
        import numpy as np
        import noisereduce as nr
        import soundfile as sf

        print("  [enhance] Applying spectral noise reduction...")
        audio_data, sample_rate = sf.read(raw_wav)
        reduced = nr.reduce_noise(y=audio_data, sr=sample_rate, prop_decrease=0.7, stationary=True)

        try:
            from pedalboard import Pedalboard, Compressor, HighpassFilter, NoiseGate

            print("  [enhance] Applying pedalboard (gate + compress + highpass)...")
            board = Pedalboard([
                NoiseGate(threshold_db=-40, ratio=4.0, attack_ms=10, release_ms=100),
                HighpassFilter(cutoff_frequency_hz=100),
                Compressor(threshold_db=-20, ratio=3.0, attack_ms=5, release_ms=50),
            ])
            processed = board(reduced.astype(np.float32), sample_rate)
            sf.write(output_path, processed, sample_rate)
            enhanced = True
            print(f"  [enhance] Enhanced audio -> {os.path.basename(output_path)}")

        except ImportError:
            # pedalboard not installed, use noisereduce output only
            sf.write(output_path, reduced, sample_rate)
            enhanced = True
            print(f"  [enhance] Noise-reduced audio -> {os.path.basename(output_path)} (pedalboard not installed)")

    except ImportError:
        print("  [enhance] SKIP -- noisereduce not installed (pip install noisereduce soundfile)")
        shutil.copy2(raw_wav, output_path)

    # Cleanup temp
    if os.path.exists(raw_wav):
        os.remove(raw_wav)

    return output_path if enhanced else None


# ============================================================================
# SILENCE & FILLER WORD REMOVAL
# ============================================================================

def remove_silence(input_path, output_path=None, margin=0.3, threshold=0.03):
    """
    Remove silence from video using auto-editor.
    Falls back to FFmpeg silencedetect if auto-editor not installed.
    """
    if output_path is None:
        base = os.path.splitext(input_path)[0]
        output_path = base + "_trimmed.mp4"

    try:
        # Try auto-editor first (best quality)
        cmd = [
            sys.executable, "-m", "auto_editor",
            input_path,
            "--edit", f"audio:threshold={threshold}",
            "--margin", f"{margin}sec",
            "--output", output_path,
            "--no-open",
        ]
        print(f"  [silence] Running auto-editor (threshold={threshold}, margin={margin}s)...")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=300)
        if result.returncode == 0 and os.path.exists(output_path):
            print(f"  [silence] Trimmed -> {os.path.basename(output_path)}")
            return output_path
        else:
            print(f"  [silence] auto-editor failed: {result.stderr[:200] if result.stderr else 'unknown'}")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("  [silence] auto-editor not installed (pip install auto-editor)")

    # Fallback: FFmpeg silencedetect -> segment-based removal
    print("  [silence] Falling back to FFmpeg silencedetect...")
    detect_cmd = [
        FFMPEG, "-i", input_path,
        "-af", f"silencedetect=noise=-35dB:d={margin}",
        "-vn", "-sn", "-f", "null", "-"
    ]
    result = subprocess.run(detect_cmd, capture_output=True, text=True, encoding="utf-8")
    stderr = result.stderr or ""

    # Parse silence ranges
    silence_starts = [float(m.group(1)) for m in re.finditer(r"silence_start: (\d+\.?\d*)", stderr)]
    silence_ends = [float(m.group(1)) for m in re.finditer(r"silence_end: (\d+\.?\d*)", stderr)]

    if not silence_starts:
        print("  [silence] No silence detected -- copying original")
        shutil.copy2(input_path, output_path)
        return output_path

    # Build keep segments
    info = probe_video(input_path)
    duration = float(info["format"]["duration"]) if info else 9999
    segments = []
    pos = 0.0
    for start, end in zip(silence_starts, silence_ends):
        if start > pos:
            segments.append((pos, start))
        pos = end
    if pos < duration:
        segments.append((pos, duration))

    if not segments:
        shutil.copy2(input_path, output_path)
        return output_path

    # Build FFmpeg select filter
    v_sel = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in segments)
    a_sel = v_sel
    cmd = [
        FFMPEG, "-y", "-i", input_path,
        "-vf", f"select='{v_sel}',setpts=N/FRAME_RATE/TB",
        "-af", f"aselect='{a_sel}',asetpts=N/SR/TB",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, encoding="utf-8")
    print(f"  [silence] Trimmed -> {os.path.basename(output_path)} ({len(segments)} segments kept)")
    return output_path


def detect_filler_words(words_data):
    """
    Identify filler words in transcription word list.
    Returns list of time ranges to cut.
    """
    fillers_found = []
    words = words_data if isinstance(words_data, list) else words_data.get("words", [])

    for w in words:
        word_lower = w["word"].lower().strip(".,!?")
        if word_lower in FILLER_WORDS:
            fillers_found.append({
                "word": w["word"],
                "start": w["start"],
                "end": w["end"],
            })

    if fillers_found:
        print(f"  [fillers] Found {len(fillers_found)} filler words: {', '.join(f['word'] for f in fillers_found[:10])}")
    return fillers_found


def remove_filler_segments(input_path, filler_ranges, output_path=None):
    """Remove filler word time segments from video using FFmpeg select filter."""
    if not filler_ranges:
        return input_path

    if output_path is None:
        base = os.path.splitext(input_path)[0]
        output_path = base + "_nofiller.mp4"

    info = probe_video(input_path)
    duration = float(info["format"]["duration"]) if info else 9999

    # Build keep segments (inverse of filler ranges)
    filler_ranges.sort(key=lambda x: x["start"])
    segments = []
    pos = 0.0
    for f in filler_ranges:
        if f["start"] > pos + 0.05:
            segments.append((pos, f["start"]))
        pos = f["end"]
    if pos < duration:
        segments.append((pos, duration))

    if not segments:
        shutil.copy2(input_path, output_path)
        return output_path

    v_sel = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in segments)
    cmd = [
        FFMPEG, "-y", "-i", input_path,
        "-vf", f"select='{v_sel}',setpts=N/FRAME_RATE/TB",
        "-af", f"aselect='{v_sel}',asetpts=N/SR/TB",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, encoding="utf-8")
    print(f"  [fillers] Removed {len(filler_ranges)} filler words -> {os.path.basename(output_path)}")
    return output_path


# ============================================================================
# TRANSCRIPTION (WhisperX with fallback)
# ============================================================================

def transcribe_word_level(input_path, offset=None, model_name=None, enhanced_audio_path=None):
    """
    Transcribe video with word-level timestamps.
    Priority: WhisperX (forced alignment) -> openai-whisper (with offset hack).
    """
    audio_source = enhanced_audio_path if enhanced_audio_path and os.path.exists(enhanced_audio_path) else input_path
    base = os.path.splitext(input_path)[0]
    srt_path = base + ".srt"
    words_path = base + ".words.json"

    # Try WhisperX first (best quality -- forced alignment, no offset needed)
    try:
        import whisperx
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        model = model_name or WHISPER_MODEL

        print(f"  [transcribe] WhisperX ({model}) on {device}...")
        whisperx_model = whisperx.load_model(model, device, compute_type=compute_type)
        audio = whisperx.load_audio(audio_source)
        result = whisperx_model.transcribe(audio, batch_size=16)

        # Forced alignment for precise word timestamps
        print("  [transcribe] Running forced alignment...")
        align_model, align_metadata = whisperx.load_align_model(language_code="en", device=device)
        result = whisperx.align(result["segments"], align_model, align_metadata, audio, device)

        # Extract word-level data (no offset needed -- alignment is precise)
        all_words = []
        for seg in result.get("segments", []):
            for w in seg.get("words", []):
                if "start" in w and "end" in w:
                    all_words.append({
                        "word": w["word"].strip(),
                        "start": round(w["start"], 3),
                        "end": round(w["end"], 3),
                    })

        # Write outputs
        with open(words_path, "w", encoding="utf-8") as f:
            json.dump({"words": all_words, "engine": "whisperx", "model": model, "aligned": True}, f, indent=2)

        with open(srt_path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(result.get("segments", []), 1):
                start = _srt_timestamp(seg.get("start", 0))
                end = _srt_timestamp(seg.get("end", 0))
                text = seg.get("text", "").strip()
                f.write(f"{i}\n{start} --> {end}\n{text}\n\n")

        print(f"  [transcribe] WhisperX: {len(all_words)} words (aligned)")
        return {"segments": result.get("segments", []), "words": all_words,
                "srt_path": srt_path, "words_path": words_path, "engine": "whisperx"}

    except ImportError:
        print("  [transcribe] WhisperX not installed -- falling back to openai-whisper")

    # Fallback: openai-whisper (with offset hack)
    try:
        import whisper
    except ImportError:
        print("ERROR: No transcription engine. Run: pip install openai-whisper (or pip install whisperx)")
        return None

    fallback_model = model_name or WHISPER_FALLBACK_MODEL
    fallback_offset = offset if offset is not None else -0.8  # Legacy offset for openai-whisper

    print(f"  [transcribe] openai-whisper ({fallback_model}), offset={fallback_offset}s...")
    model = whisper.load_model(fallback_model)
    result = model.transcribe(audio_source, word_timestamps=True)

    all_words = []
    for seg in result["segments"]:
        for word_info in seg.get("words", []):
            all_words.append({
                "word": word_info["word"].strip(),
                "start": round(word_info["start"] + fallback_offset, 3),
                "end": round(word_info["end"] + fallback_offset, 3),
            })

    with open(words_path, "w", encoding="utf-8") as f:
        json.dump({"words": all_words, "engine": "openai-whisper", "model": fallback_model,
                    "offset_applied": fallback_offset}, f, indent=2)

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(result["segments"], 1):
            start = _srt_timestamp(seg["start"] + fallback_offset)
            end = _srt_timestamp(seg["end"] + fallback_offset)
            text = seg["text"].strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")

    print(f"  [transcribe] openai-whisper: {len(all_words)} words (offset={fallback_offset}s)")
    return {"segments": result["segments"], "words": all_words,
            "srt_path": srt_path, "words_path": words_path, "engine": "openai-whisper"}


# ============================================================================
# CAPTION GENERATION (Brand-Color Word Highlighting)
# ============================================================================

def generate_word_pop_ass(words_data, output_path, orientation="portrait", style="dynamic_minimalism"):
    """
    Generate ASS captions with brand-color word-by-word highlighting.

    Styles:
      - dynamic_minimalism: Clean white + OASIS Blue highlight (default)
      - hormozi: Bold yellow highlight, ALL CAPS
    """
    if orientation == "portrait":
        res_x, res_y = 1080, 1920
        font_size = 64
        margin_v = 500
    else:
        res_x, res_y = 1920, 1080
        font_size = 48
        margin_v = 120

    # Style configuration
    if style == "hormozi":
        highlight_color = "&H0004C2F7&"  # Yellow #f7c204 in BGR
        base_color = BRAND["pearl_white"]
        font_name = "Montserrat"
        caps = True
    else:
        highlight_color = BRAND["oasis_blue"]
        base_color = BRAND["dimmed_white"]
        font_name = "Inter"
        caps = False

    header = f"""[Script Info]
Title: OASIS AI Elite Captions
ScriptType: v4.00+
PlayResX: {res_x}
PlayResY: {res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: WordPop,{font_name},{font_size},{base_color},{base_color},{BRAND['obsidian']},&H80000000&,-1,0,0,0,100,100,2,0,1,4,2,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    words = words_data if isinstance(words_data, list) else words_data.get("words", [])

    # Group into display chunks (3-5 words)
    chunk_size = 4
    for i in range(0, len(words), chunk_size):
        chunk = words[i:i + chunk_size]
        if not chunk:
            continue

        # For each word in chunk, create a highlight event
        for j, current_word in enumerate(chunk):
            word_start = max(0, current_word["start"])
            word_end = current_word["end"]

            parts = []
            for k, w in enumerate(chunk):
                word_text = w["word"].upper() if caps else w["word"]
                if k == j:
                    # Active word -- brand color, slightly larger
                    parts.append(
                        f"{{\\c{highlight_color}\\fscx110\\fscy110\\bord5}}"
                        f"{word_text}{{\\r}}"
                    )
                else:
                    # Other words -- dimmed
                    parts.append(f"{{\\c{base_color}}}{word_text}{{\\r}}")

            text = " ".join(parts)
            start_ts = _ass_timestamp(word_start)
            end_ts = _ass_timestamp(word_end)

            events.append(f"Dialogue: 0,{start_ts},{end_ts},WordPop,,0,0,0,,{text}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write("\n".join(events))

    print(f"  [captions] {style}: {len(events)} events -> {os.path.basename(output_path)}")
    return output_path


# ============================================================================
# VIDEO EDITING (Elite Pipeline)
# ============================================================================

def edit_video(input_path, output_path=None, orientation="portrait",
               auto_caption=False, captions_path=None, use_word_pop=True,
               offset=None, voiceover_path=None, stickers=None,
               grade=None, master_audio=False, enhance=False,
               remove_silence_flag=False, remove_fillers_flag=False,
               caption_style="dynamic_minimalism", cinematic=False):
    """
    OASIS AI Elite Video Pipeline V3.
    """
    print(f"\n{'='*60}")
    print(f"  OASIS AI Video Pipeline V3 -- Elite Production")
    print(f"{'='*60}")
    print(f"  Input: {os.path.basename(input_path)}")
    print(f"  Orientation: {orientation}")
    if grade:
        print(f"  Color grade: {grade}")
    if master_audio:
        print(f"  Audio mastering: ON (-14 LUFS)")
    if enhance:
        print(f"  Audio enhancement: ON (noisereduce + pedalboard)")

    # Auto-generate output path
    if output_path is None:
        base = os.path.splitext(os.path.basename(input_path))[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        output_path = os.path.join(EXPORT_DIR, f"{base}_v3_{timestamp}.mp4")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Resolution
    w, h = (1080, 1920) if orientation == "portrait" else (1920, 1080)

    # Working copy for destructive pre-processing
    working_input = input_path
    temp_files = []

    # ── Phase 1: Audio Enhancement ──
    enhanced_audio = None
    if enhance:
        print("\n[Phase 1] Audio Enhancement")
        enhanced_audio = enhance_audio(input_path)

    # ── Phase 2: Silence Removal ──
    if remove_silence_flag:
        print("\n[Phase 2] Silence Removal")
        trimmed = remove_silence(working_input)
        if trimmed and trimmed != working_input:
            temp_files.append(trimmed)
            working_input = trimmed

    # ── Phase 3: Transcription ──
    ass_path = None
    transcription = None
    if auto_caption:
        print("\n[Phase 3] Transcription")
        transcription = transcribe_word_level(working_input, offset=offset,
                                               enhanced_audio_path=enhanced_audio)

        # ── Phase 3b: Filler Word Removal ──
        if remove_fillers_flag and transcription:
            fillers = detect_filler_words(transcription["words"])
            if fillers:
                defillered = remove_filler_segments(working_input, fillers)
                if defillered and defillered != working_input:
                    temp_files.append(defillered)
                    working_input = defillered
                    # Re-transcribe after filler removal for accurate timestamps
                    print("  [fillers] Re-transcribing after filler removal...")
                    transcription = transcribe_word_level(working_input,
                                                          enhanced_audio_path=enhanced_audio)

        # Generate ASS captions
        if transcription and use_word_pop:
            ass_path = os.path.splitext(working_input)[0] + ".ass"
            generate_word_pop_ass(transcription["words"], ass_path, orientation, style=caption_style)
            captions_path = ass_path
        elif transcription:
            captions_path = transcription["srt_path"]

    # ── Phase 4: Video Encoding ──
    print(f"\n[Phase 4] Video Encoding")

    inputs = ["-i", working_input]
    filter_parts = []

    # Base scaling
    filter_parts.append(f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black")

    # Color grading
    if grade and grade in COLOR_GRADES:
        filter_parts.append(COLOR_GRADES[grade])

    # Cinematic effects
    if cinematic:
        filter_parts.append("vignette=PI/4")
        filter_parts.append("unsharp=5:5:0.5:3:3:0")

    # Combine video filters into chain
    vf_chain = ",".join(filter_parts) + "[vbase]"
    filter_complex = vf_chain
    last_v = "vbase"

    # Voiceover input
    if voiceover_path and os.path.exists(voiceover_path):
        inputs.extend(["-i", voiceover_path])

    # Subtitles
    if captions_path and os.path.exists(captions_path):
        safe_subs = captions_path.replace("\\", "/").replace(":", "\\:")

        if captions_path.endswith(".ass"):
            filter_complex += f";[{last_v}]ass='{safe_subs}'[vcap]"
        else:
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

    # Stickers (contextual emoji overlays)
    if stickers and captions_path:
        srt_to_search = captions_path
        if captions_path.endswith(".ass"):
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

    # Build command
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

    # Audio mastering chain
    if master_audio:
        command.extend(["-af", AUDIO_MASTER_CHAIN])

    command.extend([
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-movflags", "+faststart",
        output_path,
    ])

    # Execute
    print(f"  Encoding...")
    try:
        subprocess.run(command, check=True, capture_output=True, encoding="utf-8")
        print(f"\n  SUCCESS -> {output_path}")

        info = probe_video(output_path)
        if info:
            for s in info.get("streams", []):
                if s.get("codec_type") == "video":
                    print(f"  Resolution: {s['width']}x{s['height']}")
                    duration = info['format'].get('duration', 'unknown')
                    print(f"  Duration: {duration}s")
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  File size: {size_mb:.1f} MB")
    except subprocess.CalledProcessError as e:
        stderr = e.stderr[:500] if e.stderr else "none"
        print(f"  FAILED! stderr: {stderr}")
        # Cleanup temps
        for tf in temp_files:
            if os.path.exists(tf):
                os.remove(tf)
        return None

    # Cleanup temp files
    for tf in temp_files:
        if os.path.exists(tf):
            os.remove(tf)

    return output_path


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OASIS AI Video Pipeline V3 -- Elite Production")
    parser.add_argument("input", help="Path to input video file")
    parser.add_argument("-o", "--output", help="Output path (auto-generated if omitted)")
    parser.add_argument("--orientation", choices=["portrait", "landscape"], default="portrait")

    # Transcription
    parser.add_argument("--auto-caption", action="store_true", help="Auto-transcribe and caption")
    parser.add_argument("--captions", help="Path to existing .srt or .ass file")
    parser.add_argument("--no-word-pop", action="store_true", help="Disable word-level pop animation")
    parser.add_argument("--offset", type=float, default=None,
                        help="Timing offset (only used with openai-whisper fallback)")
    parser.add_argument("--model", default=None, help="Whisper model override")
    parser.add_argument("--caption-style", choices=["dynamic_minimalism", "hormozi"],
                        default="dynamic_minimalism", help="Caption visual style")
    parser.add_argument("--transcribe-only", action="store_true", help="Only transcribe, don't edit")

    # Audio
    parser.add_argument("--enhance", action="store_true",
                        help="Audio enhancement (noisereduce + pedalboard)")
    parser.add_argument("--master-audio", action="store_true",
                        help="Apply broadcast audio mastering (-14 LUFS)")
    parser.add_argument("--voiceover", help="Path to voiceover audio")

    # Editing
    parser.add_argument("--remove-silence", action="store_true",
                        help="Remove silence (auto-editor or FFmpeg)")
    parser.add_argument("--remove-fillers", action="store_true",
                        help="Remove filler words (um, uh, like)")

    # Visual
    parser.add_argument("--grade", choices=list(COLOR_GRADES.keys()),
                        help="Color grade preset")
    parser.add_argument("--cinematic", action="store_true",
                        help="Add vignette + unsharp mask")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"File not found: {args.input}")
        sys.exit(1)

    if args.transcribe_only:
        enhanced = enhance_audio(args.input) if args.enhance else None
        transcribe_word_level(args.input, offset=args.offset, model_name=args.model,
                              enhanced_audio_path=enhanced)
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
            grade=args.grade,
            master_audio=args.master_audio,
            enhance=args.enhance,
            remove_silence_flag=args.remove_silence,
            remove_fillers_flag=args.remove_fillers,
            caption_style=args.caption_style,
            cinematic=args.cinematic,
        )
