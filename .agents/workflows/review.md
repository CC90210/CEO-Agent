---
description: Run pre-landing code review with Fix-First methodology
---

## Steps

1. Identify the target app from `brain/APP_REGISTRY.md` and `cd` to its local path.

2. Load `skills/code-review/SKILL.md` for the full review protocol.

3. Check what's changed:
   ```bash
   git diff origin/main...HEAD --stat
   git diff origin/main...HEAD
   ```

4. Run the Pre-Landing Checklist (from code-review skill):
   - Secrets scan
   - Build verification (`npm run build`)
   - RLS check on new Supabase tables
   - Auth check on new API routes
   - N+1 query check
   - AI slop check
   - Mobile responsiveness check

5. Auto-fix mechanical issues (dead code, unused imports, console.log).

6. ASK CC about judgment calls (security, architecture, business logic).

7. Output the Code Review Report (severity-classified findings).

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/CAPABILITIES]]
