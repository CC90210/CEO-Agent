---
tags: [mistakes, prevention]
---
# MISTAKES LOG
> [[brain/BRAIN_LOOP]] | [[memory/PATTERNS]] | [[memory/SELF_REFLECTIONS]]

### Date Bug: Today Page Showed "Friday May 1" at 11:52pm Apr 30 EDT (2026-05-01)
**Failure:** `apps/command-center/lib/dates.ts` did `new Date(date.toLocaleString("en-US", { timeZone }))` — the locale string is TZ-naive, and `new Date()` re-parses it in the *runtime* timezone. On Vercel (UTC), at 11:52pm EDT Apr 30 (= 03:52 UTC May 1) the dashboard rendered "Friday, May 1" instead of "Thursday, April 30". Compounded by `today.toLocaleDateString(undefined, ...)` using the runtime TZ instead of the operator TZ. CC saw a wrong date on the hero subtitle and the schedule mission line.
**Why it slipped:** the implementation *looked* TZ-aware ("America/Toronto" is right there in the code), but the round-trip through a TZ-naive string silently dropped the offset. Local dev (Toronto host) hides this completely — the bug only fires on UTC servers around the day-boundary.
**Prevention:**
1. NEVER do `new Date(stringFromToLocaleString(...))` — the round-trip drops timezone.
2. For ALL operator-timezone display, use `Intl.DateTimeFormat("en-US", { timeZone, ...opts }).format(date)` directly.
3. For arithmetic across day-boundaries, use `operatorParts(date, tz)` in `apps/command-center/lib/dates.ts` which returns `{year, month, day, weekday, hour}` from `Intl.DateTimeFormat.formatToParts`.
4. Added `<LiveClock>` component that re-checks the date key every 30s and triggers `router.refresh()` at midnight, so even a long-open tab updates without a manual reload.
**Tag:** `tz-bug`, `silent-failure`, `local-vs-prod-divergence`.

### Setup Wizard 404: Public irm One-Liner on a Private Repo (2026-04-29 → resolved 2026-05-01 by flipping CEO-Agent to PUBLIC)
**Failure:** README led with `irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install/quickstart.ps1 | iex`. CEO-Agent was PRIVATE. GitHub returns `404 Not Found` for unauthenticated `raw.githubusercontent.com` requests on private repos by design. PowerShell tries to `iex` the 404 response → cryptic error. CC hit it twice in one terminal session. Codex patched docs to *add* a gh-aware path on Apr 29, but the broken path was still listed FIRST, so clients copy-pasted the failing one.
**Resolution:** CC flipped CEO-Agent to PUBLIC on 2026-05-01 to match CFO-Agent + CMO-Agent. Sister repos in the C-Suite are now consistent — clients install with a single `irm | iex` line, no prereqs, no `gh`.
**Prevention going forward:**
1. Whenever a one-liner depends on repo visibility, check visibility (`gh repo view --json visibility`) when writing the docs.
2. Documented one-liners must work for the CURRENT visibility — public path goes first when the repo is public, gh path goes first when it's private.
3. README + `install/README.md` now have a "Bulletproof installer" section with an auto-fallback one-liner that handles the visibility flip in either direction. Future-proofing for if the repo ever flips back private.
4. Whole C-Suite pattern: any new agent in the family (Atlas, Maven, Aura, Hermes) MUST be public from day one so client install never breaks.
**Tag:** `install-ux`, `repo-visibility`, `docs-led-with-broken-path`.

### Built a Cross-System Bridge CC Didn't Want (2026-04-30, REVERTED)
**Failure:** Across multiple sessions I conflated CC's two products — the OASIS AI marketing/portal site (`oasisai.work`, sells one-off N8N automations) and the OASIS AI Agent Command Center (`agent-dashboard-cc90210.vercel.app`, multi-tenant ops dashboard) — and built bridges between them: a Stripe-webhook → tenant-provisioning endpoint, marketing pages inside the dashboard project, a Vercel rewrite proxying `oasisai.work/app/*`, shared Supabase Site URL, etc. CC had to step in and explicitly say: *"I've messed up completely. You need to completely reverse all of the changes. OASIS AI's client portal is for one-off N8N automations, and the agent dashboard is a completely separate tool. They need to be completely separate."* All of it ripped out. **Root cause:** I kept hearing "merge" or "share auth" and ran with it; CC kept clarifying and I kept overshooting. **Prevention:** before any cross-system code (bridge endpoint, shared cookie domain, shared DB row, rewrite proxying another origin), STATE the assumption explicitly: *"Building a bridge between Product A and Product B such that X event in A triggers Y in B. Confirm?"* and wait for explicit confirm. Two Vercel projects + two Supabase projects + two repos is the **intentional** architecture, not a thing to consolidate. Tag: `scope-creep`, `cross-system-bridge`, `wrong-mental-model`.

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
