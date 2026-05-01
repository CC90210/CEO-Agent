---
tags: [mistakes, prevention]
---
# MISTAKES LOG
> [[brain/BRAIN_LOOP]] | [[memory/PATTERNS]] | [[memory/SELF_REFLECTIONS]]

### Took oasisai.work Down by Cycling Domain Between Vercel Projects (2026-04-30)
**Failure:** Tried to move `oasisai.work` from `oasis-ai-platform` Vercel project to `agent-dashboard` via API. Vercel issued a NEW verification TXT token at re-attach time (`cb267a1ec87c3860f900`) different from the one already in CF DNS (`a0b8da09e49fe01aaf4d,dc`). Domain failed verification on both projects. Marketing site went 404 with `DEPLOYMENT_NOT_FOUND` for the time it took CC to find their Cloudflare API token. **Root cause:** I assumed removing-then-re-adding a domain on Vercel would reuse its existing verification token. It does not — Vercel rotates the TXT token every detach/attach cycle. **Prevention:** never detach a Vercel domain without (a) having DNS write access ready, (b) a rollback plan that includes updating the TXT record. For multi-project domain ownership use `vercel domains transfer` (in CLI) which preserves verification, OR use Vercel rewrites to share a domain. **Recovery script (saved as `scripts/cloudflare_admin.py`):** read latest verification TXT from Vercel domain config, PUT it onto CF DNS at `_vercel.<apex>`, wait 8s, POST `/verify`. Worked first try.

### Misdiagnosed Cloudflare 403 as "Token Expired" (2026-04-30)
**Failure:** Inline Python urllib calls to api.supabase.com returned `HTTP 403, error code 1010`. I told CC their `SUPABASE_ACCESS_TOKEN` was expired and asked them to rotate it — twice. CC pushed back ("you literally used it an hour ago"). Re-tested with proper User-Agent header → 200 OK. The token was always fine. **Root cause:** Cloudflare in front of api.supabase.com rejects requests with the default `Python-urllib/3.x` UA (bot-protection error code 1010, NOT a Supabase auth-rejection). The pattern was ALREADY known in the codebase — `scripts/apply_migration.py` line 162 has the comment "Cloudflare in front of api.supabase.com blocks stock urllib user-agents" with a real UA set. I just didn't reuse it for inline `python -c` scripts. **Prevention:** never call the Supabase Management API from raw urllib without a real-browser UA. Always use `scripts/supabase_admin.py` (`api_get` / `api_patch` / `api_post`). It bakes in the UA + auth headers. CLI form: `python scripts/supabase_admin.py get /v1/projects/.../config/auth`. Cost: ~2 hours and a moment of CC frustration. Tag: `cloudflare-1010`, `wrong-diagnosis`.

### Codex CLI Stale — All Models Rejected (2026-04-25)
**Failure:** Tried to delegate Atlas + Maven install-chain ports via `codex-companion.mjs task`. Both spawned agents burned 5+ minutes apiece in retry loops because `@openai/codex@0.118.0` (currently installed) rejects every model alias the gateway exposes (gpt-5.5, gpt-5.4-codex, gpt-5.4-codex-mini, gpt-5-codex, gpt-5, spark, gpt-5.3-codex-spark) on the ChatGPT-account auth path. Bravo eventually killed both and executed inline. **Root cause:** `c:\Users\User\.claude\codex-plugin\scripts\codex-companion.mjs` MODEL_ALIASES map and the bundled CLI are both behind the upstream package's current model surface. **Prevention:** Before any future Codex delegation, run `codex --version && codex models 2>&1 | head -3` as a pre-flight. If version `< X` (track latest in `skills/codex-delegation/SKILL.md`) or model list is empty, run `npm i -g @openai/codex@latest` first OR Bravo handles inline. Tag this incident `delegation-path-dead` for retro pattern surfacing.

### Capability Regression from Optimization (2026-04-06)
**Systemic failure:** After CLAUDE.md compression (386→119 lines), QUICK_REFERENCE.md only documented 11 of 47 CLI tools. Agent tried to use `claude.ai Gmail` MCP instead of `google_tool.py` CLI. Root causes: (1) GWS missing from CLI routing list, (2) QUICK_REFERENCE.md was 75% incomplete, (3) ANTIGRAVITY.md still referenced dead MCPs, (4) no regression prevention protocol existed. **Prevention:** Created `brain/ORCHESTRATION.md` — governance doc with regression prevention protocol, tool hierarchy, and stress test checklist. QUICK_REFERENCE.md rebuilt with all 47 tools organized by intent. Rule 2 in CLAUDE.md rewritten to say "NEVER ask CC to authenticate anything". All 3 entry points synchronized. **The iron law: optimizing documentation must NEVER reduce routing accuracy.**

### Day-of-Week Hallucination (2026-04-04)
Said "Friday" repeatedly when it was Saturday. Never assume or state the day of the week. The system provides the date (2026-04-04) but NOT the day name. If needed, compute it: `date +%A` or `python -c "from datetime import date; print(date.today().strftime('%A'))"`. Never guess temporal information.

### Zombie Python Daemon (2026-04-02)
Editing .py does NOT affect running process. Must kill+restart. Find zombies: `Get-Process python | Select Id,StartTime | Sort StartTime`. Kill: `(Get-WmiObject Win32_Process -Filter 'ProcessId=X').Terminate()`. Verify log timestamps stop updating.

### Vercel Shared Module Crash (2026-03-23)
Shared `api/_lib/*.ts` causes FUNCTION_INVOCATION_FAILED. Fix: inline `await import()` per handler. Diagnostic: create two minimal test endpoints first.

### Windows Watchdog Zombies (2026-03-23)
`os.kill(pid, 0)` unreliable on Windows. Use `tasklist`. Never use `/rl highest` in Task Scheduler. Use `CREATE_NO_WINDOW` for headless daemons.

### subprocess cp1252 UnicodeDecodeError (2026-03-19)
`text=True` defaults to cp1252 on Windows. Always add `encoding="utf-8"`.

### Stale Cross-References (2026-03-03)
After ANY file delete/rename: `grep -rn "filename" --include="*.md"` across full project.

### Platform-Specific (archived)
- Twitter: validate char limits BEFORE posting (X=280, Threads=500, IG=2200, LinkedIn=3000)
- `__future__` import must be first line. PowerShell: use `Out-File -Encoding utf8`
- Idempotency: scripts with external side effects MUST check sent flag before execution

*Last updated: 2026-04-03*
