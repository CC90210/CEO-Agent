---
description: Debug a problem systematically — reproduce, diagnose, fix, verify
---
// turbo-all

# Debug Command

## What This Command Does
Enforces a highly systematic debugging loop. It stops you from guessing by forcing you to reproduce the error, analyze the logs, form hypotheses, implement fixes, verify, and write post-mortem documentation.

## When to Use
Use `/debug` whenever something is broken, failing to build, or not working as expected.

## How It Works / Steps

1. **Understand the problem** — Ask CC or read the error message. What's expected vs. actual behavior?
2. **Check known issues** — Read `memory/MISTAKES.md` and `memory/PATTERNS.md` for similar past bugs.
3. **Reproduce** — Run the failing command or navigate to the failing page. Capture the exact error.
4. **Diagnose** — Use the systematic debugging skill:
   - Read the relevant source files
   - Check logs (terminal output, browser console via Playwright)
   - Search for the error message in codebase with `grep_search`
   - Generate 2-3 hypotheses for root cause
5. **Fix** — Implement the fix for the most likely hypothesis. Edit files directly.
6. **Verify** — Re-run the failing command/test to confirm the fix works.
7. **Document** — If this was a non-obvious bug:
   - Add pattern to `memory/PATTERNS.md` (tag `[PROBATIONARY]`)
   - Add to `memory/MISTAKES.md` if it was a mistake we should avoid repeating
8. Report: "Fixed: [description]. Root cause: [cause]. Verified: [how]."

## Example Usage
**User:** `/debug The post_create MCP command is failing for LinkedIn.`
**Agent:** Proceeds to read recent execution logs, reproduces failure directly, analyzes the API difference, suggests fix, fixes it, and documents the resolution.
