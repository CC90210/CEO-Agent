---
last_updated: 2026-08-31
tags: [cloudflare, migration, vercel-exit, readiness]
---

# Vercel Decommissioning Readiness Report

## 2026-08-31 14:20Z — GATE 1 CLEARED BY OPERATOR DECISION · GATE 2 SOAK RUNNING

**CC cleared Gate 1 on 2026-08-31,** accepting two items as outstanding rather
than blocking:

1. **Google sign-in** — explicitly descoped. The button is not needed. The
   diagnosis stands in [[brain/MORNING_BRIEFING_2026-08-31]] if it is ever
   wanted; nothing else depends on it.
2. **`sunbizfunding.com`** — registrar change submitted; the watcher cuts it over
   automatically on propagation. Recorded in `vercel_exit_report.py`
   `OPERATOR_ACCEPTED` with its removal condition, so the gate keeps *measuring*
   it and reporting it — it simply no longer holds Gate 1 closed.

### Before the ACCOUNT can be deleted — three things, all fixable in the window

These are separate from the two items CC descoped, and were surfaced 2026-08-31
after that decision. Each one means deleting the account takes something live
down on the day.

1. **`www.oasisai.work/api/*` is still served by Vercel.** The router proxies it
   to `oasis-ai-platform.vercel.app`, which hosts the marketing site's seven Node
   functions — **including all five Stripe flow rewrites**. Deleting the account
   kills checkout. This is stage 1 of the platform migration working exactly as
   designed; stage 2 (porting those handlers into the Worker) was never done.
   **This is the one real engineering task left, and it is Bravo's to do.**
2. **`www.breezeadvance.credit` still points at Vercel IPs**, as does a `*`
   wildcard on that zone. The apex is on Workers; www is not. Deliberately not
   fixed unattended — attaching www would serve the portal instead of
   redirecting, and splitting an authenticated client financial portal across two
   hostnames risks cookie-domain session breakage. Five minutes with CC awake, or
   a Cloudflare redirect rule that preserves current behaviour exactly.
3. **`breezeadvance.com` + `www` serve a client's live site from Vercel**, and it
   is not a zone in our Cloudflare account. **Which Vercel account owns it is
   unresolved** — the project-domains API returns 403 for our token. If it is
   ours, deleting the account takes a client offline. One check settles it and
   nothing else should be pressed until it is.

Also still true and unchanged: account deletion removes **nine out-of-scope
projects** — including `listing-studio`, which CC deliberately keeps, and its
Vercel Blob store — plus any Vercel-registered domain that has not been
transferred out first.

### Gate 2 — the 7-day soak, and the date it ends

A soak measures how long the **currently deployed** state has run clean, so each
app's clock starts at its own last production deploy. The fleet clears when the
last one finishes.

| App | Soak ends (UTC) |
|---|---|
| opt-in-vault, sunbiz-funding, propflow | 2026-09-07 03:02 |
| nostalgic-requests, breeze-portal, oasis-command-center | 2026-09-07 03:03 |
| oasis-ai-platform | 2026-09-07 04:56 |
| **blue-rise-website** (last to finish) | **2026-09-07 05:37** |

**Fleet clears: Monday 7 September 2026, 05:37 UTC — 01:37 EDT Montreal.**
Practical slot: **Monday 7 September, 09:00 EDT (13:00 UTC).**

Any redeploy of an app restarts *that app's* clock. `sunbizfunding.com` has no
clock yet — its 7 days begin when the watcher cuts it over.

### What that date does and does not authorise

Passing the soak authorises **per-project retirement** — deleting the Vercel
projects for the migrated apps, one at a time. It does **not** authorise deleting
the Vercel **account**, and the difference is not pedantry: three live
dependencies still terminate on that account.

See "Before the account can be deleted" below. Everything there is fixable
inside the soak window.

> Generated 2026-08-30 ~07:45 UTC after the overnight execution run.
> Companions: [[brain/DNS_CUTOVER_AND_VERCEL_EXIT_CHECKLIST]] ·
> [[brain/WAVE3_OASIS_CC_RUNBOOK]] · baselines in
> `state/cloudflare_baselines/2026-08-30/`.

## 2026-08-31 02:30Z — GATE 1 CLOSED FOR OASIS CC: FULLY CREDENTIALED, LAST VERCEL PATH CUT

**`oasis-command-center` now runs on Workers with a complete secret set.** 100
secrets pushed, **zero `--allow-missing` warnings** — the first deploy in this
migration that needed no exemption. The live apex reports **9 of 12 integrations
present, which is exact parity with the Vercel baseline**: the same three
(`BRAVO_OPENAI_API_KEY`, `BRAVO_SUPABASE_ANON_KEY`, `CHAT_ATTACHMENT_HMAC_KEY`)
were absent on Vercel too, so they are pre-existing and not introduced here.

CC located the missing Google credentials as un-prefixed globals at the top of
the store; Antigravity mapped them in. Verified before deploying, not assumed:
`GOOGLE_CLIENT_ID` and `GOOGLE_SYSTEM_CALENDAR_CLIENT_ID` hold **different**
values, which is the specific failure an earlier adversarial review predicted
(the app keeps two Google OAuth clients on purpose — a rep-facing web client and
a headless desktop identity, and one cannot be both).

### The last Vercel path for this app, which the apex cutover did not close

`www.oasisai.work/app/*` was still proxying to `agent-dashboard-cc90210.vercel.app`
and serving a live 200. The apex cutover on 08-30 moved `oasisai.work` but left
this second route to the same dashboard pointing at Vercel. It now reaches the
Worker over a **service binding** (`DASHBOARD → oasis-command-center`), so the
request never leaves Cloudflare and nothing depends on the workers.dev subdomain
staying enabled.

Proof it is actually the Worker serving it and not a silent fall-through:
`/app/api/health` reports the Worker build, while the Vercel deployment reports a
different one. `/app`, `/app/` and `/app/login` all 200; `/app/dashboard` 307s to
auth as expected.

⚠ **One regression happened during this change and was caught before it stood.**
Naming the binding's origin `oasis-command-center.internal` routed correctly but
returned **530 on `/app` and `/app/`** while deeper paths still worked — the Next
server does host-dependent work on the root route and an unresolvable hostname
breaks it. The binding decides routing; the hostname is what the *app* sees, so
it must be the real public origin. The lesson generalises: **when a proxy target
changes, probe the ROOT path, not just a deep one** — a deep path can succeed
while the root fails.

### Google sign-in is broken, and was broken before this migration

Probing `/api/auth/google/start` on the **live Vercel** deployment shows it
hands Google a `client_id` whose registered redirect URIs do **not** include the
callback the app itself emits. Google answers `redirect_uri_mismatch`. This is a
**pre-existing production defect on Vercel, not a cutover regression** — it fails
identically on both stacks, so it neither blocks nor is fixed by the migration.

Three distinct Google OAuth clients are now accounted for, each verified against
Google's token endpoint rather than by name:

| Client | Secret in the store? | State |
|---|---|---|
| the store's `GOOGLE_CLIENT_ID` pair | yes, and it **authenticates** | valid client; its redirect URIs do not include the production callback |
| the system-calendar pair | yes, and it **authenticates** | valid, in use for the shared calendar |
| the client **live production actually uses** | **no — all six candidates failed** | its secret exists only in the Google Cloud Console |

To restore Google sign-in CC needs the client secret for the client whose id
production already serves, and that client must have the production callback
registered. Neither is blocking for the Vercel exit. Tools:
`scripts/integrations/google_client_pair_probe.py` (which secret pairs with which
client) and `scripts/integrations/secret_identity_check.py` (are two keys the
same credential, without revealing either).

### Crons after the redeploy

`cron-driver.yml` targets `https://oasisai.work`, which is the Worker. The three
most recent scheduled runs succeeded. After the 02:20Z redeploy, unauthenticated
probes of four cron routes all return **401 (configured)** rather than 500 (secret
missing) or 404 (route gone) — checked without firing production jobs.

### sunbizfunding.com — the repoint has not reached the registrar

Reported repointed twice; both times the live check disagreed, and this is **not
propagation lag**: Google's own nameservers still answer authoritatively for the
domain, which means the registrar record was never changed.

- **Set these two at the registrar:** `damian.ns.cloudflare.com` and
  `sydney.ns.cloudflare.com`
- **Currently served:** `ns-cloud-a1..a4.googledomains.com`

`wrangler_tool.py zones` now prints both lines for any zone stuck at `pending`,
so "still pending" is never reported again without the values needed to fix it.

### Adversarial parity sweep: Worker vs Vercel, route class by route class

36 differences found, adversarially verified: **1 confirmed blocking, 2 real but
non-blocking, 33 informational.** Two of these were invisible to code review and
only a live probe of both stacks could have surfaced them.

**1 — CLEARTEXT HTTP ON EVERY MIGRATED ZONE (fixed).** Vercel answered plain HTTP
with a 308 to HTTPS before app code ran; Cloudflare does not by default, and
nothing in the migration turned it on. All six hostnames were serving their
login page over http:// with a 200. Worse than it first looked:

- the HSTS header the Worker sends rides on the **cleartext** response, where
  RFC 6797 requires browsers to ignore it — it protects the second visit, not
  the first;
- `oasisai.work` is **not** on the HSTS preload list; `vercel.app` **is**. Vercel
  had two independent protections, the Worker had zero;
- `oasis_session` is `Secure`, so a successful cleartext login returns
  `{ok:true}` and the browser then **discards the cookie** — an invisible login
  loop with the password already sent unencrypted;
- middleware's own bounce preserved the scheme (`http://…/dashboard` → 307 →
  `http://…/login`), so nothing in the request path escaped cleartext.

Fixed by enabling `always_use_https` on all six zones. Verified live: every
`http://<host>/login` now 301s to https. `wrangler_tool.py zone-https` audits
this and can only ever turn encryption on.

**2 — CONTENT-HASHED ASSETS LOST IMMUTABLE CACHING (fixed).** Vercel served
`/_next/static/*` as `public,max-age=31536000,immutable`; Workers defaulted to
`max-age=0, must-revalidate`, so every repeat visitor re-validated every JS and
CSS chunk on every page load. Fleet-wide. Fixed with a `public/_headers` file
per app; verified `immutable` is now returned.

**3 — public/ SKIPS MIDDLEWARE ON WORKERS (open, CC's call).** Cloudflare's asset
handler answers before the Worker runs, so files in `public/` bypass the auth
gate. Six Arthrisil marketing mp4s that returned **307 on Vercel return 200
here**. Everything else in `public/` is unauthenticated on both stacks.

⚠ **The obvious fix is worse than the problem, and this was measured, not
assumed.** Adding `run_worker_first: ["/media/*"]` did gate the mp4s correctly —
and simultaneously turned `end-card-preview.png`, a file middleware *allows*,
into a **404**, because the Worker cannot serve a `public/` file handed to it.
Reverted. Trading a live asset for a marketing video's privacy is the wrong way
round. If CC wants these gated, the correct fix is to move them out of `public/`
behind a route handler, not to reroute the asset path.

**Refuted on inspection:** `/oasis-loop/index.html` looked like a broken public
microsite (307 on the Worker, 200 on Vercel). It is a trailing-slash
canonicalisation — it 307s to `/oasis-loop/`, which serves 200, and the path is
in middleware's public allowlist deliberately. Not a regression.

### What is left before the 7-day soak can start

| Item | Owner | Blocking Gate 1? |
|---|---|---|
| `breeze-portal` Plaid keys (3) | CC | no — CC accepted a degraded deploy; Plaid routes 401 |
| `sunbizfunding.com` nameservers | CC | **yes** — two brand hostnames still resolve to Vercel |
| Google sign-in client secret | CC | no — broken on both stacks, pre-existing |

---

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
| breezeadvance.credit | **Workers** | superseded 2026-08-31: breeze-portal deployed and attached; Plaid routes 401 until CC adds the 3 keys |
| sunbizfunding.com + www | **Vercel** | zone still PENDING — nameservers still at Google Domains |
| arthrisil.com | third party, **403** | not a zone in this account; broken before the migration |

### Cancellation timeline — three gates, in order

**Gate 1 — finish the fleet.** Superseded by the 2026-08-31 02:30Z section
above; kept here for the trail of what each item turned out to be.
- ~~`breeze-portal`~~ **DONE.** Adapter installed, deployed, `breezeadvance.credit`
  attached and serving 200 from Workers. BREEZE_ENCRYPTION_KEY was recovered by
  CC, never rotated, as required. **Plaid keys (3) remain absent** — CC accepted
  a degraded deploy, so bank-linking routes 401 until they land.
- ~~`opt-in-vault`~~ **DONE.** Deployed with all 21 secrets and a rewritten
  trust model (Cloudflare operator-attestation edge). 360 tests green.
- ~~`oasis-command-center`~~ **DONE.** 100 secrets, zero gaps, parity with the
  Vercel baseline, and its last Vercel-bound path (`/app/*`) closed.
- `sunbizfunding.com`: **STILL THE ONE BLOCKER.** The nameserver change has not
  reached the registrar — exact values in the 02:30Z section above.

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

## VERDICT: **GATE 1 CLEARED (operator decision 2026-08-31) · GATE 2 SOAK RUNNING**

`vercel_exit_report.py` still exits 2 and that is correct — it keeps measuring
what is outstanding rather than being told the answer. Two items are recorded
as operator-accepted; three (the breezeadvance hostnames) are still reported as
blocking because they gate ACCOUNT deletion and CC has not ruled on them.

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
