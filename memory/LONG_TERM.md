---
tags: [memory, persistent]
---
# LONG-TERM MEMORY — High-Confidence Persistent Facts

> Only facts with confidence >= 0.8 belong here. Reviewed quarterly. Decayed facts get demoted or removed.

> [[brain/BRAIN_LOOP]] | [[memory/PATTERNS]] | [[brain/STATE]]

## Architecture Facts

| Fact | Confidence | Source | Last Verified |
|------|-----------|--------|---------------|
| Bravo uses 3-tier agent architecture: Claude Code (Opus), Gemini CLI, Antigravity IDE | 0.95 | Implemented 2026-02-27, updated 2026-03-14 | 2026-03-14 |
| All agents share entry points, brain/, memory/, .env.agents | 0.95 | Confirmed across 3 sessions | 2026-02-28 |
| Late MCP profileId returns dict not str — requires Pydantic patch in uv cache | 0.85 | Debugged and patched 2026-02-27 | 2026-02-27 |
| Supabase MCP for Claude Code: use npx @supabase/mcp-server-supabase in .claude/mcp.json (not HTTP plugin) | 0.95 | Fixed 2026-02-28, matches Anti-Gravity pattern | 2026-02-28 |
| Supabase projects: Bravo (agent DB), nostalgic-requests, oasis-ai-platform — all us-west-2 | 0.95 | Confirmed via Anti-Gravity MCP | 2026-02-28 |
| Supabase orgs: CC (oktipozhyojufxsytrse), oasis-ai-platform (sajanpiqysuwviucycjh) | 0.95 | Confirmed via Anti-Gravity MCP | 2026-02-28 |
| PowerShell `>` redirection produces UTF-16LE which breaks Node parsers | 0.95 | Encountered and documented | 2026-02-27 |
| X/Twitter has 280 character limit (including spaces, URLs, mentions) | 0.95 | API rejection confirmed | 2026-02-27 |

## Business Facts

| Fact | Confidence | Source | Last Verified |
|------|-----------|--------|---------------|
| OASIS AI Solutions currently at ~$250/mo revenue (target: $8-12K MRR). More invested than returned so far. | 0.95 | CC corrected 2026-03-01 | 2026-03-01 |
| CC's partner Adon handles content + client relations | 0.90 | CC stated | 2026-02-26 |
| PropFlow is pre-revenue, in active development | 0.85 | CC stated | 2026-02-26 |
| CC works weekends at Nicky's Donuts | 0.90 | CC stated | 2026-02-26 |
| **Content Strategy:** Wednesday is "Content Day". CC uploads batch video/files, Agent schedules 1 piece/day across all channels via Late. | 0.95 | CC stated | 2026-03-05 |

## Technical Facts

| Fact | Confidence | Source | Last Verified |
|------|-----------|--------|---------------|
| n8n instance: https://n8n.srv993801.hstgr.cloud | 0.90 | Config file | 2026-02-27 |
| 0 n8n workflows currently exposed to MCP | 0.85 | Verified via MCP | 2026-02-27 |
| Telegram bot (telegram_agent.js) routes to Gemini CLI + Claude Code | 0.95 | Verified source code V5.4 | 2026-03-01 |
| Gemini CLI entry point: GEMINI.md (V5.4), has MCP access to Supabase, Playwright, n8n, Late, Seq Thinking | 0.90 | Read GEMINI.md | 2026-03-01 |
| Late MCP requires LATE_API_KEY env var — currently missing from .env.agents | 0.95 | Tested via Claude Code MCP | 2026-03-01 |
| __future__ imports must be absolute first line in Python files | 0.95 | Mistake encountered + fixed | 2026-02-27 |

## Confidence Decay Rules

- Facts not re-verified in 30 days: confidence -= 0.1
- Facts not re-verified in 90 days: confidence -= 0.3 (review for removal)
- Facts contradicted by new evidence: immediately flag and update
- Facts confirmed by new evidence: confidence += 0.05 (cap at 1.0)
