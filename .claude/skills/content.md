---
name: content
description: Create platform-optimized content using CC's brand voice and 5 pillars (Builder, Outsider, DJ, Transformer, Hustler). Checks trends before writing.
user-invocable: true
---

# /content — Brand Content Creation

## Steps

1. Ask CC for the topic/angle, or pick from current priorities in `brain/STATE.md`.

2. **Trend check** (before writing — find timely hooks):
   - `opencli twitter trending --json` — what's hot on X right now
   - `opencli reddit hot --subreddit smallbusiness --json` — what business owners are discussing
   - `opencli hackernews top --json` — AI/tech trends for Builder pillar

3. Load brand context:
   - Read `brain/USER.md` for CC's profile
   - Read `APPS_CONTEXT/CONTENT_BRAND_CLAUDE.md` for brand pillars

4. Ask CC which platform(s): X, LinkedIn, Instagram, Threads, TikTok, YouTube.

5. Draft content following platform rules:
   - **X/Twitter** (280 chars): Punchy, hook-first, no hashtags unless strategic
   - **LinkedIn** (3000 chars): Professional but authentic, story-driven, CTA at end
   - **Instagram** (2200 chars): Visual-first caption, hashtags at bottom
   - **Threads** (500 chars): Conversational, opinion-driven
   - **TikTok** (4000 chars): Trendy, casual, hook in first line

6. Present draft to CC for approval. Iterate if needed.

7. Once approved, run `/post` to publish.
