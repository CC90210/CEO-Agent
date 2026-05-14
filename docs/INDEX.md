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
- [[docs/OASIS_DESKTOP_CLAUDE_HANDOFF_2026-05-13]] — canonical OASIS Desktop + SunBiz portal handoff; includes consolidated product, distribution, and SunBiz architecture notes
- [[docs/AGENT_RUNNER_DESIGN]] — Agent runner backend design for the Command Center chat widget
- [[docs/N8N_INBOUND_INTEGRATION]] — n8n inbound integration patterns
- [[docs/AGENT_REPO_CROSS_ANALYSIS_2026-04-22]] — Cross-repo gap analysis (historical snapshot)

## Setup & Operations
- [[docs/INSTALL]] — Installation guide
- [[docs/ENV_KEYS_TEMPLATE]] — Environment variables template
- [[docs/AUTH_FINAL_SETUP]] — Authentication setup guide
- [[docs/N8N_INBOUND_WEBHOOK]] — n8n inbound webhook setup
- [[docs/COMMAND_CENTER_WEBHOOK_API]] — Command Center webhook API reference

## Playbooks
- [[docs/playbooks/INDEX]] — Operator playbooks (getting started, safe interaction, when to call CC, pause and rollback)

## Cross-Agent Prompts

Paste-ready system messages for sibling agents (Maven, Atlas, Bravo-Mac) live in chat history with CC, not in this repo. They were briefly committed as `docs/*_PROMPT.md` files but got removed 2026-04-26 as redundant — chat is the source of truth. Re-request them by name when needed.

## Workstation
- [[docs/AI_WORKSTATION_ROADMAP]] — Full AI workstation upgrade plan
- [[docs/COMPUTER_STORE_UPGRADE_BRIEF]] — Buyer-facing brief for computer-store upgrade
- [[docs/WORKSTATION_DEEP_AUDIT]] — Deep audit of current workstation capacity vs. agent demand

## Development Rules
- [[docs/rules/no-find-dom-node]] — Rule: avoid findDOMNode (deprecated React API)
