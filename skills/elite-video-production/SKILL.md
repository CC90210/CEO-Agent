---
name: elite-video-production
description: Complete automated video production system for CC's content pipeline. Use whenever CC provides raw video footage and says "make this a post", "edit this", or asks for a cinematic output. Replaces a human video editor entirely. Covers hook engineering, pacing, caption styling, color grading, audio mastering, sound design, motion graphics, and multi-platform export.
triggers: [video, edit, post, caption, hook, grade, audio, export, reel, short, tiktok, b-roll, lower third, film grain, remotion, ffmpeg, whisper, cinematic]
tier: full
dependencies: [content-engine]
---

# Elite Video Production

Raw iPhone footage → cinematic, captioned, platform-ready output. No questions, no half-measures.

## When CC Says "Make This a Post"

Run the full 15-step pipeline (Section 14) automatically. The only input needed is the raw video file path. Everything else is decided by this skill.

---

## Section 1: The 3-Second Hook (Non-Negotiable)

**The data:**
- 65% of viewers who pass 3 seconds continue past 10 seconds (Facebook internal)
- TikTok gates For You Page distribution on 3-second hold rate — 60%+ triggers algorithmic push
- First frame is the single highest-leverage edit decision in the entire video

**The 3 Hook Rule — all three must fire simultaneously:**

| Hook Type | What It Is | Rule |
|-----------|-----------|------|
| Visual | Movement or high contrast in frame 0 | Never open on a static, low-contrast shot |
| Text | 1-7 bold words overlaid immediately | No delay — on screen by frame 1 |
| Verbal | Payload first, no intro | Never start with "Hey guys" or "So today" |

**Hook copy patterns ranked by hold rate:**
1. Mistake/Loss Aversion: "Stop doing X" — fear of missing out drives pause
2. Secret/Curiosity Gap: "What nobody tells you about..." — information asymmetry
3. Bold Contradiction: State the opposite of conventional wisdom, no qualifier
4. Mid-Action Open: Video starts in the middle of something interesting, no setup

**Curiosity gap templates (use verbatim or adapt):**
- "I was wrong about [X]"
- "Here's what $[amount] actually looks like"
- "Nobody talks about this part"
- "I almost didn't share this"
- "The part they cut from every tutorial"

**First frame engineering checklist:**
- [ ] Tight crop: shoulders-up or tighter
- [ ] Strong emotional expression on face (not neutral)
- [ ] High contrast between subject and background
- [ ] Direct eye contact with lens
- [ ] Text overlay in upper-middle zone (not bottom 25%, not top 15%)
- [ ] Text: max 7 words, bold, high contrast font

---

## Section 2: Pacing and Cut Frequency

**2024 data:** MrBeast reduced from 38 cuts/60s to 23 cuts/60s — viewership increased. Overstimulation editing is dead. Purposeful cuts win.

**Cut rate by video length:**

| Duration | Target Cut Rate | Notes |
|----------|----------------|-------|
| 10-20s viral clip | Every 1-2 seconds | Remove all silence and breath |
| 30-60s educational | Every 3-5 seconds | Jump cuts + zoom punches |
| 60-90s story | Every 5-8 seconds | Burst at key moments (contrast pattern) |

**Hard rules:**
- Never more than 15 seconds without a visual or audio change
- Beat-synced cutting: cuts land on downbeat or snare of background track
- Pattern interrupts (zoom punch, B-roll insert, SFX) increase watch time 85% and conversion 32%

**Optimal publish lengths by platform:**

| Platform | Optimal | Algorithmic sweet spot |
|----------|---------|----------------------|
| TikTok | 21-34s | Under 30s gets full re-watch loop credit |
| Instagram Reels | 15-45s | 15-30s for discovery, 45s for community |
| YouTube Shorts | 15-35s | Loop completion is the key signal |

---

## Section 3: The Retention Edit Toolkit

### Zoom Punch
Cut (not a slow zoom) from medium shot to 10-15% tighter on the same angle. Use at emphasis words, punchlines, and logic pivots. Implementation:
```bash
# FFmpeg scale + crop zoom punch (cut-based, not smooth):
# At timestamp of emphasis word, cut to:
-vf "scale=iw*1.12:-1,crop=iw/1.12:ih/1.12"
```

### J-Cut
Audio from the next clip begins 0.5-2 seconds before the video cuts. Use for topic transitions and cutting into B-roll. Forces the viewer's brain to follow the audio before the image catches up.

### L-Cut
Video cuts to new footage but audio continues from the previous clip. Use for screen recordings and demos while narration continues.

### Jump Cut + Silence Removal
Cut every breath, filler word, and pause greater than 0.3 seconds. Non-negotiable for all talking-head content.
```bash
# auto-editor (pip install auto-editor):
auto-editor input.mp4 --margin 0.2sec --output silent-removed.mp4
```

### Speed Ramp
Requires 120fps source footage. Ramp from 1x to 0.3x at the key visual, then accelerate to 2-4x through the transition. The slowest point lands on the beat.
```bash
# FFmpeg variable speed (requires setpts filter):
-vf "setpts=0.3*PTS"   # 3.3x speed
-vf "setpts=3.33*PTS"  # 0.3x slowmo
```

### Flash Frame
1-3 white or black frames on a cut. Use for high-energy cuts, section transitions, and before major statements.
```bash
# Insert 2 white frames at cut point:
color=c=white:s=1080x1920:d=2/30,format=yuv420p
```

### Camera Shake
2-4 frame oscillation on the X/Y axis. Duration 0.5-1 second. Coincides with bass hits or impact SFX.
```bash
# FFmpeg shake (apply at impact moment):
-vf "crop=iw-20:ih-20:(sin(n/2)*10)+10:(cos(n/2)*10)+10"
```

### Freeze Frame
Pause video 0.5-1.5 seconds while audio continues. Use for reactions, data points, and joke landings.
```bash
# FFmpeg freeze at timestamp T:
-vf "setpts=if(between(t,T,T+1),T/TB,PTS)"
```

### Pattern Interrupt Frequency

| Duration | Interrupt Cadence | Method |
|----------|------------------|--------|
| 10-30s | Every 2-4 seconds | Zoom punch, B-roll, SFX hit |
| 30-60s | Every 3-6 seconds | Mixed toolkit |
| 60-90s | Contrast Pattern: steady baseline + burst every 25-35s | 5-10 rapid cuts in the burst |

---

## Section 4: Caption Engineering

**The data:** Captions increase watch time 12-40%. 92% of social video is watched without sound.

**Word-by-word highlight beats full-sentence display** — guides the eye at speech pace, never ahead or behind.

### OASIS / Kona Makana Brand Standard (Default)

| Property | Value |
|----------|-------|
| Font | Roboto Bold or SF Pro Bold |
| Base color | White (`#FFFFFF`) |
| Keyword highlight | OASIS Blue (`#0A84FF`) |
| Animation | Smooth fade/slide-up — never a jarring pop |
| Case | Mixed-case — NOT all-caps |
| Chunk size | 3-7 words per display, 1-3 seconds each |
| Position | Center-middle (avoid bottom 25%, top 15%) |
| Drop shadow | 0 2px 8px rgba(0,0,0,0.6) — subtle, no thick outline |

### Classic Hormozi (High-Energy Option)

| Property | Value |
|----------|-------|
| Font | Montserrat Bold |
| Case | ALL CAPS |
| Primary highlight | Yellow `#f7c204` |
| Secondary accent | Green `#02fb23` |
| Base | White |
| Animation | Word-by-word pop/scale on active word |

### Technical Implementation (ASS Subtitle Format)

WhisperX forced alignment produces word-level JSON timestamps. Convert to ASS with karaoke tags:

```
# Each word is a separate ASS Dialogue event
# Active word: brand color + scaleX 1.10
# Remaining words: dimmed white at 70% opacity

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.24,0:00:01.58,Default,,0,0,0,,{\c&H0A84FF&\fscx110}STOP{\r} {\c&HFFFFFF&\alpha&H46&}doing this wrong

# \c&H0A84FF& = brand color (ASS uses BGR hex, reversed from RGB)
# \fscx110 = scale X to 110% for active word
# \alpha&H46& = ~70% opacity on inactive words
```

---

## Section 5: Color Grading

### iPhone Talking-Head Starting Point (FFmpeg)

```bash
-vf "curves=r='0/0 0.5/0.56 1/0.95':g='0/0 0.5/0.48 1/1':b='0/0.22 0.5/0.44 1/0.80',\
eq=saturation=0.80:contrast=1.05,\
vignette=PI/4,\
unsharp=5:5:0.5:3:3:0"
```

### Named Grade Presets (use with `--grade` flag in pipeline script)

| Preset | FFmpeg Filter | When to Use |
|--------|--------------|-------------|
| `teal_orange` | Shadows→cyan curves, skin→warm orange | Most talking-head, high energy |
| `editorial` | `eq=saturation=0.6:contrast=1.2`, crushed blacks | Serious/professional content |
| `warm` | +200K WB feel, saturation boost, gentle vignette | Personal brand, lifestyle |
| `clean` | Neutral REC709, micro-contrast, vignette only | Screen recordings, tutorials |

**Full teal_orange implementation:**
```bash
-vf "curves=r='0/0 0.25/0.30 0.75/0.82 1/0.95':g='0/0 0.5/0.50 1/1':b='0/0.18 0.25/0.35 0.75/0.60 1/0.75',\
eq=saturation=0.85:contrast=1.08,\
vignette=PI/4"
```

### Grading Rules (Non-Negotiable)

- LUTs at 50-70% blend intensity, never 100%
- Crush blacks slightly — lift off true black for mobile viewing (blacks at luma ~16)
- Background desaturated relative to subject — creates subject separation without a key light
- Skin tones must land on vectorscope skin line (approximately 123° hue, 0.3-0.6 saturation)
- Export: Rec.709 color space, H.264 or H.265, 30fps minimum

---

## Section 6: Audio Mastering

### Complete FFmpeg Voice Mastering Chain

```bash
-af "agate=threshold=0.01:attack=80:release=840:makeup=1:ratio=3:knee=8,\
highpass=f=100:width_type=q:width=0.5,\
lowpass=f=10000,\
anequalizer=c0 f=250 w=100 g=2 t=1|c0 f=700 w=500 g=-5 t=1|c0 f=2000 w=1000 g=2 t=1,\
compand=attacks=0:points=-80/-900|-45/-15|-27/-9|0/-7|20/-7:gain=5,\
loudnorm=I=-14:TP=-1.0:LRA=11"
```

### Chain Breakdown

| Stage | Tool | What It Does |
|-------|------|-------------|
| Gate | `agate` threshold=0.01 | Kills breath noise and background hiss between words |
| Highpass | `highpass f=100` | Removes rumble, HVAC, handling noise below 100Hz |
| Lowpass | `lowpass f=10000` | Tames harshness, de-esses upper frequencies |
| EQ | `anequalizer` | +2dB at 250Hz (warmth), -5dB at 700Hz (mud), +2dB at 2kHz (presence/clarity) |
| Compression | `compand` | 3:1 ratio, -7dB hard ceiling, consistent perceived loudness |
| Loudnorm | `loudnorm I=-14` | Final normalization to platform standard |

### Platform LUFS Targets

| Platform | Target LUFS | True Peak |
|----------|------------|-----------|
| YouTube, TikTok, Reels | -14 LUFS | -1.0 dBTP |
| Podcasts / spoken audio | -16 LUFS | -1.0 dBTP |
| Broadcast (EBU R128) | -23 LUFS | -1.0 dBTP |

### Python Pre-Processing (Before FFmpeg)

```python
# pip install noisereduce pedalboard soundfile numpy
import soundfile as sf
import noisereduce as nr
from pedalboard import Pedalboard, Compressor, HighpassFilter, LowShelfFilter

# Step 1: Spectral noise reduction
audio, sr = sf.read("raw_audio.wav")
reduced = nr.reduce_noise(y=audio, sr=sr, stationary=False, prop_decrease=0.75)

# Step 2: Pedalboard studio chain (300x faster than pySoX)
board = Pedalboard([
    HighpassFilter(cutoff_frequency_hz=80),
    Compressor(threshold_db=-18, ratio=3.0, attack_ms=5.0, release_ms=100.0),
    LowShelfFilter(cutoff_frequency_hz=200, gain_db=2.0),
])
processed = board(reduced, sr)
sf.write("processed_audio.wav", processed, sr)
# Hand off processed_audio.wav to FFmpeg mastering chain
```

---

## Section 7: Sound Design

### Five Core SFX — Exact Timing

| SFX | When to Use | Timing Relative to Cut |
|-----|-------------|----------------------|
| Whoosh | Transitions, text reveals, caption slide-ins | Start 2-4 frames BEFORE cut, peak on cut frame |
| Hit / Impact | Jump cuts, title drops, zoom punches | Exactly on cut frame |
| Riser | Building to reveal, end of section | 1-3 seconds before payoff moment |
| Bass Drop / Boom | Big scene change, dramatic statement | First frame of the new scene |
| Pop / Click | Caption word pop, UI element reveals | Exactly synced to text appearance frame |

### Volume Mixing (Voice Is Reference at 0dB)

| Layer | Level Below Voice |
|-------|-----------------|
| Background music (calm) | -20 to -25 dB |
| Background music (high energy) | -8 to -12 dB |
| SFX | Just below music (felt, not heard) |

### Hormozi SFX Formula

- Zoom punch → impact hit SFX exactly on the cut frame
- Caption word pop → click at -20 dB exactly on text appearance
- Section transition → whoosh starting 3 frames before cut
- Major claim → 0.5-1 second of silence before delivery, then hit SFX on the first word

### Remotion Free SFX Assets

```
https://remotion.media/whoosh.wav
https://remotion.media/whip.wav
https://remotion.media/page-turn.wav
https://remotion.media/switch.wav
https://remotion.media/mouse-click.wav
https://remotion.media/shutter-modern.wav
https://remotion.media/shutter-old.wav
```

---

## Section 8: B-Roll and Overlays

### B-Roll Duration Rules

| Content Type | B-Roll Clip Length |
|-------------|------------------|
| Fast social (TikTok/Reels) | 1-3 seconds |
| Educational / explainer | 3-7 seconds |
| Hard maximum (short-form) | 10 seconds |

**Timing rule:** B-roll appears the MOMENT you say the relevant word — not after the sentence ends.

**Meme/reaction inserts:** 1-2 seconds maximum, placed after the punchline only. Maximum 2 per video.

**Screen recordings:** Use L-cut (voice continues). Wrap in a phone or laptop frame mockup. Duration 3-10 seconds.

### B-Roll Sourcing Hierarchy (in order of impact)

1. Real footage CC shot — strongest authenticity signal, highest retention
2. Screen recordings of real results (Stripe dashboard, Skool analytics, live demos)
3. AI-generated contextual images via Fal.ai Flux Schnell — under 1 second, $0.003/image
4. Text overlays as visual substitute when no relevant footage exists

### Fal.ai Image Generation

```python
# pip install fal-client
import fal_client
import os

result = fal_client.subscribe(
    "fal-ai/flux/schnell",
    arguments={
        "prompt": "Professional iPhone-style photo, [description of scene matching video topic]",
        "image_size": "portrait_4_3",
        "num_inference_steps": 4,  # Schnell is 4-step model
    },
)
# result["images"][0]["url"] → download and overlay at timestamp
```

---

## Section 9: Cinematic Effects (FFmpeg)

```bash
# Vignette (standard):
vignette=PI/4

# Lens distortion (subtle barrel/pincushion):
lenscorrection=k1=-0.15:k2=-0.05

# Chromatic aberration (split RGB channels):
rgbashift=rh=-3:gh=0:bh=3

# Motion blur (frame blending):
tblend=all_mode=average

# Dynamic zoom push-in (subtle, Ken Burns-style):
scale=iw*1.05:-1,crop=iw/1.05:ih/1.05

# Ken Burns slow zoom (for still image B-roll, 250 frames):
zoompan=z='min(zoom+0.0015,1.5)':d=250:s=1080x1920:fps=25

# Film grain (luminance-masked, 35mm look):
# Layer 1: Generate grain noise
# Layer 2: Mask by luminance (grain less visible in blacks)
-filter_complex "[0:v]noise=alls=25:allf=t+u[grain];[0:v][grain]blend=c0_mode=overlay:c0_opacity=0.08[out]"

# Light leak overlay (requires light_leak.mp4 asset):
-filter_complex "[1:v]colorchannelmixer=aa=0.3[leak];[0:v][leak]blend=c0_mode=screen[out]"
```

### Morph Cut (Jump Cut Smoothing)

For jump cuts on talking-head footage where the background doesn't change:
```bash
# FFmpeg interpolation approximation:
minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc

# Better: RIFE Python model (Real-Time Intermediate Flow Estimation)
# pip install rife-ncnn-vulkan
# Produces true motion-interpolated frames between cuts
```

---

## Section 10: Auto-Reframing (Landscape to Portrait)

Landscape 16:9 → Portrait 9:16 (1080x1920) with tracked crop.

### Face Detection Pipeline

```python
# pip install mediapipe ultralytics deep-sort-realtime opencv-python numpy

import mediapipe as mp
import cv2
import numpy as np
from deep_sort_realtime.deepsort_tracker import DeepSort

# MediaPipe: production-grade, better than Haar cascades on iPhone footage
mp_face = mp.solutions.face_detection
tracker = DeepSort(max_age=30)

# Rule of thirds positioning: eyes at y=640px in 1080x1920
# Headroom: 15-20% of frame height above head top
TARGET_EYE_Y = 640
HEADROOM_RATIO = 0.175

def smooth_crop_coordinates(history: list, new_x: int, new_y: int, weight: float = 0.85) -> tuple:
    """Weighted moving average prevents jitter."""
    if not history:
        return new_x, new_y
    prev_x, prev_y = history[-1]
    return int(prev_x * weight + new_x * (1 - weight)), int(prev_y * weight + new_y * (1 - weight))
```

---

## Section 11: AI-Powered Pipeline Tools

| Stage | Tool | Install | Notes |
|-------|------|---------|-------|
| Transcription | WhisperX + large-v3-turbo | `pip install whisperx` | 6x faster than base Whisper, forced word alignment |
| Silence removal | auto-editor | `pip install auto-editor` | Pairs with WhisperX word gaps for filler detection |
| Filler detection | WhisperX word list scan | — | Scan for: "um", "uh", "like", "you know", "so", "basically", "literally" |
| Scene detection | PySceneDetect | `pip install scenedetect` | ContentDetector + librosa energy peaks |
| Highlight scoring | Claude API | — | Score transcript chunks for hook strength and virality potential |
| Caption styling | ASS subtitle format | — | Word-level with brand color highlights (see Section 4) |
| Audio pre-processing | noisereduce + pedalboard | `pip install noisereduce pedalboard` | Run before FFmpeg chain |
| B-roll generation | Fal.ai Flux Schnell | `pip install fal-client` | $0.003/image, <1 second |
| Face tracking | ultralytics + DeepSORT | `pip install ultralytics deep-sort-realtime` | Smooth portrait crop |

### WhisperX Transcription

```python
import whisperx
import torch

device = "cuda" if torch.cuda.is_available() else "cpu"
model = whisperx.load_model("large-v3-turbo", device, compute_type="float16")

audio = whisperx.load_audio("processed_audio.wav")
result = model.transcribe(audio, batch_size=16)

# Forced alignment — word-level timestamps
align_model, metadata = whisperx.load_align_model(
    language_code=result["language"], device=device
)
result = whisperx.align(result["segments"], align_model, metadata, audio, device)
# result["word_segments"] → [{word, start, end, score}, ...]
```

---

## Section 12: Lower Thirds

Specification for 1080x1920 portrait safe zone.

| Property | Value |
|----------|-------|
| Y position | 1704px (120px above safe zone bottom) |
| Name font size | 52-60px Bold Inter or Helvetica Neue |
| Title font size | 36-40px Regular or Medium weight |
| Name color | `#FFFFFF` |
| Title color | `#CCCCCC` |
| Text shadow | `0 2px 8px rgba(0,0,0,0.6)` |
| Background | `rgba(0,0,0,0.6)` or brand color at 80% opacity |
| Max lines | 2 |
| Max characters per line | 28 |

**Animation spec (Remotion spring):**
- Animate in: 18-24 frames, spring `{stiffness: 120, damping: 60}`
- Hold duration: minimum 3 seconds (90 frames at 30fps)
- Animate out: 12-18 frames ease-in

---

## Section 13: Motion Graphics (Remotion)

### Spring Physics Presets

```typescript
import { spring, useCurrentFrame, useVideoConfig } from "remotion";

const frame = useCurrentFrame();
const { fps } = useVideoConfig();

// Cinematic title entrance
const cinematicTitle = spring({ frame, fps, config: { mass: 1, damping: 80, stiffness: 100 } });

// Premium slide-in (card, panel)
const premiumSlide = spring({ frame, fps, config: { mass: 1, damping: 30, stiffness: 120 } });

// Lower third
const lowerThird = spring({ frame, fps, config: { mass: 0.8, damping: 60, stiffness: 150 } });

// Word pop (captions)
const wordPop = spring({ frame, fps, from: 0.8, to: 1.0,
  config: { mass: 0.5, damping: 40, stiffness: 200 } });

// Staggered children (index = item index in list)
const staggeredFrame = frame - (index * 4);
```

### 12 Animation Principles Encoded

| Principle | Implementation |
|-----------|---------------|
| Anticipation | Move 3-5px in the opposite direction for 4-6 frames before main movement |
| Follow-through | `overshootClamping: false`, allow 2-8% overshoot past target |
| Overlap | Stagger child elements by 4-8 frames each |
| Squash/stretch | Start `scaleX: 1.05, scaleY: 0.95`, spring to `1, 1` |
| Never over-animate | Maximum 3 properties animated simultaneously per element |

---

## Section 14: Production Workflow (15-Step Pipeline)

This runs in order, every time. No steps are optional.

```
1.  ENHANCE AUDIO       noisereduce + pedalboard pre-processing → processed_audio.wav
2.  TRANSCRIBE          WhisperX large-v3-turbo with forced alignment → word_segments.json
3.  DETECT FILLERS      Scan word_segments.json for: um, uh, like, you know, so, basically, literally
4.  REMOVE SILENCE      auto-editor --margin 0.2sec + manual filler word cuts → clean_cut.mp4
5.  GENERATE CAPTIONS   Build ASS file from word_segments (brand style or Hormozi)
6.  ADD ZOOM PUNCHES    librosa volume spike detection → insert zoom punch at top 5-8 energy peaks
7.  INSERT B-ROLL       Claude API scores transcript → Fal.ai generates images → overlay at mentions
8.  COLOR GRADE         Apply --grade preset via FFmpeg curves + eq + vignette
9.  MASTER AUDIO        Full FFmpeg chain: gate → highpass → lowpass → EQ → compand → loudnorm -14 LUFS
10. ADD SFX LAYER       Whoosh on transitions, pop on caption words, hit on zoom punches
11. RENDER LOWER THIRDS ASS event or Remotion overlay if lower third needed
12. ADD FILM GRAIN      Luminance-masked grain at 8% opacity + vignette PI/4
13. CHECK FIRST FRAME   Verify: face tight crop, high contrast, text overlay present, no dead eyes
14. EXPORT PER PLATFORM Trim duration, adjust aspect, set caption length per spec (table below)
15. SCHEDULE            Zernio API (scripts/late_tool.py) across all 6 platforms
```

### Platform Export Specifications

| Platform | Max Duration | Aspect | Resolution | Caption Max |
|----------|-------------|--------|------------|-------------|
| Instagram Reels | 90s | 9:16 | 1080x1920 | 2,200 chars |
| TikTok | 180s | 9:16 | 1080x1920 | 4,000 chars |
| YouTube Shorts | 60s | 9:16 | 1080x1920 | 5,000 chars |
| LinkedIn | 600s | 9:16 | 1080x1920 | 3,000 chars |
| Facebook | 240s | 9:16 | 1080x1920 | 63,206 chars |
| X/Twitter | 140s | 9:16 | 1080x1920 | 280 chars |

### FFmpeg Export Command (Base)

```bash
ffmpeg -i clean_cut.mp4 -i processed_audio.wav \
  -vf "[video_filters_from_steps_above]" \
  -af "[audio_filters_from_step_9]" \
  -c:v libx264 -crf 18 -preset slow \
  -c:a aac -b:a 192k -ar 48000 \
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 \
  -movflags +faststart \
  output_1080x1920.mp4
```

---

## Section 15: Quality Gate

Before delivering any output, verify all of the following:

**Hook:**
- [ ] First frame: tight crop, expression, eye contact, high contrast
- [ ] Text overlay present on frame 1 (max 7 words)
- [ ] First spoken word is the payload, not an intro

**Pacing:**
- [ ] No gap exceeding 15 seconds without visual or audio change
- [ ] Silence and filler words removed
- [ ] Cut rate matches video length tier (Section 2)

**Captions:**
- [ ] Word-by-word highlight active (not full sentence)
- [ ] Brand style applied (OASIS Blue or Hormozi depending on content)
- [ ] No captions in bottom 25% or top 15% of frame

**Audio:**
- [ ] Measures at -14 LUFS (or target per platform)
- [ ] True peak at or below -1.0 dBTP
- [ ] No clipping, no audible room noise, no breath artifacts

**Color:**
- [ ] Skin tones on vectorscope skin line
- [ ] Blacks slightly lifted for mobile viewing
- [ ] Export is Rec.709

**Output:**
- [ ] Duration within platform maximum
- [ ] Resolution 1080x1920
- [ ] File size under platform upload limit

---

## Obsidian Links
- [[skills/content-engine/SKILL]] | [[brain/CAPABILITIES]] | [[memory/content-strategy]]
- `memory/content_pipeline_vision.md` | [[skills/INDEX]]
