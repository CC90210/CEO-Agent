---
tags: [apps, routing]
last_updated: 2026-06-09
freshness_threshold_days: 30
verified: 2026-06-09
---
# APP REGISTRY — External Codebase Routing

> When CC mentions an app by name or alias, `cd` to its LOCAL PATH before making any code changes.
> Code changes happen IN THE APP'S REPO — never in Business-Empire-Agent.
> Log WHAT was done in memory/SESSION_LOG.md — NOT the actual code.

## Routing Rule (ALL AGENTS — NON-NEGOTIABLE)

When CC says "fix [app]", "update [app]", "build [feature] in [app]", "debug [app]":
1. Identify the app from the table below (match name or alias)
2. `cd` to its LOCAL PATH
3. Make all code changes THERE — commit and push to GitHub from THERE
4. Return to Business-Empire-Agent cwd after work is complete
5. Append a 1-2 sentence summary to memory/SESSION_LOG.md

**NEVER store app source code in Business-Empire-Agent.**

## App Registry

| App | Aliases | Local Path | GitHub | Supabase | Stack | Deploy |
|-----|---------|-----------|--------|----------|-------|--------|
| **OASIS AI Platform** | oasis, oasis-platform | `C:\Users\User\APPS\oasis-ai-platform` | CC90210/oasis-ai-platform | sajanpiqysuwviucycjh | React 18, Vite, Supabase | Vercel |
| **PropFlow** | propflow, real estate app | `C:\Users\User\realestate-App` | CC90210/real-estate-App | — | Next.js 14, Supabase, Stripe | Vercel |
| **Nostalgic Requests** | nostalgic, song requests | `C:\Users\User\APPS\nostalgic-requests` | CC90210/nostalgic-requests | jqybbrtzpvmefgzzdagz | Next.js, Supabase, Stripe Connect | Vercel |
| **Grape Vine Cottage** | grape vine, grapevine, cottage | `C:\Users\User\APPS\Grape-Vine-Cottage` | CC90210/grapevinecottage | — | Vite, React 18, Shadcn/ui | Vercel |
| **Mindset Companion** | mindset, lucid | `C:\Users\User\APPS\MINDSET COMPANION APP\cc-mindset` | CC90210/MINDSET-COMPANION-LUCID | — | Next.js 16, React 19 | Vercel |
| **On The Hill** | on the hill, OTH | `C:\Users\User\APPS\ON-THE-HILL-WEBSITE` | CC90210/ON-THE-HILL | — | Vite, React 19 | — |
| **Atlas (CFO Agent)** | atlas, cfo, finance, tax, trading agent, trader | `C:\Users\User\APPS\CFO-Agent` | CC90210/CFO-Agent | — | Python 3.11+, CCXT, Claude API, SQLite | — |
| **Maven (CMO Agent)** | maven, cmo, marketing, ads, content, funnel, brand | `C:\Users\User\CMO-Agent` | CC90210/CMO-Agent | — | Python, Node, Meta + Google Ads SDKs, Remotion | — |
| **TIKTIK** | tiktik, daycare, attendance | `C:\Users\User\APPS\tiktik` | CC90210/tiktik | icgazynsnqyombvkocwb | Next.js 14, TypeScript, Supabase, Tailwind | Vercel (tiktik-psi.vercel.app) |
| **CC Funnel** | cc-funnel, funnel, lead form | `C:\Users\User\APPS\cc-funnel` | CC90210/cc-funnel | phctllmtsogkovoilwos (Bravo) | Next.js 14, TypeScript, Tailwind, Supabase | Vercel (cc-funnel.vercel.app) |
| **Shopify Ad Engine** | shopify-ad-engine, ad engine, kalem ads | `C:\Users\User\APPS\shopify-ad-engine` | CC90210/shopify-ad-engine | — | Remotion 4.0.436, React 19, Three.js, Zod, Python (Meta Ads) | — |
| **Lafreniere PM** | lafreniere, lafreniere-pm, ty, property management | `C:\Users\User\APPS\lafreniere-pm` | CC90210/lafreniere-pm | (pending) | Next.js 16, TypeScript, Supabase, Stripe, Framer Motion | Vercel (pending) |
| **Aura (Life/Home Agent)** | aura, smart home, apartment, life, habits, home agent | `C:\Users\User\AURA` | CC90210/Aura-Home-Agent | — | Claude Code agent, Raspberry Pi 5, Home Assistant, ESP32, voice agent | RPi5 hub |
| **IG Setter Pro** | ig-setter, ig setter, dm automation, manychat | `C:\Users\User\APPS\ig-setter-pro` | CC90210/ig-setter-pro | Turso (ig-setter-cc90210) | Next.js 14, TypeScript, Turso/libSQL, n8n, Claude API, Tailwind | Vercel (ig-setter-pro.vercel.app) |
| **Gritly** | gritly, field service, fsm, trades app | `C:\Users\User\APPS\gritly` | (pending) | Turso (libSQL) | Next.js 15, TypeScript, Drizzle ORM, Better Auth, Stripe, Framer Motion | Vercel (pending) |
| **Hermes** | hermes, lowinger, emmanuel, commerce agent, pos agent, a2000, walgreens, edi, chargeback | `C:\Users\User\hermes` | [CC90210/hermes](https://github.com/CC90210/hermes) (public) | — | Python 3.12, SQLite, FastAPI, Ollama OR Anthropic/OpenAI (DPA), pywinauto (A2000 desktop takeover), Playwright (web ERPs), reportlab (GS1-128 labels), pdfplumber/openpyxl (PO parsing) | Local (client machine) + GitHub Pages demo (cc90210.github.io/hermes) |
| **OASIS Command Center** | command center, agent command center, dashboard, agent-dashboard, oasis dashboard | `C:\Users\User\APPS\oasis-command-center` | [CC90210/oasis-command-center](https://github.com/CC90210/oasis-command-center) | shared with empire (BRAVO_SUPABASE_URL) | Next.js 15.5, React 19, TypeScript, Tailwind, Supabase SSR, Anthropic | Vercel (`agent-dashboard`, alias agent-dashboard-cc90210.vercel.app) — auto-deploys on push to `main` |
| **Breeze** | breeze, merchant-portal, mca-portal, lending-portal, david-portal | `C:\Users\User\APPS\breeze-portal` | [CC90210/breeze-portal](https://github.com/CC90210/breeze-portal) (private) | own project `xugwrhvaoihyidtdgwkq` (separate from empire — merchant-data trust boundary) | Next.js 15.5, React 19, TypeScript, Tailwind, Supabase SSR, Plaid, Resend, React Email | **Vercel — LIVE at https://breeze-portal-mu.vercel.app** (auto-deploys on push to `main`; demo creds in APPS_CONTEXT/BREEZE_CLAUDE.md) |


## App Context Files

Detailed business context for primary brands:
- OASIS AI: @APPS_CONTEXT/OASIS_AI_CLAUDE.md
- PropFlow: @APPS_CONTEXT/PROPFLOW_CLAUDE.md
- Breeze (MCA merchant portal): @APPS_CONTEXT/BREEZE_CLAUDE.md
- Nostalgic Requests: @APPS_CONTEXT/NOSTALGIC_REQUESTS_CLAUDE.md
- Gritly: @APPS_CONTEXT/GRITLY_CLAUDE.md
- IG Setter Pro: @APPS_CONTEXT/IG_SETTER_PRO_CLAUDE.md
- Skool Community (primary community-management retainer): @APPS_CONTEXT/SKOOL_COMMUNITY_CLAUDE.md

## Session Logging Pattern

After completing work in an app repo, append to memory/SESSION_LOG.md:
```
### [DATE] — [APP NAME] code change
**Change:** [1-2 sentence summary]
**Files:** [key files changed, no code]
**Commit:** [hash or "pushed to origin/main"]
```

## Removed: `app/` breadcrumb directory (audit Phase 8, 2026-06-09)

The empty `app/` directory (kept only as a "where did the dashboard go?" marker)
was removed 2026-06-09. The OASIS Command Center dashboard was extracted 2026-05-18
and now lives in its own repo:
- **Repo:** [CC90210/oasis-command-center](https://github.com/CC90210/oasis-command-center)
- **Local clone:** `~/APPS/oasis-command-center` · **Production:** `agent-dashboard-cc90210.vercel.app`

Dashboard work goes in that repo. New agent components go in `scripts/` or `apps/<name>/` — never a recreated `app/`.

## Obsidian Links
- [[APPS_CONTEXT/OASIS_AI_CLAUDE]] | [[APPS_CONTEXT/PROPFLOW_CLAUDE]] | [[APPS_CONTEXT/NOSTALGIC_REQUESTS_CLAUDE]]
- [[memory/SESSION_LOG]] | [[brain/DASHBOARD]]
