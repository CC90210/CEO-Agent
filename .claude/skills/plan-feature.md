---
name: plan-feature
description: Deep codebase analysis leading to a comprehensive implementation plan. Analyzes architecture, identifies dependencies, creates phased TDD plan saved to .agents/plans/.
user-invocable: true
---

# /plan-feature — Implementation Planning

## Steps

1. Ask CC for the feature description, target app, and any constraints.

2. Identify the target app from `brain/APP_REGISTRY.md` and `cd` to its path.

3. **Deep Analysis** — Read the codebase to understand:
   - Current architecture and file structure
   - Existing patterns and conventions
   - Database schema (if applicable)
   - API routes and data flow
   - Related components and dependencies

4. Load `skills/writing-plans/SKILL.md` for the plan format.

5. Generate a comprehensive implementation plan with:
   - Bite-sized tasks (2-5 min each)
   - TDD cycle per task (RED → GREEN → REFACTOR)
   - Exact file paths for every change
   - Complete code snippets (not pseudocode)
   - Verification commands with expected output

6. Save to `.agents/plans/YYYY-MM-DD-<feature-name>.md`.

7. Present to CC for review. Offer execution options:
   - **Subagent-Driven** (this session) — fresh subagent per task
   - **Parallel Session** (separate) — batch execution with checkpoints
