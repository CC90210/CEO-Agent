---
last_updated: 2026-08-30
tags: [cloudflare, migration, dns, cutover, vercel-exit]
---

# DNS Cutover & Vercel Cancellation Checklist

> Final-readiness audit artifact (CC-requested 2026-08-30). Companions:
> [[brain/VERCEL_TO_CLOUDFLARE_MIGRATION]] (program status header) ·
> [[brain/WAVE3_OASIS_CC_RUNBOOK]] (cron cutover) · gap report
> `state/cloudflare_baselines/2026-08-29/secret_gaps.md` (§3 NS audit, §8 state).

## 0. ⛔ BLOCKER FOUND 2026-08-30 — the Workers and the zones are in DIFFERENT accounts

Zone access is now live (CC was granted Super Admin on the zone account), and
the first real binding attempt failed on a structural problem no permission can
fix:

```
PUT /accounts/d5e302…/workers/domains  {hostname: www.oasisai.work, service: oasis-ai-platform, zone_id: 9bc95545…}
 -> 10084: The zone "9bc95545…" does not exist on your account.
```

**A Workers custom domain requires the Worker and the zone to live in the SAME
Cloudflare account.** They do not:

| | account | contents |
|---|---|---|
| Workers | `d5e302…` (Konamak@icloud.com's) | all **8** deployed workers, subdomain `oasis-cc.workers.dev` |
| Zones | `e371c0f2…` (Oasisaisolutions@gmail.com's) | `oasisai.work`, both tunnels — and **0 workers**, no workers.dev subdomain yet |

**Every custom-domain cutover in §1 is blocked until these converge.** Two ways:

- **(A) Move the 8 Workers into the zone account `e371c0f2…` — RECOMMENDED.**
  Mechanical and low-risk: the pipeline is registry-driven, so it is a
  `CLOUDFLARE_ACCOUNT_ID` change plus `wrangler_tool.py deploy --app <slug>`
  per app, then re-push secrets (they are per-account). No DNS is touched at
  any point. Costs: a new workers.dev subdomain (the account has none yet — CC
  must open Workers & Pages once in that account's dashboard to create it),
  re-verifying Workers Paid **on that account**, and re-pointing the 10 CI
  workflows' `CLOUDFLARE_ACCOUNT_ID` secret. The 5 not-yet-onboarded domains
  should then be added to `e371c0f2…` too, so one account holds zones + workers.
- **(B) Move the `oasisai.work` zone into `d5e302…`** — rejected. A zone move is
  remove-and-re-add: all 15 records recreated by hand, including two proxied
  tunnel CNAMEs and the entire Google Workspace mail set, with a live DNS
  window in between. Workers are disposable; the zone carries mail and the
  agent bridges.

Also noted: the zone account's `/subscriptions` is not readable with this token,
so **Workers Paid status on `e371c0f2…` is unverified** — check before assuming
the 3 MiB cap is lifted there.

## 0a. ⚠ FENCE LIST CORRECTED — verified against live DNS 2026-08-30

The protected-record list in §0 and the migration log was compiled from
`docs/OASISAI_WORK_DOMAIN_RESTORE.md` (what *should* exist). Live DNS says
otherwise — queried against BOTH 1.1.1.1 and 8.8.8.8:

Zone `oasisai.work` = `9bc95545d99eb45f3291a59be518cd0b` in account `e371c0f2…`.
Full snapshot: `state/cloudflare_baselines/2026-08-30/` (local only — `state/`
is gitignored, so the **exact rollback values live in this table**, which is
tracked, rather than depending on one machine's disk).

| Hostname | Live DNS | Note |
|---|---|---|
| `bridge.oasisai.work` | **EXISTS** — proxied CNAME → `769f1fae-ed2a-4c3b-9d78-e15951afa874.cfargotunnel.com` (tunnel **sunbiz-bridge**, healthy, 4 conns). `/health` returns 401 = bearer-gated, tunnel up and routing to the VPS | PROTECTED |
| `oasisai.oasisai.work` | **EXISTS** — proxied CNAME → `06f8430c-b7a3-4719-aaff-20afa7e01c7c.cfargotunnel.com` (tunnel **oasisai**, healthy, 4 conns — this Windows box) | PROTECTED; was NOT on the original fence list |
| `breeze-bridge.oasisai.work` | **DOES NOT EXIST** (no record in zone; NXDOMAIN on 1.1.1.1 + 8.8.8.8) | Mac Mini tunnel hostname absent |
| `ops.oasisai.work` | **DOES NOT EXIST** | VPS/Caddy A record absent |
| `media.oasisai.work` | **DOES NOT EXIST** | R2 public base absent |

**Mail — PROTECTED, verified present in-zone:** 5× MX (`aspmx.l.google.com`,
`alt1`–`alt4`), SPF TXT `v=spf1 include:_spf.google.com ~all`, DKIM TXT at
`google._domainkey`, DMARC TXT `v=DMARC1; p=quarantine`, and 2×
`google-site-verification`.

**Cutover targets (the only records that should change), with rollback values:**
- apex `oasisai.work` — **A → `216.198.79.1`, NOT proxied** (Vercel)
- `www.oasisai.work` — **CNAME → `cname.vercel-dns.com`, NOT proxied** (Vercel;
  currently returns 000/SSL failure while apex returns 200 — www is broken TODAY)
- `_vercel` TXT — leave in place until retirement; it is the rollback anchor

**What this changes:** only ONE tunnel record actually needs preserving, not
four. **What it means:** these three were either never restored after the
2026-07-07 domain lapse or were removed since — and anything still configured
to call `ops.` (n8n/Stripe webhooks per V6_ARCHITECTURE) or `media.` (R2 asset
URLs) is **already broken today**, independent of this migration. Not caused by
migration work: no DNS record has been created, changed or deleted by it, and
the migration token cannot even see the zone. Worth a separate look by CC.

Google Workspace MX/SPF/DKIM/DMARC were NOT re-verified here (no zone read
access) — treat them as protected until proven otherwise.

## 0. Global preconditions (before ANY cutover)
- [ ] **Workers Paid enabled** on `d5e302…` (free CPU limits + 3MiB cap; 3 deploys queued behind it: propflow, nostalgic-requests, oasis-command-center @ 8.13MiB gz).
- [ ] Zone-visibility token for the account that owns `oasisai.work` (still `e371c0f2…`-side; current token sees no zones) → take the **zone baseline snapshot** and verify the protected fence (tunnels `bridge`/`breeze-bridge`, Google MX/SPF/DKIM/DMARC, `ops.`, `media.`) BEFORE and AFTER every DNS touch.
- [ ] oasisai.work **auto-renew ON** confirmed (lapsed 2026-07-07; unverified since).
- [ ] Fix `www.oasisai.work` SSL (pre-existing breakage; apex fine).
- [ ] Per-app: worker green on workers.dev ≥24h + secrets complete (43 FILL lines outstanding: propflow 2, breeze-portal 16, OASIS CC 26 — incl. `CRON_SECRET`/`CRON_ATTEST_SECRET` before cron flip).

## 1. Per-app cutover (order = risk ascending)

**Pattern (every app):** verify worker on workers.dev → move zone to Cloudflare
(if not there) → attach Workers custom domain → verify on the domain → keep the
Vercel deployment warm 7d (14d Wave 3) → then retire the Vercel project.
Rollback at any point: restore the snapshotted Vercel A/CNAME records (the
`_vercel` TXT is NEVER deleted until retirement — it IS the rollback).

| # | App / worker | Domain(s) | NS today | Zone action (CC) | Notes |
|---|---|---|---|---|---|
| 1 | tiktik | none (vercel.app) | — | none | "Cutover" = flip external links/webhooks to `tiktik.oasis-cc.workers.dev`, CC login click-through first |
| 2 | ig-setter-pro | none (vercel.app) | — | none | Same; IG/Meta webhook URLs re-point manually |
| 3 | sunbiz-funding | sunbizfunding.com | Google Domains | Add zone to CF, change NS at Google | Static site; zero env |
| 4 | arthrisil-website | arthrisil.com | GoDaddy | Add zone to CF, change NS at GoDaddy | Resend email keys unaffected |
| 5 | breezeadvance-website | breezeadvance.credit | **Vercel NS** | Likely Vercel-registered: unlock/transfer or re-point NS from Vercel dashboard | David's funder brand — schedule with CC |
| 6 | blue-rise-website | bluerisebusinesscapital.com | **Vercel NS** | Same Vercel unlock/transfer dance | dir=sunbiz-front-website |
| 7 | nostalgic-requests | nostalgicrequests.com | **Vercel NS** | Same | Deploy blocked on Paid first |
| 8 | propflow | propflow.pro | Vercel IPs (NS TBD) | Confirm registrar; move zone to CF | 2 secret fills; 1 cron (`reap-stale`, needs its own trigger or fleet-cron entry at flip) |
| 9 | oasis-ai-platform | oasisai.work (marketing) | **Cloudflare ✓** | Swap apex/www records Vercel→Worker (fence rules apply) | MUST move in the same window as #10 (its `/app/*` proxy retargets then); stage-2 API port before or after — proxy covers the interim |
| 10 | oasis-command-center | oasisai.work (`/app` via #9 + own routes) | **Cloudflare ✓** | Same window as #9 | Full [[brain/WAVE3_OASIS_CC_RUNBOOK]] choreography: secrets → parity e2e → cron Phase A gate (24h dry stream vs Vercel log) → `CRON_FORWARD=on` → remove vercel.json crons → 24h dual verify. Mail send/receive test on @oasisai.work after any zone touch |
| 11 | breeze-portal | app.breezeadvance.com (**client's CF account**) | client-managed | Coordinate with David — we never touch that zone | Wave 3 sub-project: 16 fills + Plaid spike + 3 crons; hosting is CC's Vercel project |

**Degraded-on-Workers notice (before #10 cutover):** encrypted-PDF raster
watermark, statement-image branding, and PDF signature crops fail closed on
Workers (native-raster boundary; originals always kept, overlay watermark +
signature pad unaffected). Either accept the operator fallback, or first ship
the raster sidecar / CanvasKit spike. **Shop-out of encrypted statements
refuses until this is decided — do not cut #10 over without CC signing off on
that behavior.**

## 1b. OASIS CC branch-merge gate (BEFORE the cloudflare-workers branch merges)
- [ ] Push the branch → **Vercel PREVIEW deploy** → exercise `watermark-variant`
      (an encrypted statement) + `apply-extraction` (a PDF signature crop) on the
      preview URL. Proves the native-raster tracing includes ship the packages
      in Vercel packaging — codex finding 2026-08-30: the bundler-opaque import
      hides the edge from tracing, the includes mirror the production-proven
      pdfjs glob shape, and directory-glob includes are only observable in the
      PACKAGED artifact, not local .nft.json manifests.

## 1c. CI activation (GitHub Actions → Cloudflare Workers, added 2026-08-30)
Every app repo carries `.github/workflows/deploy-cloudflare.yml`
(`cloudflare/wrangler-action@v3`), generated by
`wrangler_tool.py workflow --app <slug>` from the registry + secret manifest.
Push to `main` → `npm ci` → OpenNext/Vite build → deploy. **Not yet active** —
three operator gates, per repo:
- [ ] **Repo secrets** `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID`
      (`d5e302…`), plus the `NEXT_PUBLIC_*`/`VITE_*` build values each workflow
      header lists (tiktik 3, nostalgic 6, oasis-ai-platform 5, propflow 6,
      OASIS CC 10; the four marketing sites need none). Until the token exists
      the job BUILDS and SKIPS deploy with a warning — deliberately no red CI.
- [ ] **Merge `cloudflare-workers` → `main`** in each repo (the workflow only
      fires on main; OASIS CC also needs its §1b preview-deploy proof first).
- [ ] **Unarchive** tiktik · ig-setter-pro · oasis-ai-platform — GitHub Actions
      does not run on archived repos, so their workflow is inert until then.
- [ ] Workers Paid before CI can succeed for oasis-command-center / propflow /
      nostalgic-requests (3MiB free cap fails the deploy step, not the build).
CI deploys the app Worker only. `oasis-cc-cron` stays manual/gated by design —
it must not flip to forwarding via a push. Its kill switch `CRON_FORWARD`
accepts `on|true|1|yes`; anything else (incl. unset) is a dry tick. **Setting
it MUST be paired in one PR with removing `cron-driver.yml`'s `schedule:`
triggers — that workflow, not vercel.json, is the active firer** (verified
2026-08-30: scheduled runs succeeding; Vercel's scheduler dead since 08-06).

## 2. Vercel cancellation gates (the account CANNOT be closed until…)
- [ ] All 11 rows above cut over + soak passed (7d/14d) + per-project retirement approved by CC one at a time.
- [ ] **Out-of-scope projects still living on Vercel are migrated, retired, or explicitly re-homed:** listing-studio (**deliberately staying** — per CC 2026-08-29), revline, oasis-vanguard, aura-home-agent, on-the-bay-painting, kli-hub-dashboard, showroom, gritly, oasis-command-center-arthrisil-deploy. An account cancellation kills ALL of them at once.
- [ ] **Vercel Blob**: listing-studio's `BLOB_READ_WRITE_TOKEN` storage — stays while listing-studio stays; must move to R2 if the account is ever closed.
- [ ] Vercel-registered domains (breezeadvance.credit, bluerisebusinesscapital.com, nostalgicrequests.com if registered there) transferred out BEFORE cancellation — cancelling with domains inside is the outage from the 2026-04-30 incident, at account scale.
- [ ] The 28 OASIS CC crons observed 24h on the worker with ZERO Vercel fires (runbook Phase D) — cancelling Vercel is what makes cron rollback impossible; this gate is last.
- [ ] `fleet_health_check.py` overlay (`config/cloudflare/fleet_hosts.json`) probing all custom domains green for 7 consecutive days post-cutover.

**Bottom line:** full account cancellation is realistic only after Wave 3 soak
AND an out-of-scope-projects decision. Until then the exit is per-project
retirement, which already captures ~all the cost savings.
