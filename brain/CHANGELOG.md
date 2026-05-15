---
tags: [changelog, audit]
---

# BRAVO — Self-Modification Changelog

> Every change the agent makes to its own files is recorded here.
> Supabase `self_modification_log` table has the structured version.

## Format
```
### [DATE] — [FILE] — [ACTION]
**Tier:** IMMUTABLE | SEMI-MUTABLE | GOVERNED MUTABLE | FREELY MUTABLE | EPHEMERAL
**What changed:** Brief description
**Why:** Reason for the change
**Confidence:** 0.0-1.0
```

---

## Changelog

### 2026-05-15 — V6.7+ — CloakBrowser stealth tier integration
**Tier:** SEMI-MUTABLE (skill + brain docs) + FREELY MUTABLE (CLI wrapper)
**What changed:**
- New CLI wrapper `scripts/cloak_browser_tool.py` (6 subcommands: scrape, goto, check-stealth, binary-info, download, clear-cache) with proxy support via `CLOAK_PROXY_URL` / `CLOAK_PROXY_USERNAME` / `CLOAK_PROXY_PASSWORD` / `CLOAK_TIMEZONE_ID` / `CLOAK_LOCALE` (all loaded via `lib/secret_loader.py`).
- New skill `skills/cloak-browser/SKILL.md` (canonical reference + license caveat + proxy guidance).
- Decision matrix promoted from 3 → 4 tools across `skills/web-scraping/SKILL.md` + `skills/browser-automation/SKILL.md`.
- Brain updates: `CAPABILITIES.md` (browser-layers section + MCP-replacement table row), `QUICK_REFERENCE.md` (intent → tool routing entry), `INTENTS.md` (new "Scrape <URL>" 4-tier playbook), `AGENT_ROUTER.md` (router-table entries for unprotected vs protected scrape), `WHEN_TO_USE_SKILLS.md` (browser-automation row split into 4 tools).
- Sibling sync per Rule 4: `CLAUDE.md`, `GEMINI.md`, `ANTIGRAVITY.md`, `AGENTS.md`, `OPENCODE.md` all carry the four-tool ladder with CloakBrowser as mandatory tier-2.
- Capability graph rebuilt (357 nodes); bridge manifest registered the 6 new subcommands.
- Memory: `memory/feedback_browser_ladder_mandatory.md` + `memory/reference_cloakbrowser.md` + MEMORY.md index updated.

**Why:** Raw Playwright fingerprints get blocked by Cloudflare/DataDome within 1-3 requests. CloakBrowser (https://github.com/CloakHQ/CloakBrowser, PyPI 0.3.28) ships a Chromium 146 binary with C++ source-level fingerprint patches — drop-in Playwright API, passes reCAPTCHA v3 (~0.9 score), Cloudflare Turnstile, DataDome, FingerprintJS, etc. Browser Harness still wins for CC-authenticated work; CloakBrowser is the missing tier for fresh-session protected scraping.

**Verified:** `check-stealth` 5/5 on Windows + NVIDIA, `scrape https://www.cloudflare.com` 200 OK with 11644 chars.

**Confidence:** 0.95 — smoke-tested live; one pre-existing Browser Harness EXE issue (`ModuleNotFoundError: 'run'`) flagged separately, not silently fixed (V6 Coherence Gate Rule 10).

---

### 2026-04-22 — V6.0 Finalization Session — MULTI-FILE SCAFFOLD + SEND_GATEWAY HARDENING
**Tier:** SEMI-MUTABLE (scaffolds are dormant until CC approves activation)
**What changed:**
- NEW `docs/V6_ARCHITECTURE.md` — Principal Architect design doc answering CC's 4 V6 upgrade questions
- NEW `database/014_v6_pgvector_memory.sql` — pgvector + memory_chunks + search_memory_chunks RPC (hybrid retrieval)
- NEW `database/015_v6_event_bus_extensions.sql` — LISTEN/NOTIFY trigger + claim/ack/fail RPCs + FOR UPDATE SKIP LOCKED
- NEW scripts: `event_bus.py` (pub/sub + offline queue), `memory_chunker.py` (MD → chunks), `memory_ingest.py` (chunks → pgvector), `memory_query.py` (RAG retrieval), `pii_scrubber.py` (reversible redaction)
- NEW `infra/` — Dockerfile (Python 3.12-slim non-root), docker-compose.yml (5 daemons + pgbouncer + Caddy), Caddyfile (Let's Encrypt + security headers), .dockerignore, README.md runbook
- NEW `.github/workflows/deploy-vps.yml` — CD pipeline with tests + Telegram notify
- UPDATE `scripts/send_gateway.py` (via Codex) — bounce circuit breaker, HOURLY_CAPS, per-domain cooldown, draft_critic gate, DNS reputation doctor
- NEW `scripts/dns_reputation.py` (via Codex) — SPF/DKIM/DMARC verification
- FIX stale Calendly references in `APPS_CONTEXT/OASIS_AI_CLAUDE.md`, `brain/MAC_SYNC_PROMPT.md`, `memory/ARCHIVES/lead_system/build_workflows.py`, `.agents/plans/inbound-engine-build-plan.md`
- UPDATE `brain/CAPABILITIES.md` — registered browser_connect.py + V6 scaffold table
- UPDATE `brain/STATE.md`, `memory/SESSION_LOG.md`, `memory/ACTIVE_TASKS.md` — session outputs + V6 active task
**Why:** CC's V6.0 upgrade brief (architectural vulnerabilities: pulse JSON race conditions, context collapse, IDE dependency) + Antigravity handover (stale-data diagnostic + send_gateway $5k MRR audit). Scaffolding V6 in-repo lets CC sign-off and activate incrementally without rewriting under pressure. Send_gateway hardening closes the 2 CRITICAL gaps blocking outbound scale past 50/day.
**Confidence:** 0.92 (code compiles; chunker + PII scrubber smoke-tested; migrations 014/015 unapplied; VPS unprovisioned; awaiting Codex test results on send_gateway)

### 2026-03-01 — AGENT_CORE_DIRECTIVES.md — UPDATE (V5.4 → V5.5)
**Tier:** SEMI-MUTABLE (approved by CC during session)
**What changed:** Added Interaction Protocol to boot sequence, self-evolution section, interaction governance section, updated file structure with mutability tags
**Why:** CC directed full system upgrade to self-evolving architecture
**Confidence:** 0.95

### 2026-03-01 — brain/INTERACTION_PROTOCOL.md — CREATE
**Tier:** SEMI-MUTABLE (new file, approved by CC)
**What changed:** Created master governance protocol for all agent interactions
**Why:** No interaction governance existed. Architecture audit identified this as critical gap.
**Confidence:** 0.92

### 2026-03-01 — brain/BRAIN_LOOP.md — UPDATE
**Tier:** SEMI-MUTABLE (approved by CC during session)
**What changed:** Added LATS multi-hypothesis generation (Step 4), Reflexion protocol (Step 7), dual-write to Supabase (Step 8), Voyager skill compositionality (Step 9), activation-scored retrieval (Step 2), failure recovery protocol
**Why:** Research into LATS, Reflexion, Voyager revealed superior reasoning patterns
**Confidence:** 0.90

### 2026-03-01 — brain/HEARTBEAT.md — UPDATE
**Tier:** GOVERNED MUTABLE
**What changed:** Added OpenClaw merge window, Supabase state sync check, duplicate suppression, enhanced session-end protocol with 13 steps, probationary item promotion checks
**Why:** OpenClaw architecture research revealed superior heartbeat patterns
**Confidence:** 0.88

### 2026-03-01 — brain/GROWTH.md — UPDATE
**Tier:** GOVERNED MUTABLE
**What changed:** Replaced flat skill list with Voyager-style tracked table (uses/status/composites), added compositionality section, expanded capability frontier to table format, added growth metrics
**Why:** Voyager research showed compositional skill libraries compound capability faster
**Confidence:** 0.90

### 2026-03-01 — memory/SOP_LIBRARY.md — UPDATE
**Tier:** GOVERNED MUTABLE
**What changed:** Added probationary validation system, activation scoring, prerequisite tracking, automatic SOP detection rules, enhanced SOP-004 with Supabase sync steps
**Why:** Self-evolving architecture requires formalized SOP lifecycle management
**Confidence:** 0.88

### 2026-03-01 — memory/PATTERNS.md — UPDATE
**Tier:** FREELY MUTABLE
**What changed:** Added validation status tags ([VALIDATED]/[PROBATIONARY]), session counts, last-used dates, two new patterns (Multi-Hypothesis, Reflexion on Failure)
**Why:** Patterns need lifecycle tracking to support probationary system
**Confidence:** 0.92

### 2026-03-01 — database/002_interaction_traces_schema.sql — CREATE
**Tier:** GOVERNED MUTABLE
**What changed:** Added 4 tables (agent_traces, self_modification_log, performance_metrics, skill_activation) + 3 helper functions
**Why:** Enable structured observability and self-evolution tracking
**Confidence:** 0.90

### 2026-03-01 — brain/STATE.md — UPDATE
**Tier:** EPHEMERAL
**What changed:** Updated to V5.5, new confidence level, updated goals and system health
**Why:** Standard session-end state update
**Confidence:** 0.95

## Obsidian Links
- [[brain/INTERACTION_PROTOCOL]] | [[brain/STATE]] | [[brain/GROWTH]]
- [[memory/PROPOSED_CHANGES]] | [[memory/SESSION_LOG]]
