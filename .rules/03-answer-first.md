---
description: Always answer CC's question first, never dump reports or boot sequences
---

# Answer First, Act Second

When CC asks a question:
1. **Answer it** using MCP tools or file reads. 1-5 sentences max.
2. Then take action if needed.

**NEVER:**
- Dump boot sequences, brain state, or file contents as output
- Write audit reports instead of fixing the actual problem
- Describe what you WOULD do — just DO it
- Use `curl` when an MCP tool exists
- Create Python/JS scripts to replace MCP tools

If an MCP tool fails: report the error in ONE sentence, stop, suggest checking `.env.agents` or restarting IDE.

## Obsidian Links
- [[.rules/INDEX]] | [[brain/INTERACTION_PROTOCOL]]


## Related (graph)

- [[.rules/INDEX]]
- [[.rules/01-identity]]
- [[.rules/02-cross-ai-context]]
- [[.rules/04-mcp-routing]]
