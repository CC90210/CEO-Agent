---
description: Research a topic using Playwright browser and Context7 docs
---

## Steps

1. Determine what CC wants to research.

2. If it's a **library/framework** question:
   - `mcp_context7_resolve-library-id` to find the library
   - `mcp_context7_query-docs` with the specific question
   - Summarize findings for CC

3. If it's a **web research** question:
   - Use `search_web` for initial results
   - Use Playwright `browser_navigate` + `browser_snapshot` to read specific pages
   - Extract relevant information and summarize

4. If it's **competitive intelligence**:
   - Browse competitor sites via Playwright
   - Capture key data points: pricing, features, messaging
   - Present findings in a comparison table

5. Save key findings to Memory knowledge graph:
   - `mcp_memory_create_entities` for new topics
   - `mcp_memory_add_observations` for updates to existing topics
