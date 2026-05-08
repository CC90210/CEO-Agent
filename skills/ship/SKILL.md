---
name: ship
description: Full deployment pipeline for any app in the registry. Use when CC says "ship it", "deploy", "push this live", or "/ship". Handles sync, tests, code review, changelog, PR, and post-ship verification in sequence.
triggers: [ship, deploy, push live, release, go live, ship it]
tier: standard
dependencies: [verification-before-completion, code-review, finishing-a-development-branch]
disable-model-invocation: true
---

# Ship — Full Deployment Pipeline

## Overview

One command to go from "code is ready" to "live on Vercel with a PR and changelog entry." Eliminates the 15-step mental checklist that causes mistakes under pressure.

**Core principle:** Every step has a gate. If the gate fails, stop and surface the issue. Never silently continue past a failure.

**Announce at start:** "Running ship pipeline for [app name]."

---

## Prerequisites

1. Identify the target app from @brain/APP_REGISTRY.md
2. `cd` to the app's local path
3. Confirm you are NOT on `main` — if on main, create a feature branch first:
   ```bash
   git checkout -b feat/[short-description]
   ```

---

## Phase 1: Sync

Get clean with the upstream.

```bash
git fetch origin
git status
```

**Gate:** Are there uncommitted changes?
- YES → Stash (`git stash`) or commit them before proceeding. Ask CC which.
- NO → Continue.

```bash
git rebase origin/main
```

**Gate:** Rebase conflicts?
- YES → Resolve conflicts, `git rebase --continue`, then continue pipeline.
- NO → Continue.

---

## Phase 2: Build Verification

```bash
npm run build
```

**Gate:** Build errors?
- YES → Stop. Fix TypeScript errors and type failures before proceeding. Do not skip.
- NO → Continue.

---

## Phase 3: Tests

```bash
# Run tests if they exist
npm test 2>/dev/null || echo "No test suite found"
```

**Gate:** Test failures?
- YES → Fix failing tests. If tests are legitimately outdated (covered by new behavior), delete the old test and write a new one. Do not comment tests out.
- NO / No test suite → Continue. Note "No automated tests" in the PR description.

---

## Phase 4: Code Review

Load `skills/code-review/SKILL.md` and run the full pre-landing review on the diff since branching from main:

```bash
git diff origin/main...HEAD --stat
git diff origin/main...HEAD
```

**Gate:** CRITICAL or HIGH issues found?
- YES → Resolve all CRITICAL and HIGH items. Re-run build. Then continue.
- Questions for CC → surface them now, wait for answers before proceeding.
- NO → Continue.

---

## Phase 4.5: Validator Gate

Spawn the Validator subagent (`subagent_type: validator`, defined in `.claude/agents/validator.md`) with:

- **GOAL** — the one-sentence ship objective
- **SUCCESS CRITERIA** — code review passed; build green; no secrets staged; the specific feature works end-to-end
- **DECLARED SCOPE** — file paths from `git diff origin/main...HEAD --stat`
- **Result Schema input** — the code-review report from Phase 4 (findings, severity counts, auto-fixed list, confidence)

The Validator returns `validation_score` (0-100) and `verdict` (APPROVE / WARN / REJECT).

**Gate:**
- `verdict: REJECT` (score < 70) → STOP. Do not push. Re-run the failing review step. Surface the validator's `failure_reasons` to CC.
- `verdict: WARN` (70-84) → Surface caveats to CC ("validation score 76 because: …"). Wait for explicit go-ahead before push.
- `verdict: APPROVE` (≥85) → Continue.

This gate exists because code-review finds problems; the Validator confirms the fixes actually landed and didn't introduce new ones. Closes Anthropic's "Observability-Evaluation Gap" (per `brain/ORCHESTRATION.md` §Validator Pattern).

---

## Phase 5: Changelog Entry

Generate a human-readable entry for `CHANGELOG.md` (or create it if absent):

```
## [YYYY-MM-DD] — [App Name]

### Added
- [User-facing feature in plain language]

### Fixed
- [Bug fixed and what it was causing]

### Changed
- [Behavioral change and why]

### Technical
- [Internal refactor, dependency update, infrastructure change]
```

Write the entry. Do not ask CC to write it — generate it from the diff and ask only if the intent is unclear.

---

## Phase 6: Version Bump (If Applicable)

Check if the app has a `package.json` with a `version` field that is tracked:

```bash
cat package.json | grep '"version"'
```

If versioning is in use (PropFlow, Nostalgic Requests, OASIS Platform):
- Patch bump for bug fixes: `1.2.3 → 1.2.4`
- Minor bump for new features: `1.2.3 → 1.3.0`
- Major bump for breaking changes: ask CC first

```bash
npm version patch --no-git-tag-version  # or minor
```

If the app has no tracked version or uses Vercel auto-deploy (most apps), skip this phase.

---

## Phase 7: Commit and Push

Stage all changes:

```bash
git add -A
git status  # Verify no .env files are staged
```

**Gate:** `.env`, `.env.local`, `.env.agents`, or any credential file staged?
- YES → `git reset HEAD [file]` immediately. Add to `.gitignore` if missing.

Commit using conventional format:

```bash
git commit -m "$(cat <<'EOF'
bravo: [feat|fix|refactor|chore] — [short description of what and why]

[Optional: 1-2 sentences of context if the commit message alone is unclear]

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

Push to remote:

```bash
git push origin [branch-name] -u
```

---

## Phase 8: Pull Request

Create the PR using the GitHub CLI:

```bash
export GH_TOKEN=$(grep GITHUB_PERSONAL_ACCESS_TOKEN /c/Users/User/Business-Empire-Agent/.env.agents | cut -d= -f2)

gh pr create --title "[App]: [short description]" --body "$(cat <<'EOF'
## What

[1-3 bullet points describing what was built or fixed]

## Why

[The business reason — what problem does this solve for CC or the user?]

## AI Effort Compression

| Task | Human Time Est. | CC Time (with Bravo) |
|------|----------------|----------------------|
| [Feature 1] | [e.g., 4 hrs] | [e.g., 12 min] |
| [Feature 2] | [e.g., 2 hrs] | [e.g., 5 min] |
| **Total** | **[X hrs]** | **[Y min]** |

## Test Plan

- [ ] [Specific manual check to verify the feature works]
- [ ] [Edge case to test]
- [ ] [Mobile check if UI changed]

## Checklist

- [ ] Build passes (`npm run build`)
- [ ] No hardcoded secrets
- [ ] RLS enabled on new tables (if any)
- [ ] Stripe webhook verified (if applicable)
- [ ] Mobile-responsive (if UI changed)

🤖 Shipped with [Bravo V5.5](https://github.com/CC90210/Business-Empire-Agent)
EOF
)"
```

Output the PR URL to CC.

---

## Phase 9: Post-Ship Verification

After Vercel deploys (usually 1-3 minutes after push):

```
[ ] Visit the production URL and verify the feature works end-to-end
[ ] Check Vercel dashboard for build/runtime errors
[ ] If Stripe or Supabase were touched: trigger one real test event
[ ] If content changed: verify it renders correctly on mobile
[ ] Check browser console for runtime errors on the affected page
```

If any post-ship check fails: create a hotfix branch immediately, do not push more changes to the broken branch.

---

## AI Effort Compression — How to Fill the Table

Estimate human developer time honestly (not optimistically). Include:
- Reading existing code to understand context: 30-60 min per unfamiliar file
- Writing the feature: 1x the actual implementation time
- Debugging: 1-2x the implementation time (realistic)
- Testing: 30-60 min
- PR write-up: 15-30 min

CC's time with Bravo includes: time to describe the task + time reviewing the output. Usually 5-20 minutes total.

The table is not marketing — it is an honest record of leverage. Log it so the pattern compounds.

---

## Failure Recovery

| Failure | Response |
|---------|----------|
| Build fails after sync | Fix TypeScript errors before any other step |
| Rebase conflict | Resolve manually, verify build again |
| Code review blocks | Fix issues, re-run code review phase only |
| PR creation fails (no GH_TOKEN) | Check `.env.agents` for GITHUB_PERSONAL_ACCESS_TOKEN |
| Vercel deploy fails | Check Vercel dashboard logs, treat as CRITICAL |
| Post-ship check fails | Hotfix branch immediately, do not continue shipping |

---

## Notes

- `gh.exe` is at `/c/Program Files/GitHub CLI/gh.exe` if not on PATH — use full path
- Always run from the app's repo directory, not Business-Empire-Agent
- Log the ship in `memory/SESSION_LOG.md` after completion
- The CHANGELOG entry goes in the app's repo, not Business-Empire-Agent

---

## Pre-Flight Checklist

Run this before Phase 7 (Commit and Push). Every item must be checked. No item is optional.

```
## Pre-Flight — [App Name] — [Date]

### Code Quality
- [ ] npm run build completes with zero errors (TypeScript strict)
- [ ] No console.log statements left in production code
- [ ] No TODO comments that block correctness (cosmetic TODOs are ok)
- [ ] No hardcoded secrets, API keys, or URLs (use grep to verify)

### Environment
- [ ] All required environment variables are documented in .env.example
- [ ] Any new env vars are added to Vercel dashboard for this app
- [ ] .env.local and .env.agents are NOT staged (git status confirms)

### Database (if Supabase was touched)
- [ ] Migrations have been run (if schema changed)
- [ ] RLS is enabled on any new tables
- [ ] New columns have appropriate NOT NULL constraints or defaults
- [ ] No raw SQL with string interpolation (use parameterized queries)

### Stripe (if payments were touched)
- [ ] Webhook signature verification is in place
- [ ] Idempotency key is used for any charge or subscription operation
- [ ] Test mode vs live mode env var is correct for this deployment

### UI / Frontend (if any UI changed)
- [ ] Mobile-responsive check (test at 375px width minimum)
- [ ] No layout overflow on small screens
- [ ] Loading and error states are handled (not blank screen)
- [ ] Accessibility: interactive elements are keyboard-navigable

### Tests
- [ ] npm test passes (or "No test suite" is explicitly noted in PR)
- [ ] New feature has at least one test covering the happy path
```

**Gate:** If any checked item fails → fix it before proceeding. Do not push with known failures.

---

## Rollback Plan

Every ship must have a defined rollback path documented before pushing. Fill this out as Phase 6.5 before the commit.

```markdown
## Rollback Plan — [Feature Name]

### Risk Assessment
**Blast radius:** [What breaks if this fails? Users affected? Revenue at risk?]
**Rollback window:** [How long before rollback becomes difficult? e.g., "Once 100+ users have new data, migration is painful"]

### Rollback Method (choose one)

**Option A — Git revert (fastest, cleanest)**
```bash
git revert [commit-hash]
git push origin main
```
Use when: Code-only change, no database migration.

**Option B — Feature flag disable**
```bash
# Set flag in Supabase or env var
FEATURE_X_ENABLED=false
# Redeploy
```
Use when: Feature is gated behind a flag.

**Option C — Database migration rollback**
```bash
# Run down migration
supabase db reset  # or specific rollback script
```
Use when: Schema was changed. Define the down migration BEFORE shipping the up migration.

**Option D — Vercel instant rollback**
```bash
vercel rollback [deployment-url]
```
Use when: Vercel deployment is broken. Rolls back to previous deployment in <30 seconds.

### Rollback Triggers (when to actually execute)
- [ ] Error rate spikes above 5% within 10 minutes of deploy
- [ ] Any CRITICAL feature (auth, payment, data write) is broken
- [ ] Monitoring alert fires within 30 minutes of deploy
- [ ] CC reports a user-facing issue that cannot be hotfixed in <15 minutes
```

---

## Deployment Verification Steps

After Vercel deploys (Phase 9 extended). This is not optional — a ship is not complete until verification passes.

### Smoke Test Checklist

Run these within 5 minutes of deploy completing.

```
[ ] Production URL loads without 500 error
[ ] The specific feature just shipped works end-to-end (one full happy path)
[ ] Login / auth still works (critical path — broken auth = total outage)
[ ] If any Supabase tables were touched: verify a read and write both succeed
[ ] Browser console shows no new errors (check DevTools → Console)
[ ] Network tab shows no new 4xx/5xx responses on page load
[ ] Mobile: open on phone or DevTools mobile emulation at 375px
```

### Monitoring Check (first 30 minutes post-deploy)

```
[ ] Vercel Functions: check runtime errors in Vercel dashboard → Functions tab
[ ] Supabase: check Database → Logs for any sudden spike in errors
[ ] If Stripe: check Stripe dashboard → Events for any failed webhook deliveries
[ ] Check browser console on 2-3 different pages (not just the new feature's page)
```

**If any smoke test fails:** Do not debug in production. Execute the rollback plan immediately, then debug in development.

---

## Changelog Auto-Generation

Generate the changelog entry from git log. Never write it from memory.

```bash
# Get all commits since last tag or since main diverged
git log origin/main...HEAD --oneline --no-merges

# Get files changed
git diff origin/main...HEAD --stat

# Get full diff for context
git diff origin/main...HEAD
```

Parse the commits to categorize:

| Commit prefix | Changelog category |
|--------------|-------------------|
| feat: / feat — | Added |
| fix: / fix — | Fixed |
| refactor: / refactor — | Changed (Technical) |
| chore: / chore — | Changed (Technical) |
| perf: | Changed (performance) |
| docs: | (skip unless user-facing) |

Write the entry in plain English — not commit message syntax. Translate for a non-technical reader.

**Example:**
```
Commits:
  bravo: feat — add Stripe webhook idempotency check
  bravo: fix — lead capture form not submitting on mobile Safari

Changelog entry:
  ## [2026-04-06] — CC Funnel

  ### Added
  - Stripe webhook processing now prevents duplicate charges if Stripe retries an event

  ### Fixed
  - Lead capture form now submits correctly on mobile Safari (was silently failing)
```

---

## Notification Protocol

After a successful ship, notify the right people through the right channel.

| Audience | Channel | What to Say |
|---------|---------|------------|
| CC (always) | Session output | "Ship complete. PR: [URL]. Verification: [passed/findings]." |
| Active client (if their feature shipped) | Email or preferred channel | Plain English: what changed and what they can now do |
| Adon (if PropFlow feature shipped) | Text/Slack | "PropFlow: [feature] is live. [1 sentence on what it does]." |
| No-one else | — | Don't notify users unless CC explicitly says to |

**Rule:** Never send a notification before verification passes. Announcing a broken feature is worse than announcing nothing.

---

## Obsidian Links
- [[skills/INDEX]] | [[brain/CAPABILITIES]] | [[skills/code-review/SKILL]] | [[skills/systematic-debugging/SKILL]]
