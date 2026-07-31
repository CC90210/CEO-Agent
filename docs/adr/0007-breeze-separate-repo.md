---
adr: 0007
title: Breeze ships as a separate repo with its own Supabase project
status: accepted
date: 2026-06-08
deciders: CC, Bravo
supersedes: —
superseded_by: —
related: ADR-0001 (skill dependency classification — Breeze is a hard-deps product, not a soft-deps skill), CONTEXT.md "MCA / Lending"
tags: [docs, adr, decision]
last_updated: 2026-06-08
---

# ADR-0007 — Breeze ships as a separate repo with its own Supabase project

## Context

David (client, MCA / business-funding industry) commissioned a merchant-facing portal that lets his funded businesses see their advance metrics (approved amount, available to draw, daily holdback, paid to date, paid today, factor & term) and submit draw requests against their line. Adon is the partner relationship; David funds development and hosting; CC + David co-own the IP per a separate agreement.

Demo target: end of week 2026-06-13.

The implementation question: where does the code live?

## Options considered

**A. Fork `oasis-command-center` and add Breeze as new route groups (`app/(breeze-merchant)/...`, `app/(breeze-lender)/...`).** Shares the existing dashboard repo, single Vercel project, single Supabase. Fastest theoretical clone of patterns since everything's already wired.

**B. Add Breeze as a new app group inside `oasis-command-center` BUT with its own Supabase project (multi-Supabase, single repo).** Hybrid. Cleaner data trust boundary, single deploy.

**C. Brand-new repo at `CC90210/breeze-portal`, own Supabase project, own Vercel project.** Patterns cloned, not imported. Independent deploy.

## Decision

**Option C** — brand-new repo + brand-new Supabase project. Live at `C:\Users\User\APPS\breeze-portal` ↔ https://github.com/CC90210/breeze-portal.

## Rationale

1. **Trust boundary on merchant financial data.** `oasis-command-center` is the empire-operator dashboard — Bravo's view into all agents + CC's internal CRM. Breeze handles real money (advance amounts, bank account tokens, draw approvals). A single Supabase shared between empire-operator data and merchant financial data means an empire-side mistake (a misapplied RLS migration, an over-broad service-role query) can leak across the boundary. Separate Supabase = blast radius capped at one product.

2. **Co-ownership / licensability.** David is a 50/50 IP partner. Bundling Breeze into the oasis-command-center repo (which has empire-internal CRM data + Bravo agent logic) would create endless legal friction when David wants the codebase for licensing to other funders. Separate repo = clean transfer surface.

3. **PropFlow precedent.** PropFlow already does this (separate Supabase, separate Next.js repo). The pattern is established; choosing differently for Breeze would be inconsistency for inconsistency's sake.

4. **Independent deploy + rollback.** A bad Breeze deploy shouldn't touch the empire dashboard, and vice versa. Separate Vercel projects = independent rollback buttons.

5. **The agent-1 exploration that recommended Option A also acknowledged "the merchant-side must be standalone."** Two of three Phase-1 Explore agents independently arrived at this conclusion; only one favored Option A, and the reasoning was speed-of-pattern-import — which Option C handles by copying patterns verbatim at scaffold time.

## Trade-offs accepted

- **Cold-start cost:** ~1 hour of pattern-cloning vs. zero in Option A. (Done — see `lib/supabase/server.ts`, `lib/path-prefix.ts`, `middleware.ts`, `app/api/unsubscribe/route.ts` — all derived from `~/APPS/oasis-command-center`.)
- **Drift risk:** when oasis-command-center fixes a bug in the cloned patterns (e.g., the 2026-05-21 path-prefix audit fix), Breeze must port the fix. Mitigation: tag-cloned files at the top with their source path so a future audit can grep for them.
- **Two Supabase projects to administer:** doubles the migration + RLS surface to monitor. Mitigation: separate is the whole point.
- **No empire substrate at runtime:** Breeze can't import `scripts/integrations/send_gateway.py` live (Python on a VPS vs. Node on Vercel). Instead Breeze ports the *logic* (CASL suppression check, List-Unsubscribe headers) to a Resend wrapper. The compliance behavior is preserved; the runtime is separate.

## Consequences

- New entry in `brain/APP_REGISTRY.md` (slug: `Breeze`).
- Six MCA-domain terms added to `CONTEXT.md` (Merchant, Advance, Factor rate, Daily holdback, Draw, RTR, ISO, Syndication, Lender CRM, Stub mode).
- This ADR.
- `memory/ACTIVE_TASKS.md` carries Breeze as an active build through demo.
- `memory/DECISIONS.md` cross-references this ADR.
- When David hands over a CRM webhook spec, the integration code lives at `breeze-portal/lib/webhooks/lender-crm.ts` and the inbound handler at `breeze-portal/app/api/webhooks/lender-crm/route.ts` — NOT in this repo.

## Verification

```bash
# Repo exists and is reachable
gh repo view CC90210/breeze-portal | head -5

# Local clone matches
ls ~/APPS/breeze-portal/package.json

# Empire docs reference it
grep -l "Breeze" brain/APP_REGISTRY.md CONTEXT.md
```

## Obsidian Links
- [[docs/adr/INDEX]]
- [[CONTEXT]]
