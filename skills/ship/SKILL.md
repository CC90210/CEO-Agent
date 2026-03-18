---
name: ship
description: Full deployment pipeline for any app in the registry. Use when CC says "ship it", "deploy", "push this live", or "/ship". Handles sync, tests, code review, changelog, PR, and post-ship verification in sequence.
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
