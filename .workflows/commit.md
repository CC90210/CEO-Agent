---
description: Smart git commit with conventional format and staged file analysis
---
// turbo-all

# Commit Command

## What This Command Does
Analyzes the currently uncommitted and unstaged changes, formats a clear conventional commit message, runs integrity checks, and prepares the repository for a push.

## When to Use
Use `/commit` when completing a feature, bug fix, task, or session. 

## How It Works / Steps

1. Run `git status --short` to see what's changed.
2. Run `git diff --stat` to see the scope of changes.

3. **PRE-COMMIT INTEGRITY CHECKS** (MANDATORY):

   **a) Referential Integrity Scan:**
   If any `.md` files were deleted or renamed in this commit:
   - For EACH deleted/renamed file, run: `grep -rn "filename" --include="*.md"` across the project root
   - If ANY stale references are found → FIX THEM before committing
   - Run the grep again to verify zero hits
   - Log: "Referential integrity: [X] stale refs found and fixed" or "clean"

   **b) Capability Count Verification:**
   If any agents, skills, or workflows were added/removed:
   - Count actual files: `dir agents\*.md`, `dir .agents\workflows\*.md`
   - Compare against `brain/CAPABILITIES.md` and `README.md`
   - Fix any mismatches

   **c) Secret Scan:**
   - Run `grep -rn "sk-\|sk_live\|whsec_\|eyJ" --include="*.md" --include="*.json" --include="*.js" --include="*.ts"` on staged files
   - If ANY secrets found → ABORT and alert CC

4. Analyze the changes and generate a conventional commit message:
   - Format: `bravo: type — description`
   - Types: `feat`, `fix`, `refactor`, `docs`, `config`, `content`, `chore`
   - Keep description under 72 chars
5. Stage the appropriate files:
   - Run `git add [files]` — stage only relevant files, not junk
   - **CRITICAL:** NEVER stage `.env`, `.env.agents`, or files with secrets
6. Show CC the proposed commit message and staged files. Wait for approval.
7. Run `git commit -m "[message]"`.
8. Report: "Committed: [message] — [X] files changed. Integrity checks: passed."
9. Ask CC if they want to push (NEVER push to main/master directly — create a branch or PR if applicable).

## Example Usage
**User:** `/commit`
**Agent:** 
1. Runs git status and diff. 
2. Runs integrity checks (referential scan, count verification, secret scan).
3. Proposes `bravo: feat — added real-time notifications for market resolution`
4. Awaits approval before staging and committing.
