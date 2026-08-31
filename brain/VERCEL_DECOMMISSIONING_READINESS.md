---
last_updated: 2026-08-30
tags: [cloudflare, migration, vercel-exit, readiness]
---

# Vercel Decommissioning Readiness Report

> Generated 2026-08-30 ~07:45 UTC after the overnight execution run.
> Companions: [[brain/DNS_CUTOVER_AND_VERCEL_EXIT_CHECKLIST]] ·
> [[brain/WAVE3_OASIS_CC_RUNBOOK]] · baselines in
> `state/cloudflare_baselines/2026-08-30/`.

## 2026-08-31 — APEX CUT OVER, CRONS VERIFIED ALIVE, AND THE CANCELLATION TIMELINE

**`oasisai.work` apex now serves the oasis-command-center Worker.** Zone diff vs
the pre-cutover snapshot: exactly 2 intended deltas (Vercel `A 216.198.79.1`
removed, Cloudflare's `AAAA 100::` marker added). **All 11 mail/TXT records and
both tunnel CNAMEs byte-identical.** Rollback is one record:
`A oasisai.work -> 216.198.79.1`, unproxied, ttl 600.

**Crons proven alive end-to-end**, not merely configured: a `workflow_dispatch`
after repointing returned **200 on all 6 due routes**.

⚠ **A live outage happened and was fixed inside the hour.** The GitHub secret was
aligned to the Worker's rotated cron bearer while `cron-driver.yml` still
targeted the Vercel deployment, which holds the OLD value. The 23:46Z scheduled
run returned 200s; the 23:51Z dispatch returned **401 on every route**. Fixed by
PR #349 repointing BASE to the apex. The lesson is the pairing rule the runbook
already stated: **align the secret AND repoint the driver in the same change.**
Half of it is an outage.

Also recorded: verifying the cutover from this machine initially showed
`Server: Vercel` and a 401, which looked like a failed cutover. It was **local
OS DNS cache** holding the old A record for its 600s TTL. Forcing resolution to
the Cloudflare edge showed `Server: cloudflare` and a 200. Verify a cutover
against the edge IP, not through a caching resolver — and note the
title-equality guard cannot catch this, because both stacks serve the same app
with the same title.

### Where each hostname now lives

| Hostname | Serving from | Note |
|---|---|---|
| oasisai.work (apex) + www | **Workers** | apex = OASIS CC, www = marketing platform |
| bluerisebusinesscapital.com + www | **Workers** | |
| propflow.pro + www | **Workers** | |
| nostalgicrequests.com + www | **Workers** | |
| breezeadvance.credit | Cloudflare → **Vercel** | zone on CF but proxied to Vercel: breeze-portal has no Worker |
| sunbizfunding.com + www | **Vercel** | zone still PENDING — nameservers still at Google Domains |
| arthrisil.com | third party, **403** | not a zone in this account; broken before the migration |

### Cancellation timeline — three gates, in order

**Gate 1 — finish the fleet (blocked on CC).**
- `breeze-portal`: install the OpenNext adapter (its build currently fails with
  "could not determine executable to run") + 16 secrets, of which
  **BREEZE_ENCRYPTION_KEY must be RECOVERED, never rotated** — it encrypts Plaid
  access tokens at rest. Then breezeadvance.credit attaches.
- `opt-in-vault`: not yet deployed.
- `oasis-command-center`: 16 secrets outstanding. The app runs today without
  them; each gap disables a subsystem (Google Calendar needs the refresh token,
  the VPS bridge needs its bearer).
- `sunbizfunding.com`: change nameservers at Google Domains → zone activates →
  attach.

**Gate 2 — per-project retirement.** Once a hostname has served from Workers for
7 clean days, its Vercel project may be deleted one at a time, each with CC's
explicit approval. Keep every Vercel deployment warm until then — it is the only
rollback, and the `_vercel` TXT records must stay for the same reason.

**Gate 3 — account closure. Separate decision, and the slowest.** Cancelling the
account also kills **nine out-of-scope projects** (listing-studio — deliberately
staying — revline, oasis-vanguard, aura-home-agent, on-the-bay-painting,
kli-hub-dashboard, showroom, gritly, oasis-command-center-arthrisil-deploy), and
any Vercel-registered domain must be transferred out first or it is lost.
Listing-studio also holds a Vercel Blob store that would need moving to R2.

**Realistic earliest full cancellation:** Gate 1 is days (operator-dependent),
Gate 2 adds 7 days after the last cutover, Gate 3 needs a decision on nine
unrelated projects. Per-project retirement captures nearly all the saving and
can begin ~7 days after each cutover — that is the lever worth pulling first.

Run `python scripts/vercel_exit_report.py` for the live verdict; it is the
authority and this section is a snapshot.

## VERDICT: **NOT READY** (`vercel_exit_report.py` exit 2 — work outstanding, 0 regressions)

> The verdict is no longer maintained by hand. Run
> `python scripts/vercel_exit_report.py` — it measures all six gates live and
> exits 0 green / 1 regression / 2 expected-work.

### 2026-08-30 late — OASIS CC deployed; soak threshold lowered to 12h

**Soak 48h → 12h at CC's direction.** Recorded in the script with what it gives
up: the 28 crons include daily, twice-daily and weekly schedules, so 12h cannot
observe one full cycle of any of them.

**OASIS Command Center IS deployed** to workers.dev — 74 secrets pushed, 26
outstanding. It corrected an earlier assumption of mine: it renders correctly
and `/api/forms/submit` + `/api/forms/upload-url` are at **exact parity with
Vercel (400/400)**. One confirmed defect: **`/api/cron/health-check` returns 500
where Vercel returns 401** — `lib/cron-auth.ts` fails closed when `CRON_SECRET`
is unset, so all 28 cron routes would fail. Harmless today only because
`cron-driver.yml` targets the Vercel URL directly; fatal the moment Vercel goes.

**`oasisai.work` apex NOT attached — deliberate.** The guard would have allowed
it (titles match), so this was judgement: that worker had **0h soak** under CC's
own newly-set 12h rule, and apex is the primary revenue domain. Attach once it
has 12h clean AND `CRON_SECRET` is filled; rollback is one record
(`A 216.198.79.1`, unproxied).

**breeze-portal does not build** — `npm error could not determine executable to
run`: the OpenNext adapter was never installed in that repo. That is a
prerequisite *before* its 16 secrets and the `BREEZE_ENCRYPTION_KEY` recovery
even become the blocker.

## Earlier: seven production hostnames moved

### 2026-08-30 evening — Workers Paid unlocked Phase 2

**Paid confirmed** on `e371c0f2`, proven by two deploys the free cap had been
rejecting: `nostalgic-requests` (3.08MiB, 19 secrets) and `propflow` (5.27MiB,
28 of 30). **9 workers now deployed.**

PropFlow shipped without `SUPER_ADMIN_EMAILS` / `NEXT_PUBLIC_SUPER_ADMIN_EMAILS`
— sensitive-type in Vercel and therefore unrecoverable. Verified fail-closed
first in `src/lib/access-control.ts`: unset yields an empty allowlist, so nobody
gains email-based admin and the DB `is_super_admin` flag still governs. Pushed
behind an explicit `--allow-missing` that names every skipped key.

**Cut over (all 200, titles matched against the live site first):**
`propflow.pro` + `www`, `nostalgicrequests.com` + `www`. Rollback A-records
printed before each deletion and recorded in the tool output.

**Running total — 7 production hostnames on Workers:** `www.oasisai.work`,
`bluerisebusinesscapital.com` + `www`, `propflow.pro` + `www`,
`nostalgicrequests.com` + `www`.

`breezeadvance.credit` remains **correctly refused** — `breeze-portal` has never
been deployed (16 unfilled secrets), so binding it would point David's live
Client Portal at a worker that does not exist.

**Mail re-verified after the cutovers:** `oasisai.work` keeps all 5 MX and 6 TXT
(SPF/DKIM/DMARC). The two "no MX" warnings on `nostalgicrequests.com` and
`propflow.pro` predate this work — both were flagged in the pre-cutover baseline
and neither ever had mail records.

### 2026-08-30 late — 6 zones baselined, Blue Rise cut over, and a near-miss

All six zones are now in the account and baselined to
`state/cloudflare_baselines/2026-08-30/` (`wrangler_tool.py zone-baseline`).
Active: `oasisai.work`, `bluerisebusinesscapital.com`, `breezeadvance.credit`.
Pending (nameservers not yet repointed): `sunbizfunding.com`, `propflow.pro`,
`nostalgicrequests.com`.

**Cut over and verified:** `bluerisebusinesscapital.com` + `www` →
`blue-rise-website` Worker. Both 200, correct title, **MX preserved**.
Rollback: apex `A 216.150.1.129` + `A 216.150.1.193`; www `A 216.150.1.1` +
`A 216.150.16.129`, all proxied.

**NEAR-MISS — `breezeadvance.credit` was NOT attached, deliberately.** The
instruction was to bind it to `breezeadvance-website`. Vercel says the domain
belongs to **`breeze-portal`**, and the live site serves *"Breeze Advance —
Client Portal"* while that Worker serves *"Same-Day Business Funding"*.
Attaching would have replaced David's live client portal with a marketing page.
**The registry's domain map was wrong in 4 places** and has been regenerated
from Vercel; never attach from the registry without checking the live title and
the owning project first.

**Two pre-existing breakages found:** `arthrisil.com` currently serves an error
page (its zone is not in Cloudflare, so it cannot be fixed here), and
`nostalgicrequests.com` is ACTIVE with **no MX records** — it shows no SPF/DMARC
either, so it likely never had mail, but confirm before assuming.

**Open question for CC:** `www.oasisai.work` now serves the *marketing platform*
Worker while apex serves *agent-dashboard* — two different sites. Before the
cutover www was returning 000/SSL-failure, so this is strictly an improvement,
but Vercel had www registered to `agent-dashboard`, i.e. the original intent was
for both to serve the Command Center. Either repoint www once OASIS CC is on
Workers, or accept the split. Rollback to the previous (broken) state is
`CNAME www → cname.vercel-dns.com`, unproxied.

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
   Paid, `deploy_oasis_cc_phase2.py` will refuse (by design). **These are not a
   copy-paste job** — proven 2026-08-30 that Vercel's `sensitive` type is
   unreadable by the API, by `vercel env pull`, and by the dashboard itself.
   Each needs recovery from its issuer or rotation on both sides; per-key routes
   in [[brain/OASIS_CC_SECRET_FILL_GUIDE]]. PropFlow's 2 remaining keys are the
   same class. Budget real time for this, not fifteen minutes.

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
