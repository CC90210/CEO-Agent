---
name: research
description: Deep research on any topic using OpenCLI (social platforms), Playwright (web browsing), and Context7 (library docs). Returns distilled findings, not raw data.
user-invocable: true
---

# /research — Multi-Source Research

## Steps

1. Determine the research type:
   - **Library/API docs** → Context7 MCP (`resolve-library-id` → `query-docs`)
   - **Social/platform data** → OpenCLI (`opencli <platform> search --json`)
   - **Website analysis** → Playwright (`browser_navigate` → `browser_snapshot`)
   - **Market/competitor** → Combine OpenCLI + Playwright

2. For library/API questions:
   - `resolve-library-id` to find the library
   - `query-docs` with specific topic
   - Max 3 Context7 calls per question

3. For platform/social media questions:
   - `opencli twitter search "<query>" --json`
   - `opencli reddit search "<query>" --subreddit <sub> --json`
   - `opencli hackernews search "<query>" --json`

4. For website/competitor analysis:
   - `opencli explore <url>` for API discovery
   - Playwright for visual analysis and data extraction

5. Distill findings into actionable summary. Never dump raw HTML or JSON to CC.

## Related

- [[.claude/skills/INDEX]]
- [[.claude/skills/codex-adversarial-review]]
- [[.claude/skills/codex-cancel]]
