---
description: Create platform-optimized content using CC's brand voice and 5 pillars
---

## Steps

1. Ask CC for the topic/angle, or pick from current priorities in `brain/STATE.md`.

2. **Trend check** (before writing — find timely hooks):
   - `opencli twitter trending --json` — what's hot on X right now
   - `opencli reddit hot --subreddit smallbusiness --json` — what business owners are discussing
   - `opencli hackernews top --json` — AI/tech trends for Builder pillar
   - Use trending topics to inform the hook and angle

3. Load brand context:
   - Read `brain/USER.md` for CC's profile
   - Read `APPS_CONTEXT/CONTENT_BRAND_CLAUDE.md` for brand pillars
   - CC's 5 pillars: Builder, Outsider, DJ, Transformer, Hustler

4. Ask CC which platform(s): X, LinkedIn, Instagram, Threads, TikTok, YouTube.

5. Draft the content following platform rules:
   - **X/Twitter** (280 chars): Punchy, hook-first, no hashtags unless strategic
   - **LinkedIn** (3000 chars): Professional but authentic, story-driven, CTA at end
   - **Instagram** (2200 chars): Visual-first caption, hashtags at bottom, emoji-light
   - **Threads** (500 chars): Conversational, opinion-driven
   - **TikTok** (4000 chars): Trendy, casual, hook in first line
   - **YouTube** (title + description): SEO-optimized title, keyword-rich description

6. Present draft to CC for approval. Iterate if needed.

7. Once approved, run `/post` workflow to publish.

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/CAPABILITIES]]
