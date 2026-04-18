---
description: "Full content pipeline: raw video → edited with karaoke captions, AI images, thumbnail, platform captions → scheduled across all social media. Use when CC says 'make this a post' or uploads video/photos."
---

# Content Pipeline — Elite Video Production

CC uploads raw video. Run the full pipeline:

```bash
python ../CMO-Agent/scripts/content_pipeline.py process <video_path> [--topic "AI agents"] [--platforms instagram tiktok youtube_shorts linkedin]
```

## Individual Commands

```bash
# Transcribe with word-level timestamps
python ../CMO-Agent/scripts/content_pipeline.py transcribe <video>

# Generate karaoke captions from transcript
python ../CMO-Agent/scripts/content_pipeline.py caption <words.json>

# Generate thumbnail
python ../CMO-Agent/scripts/content_pipeline.py thumbnail <video> --text "Bold Title Here"

# Research competitor content
python ../CMO-Agent/scripts/content_pipeline.py research chase.h.ai

# Generate content ideas
python ../CMO-Agent/scripts/content_pipeline.py ideas --niche "AI automation" --count 10

# Generate AI image via Codex
python scripts/codex_image_gen.py generate "prompt" --style branded --output path.png
```

## Pipeline Flow
1. Whisper word-level transcription (audio-synced, not time-based)
2. Karaoke ASS captions (current word highlighted, others dimmed)
3. FFmpeg encode with captions, split-screen, transitions
4. Codex generates contextual overlay images
5. Thumbnail extracted + text overlay
6. Platform captions generated (IG/TikTok/YT/LinkedIn/FB/X)
7. Schedule via Zernio: `python scripts/late_tool.py create --text "<caption>" --media "<video>"`

## When CC Says "Make This a Post"
Run `process` with the uploaded file. No questions. Cinematic output.