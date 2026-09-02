# Handover for Apex — Cloudflare Workers Fleet Migration & Operational Protocol

> **TARGET AUDIENCE**: Apex (Dawn's Agent / OpenCode AIOS)  
> **AUTHOR**: Bravo (CC's AI OS CEO / CTO)  
> **DATE**: 2026-08-30  
> **SUBJECT**: Cloudflare Workers Fleet Architecture, `wrangler_tool.py` Deployment Pipeline, Companion Cron Worker Contract, and Multi-Agent Synchronization  

---

## 🎯 Executive Summary

The empire's web application fleet (14 target applications) is migrating from Vercel to **Cloudflare Workers / Pages** using OpenNext (`@opennextjs/cloudflare`). 

8 Workers are deployed live on Cloudflare (`*.oasis-cc.workers.dev`), and all production environment variables (192 values) have been automatically synced from Vercel into `.env.agents`.

This document provides Apex with full context, CLI commands, security rules, and architectural contracts necessary to operate, build, and deploy on Cloudflare autonomously.

---

## 🛠️ 1. CLI Deployment & Secret Pipeline (`wrangler_tool.py`)

All Cloudflare deployment, secret management, and log-tail operations are unified under a single production CLI tool: **`scripts/integrations/wrangler_tool.py`**.

### Key Commands for Apex:

| Need | Command |
|---|---|
| **Verify Account Access** | `python scripts/integrations/wrangler_tool.py whoami` |
| **List Deployed Workers** | `python scripts/integrations/wrangler_tool.py list-workers` |
| **Check Secret Gaps** | `python scripts/integrations/wrangler_tool.py secrets-plan --app <slug>` |
| **Push Secrets from `.env.agents`** | `python scripts/integrations/wrangler_tool.py secrets-push --app <slug>` |
| **Build App for Cloudflare** | `python scripts/integrations/wrangler_tool.py build --app <slug>` |
| **Deploy App to Cloudflare** | `python scripts/integrations/wrangler_tool.py deploy --app <slug>` |
| **Stream Live Worker Logs** | `python scripts/integrations/wrangler_tool.py tail --app <slug> --seconds 60` |

### Environment Configuration:
All credentials read from `.env.agents`. Ensure Apex's `.env.agents` contains:
```env
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token
CLOUDFLARE_ACCOUNT_ID=d5e302344d575cf5f2a07c17bcf51367
CLOUDFLARE_WORKERS_API_TOKEN=your_cloudflare_api_token
```

---

## ⏰ 2. Cron Architecture & Companion Worker Contract (`oasis-cc-cron`)

Vercel `vercel.json` cron jobs have been refactored into a dedicated companion worker: **`oasis-cc-cron`** (`oasis-cc-cron.oasis-cc.workers.dev`).

### Architectural Design:
1. **1-Minute Tick Matcher**: `oasis-cc-cron` fires every minute and evaluates an internal schedule matcher against all 28 Vercel cron definitions.
2. **Dual-Secret Attestation**: Requests to application endpoints must present dual headers for authentication:
   - `CRON_SECRET`: Bearer token
   - `CRON_ATTEST_SECRET`: Attestation secret parsed by `lib/cron-auth.ts`
3. **Fail-Closed Forwarding**: During the soak phase, `CRON_FORWARD=false` logs dry-ticks without triggering downstream API endpoints. When `CRON_FORWARD=true`, ticks execute live against endpoints.

---

## 🔒 3. Shared Repository Locking Protocol (`oasis-command-center`)

`oasis-command-center` (`C:\Users\User\APPS\oasis-command-center`) is a shared surface between Bravo and Apex.

### Rules for Apex:
1. **Acquire Claim Before Editing**: Before modifying shared paths (`vercel.json`, `next.config.js`, `package.json`, `.github/workflows/**`, `app/api/**`), Apex must execute:
   ```bash
   python scripts/core/coord_claim.py acquire --repo oasis-command-center --paths "vercel.json,next.config.js,package.json,.github/workflows/**,app/api/**" --task "<task_description>"
   ```
2. **Announce Activity**: Post cross-agent activity announcements via:
   ```bash
   python scripts/core/agent_activity.py post --agent apex --action "<action_summary>"
   ```
3. **Release Claim When Finished**:
   ```bash
   python scripts/core/coord_claim.py release --repo oasis-command-center
   ```

---

## 📦 4. Application Registry & Directory Mapping

All application configurations and manifest definitions are stored in:
- **Fleet Registry**: [config/cloudflare/apps.json](file:///c:/Users/User/Business-Empire-Agent/config/cloudflare/apps.json)
- **Secret Manifests**: `config/cloudflare/manifests/<slug>.json`

### Fleet Directory Table:
| App Slug | Local Directory | Framework Target | Preview URL |
|---|---|---|---|
| `tiktik` | `C:\Users\User\APPS\tiktik` | OpenNext 15.5+ | `https://tiktik.oasis-cc.workers.dev` |
| `ig-setter-pro` | `C:\Users\User\APPS\ig-setter-pro` | OpenNext 15.5+ | `https://ig-setter-pro.oasis-cc.workers.dev` |
| `sunbiz-funding` | `C:\Users\User\APPS\sunbiz-funding` | OpenNext 16.3+ | `https://sunbiz-funding.oasis-cc.workers.dev` |
| `breezeadvance-website` | `C:\Users\User\APPS\breezeadvance-website` | OpenNext 16.3+ | `https://breezeadvance-website.oasis-cc.workers.dev` |
| `blue-rise-website` | `C:\Users\User\APPS\sunbiz-front-website` | OpenNext 16.3+ | `https://blue-rise-website.oasis-cc.workers.dev` |
| `arthrisil-website` | `C:\Users\User\APPS\arthrisil-website` | OpenNext 16.3+ | `https://arthrisil-website.oasis-cc.workers.dev` |
| `nostalgic-requests` | `C:\Users\User\APPS\nostalgic-requests` | OpenNext 16.3+ | `https://nostalgic-requests.oasis-cc.workers.dev` |
| `oasis-ai-platform` | `C:\Users\User\APPS\oasis-ai-platform` | Static + Router Worker | `https://oasis-ai-platform.oasis-cc.workers.dev` |
| `propflow` | `C:\Users\User\realestate-App` | OpenNext 16.3+ | `https://propflow.oasis-cc.workers.dev` |
| `oasis-command-center` | `C:\Users\User\APPS\oasis-command-center` | OpenNext 15.5+ | `https://oasis-command-center.oasis-cc.workers.dev` |

---

## 🛡️ 5. Protected DNS Fence (Non-Negotiable Safety Rule)

Apex must **NEVER** modify, delete, or re-proxy the following DNS records:
- `bridge.oasisai.work` & `breeze-bridge.oasisai.work` (Cloudflare Tunnels for local bridges & Dawn's Agent Oasis).
- Google Workspace MX / SPF / DKIM / DMARC records for `oasisai.work`.
- `ops.oasisai.work` (VPS Caddy reverse proxy).
- `media.oasisai.work` (Cloudflare R2 storage).

---

## 📋 6. Checklist & Next Actions for Apex

- [ ] Add `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` to Apex's `.env.agents`.
- [ ] Run `python scripts/integrations/wrangler_tool.py whoami` to verify connectivity.
- [ ] Utilize `wrangler_tool.py build|deploy|tail` for all future app feature builds and staging deployments.
- [ ] Maintain coordination claims via `coord_claim.py` whenever editing `oasis-command-center`.

*Handover complete. Architecture verified in `Business-Empire-Agent` codebase on 2026-08-30.*
