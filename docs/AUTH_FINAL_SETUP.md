# OASIS Command Center — Auth Setup

> **Architecture note (2026-04-30 PM):** the OASIS Command Center and the
> OASIS AI marketing/portal site (`oasisai.work`) are two **separate products**.
> Different repos, different Vercel projects, different Supabase projects.
> No cross-system bridge. The Command Center has its own auth at its own URL.

## Where things are

| | OASIS AI Platform | Agent Command Center |
|---|---|---|
| URL | https://oasisai.work | https://oasisai.work |
| Repo | `CC90210/oasis-ai-platform` | `CC90210/CEO-Agent` (subfolder `apps/command-center`) |
| Vercel project | `oasis-ai-platform` | `agent-dashboard` |
| Supabase | `oasis-ai-platform` (separate DB) | `bravo` (`phctllmtsogkovoilwos`) |
| Purpose | Marketing + checkout + client portal for one-off N8N automations | Multi-tenant agent operations dashboard |

## Sign in to the Command Center

Go to: https://oasisai.work/login

You have three options to authenticate:

### Option 1 — Continue with Google (instant, no password needed)
Click **Continue with Google** → consent → you land on the Today dashboard.

### Option 2 — Email + password (if you've set one)
Enter `conaugh@oasisai.work` + your password → Sign in.

### Option 3 — First time? Set a password
1. Visit https://oasisai.work/forgot-password
2. Enter `conaugh@oasisai.work`
3. Click the link Supabase emails you
4. You land on `/auth/reset-password` → set a password
5. Sign in normally

## Supabase Auth config (already set, do not change unless you know why)

- **Site URL:** `https://oasisai.work`
- **Redirect URLs allow-list:**
  - `https://oasisai.work/**`
  - `http://localhost:3100/**`
- **Providers enabled:** email/password + Google OAuth (Client ID + Secret in Supabase dashboard)

If you ever need to change these via API:
```bash
python scripts/integrations/supabase_admin.py get /v1/projects/phctllmtsogkovoilwos/config/auth
python scripts/integrations/supabase_admin.py patch /v1/projects/phctllmtsogkovoilwos/config/auth --body '{"site_url":"..."}'
```

## DNS / domain ops

If `oasisai.work` (the marketing site) ever needs domain re-verification on Vercel:
```bash
python scripts/integrations/cloudflare_admin.py sync-vercel-txt --domain oasisai.work --vercel-project oasis-ai-platform
```
Reads what Vercel expects, updates Cloudflare DNS, triggers verify. Built after the 2026-04-30 incident; see `memory/MISTAKES.md` for the full story.

## Related

- [[docs/INDEX]]
- [[docs/AGENT_RUNNER_DESIGN]]


## Related (graph)

- [[docs/INDEX]]
- [[docs/AGENT_RUNNER_DESIGN]]
- [[docs/AI_WORKSTATION_ROADMAP]]
