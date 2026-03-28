---
name: Knowledge Maintenance
trigger: /knowledge-maintenance
schedule: weekly (Sunday)
agent: documenter
dependencies: [memory-management, knowledge-management]
---

# Weekly Knowledge Maintenance Workflow

Keep the intelligence system clean, fresh, and useful. Stale knowledge compounds into bad decisions. This workflow runs every Sunday to prevent that.

## When to Run

- Manually via `/knowledge-maintenance` command
- Scheduled: every Sunday (before the week's first task)
- After any session where significant new information was captured

## Steps

### Step 1 — Session Log Compression

Check SESSION_LOG.md size:
```bash
wc -l memory/SESSION_LOG.md
```

If line count exceeds 200:
1. Identify all entries older than 14 days
2. Move them to `memory/ARCHIVES/sessions-YYYY-MM.md` (create file if it doesn't exist)
3. Keep the 10 most recent session entries in the active file
4. Verify the archive file was written correctly before truncating the active file
5. Log: "SESSION_LOG compressed: [N] entries archived to sessions-[YYYY-MM].md"

### Step 2 — Pattern Promotion

Read `memory/PATTERNS.md`. For each entry tagged `[PROBATIONARY]`:
1. Count how many sessions have referenced or applied this pattern
2. If 3+ verified uses across different sessions: remove `[PROBATIONARY]`, add `[VALIDATED]`
3. Update the confidence score to 0.85+ for validated patterns
4. Log any promotions: "[Pattern name] promoted from PROBATIONARY to VALIDATED"

For each entry tagged `[VALIDATED]` that hasn't been referenced in 60+ days:
1. Move to `memory/ARCHIVES/patterns-archive.md`
2. Log: "[Pattern name] archived — inactive 60+ days"

### Step 3 — Competitor Data Freshness Check

Read `data/competitors.json`. For each competitor:
1. Check the `last_checked` field
2. If older than 30 days: flag for update
3. Output a list of competitors that need re-checking

For each flagged competitor (if Playwright is available):
1. Navigate to their pricing page and check for changes
2. Update the `pricing`, `features`, and `notes` fields in competitors.json
3. Update `last_checked` to today's date

If Playwright is not available: output the list of stale competitors for CC to review manually.

### Step 4 — Mistakes Analysis

Read `memory/MISTAKES.md`. Look for recurring themes:
1. Are there 2+ entries with the same root cause? That is a systemic pattern.
2. For each systemic pattern found:
   - Draft a prevention SOP entry for `memory/SOP_LIBRARY.md`
   - Check if a hook could enforce the prevention automatically
3. Log: "Recurring mistake found: [name]. SOP drafted: [yes/no]."

### Step 5 — Long-Term Memory Confidence Audit

Read `memory/LONG_TERM.md`. For each fact:
1. Apply confidence decay based on days since `last_verified`:
   - 0-30 days: no decay
   - 31-60 days: confidence -= 0.1
   - 61-90 days: confidence -= 0.2
   - 90+ days: confidence -= 0.3 (cap floor at 0.1)
2. Flag any facts that have decayed below 0.5 (need re-verification)
3. Update confidence scores in the file
4. Log: "[N] facts audited, [N] flagged for re-verification"

### Step 6 — Active Tasks Cleanup

Read `memory/ACTIVE_TASKS.md`:
1. Remove any tasks marked `[DONE]` or `[COMPLETED]` that are older than 7 days
2. Flag any tasks with status `[IN PROGRESS]` that haven't been updated in 14+ days as `[STALE]`
3. For stale tasks: add a note asking CC to confirm if they should be continued, paused, or killed
4. Log: "[N] completed tasks removed, [N] tasks flagged as stale"

### Step 7 — Wiki-Link Integrity Check

For all files modified in the past 7 days (check with git log):
```bash
git log --oneline --since="7 days ago" --name-only | grep "\.md$" | sort -u
```

For each modified markdown file:
1. Extract all `[[wiki-links]]` from the file
2. Verify that the linked file exists at the expected path
3. Flag any broken links (linked file not found)
4. Fix any broken links where the target file exists at a different path

Log: "Wiki-link check: [N] files checked, [N] broken links found and [fixed/flagged]"

### Step 8 — brain/STATE.md Refresh

Read `brain/STATE.md` and verify each field reflects current reality:
1. Current MRR: does it match the latest Stripe data?
2. Active clients: does the count match the actual client list?
3. Current priorities: do they reflect what CC said in this week's sessions?
4. System health: any MCPs or tools broken this week that should be noted?

Update any stale fields. Log: "STATE.md refreshed: [N] fields updated"

### Step 9 — Template Library Review

Check `data/templates/` for templates used this week (search session log for template references):
1. Were any templates used and customized significantly in actual use?
2. If yes: update the template to reflect the real-world version
3. Remove sections that were always deleted
4. Add sections that were always added

Log: "[N] templates updated based on recent use"

### Step 10 — Maintenance Summary

Append to `memory/SESSION_LOG.md`:
```
### [DATE] — Weekly Knowledge Maintenance
- SESSION_LOG: [compressed N entries / no compression needed]
- Patterns: [N promoted to VALIDATED / no changes]
- Competitors: [N stale entries flagged / all current]
- Mistakes: [N recurring themes found / N SOPs drafted]
- LONG_TERM.md: [N facts audited, N flagged for re-verification]
- Active Tasks: [N cleaned up, N flagged as stale]
- Wiki-links: [N files checked, N broken links fixed]
- STATE.md: [N fields updated / no changes]
- Templates: [N updated]
```

## Output

A clean, current intelligence system. All stale data flagged. All patterns at the right validation level. All tasks either active or removed.

## Error Handling

- If any file cannot be read: log the error, skip that step, and flag for manual review
- If git log fails: skip Step 7, note that wiki-link check was skipped
- Never delete data without first verifying the archive write succeeded
