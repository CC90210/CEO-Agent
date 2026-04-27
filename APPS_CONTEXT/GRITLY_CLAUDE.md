---
tags: [brand, gritly, context, fsm, saas]
---

> **ROUTING:** Local `C:\Users\User\APPS\gritly` | GitHub: (pending) | Turso (libSQL) | Deploy: Vercel (pending)
> [[brain/DASHBOARD]] | [[brain/APP_REGISTRY]] | [[APPS_CONTEXT/INDEX]]

# Gritly — Field Service Management SaaS for Modern Trades

## Project Overview

Gritly is a Field Service Management (FSM) platform for small-to-medium trades businesses (HVAC, plumbing, electrical, landscaping, cleaning, handyman). Positioned as the modern alternative to Jobber and ServiceTitan — lower price, cleaner UX, built for owner-operators and 1-30 person crews who are priced out of enterprise FSM.

**One-liner:** "The FSM platform that doesn't feel like enterprise software."

## Why Gritly Exists

The FSM market is split between:
- **Jobber** ($29-$149/mo) — Great UX but weak reporting, QuickBooks sync breaks, punishing per-user pricing
- **ServiceTitan** ($250-$500/technician/mo) — Enterprise-grade but $8K-$15K/yr contracts, 6-12mo implementation
- **Nothing in between** for growing crews who need more than Jobber but can't afford ServiceTitan

Gritly fills this gap with a flat-rate pricing model, best-in-class mobile-first UX, and modern analytics without the ServiceTitan price tag.

## Target Customer

- **Primary:** Trades business owners running 3-15 person crews, currently on Jobber or using spreadsheets
- **Secondary:** New trades businesses starting up who don't want to commit to ServiceTitan early
- **Geography:** North America first (US + Canada), English-speaking markets

## Core Features (MVP Scope)

1. **Scheduling & Dispatch** — Drag-drop calendar, route optimization, crew assignments
2. **Quote-to-Invoice Pipeline** — Quote builder, digital signatures, automated invoicing
3. **Client Management** — CRM, service history, automated follow-ups, review requests
4. **Mobile App** — iOS/Android for field crews: job details, photo capture, time tracking, GPS
5. **Payments** — Stripe integration, ACH, card-on-file, automatic reconciliation
6. **Reporting** — Revenue forecasting, technician performance, custom report builder
7. **Online Booking Portal** — Client-facing booking with automated confirmations

## Tech Stack

- **Frontend:** Next.js 15, TypeScript, Tailwind, Framer Motion
- **Backend:** Next.js API routes, Drizzle ORM, Turso (libSQL edge database)
- **Auth:** Better Auth (modern, typescript-first)
- **Payments:** Stripe
- **Deploy:** Vercel (pending)

## Competitive Positioning

**Features Gritly absorbs from Jobber:**
- Clean quote-to-invoice flow
- Automated client follow-ups
- Job forms/checklists
- Online booking portal
- Automated review requests

**Weaknesses Gritly exploits:**
- Jobber's QuickBooks sync errors (native accounting integration instead)
- Jobber's weak reporting (custom report builder from day 1)
- Jobber's per-user pricing (flat-rate tier model)
- ServiceTitan's price barrier ($50-$150/mo vs $250+/tech)
- ServiceTitan's 6-12mo implementation (self-serve onboarding)

## Revenue Model

**Planned tiers (subject to validation):**
- **Starter** — $49/mo (1-3 users, core FSM)
- **Grow** — $99/mo (up to 10 users, reporting, route optimization)
- **Scale** — $199/mo (unlimited users, custom reports, API, priority support)

**Target unit economics:** $99 ARPU, <5% monthly churn, $15 CAC through organic content + trades communities

## Current Status (2026-04-10)

- Foundation built: auth + onboarding + dashboard (15 files, zero build errors)
- Market research completed: `APPS_CONTEXT/GRITLY_MARKET_RESEARCH.json`
- GitHub repo: not yet created
- Deployment: not yet live

## Next Priorities

1. Core scheduling/dispatch module
2. Quote builder flow
3. Stripe payment integration
4. Mobile app scaffolding (React Native or PWA-first decision pending)
5. Beta customer acquisition plan

## Key References

- Market research (13 competitor deep-dives): `APPS_CONTEXT/GRITLY_MARKET_RESEARCH.json`
- Session logs: `memory/SESSION_LOG.md` (2026-04-08, 2026-04-09)

## Obsidian Links

- [[brain/APP_REGISTRY]] | [[brain/DASHBOARD]] | [[brain/STATE]]
- [[APPS_CONTEXT/INDEX]]
