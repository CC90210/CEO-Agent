---
tags: [reference, tools, workflows]
---

# QUICK REFERENCE — CLI Tools, MCPs, Workflows, Skills

> Relocated from CLAUDE.md to keep token budget under 150 lines. Load this file when you need the full routing tables. All agents can @import this.

## CLI Tool Routing (Rule 2 Detail)

| CC Asks About | CLI Tool | Command |
|---|---|---|
| n8n workflows | `n8n_tool.py` | `python scripts/n8n_tool.py list`, `search <query>`, `execute <id>` |
| Social posts, scheduling | `late_tool.py` | `python scripts/late_tool.py accounts`, `create --text "..." --account <id>` |
| Database queries | `supabase_tool.py` | `python scripts/supabase_tool.py select <table> --project bravo --limit 10` |
| Payments, subscriptions | `stripe_tool.py` | `python scripts/stripe_tool.py balance`, `customers`, `invoices` |
| Website-to-CLI, API discovery | `opencli` | `opencli explore <url>`, `opencli list`, `opencli <platform> <cmd>` |
| Email (send/read/triage) | `google_tool.py` | `python scripts/google_tool.py gmail send --to "..." --subject "..." --body "..."`, `gmail list` |
| Calendar | `google_tool.py` | `python scripts/google_tool.py calendar list`, `calendar create --title "..." --start "..." --end "..."` |
| Google Drive / Sheets / Docs | `gws` CLI | `gws drive files list --params '{"pageSize":10}'`, `gws sheets spreadsheets get` |
| Scrape page data | Playwright CLI | `node .claude/skills/playwright/scripts/run.js <url> [--links] [--table css] [--selector css]` |
| Backend code, parallel tasks | Codex CLI | `node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" task --write "<task>"` |

## MCP Servers (Working — Stateless)

| MCP | Key Tools |
|---|---|
| Playwright | `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type` |
| Context7 | `resolve-library-id`, `query-docs` |
| Memory | `search_nodes`, `create_entities`, `open_nodes` |
| Sequential Thinking | `sequentialthinking` |

## System Maintenance CLIs

| Tool | Command | Purpose |
|---|---|---|
| Context compaction | `python scripts/context_manager.py compact` | Archive old SESSION_LOG entries |
| Cost tracking | `python scripts/cost_tracker.py summary` | Per-operation cost visibility |
| Memory aging | `python scripts/memory_aging.py scan` | Detect stale facts |
| Memory health | `python scripts/memory_aging.py health` | Letter-graded memory assessment |
| autoDream | `python scripts/auto_dream.py run` | Memory consolidation |
| Memory index | `python scripts/memory_index.py build` | Rebuild 3-layer memory index |
| Memory search | `python scripts/memory_index.py search "<query>"` | Search memory index |
| Codex health | `python scripts/codex_health.py` | Codex integration health check |

## Workflow Commands (`.agents/workflows/` + `.claude/skills/`)

| Command | Purpose |
|---|---|
| `/plan-feature` | Deep codebase analysis → implementation plan in `.agents/plans/` |
| `/execute` | Execute a plan step by step with validation gates |
| `/prime` | Load full project context and health report |
| `/commit` | Smart commit — `bravo: type — desc` format |
| `/create-prd` | Generate 15-section PRD for client projects |
| `/content` | Create platform-optimized content using CC's brand voice |
| `/post` | Publish to social media via Zernio (formerly Late) |
| `/research` | Multi-source research (OpenCLI + Playwright + Context7) |
| `/cli-anything` | Generate CLI wrapper for any software/API/service |
| `/opencli` | Explore websites, run prebuilt adapters, create website CLI adapters |
| `/skool-edit` | Edit a single Skool lesson or About page via Playwright |
| `/skool-push` | Batch push content to multiple Skool lessons from local files |
| `/review` | Pre-landing code review with Fix-First methodology |
| `/ship` | Full shipping pipeline: test → review → changelog → PR |
| `/retro` | Weekly retrospective with commit analysis and trend tracking |
| `/evolve` | Extract session patterns → promote to skills, SOPs, or CLAUDE.md rules |
| `/debug` | Systematic root-cause-first debugging |
| `/health` | Full system health check (MCP, memory, sync, workspace) |
| `/status` | Quick status report from memory files |
| `/client-health` | Client health scoring, churn alerts, retention actions |
| `/proposal` | Generate client proposals and SOWs from templates |
| `/strategic-review` | Quarterly strategic review (revenue, pipeline, competitive, OKRs) |
| `/competitive-report` | Monthly competitor monitoring and battlecard updates |
| `/qbr` | Full quarterly business review with OKR grading |
| `/onboard-team-member` | Contractor/team member onboarding workflow |
| `/meeting-prep` | Pre-meeting briefs and post-meeting action capture |
| `/investor-update` | Monthly investor/stakeholder update email |
| `/knowledge-maintenance` | Weekly knowledge system maintenance and cleanup |
| `/financial-model` | Unit economics, forecasting, scenario modeling |
| `/briefing` | Daily CEO morning briefing |
| `/content-pipeline` | Full video production: raw → edited + captions + thumbnail + scheduled |
| `/codex:setup` | Check Codex CLI readiness |
| `/codex:review` | Codex code review (second AI opinion) |
| `/codex:adversarial-review` | Codex challenge review (questions design decisions) |
| `/codex:rescue` | Delegate task to Codex (debug, fix, implement) |
| `/codex:status` | Show active/recent Codex background jobs |
| `/codex:result` | Get completed Codex job output |
| `/codex:cancel` | Cancel active Codex background job |

## Skills Quick Reference

All skills: `skills/[skill-name]/SKILL.md`. Read on demand — not at boot.

| Skill | When to Load |
|---|---|
| `systematic-debugging` | Bug reports, error investigation |
| `self-healing` | Session end, system health checks |
| `test-driven-development` | Writing tests, new features |
| `browser-automation` | Playwright tasks |
| `e2e-testing` | Full app testing |
| `writing-plans` | COMPLEX+ features |
| `executing-plans` | Implementing plans |
| `sop-breakdown` | Process creation |
| `memory-management` | Memory cleanup |
| `mcp-operations` | Tool troubleshooting |
| `skool-automation` | Skool content editing |
| `code-review` | Pre-ship review |
| `ship` | Deployment pipeline |
| `retro` | Weekly retrospective |
| `task-routing` | COMPLEX+ task assignment |
| `anti-drift` | Multi-agent tasks |
| `sparc-methodology` | COMPLEX+ implementation |
| `agent-permissions` | Access control checks |
| `hooks-automation` | Hook configuration |
| `background-workers` | System maintenance |
| `context-optimization` | Performance tuning |
| `codex-delegation` | Codex delegation decisions |
| `security-protocol` | Credential and input validation |
| `cli-anything` | Generate CLI wrappers |
| `opencli` | Website-to-CLI automation |

## Codex Companion Quick Commands

```bash
export CLAUDE_PLUGIN_ROOT="/c/Users/User/.claude/codex-plugin"
node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" task --write "<context + task>"
node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" review
node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" adversarial-review "<focus>"
node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" status
node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" result
```

## Obsidian Links
- [[CLAUDE]] | [[brain/CAPABILITIES]] | [[brain/AGENTS]] | [[brain/STATE]]
- [[skills/codex-delegation/SKILL]] | [[skills/mcp-operations/SKILL]]
