---
tags: [reference, tools, routing]
---

# QUICK REFERENCE — Complete Tool Routing

> CLAUDE.md Rule 2 points here. When CC asks for ANYTHING, find the right tool below.
> **Pattern:** CLI-first (reads .env.agents, never breaks). MCP only for stateless tools.
> **Deep reference:** @brain/CAPABILITIES.md (480 lines — full commands, schemas, config)

## Routing by Intent

### Communication & Scheduling
| CC Says | Tool | Command |
|---------|------|---------|
| **ANY autonomous outbound** (email/DM/call on CC's behalf) | **`send_gateway.py`** | `send --channel email --agent-source <engine> --to ... --subject ... --body ...`  `can-act --lead-id <id> --channel email`  `history --lead-id <id>`  `stats`  — CASL + cooldown + daily cap enforced architecturally |
| Relationship context for LLM drafting | `context_builder.py` | `show --lead-id <id>` / `--email <addr>`  `relationship-map --limit 30` |
| Apply a DB migration | `apply_migration.py` | `<path/to/migration.sql>` `--dry-run` `--json` |
| Send email / reply / check inbox | `google_tool.py` | `gmail send --to "..." --subject "..." --body "..."`, `gmail list`, `gmail read <id>` |
| Email sequences / nurture / templates | `email_engine.py` | `send-template`, `sequence run`, `templates list` (routes through send_gateway) |
| Create/check calendar events | `google_tool.py` | `calendar list`, `calendar create --title "..." --start "..." --end "..." [--meet] [--attendees "..."]` |
| Book meeting / manage slots | `booking_engine.py` | `slots open`, `book`, `available`, `remind` |
| Create/share a Google Doc | `google_tool.py` | `docs create --title "..." [--html file.html]`, `docs read <id>`, `docs export <id> --format pdf` |
| Create/read/write spreadsheet | `google_tool.py` | `sheets create --title "..."`, `sheets read <id>`, `sheets write <id> --range "A1" --values "..."`, `sheets append <id> --values "..."` |
| Create presentation / export deck | `google_tool.py` | `slides create --title "..."`, `slides read <id>`, `slides export <id> --format pdf` |
| Upload/download/share files | `google_tool.py` | `drive upload --file "..."`, `drive download <id>`, `drive share <id> --email "..."`, `drive list` |
| Google Tasks | `google_tool.py` | `tasks list`, `tasks add --list-id <id> --title "..."`, `tasks complete --list-id <id> --task-id <id>` |
| Deep research / podcast / study guide | `notebooklm_tool.py` | `ask "..."`, `generate audio`, `source add <url>`, `create --title "..."` |
| Telegram notification | `notify.py` | `send "message"` |

### Social Media & Content
| CC Says | Tool | Command |
|---------|------|---------|
| Post to social media | `late_tool.py` | `create --text "..." --account <id>`, `cross-post` |
| Content calendar / planning | `content_engine.py` | `calendar`, `create`, `week-plan`, `due` |
| "Make this a post" / content pipeline | `content_pipeline.py` | `process <video>`, `transcribe`, `caption`, `thumbnail` |
| Repurpose content across platforms | `content_repurposer.py` | Transforms content via Claude API |
| Generate AI images | `codex_image_gen.py` | `generate "<prompt>" --style branded` |
| Skool community management | `skool_engine.py` | `daemon`, `scan-posts`, `engage-members` |
| Instagram engagement | `instagram_engine.py` | `daemon`, `check-dms`, `auto-reply` |
| LinkedIn outreach | `linkedin_cli.py` | `search`, `connect`, `message` |

### Sales & CRM
| CC Says | Tool | Command |
|---------|------|---------|
| Leads / pipeline / CRM | `lead_engine.py` | `list`, `add`, `score`, `pipeline`, `followups`, `funnel` |
| Client health / churn risk | `client_health.py` | `report`, `score <client>`, `alerts`, `trends` |
| Generate proposal / SOW | `proposal_generator.py` | `generate`, `list-templates`, `export` |
| Competitive analysis / battlecards | `competitive_intel.py` | `add`, `battlecard`, `report`, `matrix` |
| Scrape leads from Google Maps | `scrape_maps_emails.py` | Maps business data + email extraction |

### Revenue & Finance
| CC Says | Tool | Command |
|---------|------|---------|
| MRR / revenue / dashboard | `revenue_engine.py` | `mrr`, `dashboard`, `sync-stripe`, `forecast`, `goal` |
| Stripe (balance, invoices, subs) | `stripe_tool.py` | `balance`, `customers`, `invoices`, `subscriptions`, `payment-links` |
| Financial modeling / unit economics | `financial_model.py` | `unit-economics`, `forecast`, `scenario`, `runway` |
| CEO briefing / KPIs | `ceo_dashboard.py` | `briefing`, `revenue`, `pipeline`, `full` |

### Database & Infrastructure
| CC Says | Tool | Command |
|---------|------|---------|
| Supabase query / CRUD | `supabase_tool.py` | `select <table> --project bravo`, `insert`, `update`, `query` |
| n8n workflows | `n8n_tool.py` | `list`, `search`, `execute <id>`, `stats` |
| Web scraping (data extraction) | `firecrawl_tool.py` | `scrape <url>`, `search <query>`, `crawl`, `extract` |
| Web automation (clicks, forms) | Playwright MCP | `browser_navigate`, `browser_click`, `browser_type` |
| Cron jobs / scheduled tasks | `cron_engine.py` | `list`, `add`, `run`, `due`, `seed` |
| Funnel sync (GoHighLevel) | `funnel_sync.py` | Sync funnels to GHL |

### Knowledge & Memory
| CC Says | Tool | Command |
|---------|------|---------|
| Library docs lookup | Context7 MCP | `resolve-library-id`, `query-docs` |
| Persistent knowledge graph | Memory MCP | `search_nodes`, `create_entities` |
| Obsidian vault graph queries | Knowledge Graph MCP | `kg_search`, `kg_central`, `kg_paths`, `kg_communities` |
| Semantic memory (fuzzy search) | `mem0_tool.py` | `add`, `search`, `list`, `stats` |
| Compile doc into knowledge wiki | `/ingest` workflow | `knowledge/` directory |
| Query compiled knowledge | `/query-knowledge` workflow | Sourced answers from wiki |

### System Maintenance
| CC Says | Tool | Command |
|---------|------|---------|
| Context tier loading | `context_manager.py` | `tier "<query>"`, `compact`, `health` |
| Cost tracking | `cost_tracker.py` | `log --label X`, `summary`, `budget --check` |
| Stale memory detection | `memory_aging.py` | `scan`, `stale`, `health`, `archive` |
| Memory consolidation | `auto_dream.py` | `run [--dry-run]`, `status` |
| Memory index rebuild | `memory_index.py` | `build`, `search "<query>"`, `stats` |
| Codex health check | `codex_health.py` | `[--json]` |

### Backend / Codex Delegation
| CC Says | Tool | Command |
|---------|------|---------|
| Backend implementation / deep debug | Codex CLI | `node "$CLAUDE_PLUGIN_ROOT/scripts/codex-companion.mjs" task --write "<task>"` |
| Code review (second opinion) | Codex CLI | `codex-companion.mjs review` |
| Adversarial review | Codex CLI | `codex-companion.mjs adversarial-review "<focus>"` |

## Routing Priority Rules

When multiple tools could handle a request, use this precedence:

1. **One-off email** → `google_tool.py` | **Email sequence/template** → `email_engine.py`
2. **One-off web page** → Playwright MCP | **Data extraction at scale** → `firecrawl_tool.py`
3. **Quick post** → `late_tool.py` | **Full content pipeline** → `content_pipeline.py`
4. **Simple DB query** → `supabase_tool.py` | **Business metrics** → `revenue_engine.py` or `ceo_dashboard.py`
5. **Structured memory** → markdown files | **Fuzzy recall** → `mem0_tool.py`

## MCP Servers (7 Active — Stateless Only)

| MCP | Purpose | Notes |
|-----|---------|-------|
| Playwright | Browser automation | Interactive: clicks, forms, screenshots |
| Context7 | Library documentation | Live docs for any framework |
| Memory | Knowledge graph | Cross-session persistent entities |
| Sequential Thinking | Multi-step reasoning | Complex problem decomposition |
| Knowledge Graph | Obsidian vault queries | PageRank, communities, paths |
| GitHub | PR/issue management | Via wrapper script (.cmd) |
| Firecrawl | Web scraping | Via wrapper script (.cmd) |

**NEVER use claude.ai MCP connectors (Gmail, Google Calendar, Square, Cloudflare).** Always use CLI tools.

## `--json` Flag Convention

Most tools accept `--json` BEFORE the subcommand: `python scripts/tool.py --json subcommand`
Exceptions (accept after): `stripe_tool.py`, `n8n_tool.py`, `firecrawl_tool.py`, `revenue_engine.py`, `ceo_dashboard.py`

## All CLI Tools (47 — prefix: `python scripts/`)

| Script | Category | Type |
|--------|----------|------|
| **--- Communication & GWS ---** | | |
| `google_tool.py` | Gmail, Calendar, Drive, Sheets, Docs | CLI tool |
| `email_engine.py` | Email sequences, SMTP, templates | CLI tool |
| `booking_engine.py` | Scheduling / slots | CLI tool |
| `notify.py` | Telegram notifications | Library (import) |
| **--- Sales & CRM ---** | | |
| `lead_engine.py` | CRM, pipeline, scoring | CLI tool |
| `client_health.py` | Client health scoring | CLI tool |
| `proposal_generator.py` | Proposals / SOWs | CLI tool |
| `competitive_intel.py` | Competitor tracking, battlecards | CLI tool |
| `outreach_engine.py` | Outreach campaign automation | CLI tool |
| `scrape_maps_emails.py` | Google Maps lead scraping | Script (no --help) |
| **--- Revenue & Finance ---** | | |
| `revenue_engine.py` | MRR tracking, Stripe sync | CLI tool |
| `stripe_tool.py` | Payments, invoices, subscriptions | CLI tool |
| `financial_model.py` | Unit economics, forecasting | CLI tool |
| `ceo_dashboard.py` | KPI aggregator, briefings | CLI tool |
| **--- Content & Social ---** | | |
| `late_tool.py` | Social posting (Zernio) | CLI tool |
| `content_engine.py` | Content calendar, planning | CLI tool |
| `content_pipeline.py` | Video production (master) | CLI tool |
| `content_repurposer.py` | Cross-platform content | CLI tool |
| `content_generator.py` | Claude API content generation | CLI tool |
| `codex_image_gen.py` | AI image generation | CLI tool |
| `generate_covers.py` | Cover art generation | Script |
| `edit_content_v2.py` | Whisper transcription + captions | CLI tool |
| `render_video.py` | Remotion video rendering | Script |
| `transcribe.py` | Whisper audio transcription | Script |
| **--- Platform Automation ---** | | |
| `skool_engine.py` | Skool community automation | Daemon |
| `skool_watchdog.py` | Skool monitoring | Daemon |
| `instagram_engine.py` | Instagram DM/engagement | Daemon |
| `linkedin_cli.py` | LinkedIn outreach | CLI tool |
| **--- Infrastructure ---** | | |
| `supabase_tool.py` | Database CRUD (3 projects) | CLI tool |
| `n8n_tool.py` | Workflow automation | CLI tool |
| `firecrawl_tool.py` | Web scraping, extraction | CLI tool |
| `mem0_tool.py` | Semantic memory | CLI tool |
| `cron_engine.py` | Scheduled jobs | CLI tool |
| `funnel_sync.py` | GoHighLevel sync | CLI tool |
| `funnel_nurture.py` | Nurture sequences | CLI tool |
| **--- System Maintenance ---** | | |
| `context_manager.py` | Context tier loading, compaction | CLI tool |
| `cost_tracker.py` | Per-operation cost tracking | CLI tool |
| `memory_aging.py` | Memory health, stale detection | CLI tool |
| `auto_dream.py` | Memory consolidation | CLI tool |
| `memory_index.py` | 3-layer memory indexing | CLI tool |
| `codex_health.py` | Codex integration diagnostics | CLI tool |
| `scheduler.py` | Task scheduling | Daemon |
| **--- System Control ---** | | |
| `windows_control.py` | Windows system automation (90+ cmds) | CLI tool |
| `macos_control.py` | macOS system automation | CLI tool |
| `music_control.py` | Audio/music control | CLI tool |
| `browse_and_capture.py` | Browser screenshot + capture | Script |
| `late_publisher.py` | Late API direct publisher | Script |

## Workflow Commands (33 — `.agents/workflows/`)

Full list with descriptions: @brain/CAPABILITIES.md § Workflows

| Daily | Weekly | Monthly | Quarterly | On-Demand |
|-------|--------|---------|-----------|-----------|
| `/briefing` | `/retro` | `/competitive-report` | `/qbr` | `/commit`, `/review`, `/ship` |
| `/ceo-briefing` | `/client-health` | `/investor-update` | `/strategic-review` | `/debug`, `/research`, `/content` |
| | `/knowledge-maintenance` | | | `/post`, `/proposal`, `/meeting-prep` |
| | | | | `/plan-feature`, `/execute`, `/prime` |
| | | | | `/skool-edit`, `/skool-push`, `/opencli` |
| | | | | `/ingest`, `/query-knowledge`, `/evolve` |
| | | | | `/generate-proposal`, `/client-health-report` |

## Sub-Agents (17 + 6 Native)

Decision matrix and full registry: @brain/AGENTS.md
Native Claude Code agents (`.claude/agents/`): architect, code-reviewer, content-writer, debugger, researcher, security-reviewer

## Obsidian Links
- [[CLAUDE]] | [[brain/CAPABILITIES]] | [[brain/AGENTS]] | [[brain/STATE]]
- [[skills/codex-delegation/SKILL]] | [[skills/mcp-operations/SKILL]]
