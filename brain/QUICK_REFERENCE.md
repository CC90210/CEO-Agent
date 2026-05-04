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
| Verify / re-sync OASIS outreach templates | `wire_all_templates.py` | `python scripts/wire_all_templates.py --verify-only --json` (enforces website + Google Calendar links) |
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
| Post to social media (quick) | `late_tool.py` | `create --text "..." --account <id>`, `cross-post` |
| "Make this a post" / full video pipeline | **Maven** (`../CMO-Agent/scripts/content_pipeline.py`) | Route to Maven — Bravo does not own video production |
| Content calendar / brand voice / captions | **Maven** | All copywriting + scheduling + brand voice lives in CMO-Agent |
| Generate AI images | `codex_image_gen.py` | `generate "<prompt>" --style branded` |
| Skool community management | `skool_engine.py` | `daemon`, `scan-posts`, `engage-members` |
| Instagram engagement (DMs/replies) | `instagram_engine.py` | `daemon`, `check-dms`, `auto-reply` |
| LinkedIn — research a profile (read-only) | Browser Harness on CC's logged-in Chrome | n/a — there is no LinkedIn outreach automation by design. CC drafts LinkedIn messages by hand. |

### Sales & CRM
| CC Says | Tool | Command |
|---------|------|---------|
| Leads / pipeline / CRM | `lead_engine.py` | `list`, `add`, `score`, `pipeline`, `followups`, `funnel` |
| Client health / churn risk | `client_health.py` | `report`, `score <client>`, `alerts`, `trends` |
| Generate proposal / SOW | `proposal_generator.py` | `generate`, `list-templates`, `export` |
| Competitive analysis / battlecards | `competitive_intel.py` | `add`, `battlecard`, `report`, `matrix` |
| Scrape leads (Firecrawl, canonical) | `scrape_firecrawl_leads.py` | `--target N --cities "X,Y" --niches "A,B"` |
| Pick leads ready to email | `outreach_eligible.py` | `--limit 20`, `--mark-dormant`, `--json` |

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
| n8n workflows (read/exec) | `n8n_tool.py` | `list`, `search`, `execute <id>`, `stats` |
| n8n workflows (build/modify) | n8n-mcp SDK flow | `get_sdk_reference` → `search_nodes` → `get_node_types` → `validate_workflow` → `create_workflow_from_code`. See `skills/n8n-mcp-integration` |
| Web scraping (data extraction) | `firecrawl_tool.py` | `scrape <url>`, `search <query>`, `crawl`, `extract` |
| Web automation (clicks, forms) | Playwright MCP | `browser_navigate`, `browser_click`, `browser_type` |
| Real logged-in browser control + reusable site memory | Browser Harness | `python scripts/browser_harness_doctor.py`; setup: `& (Get-Command browser-harness).Source --setup`; workflow: `/.agents/workflows/browser-harness.md` |
| Cron jobs / scheduled tasks | `cron_engine.py` | `list`, `add`, `run`, `due`, `seed` |
| Execute allowlisted script-backed cron jobs | `cron_dispatcher.py` | `python scripts/cron_dispatcher.py due --execute`, `run <job_id>`, `--dry-run` |
| Cross-agent health rollup (pulses + inboxes + cron + bridges + memory staleness) | `fleet_health.py` | `python scripts/fleet_health.py [--json] [--agent <name>]` |
| Refresh Bravo's ceo_pulse (atomic, schema-validated) | `pulse_publish.py` | `python scripts/pulse_publish.py refresh --net-mrr 3322 --priority "..."`, `validate`, `status` |
| Funnel sync (GoHighLevel) | `funnel_sync.py` | Sync funnels to GHL |

### Knowledge & Memory
| CC Says | Tool | Command |
|---------|------|---------|
| Library docs lookup | Context7 MCP | `resolve-library-id`, `query-docs` |
| Persistent knowledge graph | Memory MCP | `search_nodes`, `create_entities` |
| Obsidian vault graph queries | Knowledge Graph MCP | `kg_search`, `kg_central`, `kg_paths`, `kg_communities` |
| Semantic memory (fuzzy search) | `mem0_tool.py` | `add`, `search`, `list`, `stats` |
| Pick which skills to load | `register_skill.py` | `route "<plain-English task>" --json` (Supabase-backed runtime catalog: triggers, tier, owner, risk) |
| Sync/audit all skills | `register_skill.py` | `sync-all --deactivate-missing --json`; `audit --json` |
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
| Onboarding diagnostics | `onboarding_diagnostics.py` | `[--json]` |
| Browser Harness diagnostics | `browser_harness_doctor.py` | `[--json] [--strict]` |
| **Set up agent on a fresh machine for a paying client** | `install/quickstart.{ps1,sh}` (one-line installer) + `bravo_cli/wizard.py` (interactive setup) | Windows: `irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install/quickstart.ps1 \| iex` · macOS/Linux: `curl -sSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install/quickstart.sh \| bash` · Override: `OASIS_AUTO_INSTALL=1` (skip consent), `OASIS_PROFILE=atlas` (skip picker) · Per-machine setup pattern doc: `skills/agent-runtime-packaging/SKILL.md` |
| Email-safety self-check | `email_doctor.py` | `[--json]` — runs the 10-check multi-AI safety surface audit (gateway, killswitch, --dry-run flags, no-smtp-bypass, template render) |
| Force ALL outbound to dry-run (multi-AI killswitch) | env var | `export BRAVO_FORCE_DRY_RUN=1` (POSIX) / `$env:BRAVO_FORCE_DRY_RUN='1'` (PowerShell). Forces every send through send_gateway to return status=dry_run regardless of caller flags. Use in any session where you don't fully trust the AI driving. |

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
3. **Quick post** → `late_tool.py` | **Full content pipeline** → Maven (`../CMO-Agent/scripts/content_pipeline.py`)
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
Exceptions (accept after too): `register_skill.py`, `stripe_tool.py`, `n8n_tool.py`, `firecrawl_tool.py`, `revenue_engine.py`, `ceo_dashboard.py`

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
| `scrape_firecrawl_leads.py` | Firecrawl lead scraping (canonical) | CLI tool |
| `outreach_eligible.py` | Pick leads ready to email + cadence enforcement | CLI tool |
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
| _(LinkedIn outreach removed 2026-04-25)_ | research-only via Browser Harness — no automation by design | n/a |
| **--- Infrastructure ---** | | |
| `supabase_tool.py` | Database CRUD (3 projects) | CLI tool |
| `n8n_tool.py` | Workflow automation | CLI tool |
| `firecrawl_tool.py` | Web scraping, extraction | CLI tool |
| `browser_harness_doctor.py` | Browser Harness install/attach diagnostics | CLI tool |
| `onboarding_diagnostics.py` | Productized Bravo onboarding health check | CLI tool |
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
