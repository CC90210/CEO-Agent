---
tags: [knowledge, video, production, tools]
sources: [memory/MEMORY.md, ../CMO-Agent/scripts/content_pipeline.py, ../CMO-Agent/scripts/edit_content_v2.py, ../CMO-Agent/content-studio/]
last_updated: 2026-04-06
confidence: 0.93
---

# Video Production Bible — AI-Powered Editing Stack

> Complete reference for the open-source AI video pipeline. Know WHAT each tool does, HOW to install it, and WHEN to use it.
> [[knowledge/index]] | [[knowledge/wiki/tech-stack]] | [[knowledge/wiki/ai-automation-agency]]

## Quick Decision Matrix

| Task | Tool | Why |
|------|------|-----|
| Transcription (accuracy) | WhisperX large-v3-turbo | Word-level forced alignment |
| Transcription (speed) | faster-whisper | 4x faster, same accuracy |
| Noise removal (simple) | noisereduce | Spectral gating, no GPU needed |
| Noise removal (heavy) | pedalboard + Facebook denoiser | Reverb + complex environments |
| Silence removal | auto-editor | Loudness-aware, margin control |
| Scene detection | PySceneDetect | Frame diff or fade detection |
| Face reframing | MediaPipe → YOLOv8 | Fast → precise upgrade path |
| Captions | ASS format via FFmpeg | Full karaoke-style word animation |
| B-roll images | Fal.ai Flux Schnell | Sub-1s, $0.003/image |
| Motion graphics | Remotion 4.0.436 | Transparent overlay compositing |

---

## Transcription Stack

### WhisperX
```bash
pip install whisperx
```
- Forced alignment using wav2vec2 — word-level timestamps accurate to ~50ms
- Speaker diarization via pyannote.audio (requires HuggingFace token)
- Batch processing, significantly faster than openai-whisper at same quality
- **When to use:** Any production video where caption sync to speech is required

### faster-whisper
```bash
pip install faster-whisper
```
- CTranslate2 backend — 4x faster inference than openai-whisper, same WER
- Supports `int8`, `float16`, `float32` quantization — runs on CPU without GPU
- **When to use:** Fast drafts, batch transcription jobs, server environments without GPU

### Model Selection
| Model | Speed vs large-v3 | WER Penalty | Use Case |
|-------|------------------|-------------|----------|
| large-v3 | baseline | 0% | Max accuracy |
| large-v3-turbo | 6x faster | ~1% | **Default for production** |
| medium | 3x faster | ~5% | Quick drafts |
| small | 6x faster | ~10% | Real-time previews |

**Current system:** `openai-whisper small` — **UPGRADE TARGET: faster-whisper large-v3-turbo**

---

## Audio Enhancement Stack

### noisereduce
```bash
pip install noisereduce
```
- Spectral gating algorithm — works on stationary noise (AC hum, fan noise)
- Non-stationary mode handles varying background noise
- Pure Python, no GPU required
- **When to use:** Indoor recordings with consistent background noise

### pedalboard (Spotify)
```bash
pip install pedalboard
```
- VST/AU plugin wrapper — compression, EQ, gate, reverb in one library
- 300x faster than pySoX for audio processing chains
- **When to use:** Broadcast-quality voice polish (gate → EQ → compress → limiter chain)

```python
from pedalboard import Pedalboard, NoiseGate, Compressor, HighpassFilter, LowpassFilter
board = Pedalboard([
    NoiseGate(threshold_db=-30, ratio=1.5, release_ms=250),
    HighpassFilter(cutoff_frequency_hz=80),
    Compressor(threshold_db=-16, ratio=2.5),
    LowpassFilter(cutoff_frequency_hz=12000),
])
```

### Facebook Denoiser (facebookresearch/denoiser)
```bash
pip install denoiser
```
- DEMUCS-based speech enhancement — handles reverb and complex environments
- Real-time capable at 16kHz, handles speech separation
- **When to use:** Outdoor recordings, reverb-heavy rooms, phone audio

### SpeechBrain
```bash
pip install speechbrain
```
- Pre-trained enhancement models, MetricGAN+, SEGAN architectures
- Heaviest option — best quality for severely degraded audio
- **When to use:** Last resort for unusable audio that must be salvaged

---

## Scene Intelligence Stack

### PySceneDetect
```bash
pip install scenedetect
```
- `ContentDetector` — frame difference threshold (default: 27.0), fast
- `ThresholdDetector` — fade-to-black/white detection
- Outputs timestamps, scene images, or split video files
- **When to use:** Long-form video to find natural cut points before editing

```python
from scenedetect import detect, ContentDetector
scenes = detect('input.mp4', ContentDetector(threshold=27.0))
```

### librosa
```bash
pip install librosa
```
- Audio energy analysis — RMS envelope, spectral centroid, onset detection
- Beat tracking via dynamic programming beat estimator
- **When to use:** Cut to music beats, detect applause/laughter moments, energy-based highlight extraction

### Claude API — LLM Hook Scoring
- Score transcript chunks (30s windows) for hook strength and virality potential
- Prompt: extract the 3 most emotionally charged or surprising statements
- Rank by: novelty, emotional valence, curiosity gap, specificity
- **When to use:** Long-form content → identify the 60s clip worth posting

---

## Auto-Editing Stack

### auto-editor
```bash
pip install auto-editor
```
- Analyzes audio loudness to detect silence, removes it automatically
- `--margin 0.3sec` adds buffer before/after speech to prevent choppy cuts
- Supports EDL output for manual review before final encode
- **When to use:** Raw talking-head footage, podcast clips, removing dead air

```bash
auto-editor input.mp4 --margin 0.3sec -o output.mp4
```

### unsilence
```bash
pip install unsilence
```
- Simpler silence removal, better as a Python library import than CLI
- More scriptable for pipeline integration
- **When to use:** When auto-editor's output format doesn't fit pipeline needs

---

## Face Detection and Reframing

### MediaPipe
```bash
pip install mediapipe
```
- Google's face detection — normalized bounding box coordinates (0.0–1.0)
- Fast on iPhone footage, handles partial occlusion, multiple faces
- Returns `detection.location_data.relative_bounding_box`
- **When to use:** Standard portrait reframing for vertical 9:16 output

```python
import mediapipe as mp
face_detection = mp.solutions.face_detection.FaceDetection(min_detection_confidence=0.5)
```

### Ultralytics (YOLOv8/v11)
```bash
pip install ultralytics
```
- YOLOv8n: ~180-200 fps face detection on CPU
- Returns `boxes.xywhn` for normalized coordinates
- **When to use:** Upgrade from MediaPipe when accuracy matters more than simplicity

### DeepSORT (Temporal Tracking)
- Combines detection (MediaPipe/YOLO) with Kalman filter tracking
- Smooth crop box that follows face centroid across frames — prevents jitter
- **When to use:** Any video with head movement — prevents jarring crop repositioning

**Reframing Pipeline:**
```
Detect face (MediaPipe/YOLO) → Track centroid (DeepSORT) →
Smooth crop box (Kalman) → Apply via FFmpeg crop+scale filter
```

---

## Caption Generation

### @remotion/captions (npm)
```bash
npm install @remotion/captions
```
- Word timing data structure — `caption.words[].startMs`, `.endMs`, `.text`
- Powers TikTok-style page-based caption rendering
- Pairs with `@remotion/media-utils` for audio analysis

### beautiful-captions
```bash
pip install beautiful-captions
```
- FFmpeg-native ASS subtitle generation with custom fonts, colors, animations
- **When to use:** Pure FFmpeg pipeline without Remotion overhead

### ASS Format — Full Karaoke Capability
ASS (Advanced SubStation Alpha) supports per-word styling via override tags:

| Tag | Effect |
|-----|--------|
| `{\k50}` | Karaoke timing — 50 centiseconds per syllable |
| `{\c&H00FFFF&}` | Color change mid-line |
| `{\fscx120\fscy120}` | Scale word to 120% |
| `{\blur5}` | Gaussian blur on text |
| `{\fad(200,200)}` | Fade in/out 200ms |

**When to use:** Production captions with word-level highlight animation (current system default).

---

## Image Generation for B-Roll

### Fal.ai (Flux Schnell)
```bash
pip install fal-client
```
- Flux Schnell: sub-1 second per image, ~$0.003/image
- FLUX.2 Pro: highest quality photorealism, ~$0.05/image
- **When to use:** Default B-roll generation — fast and cheap enough for every video

```python
import fal_client
result = fal_client.subscribe("fal-ai/flux/schnell", arguments={"prompt": prompt})
image_url = result["images"][0]["url"]
```

### DALL-E 3
- Best for text-in-image (logos, signs, readable words in scene)
- ~$0.04/image via OpenAI API
- **When to use:** When generated image must contain readable text

### B-Roll Insertion Logic
- Bravo decides WHERE to insert (dead-air zones from PySceneDetect + librosa energy dips)
- Bravo decides WHAT to generate (topic extraction from transcript chunk)
- Insert duration: 2–4 seconds, overlaid at 70% opacity with cross-dissolve

---

## Video Intelligence Platforms (Reference Only)

These are competitor/reference platforms — not installed in the pipeline. Study their output for quality benchmarks.

| Platform | Core Capability | Key Metric |
|----------|----------------|------------|
| OpusClip | Long→short extraction, Virality Score | 0.93 mAP on highlights |
| Descript | Transcript-first editing, Overdub voice clone | — |
| Gling | YouTube bad-take/silence removal | — |
| AutoPod | Premiere multi-cam jump cuts | — |
| Vizard | Transcript highlight + auto-caption | — |
| reap.video | REST API + MCP: clip/caption/dub/b-roll | Has MCP server |

**reap.video note:** Has an MCP server — evaluate for pipeline integration if REST API coverage is sufficient.

---

## Cinematic Effects (FFmpeg 8.0.1)

FFmpeg binary: `C:\Users\User\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_...\bin\ffmpeg.exe`

### Film Grain (geq luminance-masked)
```bash
-vf "geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)+5*sin(2*PI*X/3+random(1)*2*PI)'"
```
Adds organic grain correlated to luminance — grain heavier in shadows, lighter in highlights.

### Vignette
```bash
-vf "vignette=PI/4"
```
Standard 45-degree vignette. Increase angle (toward PI/2) for heavier falloff.

### Lens Distortion
```bash
-vf "lenscorrection=cx=0.5:cy=0.5:k1=-0.15:k2=-0.05"
```
Subtle barrel distortion simulating 24mm lens character. Negative k1/k2 = barrel, positive = pincushion.

### Chromatic Aberration
```bash
-vf "rgbashift=rh=2:rv=0:bh=-2:bv=0"
```
Shifts red channel +2px right, blue channel -2px left. Subtle fringing on high-contrast edges.

### Motion Blur (tblend)
```bash
-vf "tblend=all_mode=average,framestep=2"
```
Blends adjacent frames — simulates 180-degree shutter. Use at 2x frame rate source.

### Light Leak Overlay
```bash
-filter_complex "[0:v][1:v]blend=all_mode=screen:all_opacity=0.3"
```
Requires a light leak video asset as second input. Screen blend mode at 30% opacity.

### Color Grading — Cinematic Teal-Orange
```bash
-vf "curves=r='0/0 0.5/0.45 1/0.9':g='0/0 0.5/0.5 1/1.0':b='0/0.05 0.5/0.55 1/0.85',eq=saturation=1.2:gamma=0.95"
```
Pushes shadows toward teal, highlights toward warm orange. Slight saturation boost.

### Ken Burns Zoom (zoompan)
```bash
-vf "zoompan=z='min(zoom+0.0015,1.5)':d=125:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080"
```
Slow zoom from 1.0x to 1.5x over 125 frames (at 25fps = 5 seconds). Center-anchored.

### Morph Cut Approximation (minterpolate)
```bash
-vf "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
```
Motion-compensated frame interpolation — smooths jump cuts between similar frames. Heavy CPU load.

### RIFE (Real-Time Intermediate Flow Estimation)
- Python-based, superior to FFmpeg minterpolate for morph cuts
- Install: `pip install rife-ncnn-vulkan` or use the `rife-ncnn-vulkan` binary
- Generates intermediate frames between any two frames using optical flow
- **When to use:** Clean jump cuts on talking-head footage where minterpolate artifacts

---

## Motion Graphics (Remotion 4.0.436)

**Architecture principle:** FFmpeg handles pixels (encode, color grade, effects). Remotion renders transparent RGBA overlay. FFmpeg composites final output.

```bash
npm install remotion @remotion/three @remotion/transitions @remotion/captions
```

### Spring Animation Presets
```typescript
import { spring } from 'remotion';

// Cinematic — slow, weighty, professional
spring({ fps, frame, config: { mass: 1.5, stiffness: 80, damping: 20 } })

// Premium — smooth, confident
spring({ fps, frame, config: { mass: 1, stiffness: 100, damping: 15 } })

// Snappy — energetic, TikTok-style
spring({ fps, frame, config: { mass: 0.5, stiffness: 200, damping: 12 } })

// Word pop — caption highlight bounce
spring({ fps, frame, config: { mass: 0.3, stiffness: 400, damping: 8 } })
```

### @remotion/three — 3D Elements
- Three.js inside Remotion compositions — `<ThreeCanvas>` wrapper
- Use for: floating product mockups, 3D text reveals, particle systems
- Renders frame-perfect at any resolution

### @remotion/transitions
| Transition | Effect | Use Case |
|-----------|--------|----------|
| `fade` | Opacity crossfade | Safe default |
| `slide` | Directional slide | Section changes |
| `wipe` | Hard edge wipe | Energetic cuts |
| `flip` | 3D card flip | Reveal moments |
| `clockWipe` | Radial wipe | Time-based content |

### @remotion/light-leaks
- `<LightLeak>` component — organic light burst overlays
- Parameters: `intensity`, `color`, `seed` (deterministic per seed value)
- Composites via `mix-blend-mode: screen`

### Overlay Compositing with FFmpeg
```bash
ffmpeg -i source.mp4 -i remotion_overlay.mov \
  -filter_complex "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p" \
  -c:v libx264 -crf 18 -preset slow output.mp4
```
Remotion output must be `.mov` with ProRes 4444 codec for alpha channel preservation.

---

## Existing Pipeline Files

| File | Purpose | Status |
|------|---------|--------|
| `../CMO-Agent/scripts/content_pipeline.py` | Master 7-phase orchestrator | Active |
| `../CMO-Agent/scripts/edit_content_v2.py` | Whisper + ASS captions + FFmpeg encode | Active |
| `scripts/transcribe.py` | Standalone Whisper wrapper | Active |
| `../CMO-Agent/scripts/codex_image_gen.py` (owned by Maven) | AI image generation (Fal.ai + DALL-E) | Active |
| `../CMO-Agent/scripts/render_video.py` | Remotion rendering bridge | Active |
| `../CMO-Agent/content-studio/src/compositions/OasisPromo.tsx` | OASIS brand composition | Active |
| `../CMO-Agent/content-studio/src/compositions/QuoteDrop.tsx` | Daily quote drop format | Active |
| `../CMO-Agent/content-studio/src/compositions/CeoLog.tsx` | CEO log talking-head format | Active |
| `../CMO-Agent/content-studio/src/compositions/SkoolIntro.tsx` | Skool community intro | Active |
| `../CMO-Agent/content-studio/.claude/rules/remotion/` | 30+ Remotion skill rules | Reference |

### Pipeline Phase Summary
1. **Ingest** — probe video metadata (resolution, fps, duration, audio channels)
2. **Transcribe** — Whisper → SRT/JSON with word timestamps
3. **Enhance audio** — noisereduce → pedalboard chain → normalize
4. **Scene detection** — PySceneDetect + librosa energy map
5. **Auto-edit** — auto-editor silence removal → LLM hook scoring → clip selection
6. **Render graphics** — Remotion overlay → Fal.ai B-roll → ASS captions
7. **Encode** — FFmpeg final pass (cinematic effects + overlay composite + encode)

---

## Upgrade Roadmap

| Current | Target | Benefit | Priority |
|---------|--------|---------|----------|
| openai-whisper small | faster-whisper large-v3-turbo | 6x faster, ~1% WER penalty | HIGH |
| No face tracking | MediaPipe + DeepSORT | Auto-reframe portrait | HIGH |
| Static captions | ASS karaoke word-highlight | TikTok-style animation | MEDIUM |
| No audio enhancement | pedalboard gate+compress chain | Broadcast voice quality | MEDIUM |
| No B-roll | Fal.ai Flux Schnell | Visual variety, retention | LOW |

## Obsidian Links
- [[knowledge/index]] | [[knowledge/wiki/tech-stack]]
- [[brain/CAPABILITIES]] | `memory/content_pipeline_vision.md`
- `../CMO-Agent/scripts/content_pipeline.py` | `../CMO-Agent/scripts/edit_content_v2.py`
