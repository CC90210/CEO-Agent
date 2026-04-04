---
name: e2e-testing
description: Comprehensive end-to-end application testing using Playwright MCP. Launches parallel sub-agents to research the codebase, then systematically tests every user journey with screenshots, database validation, and bug hunting. Run after implementation to validate before commit.
triggers: [end-to-end, E2E, user journey, integration test, full test, playwright test]
tier: standard
dependencies: [browser-automation, systematic-debugging]
---

# End-to-End Application Testing

## Pre-flight Check

### 1. Application Check
Verify the application has a browser-accessible frontend:
- Check package.json for dev/start script
- Check for frontend framework files (pages/, app/, src/components/)
- Identify the dev server URL and port

### 2. Playwright MCP Check
Verify Playwright MCP is connected:
```
browser_navigate url="about:blank"
```
If this fails, check `.claude/mcp.json` for Playwright server config.

## Phase 1: Parallel Research (3 Sub-agents)

Launch THREE sub-agents simultaneously using the Agent tool:

### Sub-agent 1: Application Structure & User Journeys
Research and return:
1. How to start the application (exact commands, URL, port)
2. Authentication flow (test credentials from .env.example, seed data, or sign-up flow)
3. Every user-facing route/page (URL path + what it renders)
4. Every user journey (complete flows with steps, interactions, expected outcomes)
5. Key UI components (forms, modals, dropdowns, toggles)

### Sub-agent 2: Database Schema & Data Flows
Research and return:
1. Database type and connection (from .env.example — NEVER read .env directly)
2. Full schema (tables, columns, types, relationships)
3. Data flows per user action (what records are created/updated/deleted)
4. Validation queries (exact SQL to verify records after each action)
Use Supabase MCP if the project uses Supabase.

### Sub-agent 3: Bug Hunting
Analyze codebase for:
1. Logic errors (incorrect conditionals, off-by-one, missing null checks, race conditions)
2. UI/UX issues (missing error handling, no loading states, broken responsive layouts)
3. Data integrity risks (missing validation, potential orphaned records, cascade behavior)
4. Security concerns (SQL injection, XSS, missing auth checks, exposed secrets)
Return prioritized list with file paths and line numbers.

**Wait for ALL THREE to complete before proceeding.**

## Phase 2: Start the Application
Using Sub-agent 1's startup instructions:
1. Install dependencies if needed (`npm install`)
2. Start dev server in background (`npm run dev &` or equivalent)
3. Wait for server to be ready
4. Navigate with Playwright: `browser_navigate url="http://localhost:PORT"`
5. Verify it loads: `browser_snapshot`
6. Take initial screenshot: `browser_take_screenshot filename="e2e-screenshots/00-initial-load.png"`

## Phase 3: Create Task List
Using journeys from Sub-agent 1 and findings from Sub-agent 3:
- Create a TodoWrite task for each user journey
- Add final task: "Responsive testing across viewports"

## Phase 4: User Journey Testing

For each journey, mark as in_progress, then execute:

### 4a. Browser Testing with Playwright MCP
```
browser_navigate        url="<page URL>"
browser_snapshot        → Get element refs
browser_click           ref="<ref>" element="<description>"
browser_type            ref="<ref>" text="<input>"
browser_fill_form       fields=[...]
browser_press_key       key="Enter"
browser_wait_for        text="Expected result"
browser_take_screenshot filename="e2e-screenshots/{journey}/{step}.png"
browser_console_messages level="error"  → Check JS errors
```

**CRITICAL:** Refs become invalid after navigation or DOM changes. ALWAYS re-snapshot after:
- Page navigation
- Form submissions
- Dynamic content updates (modals, tabs, theme changes)

For each step in a journey:
1. `browser_snapshot` to get current refs
2. Perform the interaction
3. `browser_wait_for` page to settle
4. `browser_take_screenshot` (save to `e2e-screenshots/{journey-name}/{step}.png`)
5. Analyze screenshot with Read tool — check visual correctness, UX issues
6. Check `browser_console_messages` periodically for JS errors

**Test EVERY interaction, EVERY form field, EVERY button.**

### 4b. Database Validation
After any data-modifying interaction:
1. Query the database to verify records:
   - Supabase: Use `mcp__supabase__execute_sql` with the project_id
   - Other: Write and run ad-hoc query script
2. Verify: records created/updated/deleted as expected, values match UI input, relationships correct

### 4c. Issue Handling
When an issue is found:
1. Document: expected vs actual, screenshot path, relevant DB query results
2. Fix the code directly
3. Re-run the failing step to verify fix
4. Take new screenshot confirming fix

### 4d. Responsive Testing
Revisit key pages at three viewports:
```
browser_resize width=375 height=812     → Mobile (iPhone)
browser_resize width=768 height=1024    → Tablet (iPad)
browser_resize width=1440 height=900    → Desktop
```
Screenshot every major page. Analyze for layout issues, overflow, broken alignment.

After completing each journey, mark task as completed.

## Phase 5: Cleanup
1. Stop the dev server background process
2. `browser_close`

## Phase 6: Report

```
## E2E Testing Complete

**Journeys Tested:** [count]
**Screenshots Captured:** [count]
**Issues Found:** [count] ([count] fixed, [count] remaining)

### Issues Fixed During Testing
- [Description] — [file:line]

### Remaining Issues
- [Description] — [severity: high/medium/low] — [file:line]

### Bug Hunt Findings (from code analysis)
- [Description] — [severity] — [file:line]

### Screenshots
All saved to: `e2e-screenshots/`
```

## Skills Integration
- **Use:** skills/browser-automation for Playwright MCP reference
- **Use:** skills/systematic-debugging for any bugs found
- **Use:** skills/verification-before-completion before claiming tests pass

## Obsidian Links
- [[skills/INDEX]] | [[brain/CAPABILITIES]]
