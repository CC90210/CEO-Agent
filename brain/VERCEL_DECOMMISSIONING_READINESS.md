---
last_updated: 2026-08-30
tags: [cloudflare, migration, vercel-exit, readiness]
---

# Vercel Decommissioning Readiness Report

> Generated 2026-08-30 ~07:45 UTC after the overnight execution run.
> Companions: [[brain/DNS_CUTOVER_AND_VERCEL_EXIT_CHECKLIST]] ·
> [[brain/WAVE3_OASIS_CC_RUNBOOK]] · baselines in
> `state/cloudflare_baselines/2026-08-30/`.

## VERDICT: **NOT READY.** One production hostname has moved. Three blockers remain, all operator-side.

Vercel still serves ~all production traffic. Cancelling today would take down
every brand. The migration is, however, materially unblocked: the account split
that made custom domains impossible is resolved, and the first real cutover
succeeded and *fixed a live outage*.

---

## What moved tonight

**Account consolidation (the blocker from the previous run).** Workers and zones
were in different Cloudflare accounts, so no custom domain could bind. **7 of 10
workers were redeployed into the zone-owning account `e371c0f2…`** with their
secrets re-pushed, and now serve on `*.oasisaisolutions.workers.dev`:

| worker | status |
|---|---|
| tiktik | 307 → /login (auth redirect, correct) |
| ig-setter-pro · sunbiz-funding · breezeadvance-website · blue-rise-website · arthrisil-website · oasis-ai-platform | 200 |

⚠ The old copies in `d5e302…` are still deployed and serving on
`*.oasis-cc.workers.dev`. No traffic depends on them. **Do not delete until the
new ones pass soak** — then remove them so one fleet does not silently diverge.

**FIRST PRODUCTION CUTOVER — `www.oasisai.work`.** It was **broken** before this
run (000 / SSL failure: a grey-clouded `cname.vercel-dns.com` with no working
cert) while apex served fine. Now bound to the `oasis-ai-platform` Worker and
returning **200** with the correct title. Net: a live outage fixed, not just a
migration step.
- Rollback (one record): `CNAME www.oasisai.work → cname.vercel-dns.com`, proxied=false, ttl=1.
- **Zone integrity verified by full-fidelity diff** (type+name+content+proxied+priority)
  against the pre-cutover baseline: exactly 2 deltas, both intended (removed the
  broken Vercel CNAME, added Cloudflare's `AAAA 100::` custom-domain marker).
  **All 11 mail/TXT records and both tunnel CNAMEs byte-identical.**

**CI is green for the first time since 2026-08-27**, and both PRs merged:
- **#346** (`8aadddb0`) — the role-scoping regression: `member`, the team_role
  column default, had been granted sales-operator rights by `01461615`.
- **#347** (`50a17f83`) — the 28 crons relocated to `config/cron-registry.json`;
  `vercel.json` no longer declares a `crons` key. Registry confirmed on main:
  28 entries. Both CI suites (`test:sunbiz`, `test:website-sales`) pass.

---

## Blockers (all operator-side)

1. **Workers Paid is not enabled on `e371c0f2…`.** It is a fresh account. The
   three largest workers fail validation at the 3 MiB free cap:
   `oasis-command-center` (8.13 MiB gz), `propflow` (5.27), `nostalgic-requests`
   (3.08). All three build clean — this is purely a plan setting. **This is the
   single highest-leverage action**: it unblocks 3 deploys and Wave 3 entirely.
2. **5 of 6 domains are not in Cloudflare at all.** Only `oasisai.work` is a
   zone in the account. `sunbizfunding.com` (Google Domains NS),
   `breezeadvance.credit`, `bluerisebusinesscapital.com`, `nostalgicrequests.com`
   (Vercel NS), `arthrisil.com` (GoDaddy NS) must each be added to `e371c0f2…`
   and have their nameservers repointed at the registrar before any binding is
   possible. Registrar access is CC's.
3. **The 26 `OASIS_COMMAND_CENTER__*` secrets are still unfilled**, so even with
   Paid, `deploy_oasis_cc_phase2.py` will refuse (by design).

**Not executable as specified:** Gate Zero — `turso_bridge_smoke.mjs` does not
exist in either repo (searched both, excluding node_modules), and OASIS CC is
not deployed to Workers to run it against. Needs the script, or a named
substitute, plus blocker 1 cleared.

---

## Soak clock

**Started 2026-08-30 07:45 UTC** for the 7 migrated workers and the one migrated
hostname. **48h gate closes ~2026-09-01 08:00 UTC.** Nothing should be retired
on Vercel before then. What passing looks like, per the checklist: HTTP parity
holding, zero uncaught exceptions in `wrangler tail`, flat error rate, and for
`www` specifically a clean zone-diff against
`state/cloudflare_baselines/2026-08-30/`.

## Apex is deliberately NOT cut over

`oasisai.work` apex still points at Vercel (`A 216.198.79.1`) and returns 200.
It is coupled to OASIS CC through the `/app/*` proxy and should move in the same
window, per checklist §1 row 9-10. Moving it now would be a working-production
cutover with hours of soak, against a checklist that asks for 24h — and unlike
`www`, there is no broken hostname to justify the exception.

## Fleet health

`fleet_health_check.py`: **4/5 apps fully healthy.** The one flag is
`agent-dashboard: DOMAIN BROKEN`, which is **`apply.sunbizfunding.com` failing
to resolve** (NXDOMAIN) — pre-existing, unrelated to this migration, and worth a
separate look. `oasisai.work` apex resolves correctly to Vercel as intended.

## Next actions, in dependency order

1. CC: enable **Workers Paid on `e371c0f2…`** → I deploy the remaining 3.
2. CC: fill the **26 OASIS CC secrets** → Phase 2 preflight passes.
3. CC: add the **5 remaining zones** to `e371c0f2…` + repoint nameservers.
4. Bravo: soak review at the 48h gate, then per-domain cutovers one at a time,
   each with a zone-diff, each keeping its Vercel deployment warm 7 days.
5. Only then: per-project Vercel retirement, and finally the account-level
   decision (which also depends on the 9 out-of-scope projects in checklist §2).
