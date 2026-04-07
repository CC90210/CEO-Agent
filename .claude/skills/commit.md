---
name: commit
description: Smart git commit with conventional format (bravo: type — desc). Auto-stages relevant files, generates commit message from diff, excludes .env files.
user-invocable: true
---

# /commit — Smart Conventional Commit

## Steps

1. Run `git status` to see all changes.

2. Run `git diff --cached` and `git diff` to understand what changed.

3. Check for dangerous files — NEVER stage:
   - `.env`, `.env.*`, `.env.agents`
   - Any file containing API keys or tokens
   - `.obsidian/` config files (Obsidian manages these)

4. Stage relevant files:
   - `git add [specific files]` — prefer explicit file names over `git add -A`

5. Generate commit message in conventional format:
   ```
   bravo: [type] — [short description of what and why]
   ```
   Types: `feat`, `fix`, `refactor`, `chore`, `docs`, `style`, `perf`

6. Commit with Co-Authored-By:
   ```bash
   git commit -m "$(cat <<'EOF'
   bravo: type — description

   Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
   EOF
   )"
   ```

7. Show `git log --oneline -3` to confirm.

Do NOT push unless CC explicitly asks.
