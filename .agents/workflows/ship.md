---
description: Full shipping pipeline — test, review, changelog, PR, deploy verification
---

## Steps

1. Load `skills/ship/SKILL.md` for the full pipeline protocol.

2. Identify the target app from `brain/APP_REGISTRY.md` and `cd` to its local path.

3. Execute the 10-phase pipeline:
   - **Phase 1: Sync** — `git fetch origin`, `git rebase origin/main`
   - **Phase 2: Build** — `npm run build` (zero TypeScript errors)
   - **Phase 3: Tests** — `npm test` (fix failures, don't comment out)
   - **Phase 4: Code Review** — run `/review` workflow
   - **Phase 4.5: Validator Gate** — spawn `subagent_type: validator` to score the review (REJECT <70 blocks push)
   - **Phase 5: Changelog** — generate CHANGELOG.md entry from diff
   - **Phase 6: Version Bump** — patch/minor bump if versioning is tracked
   - **Phase 7: Commit & Push** — conventional format, no .env files
   - **Phase 8: Pull Request** — create via `gh pr create`
   - **Phase 9: Post-Ship Verification** — check Vercel deploy, test in production

4. Each phase has a gate. If a gate fails, stop and surface the issue.

5. Log the ship to `memory/SESSION_LOG.md`.

6. Return the PR URL to CC.

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/CAPABILITIES]]
