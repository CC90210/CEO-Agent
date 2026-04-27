---
tags: [brand, ig-setter, context, instagram, automation]
---

> **ROUTING:** Local `C:\Users\User\APPS\ig-setter-pro` | GitHub: CC90210/ig-setter-pro | Turso: ig-setter-cc90210 | Deploy: Vercel (ig-setter-pro.vercel.app)
> [[brain/DASHBOARD]] | [[brain/APP_REGISTRY]] | [[APPS_CONTEXT/INDEX]]

# IG Setter Pro — Next-Gen Instagram DM Automation

## Project Overview

IG Setter Pro is an AI-powered Instagram DM automation dashboard that replaces ManyChat for cold outreach, lead qualification, and appointment setting. Built as a modern alternative to legacy DM automation tools — faster, smarter, with native Claude API integration for contextual conversations that don't feel like bots.

**One-liner:** "ManyChat for people who actually want DMs that convert."

## Why IG Setter Pro Exists

ManyChat and similar tools have key problems:
- Scripted flows that break when prospects go off-script
- No real conversation memory (each DM is context-free)
- Expensive at scale ($45-$200+/mo)
- Can't integrate with modern AI models for natural responses
- Weak lead classification (boolean tags, not intelligent scoring)

IG Setter Pro solves these by using Claude Haiku for classification + Claude Sonnet for response generation, with full conversation history passed as context on every message.

## Target Customer

- **Primary:** Solopreneurs and agencies doing cold DM outreach on Instagram (coaches, consultants, SaaS founders, service businesses)
- **Secondary:** OASIS AI clients who need lead qualification automation baked into their funnels
- **Use case:** High-volume DM outreach where manual qualification is the bottleneck

## Core Features

1. **Multi-Account Support** — Connect and manage multiple IG accounts from one dashboard
2. **AI-Powered Lead Classification** — Claude Haiku auto-classifies every inbound DM (hot/warm/cold/junk) with scoring
3. **Conversation History → Claude Context** — Every AI response includes full conversation history, making replies contextually aware
4. **Auto-Send Toggle** — Manual approval mode or full autopilot per account
5. **NEPQ Sales Framework** — Built-in Jeremy Miner methodology (pattern interrupt, discovery questions, consequence framing)
6. **Automation Rules Engine** — If/then logic for trigger-based follow-ups
7. **Multi-Step DM Sequences** — Drip campaigns with conditional branching
8. **Token Refresh Automation** — Handles IG API token expiry without manual intervention
9. **Retry Logic** — Rate limit handling, exponential backoff, failed message recovery

## Tech Stack

- **Frontend:** Next.js 14, TypeScript, Tailwind
- **Backend:** Next.js API routes (14 routes), Turso/libSQL (edge database)
- **Database:** Turso (ig-setter-cc90210.aws-us-west-2.turso.io), 8 tables
- **AI:** Claude Haiku (classification) + Claude Sonnet (responses)
- **Automation:** n8n 20-node workflow for DM polling and sequence orchestration
- **Deploy:** Vercel (https://ig-setter-pro.vercel.app)

## Production Hardening Status (2026-04-09)

Went through 3-parallel-agent audit (Code Reviewer + Security Reviewer + Codex), fixed all CRITICAL/HIGH findings:
- Client → API fetch refactor (4 new routes)
- `/api/history` for Claude conversation context
- Atomic SQL + message deduplication
- `/api/sequences/pending` endpoint
- API auth middleware
- Auto-send flag in webhook response
- Sanitized error messages (no DB leaks)
- FK pragma enforcement
- Removed date-fns (smaller bundle)
- Sequence step limits enforced

**Bundle size:** 117KB → 91.3KB after hardening
**Routes:** 9 → 14

## Revenue Model

**Plan:** Internal tool for OASIS AI clients initially, then SaaS spinoff.

**Pricing target (when commercial):**
- Solo — $29/mo (1 IG account, 500 DMs/mo)
- Pro — $79/mo (3 accounts, 2,000 DMs/mo, sequences)
- Agency — $199/mo (10 accounts, 10K DMs/mo, white-label)

## Build History

- **2026-04-08:** Full build from scratch (enhanced rebuild of `brodyautomates/ig-setter`). 32 files, 8 tables, 20-node n8n workflow.
- **2026-04-08:** Turso migration + Vercel deploy + E2E verification
- **2026-04-09:** 3-agent production hardening audit (40+ findings fixed)

## Key Dependencies

- **Claude API** — For classification and response generation
- **Instagram Graph API** — For DM send/receive (requires approved IG Business account)
- **n8n** — For DM polling and sequence orchestration
- **Turso** — For edge-distributed database (low-latency DM responses)

## Key References

- GitHub: https://github.com/CC90210/ig-setter-pro
- Deployed: https://ig-setter-pro.vercel.app
- Session logs: `memory/SESSION_LOG.md` (2026-04-08, 2026-04-09)

## Obsidian Links

- [[brain/APP_REGISTRY]] | [[brain/DASHBOARD]] | [[brain/STATE]]
- [[APPS_CONTEXT/INDEX]]
