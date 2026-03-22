---
description: Research a topic using Playwright browser and Context7 docs
---

## Steps

1. Determine what CC wants to research.

2. If it's a **library/framework** question:
   - `mcp_context7_resolve-library-id` to find the library
   - `mcp_context7_query-docs` with the specific question
   - Summarize findings for CC

3. If it's a **platform/social media** question (use OpenCLI first — faster, structured):
   - `opencli twitter search "<topic>" --json` — trending conversations
   - `opencli reddit search "<topic>" --json` — community discussions
   - `opencli hackernews top --json` — tech/AI trends
   - `opencli youtube search "<topic>" --json` — video content landscape
   - `opencli arxiv search "<topic>" --json` — academic research
   - If platform has an OpenCLI adapter (`opencli list`), use it before Playwright

4. If it's a **web research** question (no OpenCLI adapter):
   - Use Playwright `browser_navigate` + `browser_snapshot` to read specific pages
   - Extract relevant information and summarize
   - Consider `opencli explore <url>` to discover the site's API for future use

5. If it's **competitive intelligence**:
   - Use OpenCLI to check competitor social presence first
   - Browse competitor sites via Playwright for pricing, features, messaging
   - Present findings in a comparison table

6. Save key findings to Memory knowledge graph:
   - `mcp_memory_create_entities` for new topics
   - `mcp_memory_add_observations` for updates to existing topics
