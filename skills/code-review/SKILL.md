---
name: code-review
description: Pre-landing code review for TypeScript/Next.js/Supabase/Stripe/Vercel projects. Use before any merge to main. Auto-fixes mechanical issues; asks about judgment calls. Catches security holes, AI slop, and stack-specific gotchas.
triggers: [review, PR, quality, security audit, checklist, pre-landing, code review]
tier: standard
dependencies: [systematic-debugging]
tags: [skill, code-review]
last_updated: 2026-05-23
---

# Code Review — Pre-Landing Quality Gate

## Overview

Gary Tan's "Fix-First" methodology applied to CC's stack: auto-fix everything mechanical without asking, ask for every judgment call. Zero noise, maximum signal.

**Core principle:** Reviewers who ask about obvious fixes waste the author's time. Reviewers who silently fix judgment calls break things. Know the difference.

**Announce at start:** "Running pre-landing code review."

> **MANDATORY pairing on big tasks (added 2026-05-23 per CC):** Bravo's own pre-landing review is biased — the agent that did the work will undersell mistakes and oversell completeness. On any big task (≥3 commits / ≥5 files / any user-facing change), this skill's report MUST be paired with a Codex independent audit. Run `node ~/.claude/codex-plugin/scripts/codex-companion.mjs review --wait` against the diff, present BOTH reports verbatim. See [skills/codex-delegation/SKILL.md](../codex-delegation/SKILL.md) Pattern 5 + CLAUDE.md Rule 8 for the canonical workflow.

---

## The Fix-First Divide

### AUTO-FIX Without Asking
These are mechanical — there is only one correct answer.

- Dead code (functions defined but never called, imports never used)
- Unused variables and parameters
- Stale comments that contradict the current implementation
- Missing TypeScript types where inference fails (explicit `any` without comment)
- Trailing whitespace, double blank lines, inconsistent quote style
- `console.log` left in production paths
- Hardcoded `localhost` URLs that should be `process.env.*`
- `TODO` comments with no linked issue after 30+ days in the diff context
- Obvious spelling errors in identifiers and user-facing strings

### ASK Before Touching
These require judgment — wrong call breaks production.

- Security pattern choices (auth middleware placement, RLS policy logic)
- Race conditions and async ordering in multi-step flows
- Architecture changes (new abstractions, file structure moves, naming conventions)
- Business logic that seems wrong but may reflect a product decision
- Error handling strategy (fail-silent vs. fail-loud)
- Data migration approach (destructive vs. non-destructive)
- API contract changes (adding required fields, changing response shape)
- Performance tradeoffs (caching strategy, query approach)

---

## Severity Classification

| Level | Definition | Action |
|-------|-----------|--------|
| **CRITICAL** | Data loss, secret exposure, auth bypass, broken production deploy | Block merge. Fix before anything else. |
| **HIGH** | Security hole (non-auth), missing error handling on payment/data paths, broken RLS | Block merge. |
| **MEDIUM** | N+1 queries, type unsafety, missing loading/error states in UI | Fix before merge, or document why not. |
| **LOW** | Code style, naming inconsistency, dead comment, minor DX friction | Auto-fix or note for next pass. |

---

## Security Checklist

Run every review. No exceptions.

> **This list is the fast pass.** The authoritative one is the **20-Point Vibe-Security Matrix**
> in [[skills/security-protocol/SKILL]] — it carries a mechanical check per row and covers eight
> classes this section does not (rate-limiter keying, CORS, mass assignment, upload validation,
> email verification, password policy, dependency hygiene, token storage). Use the fast pass on
> an ordinary diff; run the full matrix before a public flip, a first production deploy, or any
> diff adding an unauthenticated surface, an upload, a webhook, or a tenant-scoped table
> ([[brain/EXECUTION_RULES]] § 21).

```
[ ] Hardcoded secrets — grep for API keys, tokens, passwords inline
    Pattern: /sk_live_|Bearer |password\s*=|api_key\s*=/i
    Check: .env vars used everywhere? No .env file committed?

[ ] SQL injection — raw string interpolation in Supabase queries
    Pattern: `...${userInput}...` inside .from() or .rpc() calls
    Fix: Always use parameterized queries or Supabase's typed client

[ ] XSS — dangerouslySetInnerHTML with unescaped user input
    Pattern: dangerouslySetInnerHTML={{ __html: userControlledVar }}
    Fix: Sanitize with DOMPurify or restructure to avoid raw HTML injection

[ ] Missing auth checks — server actions and API routes that skip session validation
    Pattern: async function (req) without getServerSession() or supabase.auth.getUser()
    Fix: Every route that touches data must validate the session first

[ ] RLS disabled — tables without Row Level Security
    Check: supabase.com dashboard → Table Editor → RLS column
    Fix: Enable RLS + add SELECT/INSERT/UPDATE/DELETE policies

[ ] Stripe webhook signature missing
    Pattern: stripe.webhooks.constructEvent() missing or in a try/catch that swallows errors
    Fix: Always verify signature; throw on failure so the 400 response is returned

[ ] Exposed service role key client-side
    Pattern: SUPABASE_SERVICE_ROLE_KEY used in a file under app/ or components/
    Fix: Service role key belongs only in server actions, API routes, and scripts
```

---

## Stack-Specific Checks

### Next.js App Router
```
[ ] Server Components fetching with user-specific data without cookies/headers()
    — Static rendering will cache one user's data for all users
[ ] Client Components marked "use client" that do heavy data fetching
    — Move fetches to Server Components, pass data as props
[ ] Missing error.tsx and loading.tsx for routes with async data
[ ] generateMetadata() missing on public-facing pages (SEO impact)
[ ] Images not using next/image (unoptimized, layout shift)
[ ] Links using <a href> instead of next/link (full page reload)
[ ] Environment variables exposed: NEXT_PUBLIC_ prefix check
    — Any secret without NEXT_PUBLIC_ is safe server-side; verify this is intentional
```

### Supabase
```
[ ] N+1 queries — loop that calls supabase inside .map()
    Fix: Single .select('*, relation(*)') with join syntax
[ ] Missing .limit() on unbounded queries that could return thousands of rows
[ ] Optimistic UI without rollback on error
[ ] Realtime subscriptions not unsubscribed in useEffect cleanup
[ ] Migration files that ALTER instead of creating new columns (data loss risk)
[ ] anon key used server-side where service role is needed
    — anon key respects RLS; service role bypasses it
```

### Stripe
```
[ ] Payment intent created but not confirmed in a single atomic flow
[ ] Webhook handler not idempotent (processes same event_id twice)
    Fix: Check event.id in DB before processing
[ ] Price IDs hardcoded instead of from environment variables
[ ] Customer ID not stored after checkout.session.completed
[ ] Failed payment not surfaced to the user (silent swallow)
```

### Vercel
```
[ ] Edge Runtime functions using Node.js APIs (fs, crypto, net)
    — Edge Runtime only supports Web APIs
[ ] Function timeout risk — DB queries in Serverless Functions > 10s
[ ] Missing CORS headers on API routes consumed by other origins
[ ] Build-time environment variables vs runtime (NEXT_PUBLIC_ at build, others at runtime)
```

---

## AI Slop Detection

### Code Slop
Patterns that indicate low-quality AI-generated code — flag for human review:

```
[ ] Overly defensive null checks on values that cannot be null in context
[ ] Copy-paste duplication across 3+ files with trivial variation
[ ] Functions longer than 80 lines with no single responsibility
[ ] Variable names: data, result, response, temp, item used as meaningful names
[ ] Comments that restate the code: // increment i by 1 → i++
[ ] useEffect with empty dependency array that uses stale closure values
[ ] try/catch that catches everything and logs nothing (silent failures)
[ ] "Just in case" setTimeout/sleep to fix race conditions
```

### UI/Design Slop
Patterns to flag in any JSX/TSX being reviewed:

```
[ ] Purple-to-blue gradient as a "hero" background — generic and dateless
[ ] Generic hero copy: "Transform Your Business" / "Streamline Your Workflow" / "Unlock Potential"
[ ] Everything centered on mobile AND desktop — no visual rhythm
[ ] Excessive border-radius (rounded-3xl or rounded-full on non-pill elements)
[ ] 3-column icon grid as the sole representation of features
[ ] Placeholder stock photo alt text: "Hero image" / "Team photo"
[ ] Gradient text on gradient background (illegible)
[ ] Loading spinner with no skeleton — abrupt content jumps
```

---

## Pre-Landing Checklist (Run in Order)

```
[ ] 1. Secrets scan — no hardcoded credentials (CRITICAL gate)
[ ] 2. Build passes — npm run build in the app directory, zero TypeScript errors
[ ] 3. RLS enabled on every new/modified Supabase table
[ ] 4. Stripe webhook signature verified (if webhook handler changed)
[ ] 5. Auth check present on every new API route and server action
[ ] 6. No console.log in production paths (auto-fix)
[ ] 7. No unused imports (auto-fix)
[ ] 8. N+1 query check on any new data-fetching code
[ ] 9. Error states handled in UI (no unhandled promise rejections reaching users)
[ ] 10. Mobile-responsive (new UI components checked at 375px width)
[ ] 11. AI slop check on any new UI copy or component structure
[ ] 12. Edge cases: empty state, loading state, error state all accounted for
```

---

## Report Format

After completing the review, output this exact structure:

```
## Code Review Report

**Files reviewed:** [N]
**Auto-fixed:** [N issues] — [brief list]
**Confidence score:** [0-100]%

### CRITICAL [count]
- [File:line] — [issue] — [fix or question]

### HIGH [count]
- [File:line] — [issue] — [fix or question]

### MEDIUM [count]
- [File:line] — [issue] — [fix or question]

### LOW [count]
- [File:line] — [issue] — [auto-fixed or noted]

### Questions for CC [count]
1. [Specific judgment call with context and the two options]
2. ...

### Verdict
[APPROVED — safe to merge]
[APPROVED WITH CONDITIONS — fix HIGH items first]
[BLOCKED — CRITICAL issues must be resolved]
```

**Confidence score logic:** Start at 100. Subtract 25 per CRITICAL, 10 per HIGH, 3 per MEDIUM, 1 per LOW. Cap floor at 0.

---

## Integration

- Load this skill before any `/ship` command execution
- Run after `npm run build` passes, not before
- Questions for CC → answer before merge, not after
- See `skills/requesting-code-review/SKILL.md` for sub-agent dispatch pattern
- See `skills/receiving-code-review/SKILL.md` for how to handle feedback

## Post-Review Validator Gate

After producing the report above and before declaring the review "done", spawn the Validator subagent (`subagent_type: validator`, defined in `.claude/agents/validator.md`) with:

- **GOAL** — "Validate the pre-landing code-review findings before merge."
- **SUCCESS CRITERIA** — every CRITICAL/HIGH item the report claims is auto-fixed actually shows the fix in the working tree; every flagged file path exists; every remaining issue references a real file:line.
- **DECLARED SCOPE** — the file paths covered by the review (from `git diff origin/main...HEAD --stat`).
- **Result Schema input** — pass the structured report (CRITICAL/HIGH/MEDIUM/LOW counts, auto-fixed list, confidence_score, files_reviewed).

The Validator returns `validation_score` (0-100) and `verdict`:

- `REJECT` (<70) → re-run the review on the failing scope; do NOT surface the report to CC as final.
- `WARN` (70-84) → surface with caveats ("validation score 76 because: …").
- `APPROVE` (≥85) → report is trustworthy, hand off to ship/commit.

This gate is mandatory when the code-review was spawned as a parallel sub-agent (per `brain/ORCHESTRATION.md` §Validator Pattern). It is optional but recommended on inline reviews — fast, read-only, and catches hallucinated "auto-fixed" claims.

## Obsidian Links
- [[skills/INDEX.md]] | [[brain/CAPABILITIES]]
