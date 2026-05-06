---
tags: [memory, persistent]
last_updated: 2026-03-26
freshness_threshold_days: 90
---
# LONG-TERM MEMORY — High-Confidence Persistent Facts

> Only facts with confidence >= 0.8 belong here. Reviewed quarterly (90-day threshold — this file is meant to be slow-moving).
>
> ⚠️ **Per-entry freshness still applies.** Each entry has its own date — `memory_aging.py` decays confidence per-entry by category (business 0.02/day, technical 0.015/day, architectural 0.005/day). Even within this file, an entry > 90 days without re-verification is suspect. Run `python scripts/memory_aging.py stale --days 30` before quoting business facts.
>
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
| OASIS AI Solutions at ~$2,982 USD/mo Net MRR ($191 base + $2,500 primary retainer flat + $291 rev share). Target: $5K USD by May 15, 2026. | 0.95 | STATE.md verified | 2026-03-26 |
| CC's partner Adon handles content + client relations | 0.90 | CC stated | 2026-02-26 |
| PropFlow is pre-revenue, in active development | 0.85 | CC stated | 2026-02-26 |
| CC works weekends at Nicky's Donuts | 0.90 | CC stated | 2026-02-26 |
| **Content Strategy:** Wednesday is "Content Day". CC uploads batch video/files, Agent schedules 1 piece/day across all channels via Late. | 0.95 | CC stated | 2026-03-05 |
| primary retainer is 94% of revenue — diversification is critical risk #1 | 0.95 | STATE.md, ACTIVE_TASKS.md | 2026-03-26 |
| Atlas (CFO agent) manages trading ($136 Kraken), tax filing, FIRE planning at C:\Users\User\APPS\trading-agent | 0.95 | CLAUDE.md cross-ref established | 2026-03-26 |
| CC Funnel live at cc-funnel.vercel.app — lead capture → Supabase → Telegram notify | 0.90 | Deployed 2026-03-24 | 2026-03-24 |
| primary retainer relationship is friend-based, no formal contract. $2,500/mo flat + 15% rev share on Skool community MRR. He outsources a lot of work to CC. | 0.95 | CC stated 2026-03-26 | 2026-03-26 |
| primary retainer coaching referral: 2 companies (tugboat + real estate) want coaching on AI/automation systems. $5,000 each, 16 sessions total, 1hr/session. $10K upfront cash opportunity. | 0.95 | CC stated 2026-03-26 | 2026-03-26 |
| Adon is 50-50 partner on PropFlow only. CC owns 100% of OASIS AI. Adon's role: networking, connections, marketing. Technically 3-4 months behind CC. | 0.95 | CC stated 2026-03-26 | 2026-03-26 |
| CC's #1 priority is CONTENT CREATION for personal brand (Conaugh McKenna) to build inbound funnel. Content → leads → sales. | 0.95 | CC stated 2026-03-26 | 2026-03-26 |
| CC's role: content creation, marketing, sales, face-to-face. Everything else = Bravo handles autonomously. | 0.95 | CC stated 2026-03-26 | 2026-03-26 |
| Monthly overhead: ~$184 USD (Claude $140, Supabase $25, Hostinger/n8n $14, ElevenLabs ~$5 maybe cancelled) | 0.90 | CC stated 2026-03-26 | 2026-03-26 |
| Cedarwood and Vortex leads are effectively dead. CC wants to start fresh with inbound funnel approach. | 0.85 | CC stated 2026-03-26 | 2026-03-26 |

## Technical Facts

| Fact | Confidence | Source | Last Verified |
|------|-----------|--------|---------------|
| n8n instance: https://n8n.srv993801.hstgr.cloud | 0.90 | Config file | 2026-02-27 |
| 47 n8n workflows on Hostinger VPS. CLI tool (n8n_tool.py) for full CRUD. MCP uses community package. | 0.90 | n8n_tool.py list verified | 2026-03-26 |
| Telegram bot V11.0 (telegram_agent.js) — full-context parity, loads CLAUDE.md + brain files, 25 max turns | 0.95 | Rewritten 2026-03-26 | 2026-03-26 |
| Gemini CLI entry point: GEMINI.md (V5.4), has MCP access to Supabase, Playwright, n8n, Late, Seq Thinking | 0.90 | Read GEMINI.md | 2026-03-01 |
| Zernio (formerly Late) API works via raw HTTP. Base URL: https://zernio.com/api/v1/. 8 accounts connected. Rebranded 2026-03-26. | 0.95 | Both URLs verified, code updated | 2026-03-26 |
| __future__ imports must be absolute first line in Python files | 0.95 | Mistake encountered + fixed | 2026-02-27 |

## Confidence Decay Rules

- Facts not re-verified in 30 days: confidence -= 0.1
- Facts not re-verified in 90 days: confidence -= 0.3 (review for removal)
- Facts contradicted by new evidence: immediately flag and update
- Facts confirmed by new evidence: confidence += 0.05 (cap at 1.0)

*Last updated: 2026-03-26*
