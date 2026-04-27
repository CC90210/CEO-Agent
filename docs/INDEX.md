---
tags: [docs, index, hub]
---

# Documentation Index

> Reference documents, legal, and technical documentation.
> [[brain/CAPABILITIES]] | [[brain/DASHBOARD]]

## Documents
- [[docs/LEGAL]] — Legal templates and compliance
- [[docs/Cedarwood_ROI_Analysis]] — Cedarwood prospect ROI analysis
- [[docs/MOBILE_TERMINAL]] — Mobile terminal setup guide
- [[docs/V6_ARCHITECTURE]] — V6.0 principal-architect design doc (pgvector + LISTEN/NOTIFY + Hetzner VPS)
- [[docs/N8N_INBOUND_INTEGRATION]] — n8n inbound integration patterns
- [[docs/AGENT_REPO_CROSS_ANALYSIS_2026-04-22]] — Cross-repo gap analysis (historical snapshot)

## Cross-Agent Prompts (paste into sibling Claude Code sessions)

### Maven prompts — recommended paste order

CC's recommended sequence when picking Maven up after the 2026-04-26 marketing transfer:

| Order | Prompt | Status | Purpose |
|-------|--------|--------|---------|
| **1️⃣ FIRST** | [[docs/MAVEN_ONBOARDING_PROMPT]] | **ACTIVE** | Get acquainted with the 4 transferred files + new `script_ideation.py` tool, run 21-test suite, do a real ideation run, commit + push |
| **2️⃣ THEN** | [[docs/MAVEN_BRIDGE_BUILD_PROMPT]] | **ACTIVE** | Build Maven's Telegram bridge from scratch (3rd chat in CC's phone trio) |
| **3️⃣ THEN** | [[docs/MAVEN_FINALIZATION_PROMPT]] | **ACTIVE** | V1.1→V1.2 deep audit — close integration debt from 4-script transfer + 6-lens hardening pass |
| ✅ DONE | [[docs/MAVEN_UPDATE_PROMPT]] | COMPLETE (commit 067cde8) | V1.0→V1.1 — frontmatter/skill-import/send_gateway upgrade |
| ✅ DONE | [[docs/MAVEN_SYSTEM_MESSAGE]] | COMPLETE (commit 067cde8) | Paste-wrapper for the V1.0→V1.1 upgrade |

### Atlas prompts

| Prompt | Status | Purpose |
|--------|--------|---------|
| [[docs/ATLAS_FINALIZATION_PROMPT]] | **ACTIVE** | V1.0 foundation build — 8 agents, math-grade test coverage, cfo_pulse contract, dispatch chokepoint |
| [[docs/ATLAS_BRIDGE_FINALIZATION_PROMPT]] | **ACTIVE** | Add C-Suite snapshot + ATLAS_FORCE_DRY_RUN killswitch + document cfo_pulse contract |

### Bravo prompts (cross-machine)

| Prompt | Status | Purpose |
|--------|--------|---------|
| [[docs/MACBOOK_SYNC_PROMPT]] | **ACTIVE** | Pull unpushed commits + run all verification + restart bridge with `loadCSuiteSnapshot`. **Bundles the Mac bridge fix.** |
| [[docs/BRAVO_BRIDGE_FINALIZATION_PROMPT]] | ⚠️ SUPERSEDED by MACBOOK_SYNC_PROMPT | Historical reference — diagnostic findings explain the original 04:08 AM screenshot bug |

When in doubt: ACTIVE prompts are paste-ready. COMPLETE prompts are historical reference — don't re-run them. SUPERSEDED prompts have been replaced by something better — use the replacement.

## Workstation
- [[docs/AI_WORKSTATION_ROADMAP]] — Full AI workstation upgrade plan
- [[docs/COMPUTER_STORE_UPGRADE_BRIEF]] — Buyer-facing brief for computer-store upgrade
- [[docs/WORKSTATION_DEEP_AUDIT]] — Deep audit of current workstation capacity vs. agent demand

## Development Rules
- [[docs/rules/no-find-dom-node]] — Rule: avoid findDOMNode (deprecated React API)
