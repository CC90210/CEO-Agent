---
last_updated: 2026-05-14
author: Bravo (Claude Opus 4.7)
scope: end-of-phases retrospective for the Phase 0–4 rearchitecture
status: durable — reference for future multi-phase work
---

# OASIS Rearchitecture — End-of-Phases Retrospective

Five phases (0 through 4), ~16 commits, ~10,000 net lines across two apps,
one Supabase project, three database migrations. Everything `main`,
everything deployed, no rollbacks. Worth recording what actually
worked and what bit us so the next multi-phase epic moves faster.

## What worked

**Phased + waved commit structure held up.** Splitting each phase into
2–3 atomic waves (2a/2b/2c/...) meant every commit was independently
shippable to production. Vercel got a clean build between every wave;
the dashboard never showed half-finished features. The "one big mega
commit" temptation was real (especially Phase 2) — resisting it paid off.

**Hard pre-phase audits caught 4 real bugs.** Between Phase 2 and
Phase 3 I stopped to look back and found: layout slug detection only
recognised seeds (DB-only tenants would 404), cross-tenant write guard
was missing on /api/manifest/[slug] POST, wizard let any user overwrite
seed slugs, and admin gate locked out first-time signups. None would
have been caught by build / typecheck / smoke probes — only by reading
the code with adversarial intent. Committed as `41859a7` before Phase 3.
Pattern is repeatable.

**Manifest seeds in TypeScript, not JSON, paid off twice.** Once when
the schema evolved between phases (tsc caught every drift); again when
the wizard finalizer composed manifests through real mutator calls
(typed input → typed output). JSON would have silently shipped invalid
manifests.

**Reusing existing infrastructure beat rebuilding it.** The AI editor
chat (Phase 2) reuses `streamChat` from `lib/providers`. The agent chat
(Phase 3) does the same. Both pick up the tenant's encrypted provider
key from `agent_model_config` automatically. Zero new provider
integration code in two whole phases — the seam was already there.

**The 87-assertion `release-check.js` suite caught regressions
implicitly.** Every wave I extended it (now at 93 OK across desktop +
phase 4). When the marketplace/build rename broke, the suite still
passed because the assertion was on bundle wiring, not the renamed
route — that was a coverage gap, but every assertion that DID exist
held. Worth keeping the discipline of "every new module gets a check."

## What bit us

**The `build/` gitignore collision.** Named a route
`/t/[slug]/marketplace/build/page.tsx`; the repo's root `.gitignore`
line 151 has `build/` (intended for build artifacts) which silently
matched. `git add` quietly dropped the file. The route compiled from
disk via `npm run build` but never reached GitHub. Caught after pushing
because `npx vercel ls` reported the deployment but the route would
404. Cost: commit `22d4980` to rename to `marketplace/new`.

  **Lesson:** before creating any new app route, run
  `git check-ignore <path>` — instant. Bracketed-path globs (`[slug]`)
  also need `--literal-pathspecs` or PowerShell single-quoting; bash
  treats them as character classes.

**SemVer comparison hand-rolled wrong.** First `compareVersions` sorted
`0.1.0-alpha` as *newer* than `0.1.0` — opposite of SemVer §11.4.
Caught only when I deliberately walked the function during the
diagnostic review. Replaced with a §11-compliant comparator + 13-case
unit test.

  **Lesson:** prefer importing a battle-tested SemVer lib, OR write
  the unit test in the same commit as the helper. The 2 minutes to
  write 13 cases would have caught it instantly.

**Cross-tenant guards duplicated, then drifted.** The "this slug
belongs to another tenant" check was hand-rolled into 3 routes
(`/api/manifest/[slug]`, `/api/manifest/chat`,
`/api/onboarding/wizard`). By the time I extracted `lib/manifest/
guards.ts`, the error reason strings were already slightly different
between the two manifest routes — drift had started.

  **Lesson:** when the SECOND copy of a check shows up, that's the
  signal to extract — not the third. The bar is "duplicated security
  logic in two places," not "duplicated logic in three places."

**TypeScript types didn't enforce mutator constraints.** Mutator
`updateAgent.changes` was `Partial<Omit<ManifestAgentBinding, "slug">>`
which included `model_override`, even though the runtime explicitly
dropped it. AI could see the field in the type, propose changes,
parser accepted, mutator no-op'd. Fixed to `Omit<..., "slug" |
"model_override">`.

  **Lesson:** every "the runtime silently ignores this field" needs
  the field omitted from the TYPE first. Compile-time enforcement
  beats runtime ignoring every single time.

**Parallel sub-agent dispatch for the diagnostic review didn't deliver.**
Asked 4 reviewer agents to do focused adversarial passes. All 4
finished, all 4 self-rejected their own stop hooks, all 4 returned
only meta-acknowledgments. SendMessage couldn't unstick them.
The actual findings stayed trapped in transcripts I couldn't read.
Codex via `codex-companion.mjs` produced 0 bytes — script path either
not wired or needed interactive auth.

  **Lesson:** the agent-orchestrated review flow has reliability
  issues I can't debug from here. For genuinely independent eyes on
  security-critical scopes, plan for direct human review. The
  parallel-agent dispatch is good for read-only exploration, not for
  audit reporting.

**Auto-promotion patterns are racy by default.** Wizard's "first user
becomes owner" was a SELECT then UPDATE pattern. Two simultaneous
wizards for the same tenant both pass the SELECT, second UPDATE
collides with the partial unique index. Original code didn't catch
the Postgres 23505. Fix: catch 23505 → ignore (first user won, that's
correct), log other errors as warn, never fail the wizard response.

  **Lesson:** any "if no X exists, create X" pattern must let the
  DB constraint be the authority, with application-level error
  handling for the violation. Pre-checking the absence is a hint,
  not a contract.

**Prompt injection via tenant data wasn't on my Phase 3 threat model.**
`{{tenant.brand.name}}` interpolated raw into agent system prompts.
Today the surface is self-attack (operator controls their own brand);
the moment marketplace ships public custom agents running against
arbitrary tenants' brand context, this is a real lateral exposure.
Now sanitised: cap 240 chars, strip control chars, strip code-fence
markers, strip prompt-style headers ("SYSTEM:", "ASSISTANT:", "###").

  **Lesson:** every tenant-controlled string that lands in a prompt
  needs defensive sanitisation, not just escaping. The threat surface
  expands the moment cross-tenant features ship.

## What I'd do differently next epic

1. **Write security tests in the SAME commit as the endpoint.** Not in
   a hardening pass. The Phase 2 hardening commit caught 4 things that
   would have been blocked at commit time by `route.test.ts` files —
   would have been instead "would-have-been-blocked-at-PR-time" if PRs
   existed here.

2. **Run `git check-ignore` on every new path.** The `build/` collision
   cost one commit. The fix is one command. There's no excuse for it
   happening twice.

3. **Schedule a diagnostic review at the END of every phase, not when CC
   asks.** This epic the review was CC-prompted and surfaced 9 real
   findings (1 medium race, 1 medium semver, 1 medium prompt injection,
   plus 6 LOW). At least 3 of those would have shipped to clients
   without the prompt. Bake it in as a phase-completion criterion.

4. **Treat the "tie the bow" phase as planned, not optional.** This
   commit (`f4ebd60` + the one shipping with this retrospective) wasn't
   in the original 5-phase plan. Real engineering always has a wrap-up
   beat. Allocate the time upfront so it doesn't compete with phase
   work.

5. **Prefer compile-time enforcement of "don't touch this" over runtime
   ignoring.** The `model_override` lesson generalises: every "I'm
   intentionally not handling this field" comment is also a "but the
   AI / future code / refactor will think it's valid." Omit from the
   type and the comment can come out.

6. **Sanitise tenant-controlled strings before they hit prompts, by
   default.** Don't make the threat model the gate. Every interpolation
   site gets a sanitiser; the sanitiser can be a no-op for trusted
   inputs, but the call sites all go through it.

7. **For high-stakes scopes, manual review beats agent review.** Use
   sub-agents for read-only exploration and code search — they're
   reliable there. Don't use them as the only audit channel for
   security boundaries. Plan for a human pass before any paying client
   touches the surface.

## Concrete next-epic checklist

When the next multi-phase epic starts:

- [ ] Run `git check-ignore` on each new app/* path before considering
      it staged
- [ ] Bracketed-path file operations use `--literal-pathspecs` or
      PowerShell single-quoting
- [ ] Every new write-endpoint has a cross-tenant test case in the
      same commit
- [ ] Every new helper that does comparison / parsing / sanitisation
      has unit tests written before the call site
- [ ] Every phase ends with a written diagnostic review (not just a
      smoke probe) before the next phase starts
- [ ] Every tenant-controlled string that lands in a prompt goes
      through a sanitiser
- [ ] Compile-time enforcement (`Omit`/branded types) preferred over
      runtime ignoring
- [ ] `release-check.js` gets new assertions for every new module
      before the next commit
