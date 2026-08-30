---
last_updated: 2026-08-29
---

# Vercel to Cloudflare Migration: Master Handover Plan

> **STATUS**: EXECUTING as of 2026-08-29 — Phase 0/0.5 complete (commit `ce0cdba6`), paused for CC unblocks.
> **⚠ SUPERSEDED IN PART.** Live verification (2026-08-29) invalidated key steps below; the approved
> execution plan + corrections live in `state/cloudflare_baselines/2026-08-29/secret_gaps.md` and
> `config/cloudflare/apps.json`. Deltas: (1) `@cloudflare/next-on-pages` is deprecated and cannot build
> the fleet's Next 16 apps — use OpenNext `@opennextjs/cloudflare` on **Workers**, no
> `wrangler pages project create`; (2) Vercel's API never returns `sensitive`-type prod values — secrets
> flow from the agents env store via `scripts/integrations/wrangler_tool.py` (192/237 auto-recovered by
> `vercel_secret_sync.py`); (3) 32 Vercel crons (28 in OASIS CC) need companion cron Workers — unmentioned
> below; (4) app list: −Mindset Companion (phantom), −Showroom/−Gritly (0 deployments), +Listing Studio;
> (5) tunnels `bridge`/`breeze-bridge`.oasisai.work are proxied CNAMEs this doc's Phase 2 would destroy —
> a protected-fence list now gates every DNS touch.
> **ORIGINAL (2026-08-11, historical):** Pending Execution (Rainy Day Project)
> **PURPOSE**: Handover document for the AI agent tasked with executing the massive migration of 14 empire projects from Vercel to Cloudflare hosting to eliminate Vercel costs and unify infrastructure.

## 🎯 The Objective

Replace Vercel completely with Cloudflare (Pages/Workers) using the Cloudflare CLI (`wrangler` and `c3`). The goal is to fully automate the provisioning, environment variable transfer, and deployment of all projects without needing to click around the Cloudflare dashboard.

---

## 📦 App Inventory (The 14 Vercel Targets)

The following apps need to be migrated, categorized by their underlying framework. (Source: `APP_REGISTRY.md`, cleaned 2026-08-11)

### Next.js Projects (Requires `next-on-pages` / OpenNext on Cloudflare)
1. **PropFlow** (Next.js 14)
2. **Nostalgic Requests** (Next.js)
3. **Mindset Companion** (Next.js 16)
4. **TIKTIK** (Next.js 14)
5. **IG Setter Pro** (Next.js 14)
6. **Gritly** (Next.js 15)
7. **OASIS Command Center** (Next.js 15.5)
8. **Breeze** (Next.js 15.5)
9. **SunBiz Funding** (Next.js 16)
10. **BreezeAdvance** (Next.js 16)
11. **Blue Rise Website** (Next.js 16)
12. **Arthrisil** (Next.js)
13. **Opt-in Vault** (Next.js 15) ⚠️ *Critical: Code change required. Change `CONSENT_TRUSTED_EDGE_PROVIDER=vercel` to support Cloudflare edge environment.*

### Vite / React Projects (Static Assets)
14. **OASIS AI Platform** (React 18, Vite)

> **Note on "Showroom"**: CC noted this app is important, but its local codebase location is currently unknown. If it surfaces on Vercel, it must be migrated manually or added to this list later.

---

## 🤖 Phase 1: AI Agent Execution Steps (Automated via CLI)

When the rainy day comes, the agent should execute these steps sequentially using the terminal.

### 1. Cloudflare CLI Authentication
The agent will initiate the login, but CC must click the OAuth link:
```bash
npx wrangler login
```
*Agent must wait for CC to confirm successful browser authentication before proceeding.*

### 2. Environment Variable Extraction
For each project, the agent will:
1. Extract existing production environment variables from Vercel.
2. Format them for injection into Cloudflare.

### 3. Provisioning Cloudflare Pages Projects
For each of the 14 projects, the agent will run:
```bash
npx wrangler pages project create <project-name> --production-branch main
```

### 4. Bulk Secret Injection
Instead of manual entry, the agent will loop through the extracted Vercel secrets and inject them via CLI:
```bash
# Executed programmatically by the agent
echo "<SECRET_VALUE>" | npx wrangler pages secret put <SECRET_NAME> --project-name <project-name>
```

### 5. Repository Configuration & First Deploy
The agent will configure the build commands for Cloudflare:
- **For Vite**: Build command `npm run build`, output directory `dist`.
- **For Next.js**: Build command `npx @cloudflare/next-on-pages`, output directory `.vercel/output/static`.

The agent will run the initial CLI deployment to verify the build works:
```bash
npx wrangler pages deploy <output-dir> --project-name <project-name>
```

---

## 👤 Phase 2: CC's Manual Steps (DNS & Domains)

While the AI can automate the infrastructure setup, domain transfer requires owner authorization. 

> [!IMPORTANT]
> **Domains purchased through Vercel** cannot be managed via CLI initially. 

**Steps for CC:**
1. **Unlock Domains in Vercel**: Go to the Vercel Dashboard -> Domains -> Select domain -> Unlock for transfer.
2. **Transfer to Cloudflare Registrar**: Open the Cloudflare Dashboard -> Domain Registration -> Transfer Domains. Input the auth codes from Vercel. Cloudflare provides wholesale pricing for renewals.
3. **Update Nameservers**: If the domains are registered elsewhere, log in to the registrar and change the nameservers to Cloudflare's provided nameservers.
4. **Link Custom Domains**: In Cloudflare Pages, go to the project -> Custom Domains -> add the domain. Cloudflare automatically issues the SSL certificates.

---

## 🛑 Known Gotchas & Agent Reminders

1. **Next.js Edge Runtime**: Cloudflare runs on V8 isolates (Workers), not Node.js containers. Any Next.js API routes relying on heavy Node.js standard libraries (`fs`, `child_process`) must be refactored or moved to Edge API routes. 
2. **Opt-In Vault**: The `CONSENT_TRUSTED_EDGE_PROVIDER` environment variable currently hardcodes Vercel headers. The agent migrating this must update the codebase to parse Cloudflare's specific geographic/IP headers (`CF-Connecting-IP`, `CF-IPCountry`).
3. **Database Drivers**: We already successfully migrated to Turso (libSQL). Turso's HTTP driver works natively and perfectly inside Cloudflare Workers! No changes needed there.
