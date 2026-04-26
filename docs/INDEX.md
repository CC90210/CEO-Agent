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

| Prompt | Target | Status | Purpose |
|--------|--------|--------|---------|
| [[docs/MAVEN_FINALIZATION_PROMPT]] | Maven (CMO-Agent) | **ACTIVE 2026-04-26+** | V1.1→V1.2 finalization — close 4-script transfer integration debt + 6-lens deep audit |
| [[docs/ATLAS_FINALIZATION_PROMPT]] | Atlas (CFO-Agent) | **ACTIVE 2026-04-26+** | V1.0 foundation build — 8 agents, math-grade test coverage, cfo_pulse contract, dispatch chokepoint |
| [[docs/MAVEN_UPDATE_PROMPT]] | Maven (CMO-Agent) | ✅ COMPLETE (commit 067cde8) | V1.0→V1.1 — original frontmatter/skill-import/send_gateway upgrade |
| [[docs/MAVEN_SYSTEM_MESSAGE]] | Maven (CMO-Agent) | ✅ COMPLETE (commit 067cde8) | Paste-wrapper for the V1.0→V1.1 upgrade |

When in doubt: ACTIVE prompts are the ones to paste right now. COMPLETE prompts are historical reference — don't re-run them on agents that already shipped them.

## Workstation
- [[docs/AI_WORKSTATION_ROADMAP]] — Full AI workstation upgrade plan
- [[docs/COMPUTER_STORE_UPGRADE_BRIEF]] — Buyer-facing brief for computer-store upgrade
- [[docs/WORKSTATION_DEEP_AUDIT]] — Deep audit of current workstation capacity vs. agent demand

## Development Rules
- [[docs/rules/no-find-dom-node]] — Rule: avoid findDOMNode (deprecated React API)
