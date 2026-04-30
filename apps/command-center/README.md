# OASIS AI · Agent Command Center

The operating system for your AI agents. One URL that shows what every agent
in your empire is doing — outbound, inbound, decisions, pipeline, agent family,
live event bus tape. Multi-tenant, profile-driven, sellable to clients via the
setup wizard.

> Branded "OASIS AI" by default; the brand string is profile-driven, so each
> operator's dashboard renders their own brand pulled from `user_profiles.brand`.

Read-only for v1. Server-side Supabase queries (service role key stays on
the server). Built with Next.js 15 + React 19 + Tailwind + recharts + lucide-react.
No third-party auth libraries, no client-side state management.

## Pages

| Path | What it shows |
|---|---|
| `/` (Today) | Live MRR + primary lead + day schedule + manifesto |
| `/pipeline` | Merged Leads + Outbound + Inbound funnel |
| `/playbook` | Sales script + objection handlers + deal arch + daily drills |
| `/playbook/cold-call` | Cold Call Script V1 (5 stages, NEPQ) |
| `/playbook/objections` | 8 objection handlers |
| `/playbook/deals` | 3 client offers + 2 partner tiers |
| `/playbook/drills` | Mirror Run · Objection Volley · Recording Review |
| `/reasoning` | Decision tape with confidence + alternatives |
| `/agents` | Multi-agent status + event bus (filtered to enabled agents) |
| `/analytics` | MRR trajectory + funnel + lead sources |
| `/integrations` | Health dots for every connected service |
| `/settings` | Profile · integrations · agent wiring |
| `/api/inbound/n8n` | POST endpoint — n8n workflow posts classified emails here |

## Local dev

```bash
cd apps/command-center
npm install
# Set BRAVO_SUPABASE_URL + BRAVO_SUPABASE_SERVICE_ROLE_KEY + OPERATOR_EMAIL
# (.env.local in this folder, or pull from .env.agents at repo root)
npm run dev
# Open http://localhost:3100
```

## Deploy to Vercel — one command

The repo's `.env.agents` already has `VERCEL_TOKEN` and Supabase credentials.
The deploy script handles everything: link, env vars, deploy, verify.

```bash
python scripts/deploy_command_center.py
```

What that does (idempotent — safe to re-run):
1. Links `apps/command-center/` to the Vercel project `cc90210/agent-dashboard`
2. Syncs production env vars from `.env.agents`:
   - `BRAVO_SUPABASE_URL`
   - `BRAVO_SUPABASE_SERVICE_ROLE_KEY`
   - `OPERATOR_EMAIL` (defaults to `conaugh@oasisai.work`)
3. Runs `vercel deploy --prod`
4. Curls the live URL to confirm it's reachable (200 or 401-SSO-gate)

Aliased URL: `https://agent-dashboard-cc90210.vercel.app`

### Variants

```bash
# Just sync env vars, skip the build (fast iteration after editing .env.agents)
python scripts/deploy_command_center.py --env-only

# Just link the local folder to Vercel (first-time setup on a new machine)
python scripts/deploy_command_center.py --link-only

# Skip the post-deploy curl verification
python scripts/deploy_command_center.py --no-verify
```

## Auto-deploy on `git push`

The Vercel project's GitHub integration may or may not be wired — check
**Vercel → agent-dashboard → Settings → Git**. If it shows the repo
connected to `main`, every push auto-deploys. If not, use the script above.

The script is the source of truth either way; auto-deploy is a convenience.

## ISR — how fresh is the data?

Every page exports `dynamic = "force-dynamic"`, so every request hits Supabase
on the server. (We can switch to `revalidate = 20` later if Supabase egress
becomes a cost.)

## Why service role on the server (and why it's safe)

Every page is a React Server Component. Supabase queries run on Vercel's
serverless runtime; the service role key never touches the browser. The
client bundle contains zero Supabase credentials.

The `/api/inbound/n8n` route handler is a plain Node route (not edge) because
it uses Node's `crypto` for the SHA-256 secret hashing.

## Extending the dashboard

- **Add a page**: drop a folder under `app/` with `page.tsx` (or `route.ts` for an API)
- **Add a query**: extend `lib/queries.ts` — single source for all reads
- **Add a component**: drop it in `components/`, import with `@/components/...`
- **Add an agent**: edit `lib/agents.ts` (single registry feeds `/agents` + `/settings`)
- **Change the palette**: `tailwind.config.ts` has the OASIS-brand colors

## Files

| File | Purpose |
|---|---|
| `app/layout.tsx` | Root layout + Sidebar + footer |
| `app/page.tsx` | Today — the home dashboard |
| `app/<route>/page.tsx` | Every other page |
| `app/api/inbound/n8n/route.ts` | n8n inbound webhook |
| `components/Sidebar.tsx` | Left-rail nav |
| `components/Card.tsx` | Card / Stat / EmptyState / PageHeader / Tag |
| `components/IntegrationDot.tsx` | Green/red status dot for integrations |
| `components/charts/*.tsx` | recharts MRR + custom funnel + custom gauges |
| `lib/supabase.ts` | Supabase client factory + shared types |
| `lib/queries.ts` | Every query the dashboard makes |
| `lib/agents.ts` | Single agent registry (feeds `/agents` + `/settings`) |
| `lib/fmt.ts` | Time + status-color formatters |
| `tailwind.config.ts` | Theme (OASIS dark + gold) |

## Related backend

- **Migration**: `database/017_user_profiles.sql` — `user_profiles`, `daily_plans`, `n8n_webhook_secrets`, `integrations_health`, RPCs
- **Profile seeder**: `python scripts/seed_profile.py` — seeds operator + today's plan
- **n8n bridge**: `python scripts/n8n_webhook_secret.py issue --profile-email <email>` — issue secrets
- **n8n setup**: `docs/N8N_INBOUND_WEBHOOK.md` — copy-paste guide
- **Bridge smoke test**: `python scripts/test_n8n_inbound_rpc.py` — 8-step end-to-end verify
- **Setup wizard hook**: `python install/bootstrap.py --create-command-center-account --email X --full-name Y`
