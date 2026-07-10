---
tags: [reference, tools, routing]
last_updated: 2026-06-09
freshness_threshold_days: 90
verified: 2026-06-09
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
| Create/read/write spreadsheet | `google_tool.py` | `sheets create --title "..."`, `sheets read <id>`, `sheets write <id> --range "A1" --values "..."` (simple) or `--json-values '[["a","b,c"]]'` (preserves commas/semicolons/newlines — use this for URLs, prose, structured content), `sheets append <id> --values "..."` or `--json-values` |
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
| Instagram engagement (DMs/replies) | `instagram_engine.py` | `daemon`, `check-dms`, `auto-reply` |
| LinkedIn — research a profile (read-only) | Browser Harness on CC's logged-in Chrome | n/a — there is no LinkedIn outreach automation by design. CC drafts LinkedIn messages by hand. |

### Sales & CRM
> **Primary CRM motion is INBOUND** (funnel, DMs, social content → nurture → book a call). Cold outbound is on-demand only, never the default. `lead_engine.py` `pipeline`/`followups` are tenant-scoped to `OASIS_TENANT_ID` (2026-07-09).

| CC Says | Tool | Command |
|---------|------|---------|
| Leads / pipeline / CRM | `lead_engine.py` | `list`, `add`, `score`, `pipeline`, `followups`, `funnel` |
| Client health / churn risk | `client_health.py` | `report`, `score <client>`, `alerts`, `trends` |
| Generate proposal / SOW | `proposal_generator.py` | `generate`, `list-templates`, `export` |
| Competitive analysis / battlecards | `competitive_intel.py` | `add`, `battlecard`, `report`, `matrix` |
| Scrape leads (Firecrawl, canonical) | `scrape_firecrawl_leads.py` | `--target N --cities "X,Y" --niches "A,B"` |
| Pick leads ready to email | `outreach_eligible.py` | `--limit 20`, `--mark-dormant`, `--json` |

### Revenue & Finance
> **ATLAS-OWNED domain.** Bravo does not report MRR/revenue — "what's my MRR" → defer to Atlas. The tools below stay for on-demand mechanics on explicit CC request only.

| CC Says | Tool | Command |
|---------|------|---------|
| MRR / revenue (ATLAS-owned — defer; mechanics on explicit CC ask only) | `revenue_engine.py` | `mrr`, `dashboard`, `sync-stripe`, `forecast`, `goal` |
| Stripe (balance, invoices, subs) | `stripe_tool.py` | `balance`, `customers`, `invoices`, `subscriptions`, `payment-links` |
| Financial modeling / unit economics | `financial_model.py` | `unit-economics`, `forecast`, `scenario`, `runway` |
| CEO briefing / KPIs (no revenue — Atlas's brief) | `ceo_dashboard.py` | `briefing`, `pipeline`, `full` |

### Database & Infrastructure
| CC Says | Tool | Command |
|---------|------|---------|
| Supabase query / CRUD | `supabase_tool.py` | `select <table> --project bravo`, `insert`, `update`, `query` |
| n8n workflows (read/exec) | `n8n_tool.py` | `list`, `search`, `execute <id>`, `stats` |
| n8n workflows (build/modify) | n8n-mcp SDK flow | `get_sdk_reference` → `search_nodes` → `get_node_types` → `validate_workflow` → `create_workflow_from_code`. See `skills/n8n-mcp-integration` |
| **Fetch a URL — DEFAULT entry point (auto-escalates Firecrawl→Cloak + remembers per-domain)** | `research_fetch.py` | `python scripts/research_fetch.py <url> --json`. Reputation: `reputation [domain]`, `reputation-clear <domain>`. Skill: `skills/research-fetch/SKILL.md` |
| Web scraping (data extraction, public unprotected — when you want Firecrawl-specific features) | `firecrawl_tool.py` | `scrape <url>`, `search <query>`, `crawl`, `extract`, `map` |
| **Scrape a bot-protected site directly (Cloudflare, DataDome, reCAPTCHA, FingerprintJS, etc.) — usually `research_fetch` handles this for you** | `cloak_browser_tool.py` | `scrape <url> --json`, `check-stealth`, `goto <url> --eval "..."`, `download`, `binary-info`. Optional `CLOAK_PROXY_URL` in `.env.agents` for residential proxy. Skill: `skills/cloak-browser/SKILL.md` |
| Web automation (clicks, forms) on unprotected sites | Playwright MCP | `browser_navigate`, `browser_click`, `browser_type` |
| Real logged-in browser control + reusable site memory | Browser Harness | `python scripts/browser/browser_harness_doctor.py`; setup: `& (Get-Command browser-harness).Source --setup`; workflow: `/.agents/workflows/browser-harness.md` |
| Cron jobs / scheduled tasks | `cron_engine.py` | `list`, `add`, `run`, `due`, `seed` |
| Execute allowlisted script-backed cron jobs | `cron_dispatcher.py` | `python scripts/core/cron_dispatcher.py due --execute`, `run <job_id>`, `--dry-run` |
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
| Cross-agent self-improvement sweep | `agent_self_improvement.py` | `run [--json] [--agents bravo,atlas,maven]` — runs **weekly Sunday 4 AM** via cron `7d3d2a77`. Now wired to call drift_autofix + memory archive before reporting. Zero LLM cost. |
| Auto-fix capability-graph drift | `drift_autofix.py` | `scan` (preview) / `apply` — deterministically adds missing `triggers:` to skills (from description) + module docstrings to scripts. No LLM. Bravo went 115→28 drift (remaining are detector false positives). |
| Real-time anti-pattern hook | `anti_pattern_hook.py` | Wired as PreToolUse Bash hook. Reads `memory/ANTI_PATTERNS.json` regex list, warns when about-to-execute commands match logged anti-patterns (e.g. ad-hoc `python -c` lead filters). Pure regex, ~50ms, no LLM. Add patterns to JSON, no settings.json edits. |
| Cron cost audit | `cost_audit.py` | `[--json] [--include-disabled]` — for each active cron, traces handler chain (scheduler → scripts → cross-agent repos), reports per-cron LLM use. Distinguishes transactional vs commercial sends. Zero LLM cost, static analysis only. |
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
2. **Any "fetch URL X" task** → **`research_fetch.py` (default, auto-escalates + remembers per-domain)**. Specific tiers only when you need their unique features: `firecrawl_tool.py` (crawl / extract / map / search), `cloak_browser_tool.py` (interactive goto / screenshot / direct Cloak), Playwright MCP (interactive flow on unprotected), Browser Harness (act as CC under CC's login).
3. **Quick post** → `late_tool.py` | **Full content pipeline** → Maven (`../CMO-Agent/scripts/content_pipeline.py`)
4. **Simple DB query** → `supabase_tool.py` | **Operational metrics (pipeline/health)** → `ceo_dashboard.py` | **MRR/revenue** → ATLAS-owned, defer
5. **Structured memory** → markdown files | **Fuzzy recall** → `mem0_tool.py`
6. **Model call from ANY automation/script** → `scripts/lib/claude_cli.py` `run_claude_cli()` — local `claude` CLI on CC's subscription OAuth, toolless. NEVER call api.anthropic.com / `ANTHROPIC_API_KEY` from an automation (key is out of credits AND banned — CLI-only rule).
7. **Is the harness itself healthy? (ANY runtime, session-start on unfamiliar machines, after substrate changes)** → `python scripts/harness_eval.py` — 10 deterministic checks (entry-point lockstep, skill routing, Atlas boundary, guards, crons, PM2, tenant scoping); `--json` for machines, `--with-model` adds a live claude-CLI probe. All-green = turnkey. Nightly cron runs it at 03:30 and Telegrams CC on any red.
8. **Identity/wiring change across runtimes** → edit `PERSONAL.md` (germline seed) → `python scripts/genome_sync.py` (stamps all 6 entry points + mirrors). Verify expression anywhere: `python scripts/agent_genome.py [--repo <sibling>]` — 10-gene score (fleet: Bravo/Atlas/Maven 10/10, SunBiz 8/10 by design, Breeze 5/10 product).
9. **Associative recall (2026-07-10)** → `memory_retriever.py query` now spreads activation over the vault's `[[wiki-link]]` graph — well-connected notes rank up, and 1-hop neighbors of strong matches surface as `kind: associative` extras. Engine: `scripts/core/graph_activation.py` (`build` / `status` / `neighbors <rel>` / `query "<q>"`); cache `state/graph_adjacency.json` (6h TTL). Opt-out per-call env `EMPIRE_GRAPH_BOOST=0`; hard fallback to plain hybrid on any failure. This is WHY every markdown file needs ≥2 wiki-links (RULE 6) — links are the agent's associations, not just human navigation.

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
| **--- Revenue & Finance (ATLAS-OWNED — mechanics on explicit CC ask only) ---** | | |
| `revenue_engine.py` | MRR tracking, Stripe sync (Atlas-owned; Bravo never reports MRR) | CLI tool |
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
| `agent_self_improvement.py` | Cross-agent self_audit + autofix + archive + mistake-repeat detection | CLI tool + cron `7d3d2a77` weekly Sun 4 AM |
| `drift_autofix.py` | Deterministic capability-graph drift autofix (zero LLM cost) | CLI tool, called by self_improvement |
| `anti_pattern_hook.py` | Real-time PreToolUse hook scanning Bash commands against ANTI_PATTERNS.json | Hook (settings.local.json) |
| `cost_audit.py` | Static-analysis cost audit — traces every active cron's handler chain to identify which jobs burn Anthropic tokens | CLI tool |
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
| | | | | `/opencli` |
| | | | | `/ingest`, `/query-knowledge`, `/evolve` |
| | | | | `/generate-proposal`, `/client-health-report` |

## Sub-Agents (17 + 6 Native)

Decision matrix and full registry: @brain/AGENTS.md
Native Claude Code agents (`.claude/agents/`): architect, code-reviewer, content-writer, debugger, researcher, security-reviewer

## Obsidian Links
- **Core router (the 5 brain entry points):** [[brain/AGENT_ROUTER]] · [[brain/EXECUTION_RULES]] · [[brain/INTENTS]] · [[brain/WHEN_TO_USE_SKILLS]] · QUICK_REFERENCE (this file)
- [[CLAUDE]] | [[brain/CAPABILITIES]] | [[brain/AGENTS]] | [[brain/STATE]]
- [[skills/codex-delegation/SKILL]] | [[skills/mcp-operations/SKILL]]
