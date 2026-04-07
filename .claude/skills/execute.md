---
name: execute
description: Execute an implementation plan step by step with validation gates. Loads plan from .agents/plans/, runs tasks in batches, reports for review between batches.
user-invocable: true
---

# /execute — Plan Execution Engine

Load `skills/executing-plans/SKILL.md` for the full execution protocol.

## Steps

1. Ask CC which plan to execute (or auto-detect the most recent in `.agents/plans/`).

2. Read the plan file and review critically — flag any concerns before starting.

3. Execute in batches of 3 tasks:
   - Mark each task `in_progress` before starting
   - Follow each step exactly (plan has bite-sized steps)
   - Run all verification commands
   - Mark `completed` when done

4. After each batch, report:
   - What was implemented
   - Verification output
   - "Ready for feedback."

5. Apply any feedback from CC, then continue to next batch.

6. After all tasks complete, run the finishing-a-development-branch skill.
