---
tags: [docs, index, hub]
last_updated: 2026-08-19
---

# Documentation Index

> Reference documents, legal, and technical documentation.
> [[brain/CAPABILITIES]] | [[brain/DASHBOARD]]

## Documents
- [[docs/LEGAL]] — Legal templates and compliance
- [[docs/MOBILE_TERMINAL]] — Mobile terminal setup guide
- [[docs/V6_ARCHITECTURE]] — V6.0 principal-architect design doc (pgvector + LISTEN/NOTIFY + Hetzner VPS)
- [[docs/AGENT_RUNNER_DESIGN]] — Agent runner backend design for the Command Center chat widget
- [[docs/N8N_INBOUND_INTEGRATION]] — n8n inbound integration patterns

## Setup & Operations
- [[docs/INSTALL]] — Installation guide
- [[docs/ENV_KEYS_TEMPLATE]] — Environment variables template
- [[docs/AUTH_FINAL_SETUP]] — Authentication setup guide
- [[docs/N8N_INBOUND_WEBHOOK]] — n8n inbound webhook setup
- [[docs/COMMAND_CENTER_WEBHOOK_API]] — Command Center webhook API reference

## Playbooks
- [[docs/playbooks/INDEX]] — Operator playbooks (getting started, safe interaction, when to call CC, pause and rollback)

## Cross-Agent Prompts

Committed paste-ready `*_PROMPT.md` runbooks (VPS deploy/verify, Mac sync, etc.) live in `docs/deploy/` — check the superseded banners before reusing any of them.
- [[docs/LISTING_STUDIO_VPS_AGENT_SYSTEM_MESSAGE]] — paste-in system message for the Listing Studio VPS agent (colour-grading, leads UI, DM + SMS automations, CRM profiles)
- [[docs/LISTING_STUDIO_OUTREACH_CRM_SYSTEM_MESSAGE]] — sequel paste-in system message: manual outbound quick-add, conversation-hold tracking, reminder-mode + auto-SMS follow-up engine (client request 2026-08-24)
- [[docs/LISTING_STUDIO_OUTREACH_CRM_AMENDMENT_A]] — paste into the RUNNING session: `/leads` path fix, auto-text gate fix (listing_id excluded every hand-entered lead), Mandy Telegram bot decision, Mission 10 spreadsheet import + broadcast mass-text
- [[docs/SUNBIZ_VPS_TURNKEY_SYSTEM_MESSAGE]] — paste-in system message for the SunBiz VPS bring-up

## Workstation
- [[docs/AI_WORKSTATION_ROADMAP]] — Full AI workstation upgrade plan

## Development Rules
- [[docs/rules/no-find-dom-node]] — Rule: avoid findDOMNode (deprecated React API)
