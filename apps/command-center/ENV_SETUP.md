# Environment variables

The Command Center needs two env vars, set both locally (`.env.local`) and
in Vercel's project settings.

## Required

| Variable | Value | Where to get it |
|---|---|---|
| `BRAVO_SUPABASE_URL` | `https://<project-ref>.supabase.co` | Copy from `.env.agents` in the repo root |
| `BRAVO_SUPABASE_SERVICE_ROLE_KEY` | the service role JWT | Copy from `.env.agents` in the repo root |
| `BRAVO_FIELD_ENCRYPTION_KEY` | random 32+ byte string | `python -c "import secrets; print(secrets.token_urlsafe(48))"` — used by `/api/agent-config` to pgp_sym_encrypt per-tenant API keys at rest. Rotating this orphans every stored key, so set once and treat like a master secret. |

## Local setup

1. In this folder (`apps/command-center`), create a file named `.env.local`
2. Paste these two lines and fill in the values:

   ```
   BRAVO_SUPABASE_URL=https://<your-project-ref>.supabase.co
   BRAVO_SUPABASE_SERVICE_ROLE_KEY=<paste service role key>
   ```

3. Run `npm run dev` — opens at `http://localhost:3100`

`.env.local` is gitignored by Next.js defaults. Do not commit it.

## Vercel setup

After `vercel link`:

1. Go to https://vercel.com → your project → Settings → Environment Variables
2. Add both variables for **Production** and **Preview** environments
3. `vercel --prod` to deploy

## Why service role (not anon)?

Every page renders on Vercel's server runtime via React Server Components.
The service role key never reaches the browser. If you add interactive
features later, swap to per-request patterns using the anon key with RLS
policies.

## Related
- [[apps/command-center/README]]
- [[brain/APP_REGISTRY]]


## Related (graph)

- [[apps/command-center/README]]
