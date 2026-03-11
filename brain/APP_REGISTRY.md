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
| **Nostalgic Requests** | nostalgic, song requests | (GitHub only) | CC90210/nostalgic-requests | jqybbrtzpvmefgzzdagz | Next.js, Supabase, Stripe Connect | Vercel |
| **Grape Vine Cottage** | grape vine, grapevine, cottage | `C:\Users\User\APPS\Grape-Vine-Cottage` | CC90210/grapevinecottage | — | Vite, React 18, Shadcn/ui | Vercel |
| **Mindset Companion** | mindset, lucid | `C:\Users\User\APPS\MINDSET COMPANION APP\cc-mindset` | CC90210/MINDSET-COMPANION-LUCID | — | Next.js 16, React 19 | Vercel |
| **On The Hill** | on the hill, OTH | `C:\Users\User\APPS\ON-THE-HILL-WEBSITE` | CC90210/ON-THE-HILL | — | Vite, React 19 | — |
| **PING App** | ping | `C:\Users\User\APPS\PING-APP` | CC90210/PING-APP | — | Next.js, Prisma, Anthropic SDK | Vercel |
| **Echoes** | echoes | `C:\Users\User\APPS\Echoes_APP\ECHOES_APP` | CC90210/ECHOES_APP | — | Next.js, Prisma | Vercel |


## App Context Files

Detailed business context for primary brands:
- OASIS AI: @APPS_CONTEXT/OASIS_AI_CLAUDE.md
- PropFlow: @APPS_CONTEXT/PROPFLOW_CLAUDE.md
- Nostalgic Requests: @APPS_CONTEXT/NOSTALGIC_REQUESTS_CLAUDE.md

## Session Logging Pattern

After completing work in an app repo, append to memory/SESSION_LOG.md:
```
### [DATE] — [APP NAME] code change
**Change:** [1-2 sentence summary]
**Files:** [key files changed, no code]
**Commit:** [hash or "pushed to origin/main"]
```
