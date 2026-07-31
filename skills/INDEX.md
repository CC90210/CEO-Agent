---
tags: [skills, index, hub]
last_updated: 2026-07-19
---

# Skills Index — Specialized Capabilities (live count: `CAPABILITY_GRAPH.json` totals — 152 as of 2026-07-19; never hand-count here)

> Central hub for all Bravo skills. Each skill is a reusable protocol loaded on-demand.
> [[brain/CAPABILITIES]] | [[brain/AGENTS]] | [[brain/DASHBOARD]]
>
> **Newest (2026-06/07, currency-audit backfill):** [[skills/currency-audit/SKILL.md]] (semantic-staleness sweep, V7.3.5) · [[skills/resource-radar/SKILL.md]] (Free-Tier Radar lookup, V7.1) · [[skills/manifest-ai-editor/SKILL.md]] · [[skills/silver-platter/SKILL.md]] · [[skills/memory-journaling/SKILL.md]] · [[skills/gws-docs-edit/SKILL.md]] · [[skills/score-b2b-lead-quality/SKILL.md]]
>
> Last cluster-audit: 2026-05-16 (V6.7+). 9 archived persona-* skills moved to `skills/_archive/personas/` (orphaned 2026-05-07, never physically removed). Knowledge + memory clusters confirmed non-redundant. GWS cluster confirmed intentional auto-gen (OpenClaw). Routing-accuracy bug fixed: capability_query resolver now respects `disable-model-invocation: true` and `archived: <date>` per skill frontmatter.

## Research + Web (V6.7+, 2026-05-16 update)
- [[skills/research-fetch/SKILL.md]] — **DEFAULT URL fetcher** (V6.7+). Auto-escalates Firecrawl → CloakBrowser + SQLite per-domain reputation memory. `python scripts/research_fetch.py <url>`
- [[skills/cloak-browser/SKILL.md]] — Stealth Chromium 146 tier (drop-in Playwright with C++ fingerprint patches). Called by `research-fetch`; use directly for interactive goto / screenshot / check-stealth
- [[skills/web-scraping/SKILL.md]] — Decision matrix: research-fetch / Firecrawl / CloakBrowser / Playwright / Browser Harness
- [[skills/browser-harness/SKILL.md]] — Real-Chrome attach for CC-authenticated work
- [[skills/browser-automation/SKILL.md]] — Playwright MCP reference (unprotected interactive flows)

## Meta
- [[skills/SKILL_LOADING.md]] — How skills are loaded and activated across AI interfaces
- [[skills/hyperthink/SKILL.md]] — **Maximum-depth reasoning protocol** (wraps ultrathink + 7-phase LATS + Reflexion). Fire for architectural / irreversible / multi-hypothesis problems. Trigger: CC says "hyperthink" or any `think harder` synonym.

## Core Operations
- [[skills/systematic-debugging/SKILL.md]] — Bug investigation, root-cause analysis
- [[skills/code-review/SKILL.md]] — Pre-ship code quality review
- [[skills/receiving-code-review/SKILL.md]] — How to receive and act on code reviews
- [[skills/requesting-code-review/SKILL.md]] — How to request a code review
- [[skills/ship/SKILL.md]] — Full deployment pipeline
- [[skills/executing-plans/SKILL.md]] — Step-by-step plan execution
- [[skills/writing-plans/SKILL.md]] — Feature planning and architecture
- [[skills/test-driven-development/SKILL.md]] — TDD methodology
- [[skills/verification-before-completion/SKILL.md]] — Pre-merge verification
- [[skills/finishing-a-development-branch/SKILL.md]] — Branch completion protocol

## Agent Infrastructure
- [[skills/agent-forge/SKILL.md]] — Create new agents from template with identity, memory, safety, and a doctor command on day one. Bravo's moat extension.
- [[skills/agent-runtime-packaging/SKILL.md]] — Product-grade agent infrastructure: onboarding diagnostics, runtime home, packaging, skill lifecycle, tool manifests, Browser Harness integration, and agent scaffolds.
- [[skills/agent-teams/SKILL.md]] — Native parallel subagent orchestration
- [[skills/task-routing/SKILL.md]] — Complexity-based agent assignment
- [[skills/anti-drift/SKILL.md]] — Preventing agent divergence
- [[skills/sparc-methodology/SKILL.md]] — SPARC for COMPLEX+ tasks
- [[skills/agent-permissions/SKILL.md]] — Claims-based access control
- [[skills/codex-delegation/SKILL.md]] — Dual-AI routing (Bravo + Codex)
- [[skills/background-workers/SKILL.md]] — Automated system workers
- [[skills/hooks-automation/SKILL.md]] — Hook configuration
- [[skills/context-optimization/SKILL.md]] — Token cost reduction
- [[skills/subagent-driven-development/SKILL.md]] — Multi-agent workflows
- [[skills/dispatching-parallel-agents/SKILL.md]] — Parallel execution
- [[skills/self-healing/SKILL.md]] — System health recovery
- [[skills/heartbeat/SKILL.md]] — Proactive monitoring heartbeat
- [[skills/ai-integration/SKILL.md]] — AI service integration patterns
- [[skills/agent-inbox/SKILL.md]] — **Async agent-to-agent messaging** (mcp_agent_mail pattern). Codex posts task-complete → Bravo picks up on next checkpoint. Replaces polling. Backed by `scripts/core/agent_inbox.py`.

## Memory & Knowledge
- [[skills/memory-management/SKILL.md]] — Memory cleanup and budgets
- [[skills/memory-compression/SKILL.md]] — Memory file compression and archival
- [[skills/strategic-compact/SKILL.md]] — Context compaction
- [[skills/sequential-reasoning/SKILL.md]] — Multi-step reasoning
- [[skills/knowledge-management/SKILL.md]] — Knowledge system maintenance
- [[skills/knowledge-graph/SKILL.md]] — Knowledge graph operations
- [[skills/semantic-memory/SKILL.md]] — Semantic memory with vector search

## Content & Outreach
- [[skills/outreach-send/SKILL.md]] — Canonical one-command OASIS outreach send workflow (HTML templates, booking link, geo-rapport, deliverability gates)
- [[skills/telegram-demo-workflows/SKILL.md]] — 5 content-ready Telegram demo sequences for filming
- [[skills/revenue-operations/SKILL.md]] — Revenue pipeline
- [[skills/send-gateway/SKILL.md]] — **The single outbound chokepoint** for every email/DM/outbound message. Enforces CASL compliance, cooldowns, daily caps, cross-engine idempotency. Every autonomous send goes through `scripts/integrations/send_gateway.py`.

## Business Operations
- [[skills/verticals/SKILL.md]] — Vertical-specific playbooks (HVAC, wellness, real estate, retail)
- [[skills/proposal-generation/SKILL.md]] — Client proposals and SOWs
- [[skills/market-research/SKILL.md]] — Market research and analysis
- [[skills/client-success/SKILL.md]] — Client health scoring
- [[skills/scaling-playbook/SKILL.md]] — Growth playbook
- [[skills/investor-materials/SKILL.md]] — Investor updates
- [[skills/investor-communications/SKILL.md]] — Investor and stakeholder communications
- [[skills/financial-modeling/SKILL.md]] — Unit economics
- [[skills/booking-management/SKILL.md]] — Booking system
- [[skills/strategic-planning/SKILL.md]] — OKRs and strategic planning
- [[skills/sales-methodology/SKILL.md]] — NEPQ sales methodology
- [[skills/risk-management/SKILL.md]] — Risk identification and mitigation
- [[skills/crisis-response/SKILL.md]] — Crisis management protocol
- [[skills/project-management/SKILL.md]] — Project tracking and delivery
- [[skills/meeting-automation/SKILL.md]] — Meeting prep and follow-up automation
- [[skills/team-management/SKILL.md]] — Team and contractor management
- [[skills/internal-comms/SKILL.md]] — Internal communications
- [[skills/daily-planner/SKILL.md]] — Daily planning and prioritization
- [[skills/ceo-briefing/SKILL.md]] — CEO situation briefing
- [[skills/ceo-dashboard/SKILL.md]] — CEO metrics dashboard

## Browser & Automation
- [[skills/browser-harness/SKILL.md]] — **Direct Chrome/Edge control + compounding browser domain skills** with Bravo safety gates. Installed at `C:\Users\User\APPS\browser-harness`; diagnose with `python scripts/browser/browser_harness_doctor.py`.
- [[skills/browser-automation/SKILL.md]] — Playwright tasks
- [[skills/e2e-testing/SKILL.md]] — End-to-end testing
- [[skills/webapp-testing/SKILL.md]] — Web app testing
- [[skills/computer-control/SKILL.md]] — OS-level automation (mouse, keyboard, window management)
- [[skills/web-scraping/SKILL.md]] — Web data extraction

## Development Tools
- [[skills/mcp-operations/SKILL.md]] — MCP troubleshooting
- [[skills/mcp-builder/SKILL.md]] — MCP server creation
- [[skills/cli-anything/SKILL.md]] — CLI wrapper generation
- [[skills/opencli/SKILL.md]] — OpenCLI website exploration
- [[skills/supabase-patterns/SKILL.md]] — Supabase best practices
- [[skills/n8n-mcp-integration/SKILL.md]] — n8n workflow integration
- [[skills/n8n-patterns/SKILL.md]] — n8n workflow patterns
- [[skills/using-git-worktrees/SKILL.md]] — Git worktree management
- [[skills/using-superpowers/SKILL.md]] — Advanced capabilities
- [[skills/python-daemon-automation/SKILL.md]] — Python daemon management
- [[skills/security-protocol/SKILL.md]] — Security hardening
- [[skills/notebooklm/SKILL.md]] — NotebookLM integration
- [[skills/doc-coauthoring/SKILL.md]] — Document co-authoring workflows

## Content Formats
- [[skills/pdf/SKILL.md]] — PDF generation
- [[skills/docx/SKILL.md]] — Word document generation
- [[skills/pptx/SKILL.md]] — PowerPoint generation
- [[skills/xlsx/SKILL.md]] — Excel generation
- [[skills/web-artifacts-builder/SKILL.md]] — Web artifact creation

## SOPs & Process
- [[skills/sop-breakdown/SKILL.md]] — Process documentation
- [[skills/retro/SKILL.md]] — Weekly retrospective
- [[skills/skill-creator/SKILL.md]] — New skill generation
- [[skills/writing-skills/SKILL.md]] — Skill authoring

## Creative
- [[skills/brainstorming/SKILL.md]] — Ideation sessions
- [[skills/canvas-design/SKILL.md]] — Visual design
- [[skills/frontend-design/SKILL.md]] — UI/UX design
- [[skills/theme-factory/SKILL.md]] — Theme generation
- [[skills/algorithmic-art/SKILL.md]] — Generative art
- [[skills/slack-gif-creator/SKILL.md]] — GIF creation

## Personas (archived 2026-05-07)

The 9 `persona-*/SKILL.md` files were thin GWS-workflow wrappers — role-flavored aliases that never added executable capability. Archived per Architecture Certification finding C9. The role-to-stack mappings now live in `memory/PERSONAS.md`. Use the GWS workflows directly (`gws workflow +standup-report`, `+meeting-prep`, etc.) — see [[skills/gws-workflow/SKILL.md]].

- See [[memory/PERSONAS]] for the consolidated role-to-GWS-stack reference.

## Google Workspace
- [[skills/gws-shared/SKILL.md]] — `gws` CLI reference (auth, global flags, usage). All per-action + per-service hubs are wikilinked from there.
- [[skills/google-workspace-recipes/SKILL.md]] — **Cookbook of 41 multi-step workflows** (Gmail + Drive + Calendar + Docs + Sheets + Tasks)
- [[skills/email-safety/SKILL.md]] — universal dry-run kill-switch + multi-AI rulebook for any agent that may send mail

### GWS — Gmail
- [[skills/gws-gmail/SKILL.md]] — Gmail service hub
- [[skills/gws-gmail-read/SKILL.md]] · [[skills/gws-gmail-send/SKILL.md]] · [[skills/gws-gmail-reply/SKILL.md]] · [[skills/gws-gmail-reply-all/SKILL.md]] · [[skills/gws-gmail-forward/SKILL.md]]
- [[skills/gws-gmail-triage/SKILL.md]] · [[skills/gws-gmail-watch/SKILL.md]]

### GWS — Calendar + Meet
- [[skills/gws-calendar/SKILL.md]] · [[skills/gws-calendar-agenda/SKILL.md]] · [[skills/gws-calendar-insert/SKILL.md]] · [[skills/gws-meet/SKILL.md]]

### GWS — Docs / Sheets / Slides / Forms
- [[skills/gws-docs/SKILL.md]] · [[skills/gws-docs-write/SKILL.md]]
- [[skills/gws-sheets/SKILL.md]] · [[skills/gws-sheets-read/SKILL.md]] · [[skills/gws-sheets-append/SKILL.md]]
- [[skills/gws-slides/SKILL.md]] · [[skills/gws-forms/SKILL.md]]

### GWS — Drive / Tasks / Keep / People / Chat / Classroom / Admin / Events
- [[skills/gws-drive/SKILL.md]] · [[skills/gws-drive-upload/SKILL.md]]
- [[skills/gws-tasks/SKILL.md]] · [[skills/gws-keep/SKILL.md]] · [[skills/gws-people/SKILL.md]]
- [[skills/gws-chat/SKILL.md]] · [[skills/gws-chat-send/SKILL.md]]
- [[skills/gws-classroom/SKILL.md]] · [[skills/gws-admin-reports/SKILL.md]]
- [[skills/gws-events/SKILL.md]] · [[skills/gws-events-subscribe/SKILL.md]] · [[skills/gws-events-renew/SKILL.md]]

### GWS — Workflows (composite)
- [[skills/gws-workflow/SKILL.md]] — workflow hub
- [[skills/gws-workflow-email-to-task/SKILL.md]] · [[skills/gws-workflow-file-announce/SKILL.md]] · [[skills/gws-workflow-meeting-prep/SKILL.md]] · [[skills/gws-workflow-standup-report/SKILL.md]] · [[skills/gws-workflow-weekly-digest/SKILL.md]]

### GWS — Model Armor (PII / safety)
- [[skills/gws-modelarmor/SKILL.md]] — Model Armor hub
- [[skills/gws-modelarmor-create-template/SKILL.md]] · [[skills/gws-modelarmor-sanitize-prompt/SKILL.md]] · [[skills/gws-modelarmor-sanitize-response/SKILL.md]]

## Standalone (not yet bucketed)
- [[skills/ethical-hacking/SKILL.md]] — security testing playbook (CTF / authorized pentest only)
- [[skills/knowledge-compilation/SKILL.md]] — Karpathy-style compile-into-weights pattern
- [[skills/sales-closing/SKILL.md]] — close discipline (paired with [[skills/sales-methodology/SKILL.md]])
- [[skills/self-improvement-protocol/SKILL.md]] — Rule 9 executable decision tree
