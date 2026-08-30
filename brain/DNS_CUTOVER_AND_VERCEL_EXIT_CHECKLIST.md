---
last_updated: 2026-08-30
tags: [cloudflare, migration, dns, cutover, vercel-exit]
---

# DNS Cutover & Vercel Cancellation Checklist

> Final-readiness audit artifact (CC-requested 2026-08-30). Companions:
> [[brain/VERCEL_TO_CLOUDFLARE_MIGRATION]] (program status header) ·
> [[brain/WAVE3_OASIS_CC_RUNBOOK]] (cron cutover) · gap report
> `state/cloudflare_baselines/2026-08-29/secret_gaps.md` (§3 NS audit, §8 state).

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
