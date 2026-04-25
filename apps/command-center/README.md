# Bravo Command Center

The one URL you bookmark on your phone that shows what every agent in CC's
empire is doing — outbound, inbound, decisions, pipeline, agent family,
live event bus tape.

Read-only for v1. Server-side Supabase queries (service role key stays on
the server). Built with Next.js 14 + Tailwind + shadcn-style components,
no third-party auth libraries, no client-side state management.

## What it shows

- **`/`** — today's counters + channel caps + recent decisions + recent inbound + pipeline
- **`/decisions`** — the full reasoning-loop decision tape with confidence + alternatives
- **`/inbound`** — every classified reply with intent/priority/sentiment
- **`/outbound`** — every send through the gateway with brand + cooldown
- **`/leads`** — CRM pipeline by stage
- **`/agents`** — Bravo/Codex/Atlas/Maven/Aura status + cross-agent event bus

## Local dev

```bash
cd apps/command-center
npm install
cp .env.local.example .env.local
# Fill in BRAVO_SUPABASE_URL + BRAVO_SUPABASE_SERVICE_ROLE_KEY (copy from .env.agents)
npm run dev
# Open http://localhost:3100
```

> Detailed env-var spec: [[apps/command-center/ENV_SETUP]]

## Deploy to Vercel

The first time:

```bash
cd apps/command-center
npm i -g vercel          # if not already installed
vercel login             # opens browser, authenticate to your Vercel account
vercel link              # link this folder to a new Vercel project (suggested name: bravo-dashboard)
```

Then set the two environment variables in the Vercel project:

- `BRAVO_SUPABASE_URL` — same value as in `.env.agents`
- `BRAVO_SUPABASE_SERVICE_ROLE_KEY` — same value as in `.env.agents`

(In the Vercel dashboard: Settings → Environment Variables → add both.)

Then deploy:

```bash
vercel --prod
```

Vercel prints a URL. Bookmark it. Every time you push to the linked branch,
Vercel rebuilds and redeploys automatically.

## ISR — how fresh is the data?

Every page has `export const revalidate = 20` (20 seconds). First visit
hits Supabase; every visit in the next 20 seconds serves cached HTML; after
that, Vercel regenerates in the background on next request. Free plan
absorbs this without sweat.

To force a full refresh: `vercel redeploy --prod` or hit the URL with
`?nocache=<random>` (cache-busting is a cheap trick, not a guarantee).

## Why service role on the server (and why it's safe)

Every page is a React Server Component. Supabase queries run on Vercel's
serverless runtime; the service role key never touches the browser. The
client bundle contains zero Supabase credentials.

If you ever add interactive features (forms, approval buttons), switch to
a per-request pattern: client calls a Next.js Route Handler, the handler
validates the request, then does the Supabase work server-side.

## Extending the dashboard

- **Add a page**: drop a new folder under `app/` with a `page.tsx`
- **Add a query**: extend `lib/queries.ts`; it's the single entry point
- **Add a component**: drop it in `components/`; import with `@/components/...`
- **Change the palette**: `tailwind.config.ts` has the OASIS-brand colors

## Known limitations (by design, for v1)

- **Read-only**. No approve/skip/reassign buttons yet. Those are in the
  reasoning-loop + Telegram paths (already interactive).
- **No auth**. Anyone with the URL sees the data. If you care, add a
  password in a Route Handler middleware — 10 lines. Plan B: use Vercel's
  password-protect feature (paid).
- **No custom SQL in the UI**. If you want ad-hoc analytics, add a new
  entry in `lib/queries.ts`.

## Files

| File | Purpose |
|---|---|
| `app/layout.tsx` | Root layout + Nav + footer |
| `app/page.tsx` | Today — the home dashboard |
| `app/{decisions,inbound,outbound,leads,agents}/page.tsx` | Per-section pages |
| `components/Nav.tsx` | Top nav bar |
| `components/Card.tsx` | Card / Stat / EmptyState primitives |
| `lib/supabase.ts` | Supabase client factory + shared types |
| `lib/queries.ts` | Every query the dashboard makes, in one file |
| `lib/fmt.ts` | Time + status-color formatters |
| `tailwind.config.ts` | Theme (OASIS dark + gold) |
| `next.config.js` | Next.js config |
| `package.json` | Deps: next, react, @supabase/supabase-js |
