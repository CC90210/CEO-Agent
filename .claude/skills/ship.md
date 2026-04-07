---
name: ship
description: Full shipping pipeline — sync, build, test, review, changelog, commit, PR, deploy verification. The complete path from code-ready to live-on-Vercel.
user-invocable: true
---

# /ship — Full Deployment Pipeline

Load `skills/ship/SKILL.md` for the complete 9-phase protocol.

## Quick Steps

1. Identify target app from `brain/APP_REGISTRY.md`, `cd` to its path.

2. Execute the 9-phase pipeline:
   - **Phase 1: Sync** — `git fetch origin`, `git rebase origin/main`
   - **Phase 2: Build** — `npm run build` (zero TypeScript errors)
   - **Phase 3: Tests** — `npm test` (fix failures, don't comment out)
   - **Phase 4: Code Review** — run `/review` workflow
   - **Phase 5: Changelog** — generate CHANGELOG.md entry from diff
   - **Phase 6: Version Bump** — patch/minor bump if versioning is tracked
   - **Phase 7: Commit & Push** — conventional format, no .env files
   - **Phase 8: Pull Request** — create via `gh pr create`
   - **Phase 9: Post-Ship Verification** — check Vercel deploy, test in production

3. Each phase has a gate. If a gate fails, stop and surface the issue.

4. Log the ship to `memory/SESSION_LOG.md`.

5. Return the PR URL to CC.
