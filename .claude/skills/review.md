---
name: review
description: Pre-landing code review with Fix-First methodology. Auto-fixes mechanical issues, asks about judgment calls. Run before shipping any code.
user-invocable: true
---

# /review — Pre-Landing Code Review

Load `skills/code-review/SKILL.md` for the full review protocol.

## Quick Steps

1. Identify the target app from `brain/APP_REGISTRY.md` and `cd` to its local path.

2. Check what's changed:
   ```bash
   git diff origin/main...HEAD --stat
   git diff origin/main...HEAD
   ```

3. Run the Pre-Landing Checklist:
   - Secrets scan (grep for hardcoded keys)
   - Build verification (`npm run build`)
   - RLS check on new Supabase tables
   - Auth check on new API routes
   - N+1 query check
   - AI slop check
   - Mobile responsiveness check

4. Auto-fix mechanical issues (dead code, unused imports, console.log).

5. ASK CC about judgment calls (security, architecture, business logic).

6. Output the Code Review Report (severity-classified findings).

## Related

- [[.claude/skills/INDEX]]
- [[.claude/skills/codex-adversarial-review]]
- [[.claude/skills/codex-cancel]]
