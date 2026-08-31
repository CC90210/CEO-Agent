---
last_updated: 2026-08-31
tags: [cloudflare, migration, vercel-exit, overnight, briefing]
---

# Morning Briefing — overnight of 2026-08-30 → 31

> Companions: [[brain/VERCEL_DECOMMISSIONING_READINESS]] ·
> [[brain/DNS_CUTOVER_AND_VERCEL_EXIT_CHECKLIST]]
> Live verdict is always `python scripts/vercel_exit_report.py`, not this file.

## The one-line answer

**Gate 1 is NOT cleared, and it is not close to failing either — it is waiting on
a single registrar edit that only you can make.** Everything else on the fleet is
done, deployed, verified and healthy. Nothing is blocked on me.

## Do these three things and Gate 1 closes

**1. Move the nameservers (2 minutes, unblocks the 7-day soak).**
At whatever registrar holds `sunbizfunding.com`, replace the four
`ns-cloud-*.googledomains.com` entries with exactly:

```
damian.ns.cloudflare.com
sydney.ns.cloudflare.com
```

A watcher is running right now. Within 15 minutes of that change taking effect it
will verify the Cloudflare zone is active, health-check the Worker, cut the
domain over, and Telegram you the result. **You do not need to do anything else
for sunbizfunding.** If it is still not moved by 08:00 you will get a message
saying so.

> This has now been reported as done twice and both times the live check
> disagreed — and it is not propagation lag: Google's own nameservers still
> answer authoritatively for the domain, which means the registrar record itself
> was never changed. Worth confirming the save actually took.

**2. Fix Google sign-in (one console visit — details and the *corrected*
diagnosis below).**

**3. Add the three Plaid keys** whenever convenient — `PLAID_CLIENT_ID`,
`PLAID_SECRET`, `PLAID_ENV`. Breeze bank-linking 401s until then, which you
already accepted.

**And before ANY Vercel cancellation — settle one question:** who owns the Vercel
account serving `breezeadvance.com`? It is a client's live site, it is served
entirely by Vercel, and it is not in our Cloudflare account. If it is on our
Vercel, cancelling takes a client offline. Details below.

---

## ⚠ I caused a production outage last night and fixed it

Being straight about this because it is the most important thing that happened.

My service-binding refactor earlier in the evening wrote the proxy fallback as
`(via ?? { fetch }).fetch(proxied)`. That reads as identical to `fetch(proxied)`
and is not: pulling the global `fetch` into an object literal calls it with that
literal as `this`, which throws. Cloudflare returned **error 1101 on every
`/api/*` request to `www.oasisai.work`** — including **all five Stripe flow
rewrites** — while the Vercel origin behind them sat healthy at 200.

`/app/*` kept working, which is exactly why I missed it: that path passes a real
service binding and never reaches the broken branch. **I verified the path I
changed and not the path I did not.**

Fixed, deployed and verified: all five Stripe flows, `/api/health` and
`/api/contact` return 200 through the proxy and match the Vercel origin
status-for-status; `/app` and `/app/login` still 200.

### The worse part, and what I did about it

**`fleet_health_check.py` reported the fleet 10/11 healthy for the entire
outage.** Its probe list for `oasis-ai-platform` was `["/"]` — a static landing
page served by the assets binding, which never touches the failing code path.

That router fronts **three surfaces served by three different mechanisms**
(assets binding, service binding to the dashboard Worker, proxy to Vercel
functions). One being healthy says nothing about the other two. All three are
probed now, revenue path included, and I confirmed the fix is not decorative:
`classify(500)` returns `SERVER-ERROR`, not `ok`, so these probes *would* have
failed during the outage.

---

## Google sign-in — root cause found, and it CORRECTS what I told you earlier

**What I said last night:** the store's Google client is valid, it just does not
have the production callback registered.

**What is actually true:** the store's `GOOGLE_CLIENT_ID` is a **native/Desktop
OAuth client**. It is the wrong *type*. **No Cloud Console change can rescue it**
— a Desktop client can never accept an `https://` redirect.

Proof (a Desktop client accepts the out-of-band redirect; a Web client rejects
it):

| Client | `urn:ietf:wg:oauth:2.0:oob` | Type |
|---|---|---|
| `877445197300-3vgs…` — what the Worker serves, = store `GOOGLE_CLIENT_ID` | accepted | **Desktop** |
| `266259068460-6hiq…` — what Vercel serves | explicitly rejected | **Web** |

So the two stacks fail identically (`redirect_uri_mismatch`) for **different
reasons**:

- **`oasisai.work` (Worker):** wrong client type. Unfixable in the console.
- **Vercel:** right client type, but `/api/auth/google/callback` is not in its
  registered URI list.

Both were broken **before** this migration. Neither is a cutover regression.

### The fix — one console visit, then hand me two values

You need **a Web-type OAuth client** whose registered redirect URIs include the
callback the Worker actually emits. In Google Cloud Console:

1. Either reuse the existing Web client
   `266259068460-6hiqinfgi0srcbadae8rkir5qhn82lkg…` **or create a new Web
   client** — both work, pick whichever is tidier.
2. **Authorized redirect URIs → add BOTH of these** (keep anything already
   there):
   ```
   https://oasisai.work/api/auth/google/callback
   https://oasisai.work/api/auth/google-oauth/callback
   ```

   > **Both, not one.** Sign-in and the Gmail-connect feature in Settings share
   > the *same* `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` pair but use
   > *different* callback paths (`app/api/auth/google/callback` vs
   > `app/api/auth/google-oauth/callback`). Registering only the first fixes
   > sign-in and leaves Gmail connect broken — I verified both are currently
   > MISMATCH on `oasisai.work`.
   >
   > **Gmail connect is a live Vercel dependency you may not know about.** It
   > works today *only* because the vercel.app connect callback is registered on
   > that client — I confirmed that one is accepted. When Vercel goes away, the
   > feature dies unless the `oasisai.work` URI above is added.

   Optionally add the two `https://agent-dashboard-cc90210.vercel.app/...`
   equivalents if you want both flows working on Vercel during the soak.
3. Copy that client's **id and secret** (minting a fresh secret is cleaner — you
   never handle the old value, and Google supports two during rotation).

Hand me both and I will update the store and redeploy.

> Two independent analyses disagreed on whether to reuse `266259068460` (one
> called it the legacy Vercel client that should be left alone). I have written
> the instruction so it is correct either way — what actually matters is that the
> client is **Web type** and carries that redirect URI. Reusing or replacing it
> is your call, not a correctness question.

**Why I cannot do step 2 myself:** Vercel marks that variable `sensitive`, which
means its API will not decrypt it for anyone — I verified this specifically
(`GOOGLE_CLIENT_SECRET` shows as `FILL(sensitive)`, one of 26 unrecoverable of
100). It is not in the store under any name either: I tested all six
`*CLIENT_SECRET*` keys against Google's token endpoint and every one returned
`invalid_client`.

**Expect a second failure after this.** Fixing the redirect gets you to Google's
consent screen; whether the *callback* then succeeds depends on the user lookup
behind it. Worth a single end-to-end sign-in attempt rather than assuming.

### Three things NOT to do, each of which looks reasonable

- **Do not "fix" the redirect_uri in code.** `app/api/auth/google/start/route.ts:25`
  derives it from `req.url`, which resolves to the correct public host on both
  stacks — verified in the live `Location` headers. The URI the app emits is
  right; the registration is what is missing.
- **Do not add `PUBLIC_APP_URL` to the sign-in route.** It is already set
  correctly (`https://oasisai.work` — confirmed by digest without reading it),
  and the sign-in family deliberately ignores it so that every host serving the
  app self-describes correctly. Adding it changes nothing and removes that
  property.
- **Do not treat broken Google sign-in as a reason to roll back to Vercel.** It
  was already dead there — the sign-in callback is unregistered on *both* hosts.
  Rolling back restores nothing. Password login works on both stacks and is
  unaffected.

Incidental security check while probing: a spoofed `Host:` header against
`oasisai.work` is rejected at the Cloudflare edge with a 403, so the `req.url`
derivation is not an injection surface.

---

## Traffic audit — where every byte is served from

| Hostname | Served by | Status |
|---|---|---|
| oasisai.work, www.oasisai.work | **Workers** | 200, cf-ray |
| bluerisebusinesscapital.com (+www) | **Workers** | 200, cf-ray |
| propflow.pro (+www) | **Workers** | 200, cf-ray |
| nostalgicrequests.com (+www) | **Workers** | 200, cf-ray |
| breezeadvance.credit | **Workers** | 200, cf-ray |
| **sunbizfunding.com, www.sunbizfunding.com** | **Vercel** | the known blocker |
| apply.sunbizfunding.com | NXDOMAIN | broken before the migration |

**The honest answer to "0 bytes from Vercel" is NO — and my first pass at this
undercounted it.** I originally audited only the hostnames in our own registry,
which is exactly the mistake of trusting a map over the territory. A wider sweep,
measuring the FIRST response without following redirects (a redirect is itself
served by someone), finds **five** Vercel-origin hostnames plus a proxied path:

| Hostname | First response | Origin |
|---|---|---|
| `sunbizfunding.com` | 308 → www | **Vercel** — known blocker |
| `www.sunbizfunding.com` | 200 | **Vercel** — known blocker |
| `www.breezeadvance.credit` | 307 → apex | **Vercel** ← *not previously known* |
| `breezeadvance.com` | 308 → www | **Vercel** ← *not previously known* |
| `www.breezeadvance.com` | 200, the client's live site | **Vercel** ← *not previously known* |

Plus: **`www.oasisai.work/api/*` is proxied to `oasis-ai-platform.vercel.app`.**
The edge is Cloudflare so the headers look like Workers, but the response body is
generated by Vercel's Node functions, Stripe handlers included. That is stage 1
of the platform migration by design; stage 2 (porting the seven handlers into the
Worker) has not been done.

### Two things here that change the cancellation decision

**1. The breeze cutover is half-done.** I attached the apex and not `www`. The
zone still has `www.breezeadvance.credit` — and a `*` wildcard — pointing at
Vercel IPs (216.150.x). Cloudflare proxies them, which is why they show `cf-ray`
and looked migrated; the origin is Vercel. Cancelling Vercel breaks the www
redirect and anything matching that wildcard.

> I did **not** fix this overnight, deliberately. Attaching `www` to the Worker
> would make it serve the portal directly instead of redirecting, and
> breeze-portal is an authenticated client financial portal — serving it on two
> hostnames risks splitting sessions via cookie domain. That is not a change to
> make unattended at 5am on a client's money surface. It is a five-minute job
> with you awake, and the alternative (a Cloudflare redirect rule) keeps the
> current behaviour exactly.

**2. `breezeadvance.com` is a client's live business site, served entirely by
Vercel, and it is NOT a zone in our Cloudflare account.** Its nameservers are at
Google Domains. **I could not determine which Vercel account owns it** — the
project-domains API returned 403 for our token, so I am not going to guess.

**This must be resolved before anyone cancels anything.** If that domain sits on
our Vercel account, cancelling takes down a client's website. If it sits on the
client's own account, it is irrelevant to us. One check settles it, and it is the
single highest-stakes unknown from tonight.

**Net:** `oasis-ai-platform`'s Vercel project cannot be cancelled at all yet (the
`/api/*` dependency), `breeze-portal`'s cannot until `www` moves, and the
`breezeadvance.com` ownership question gates the whole decision.

### Rollback assets — checked, and the scare was unfounded twice over

Only `oasisai.work` carries a `_vercel` TXT record; four zones have none. Those
are the documented rollback path, so I checked what it costs — and it costs
nothing, for two independent reasons:

1. Vercel reports all four domains **"already verified"** on their projects and
   still attached. The TXT is only needed for the initial verification
   handshake, not to keep serving.
2. On at least three of those zones the records were **never there to begin
   with** — they were not deleted by the migration.

**Rollback is intact.** Verified by querying Vercel, not inferred from DNS.

---

## Fixed overnight: Blue Rise was telling Google its home was a vercel.app URL

`bluerisebusinesscapital.com` — a live customer domain — served
`rel="canonical"` and `og:url` both pointing at
`https://blue-rise-website.vercel.app`. So the real domain was serving the
content while declaring the *platform* URL canonical. That invites the vercel.app
URL to outrank the brand, and it becomes a dead canonical the moment that Vercel
project is retired.

Predates the migration, but the cutover made it worse: the real domain moved to
Workers while the canonical kept naming Vercel. Fixed, deployed, verified live —
canonical and `og:url` now read `https://bluerisebusinesscapital.com` and the
served HTML contains zero `vercel.app` references. I checked the other five
migrated hostnames first; theirs are correct or absent, so this was an instance
rather than a class.

## The exit gate itself was wrong, and that is now fixed

Worth its own heading because of what it authorises. `vercel_exit_report.py` is
the check you would run before cancelling. It reported **two** hostnames still on
Vercel. There are **five** — I found the other three by hand, which means the
gate could not have.

Two independent blind spots:

- **Enumeration.** It read hostnames from `apps.json` `custom_domains`. A
  registry cannot reveal what it omits, and `www.breezeadvance.credit` /
  `breezeadvance.com` were never listed. It now derives `www` for every apex it
  sees — which is exactly where a half-finished cutover hides — plus a curated
  list for hostnames outside our Cloudflare account, which no zone listing can
  discover.
- **Method.** It compared resolved IPs to Vercel's prefixes. Anything proxied
  through Cloudflare resolves to `172.x` regardless of what sits behind it, so a
  record whose *origin* is Vercel passed. It now also probes over HTTP for
  `x-vercel-id` **with redirects disabled** — because a redirect is a response
  somebody serves, and following the hop reports the destination instead.

It now watches 15 hostnames and flags all five, labelling the proxied one
explicitly. No migrated hostname is falsely flagged.

## Flagged, not acted on — worth your judgement

From a 46-agent sweep over the OAuth path and the data layer behind it. These are
reported rather than fixed because each is a judgement call or needs production
data I would not query unattended:

- **The Google callback refuses unknown accounts by design** — the user row must
  pre-exist. So after the redirect URIs are registered, sign-in may still fail
  for an account that has never been provisioned. That is the "second failure"
  to expect, and it is intended behaviour, not a bug.
- **A user with more than one `user_profiles` row 401s on every API call**, and
  two profile resolvers disagree with each other — so a page can render while
  every request behind it fails. Latent, not currently firing.
- **The OAuth sign-in path has no executable test.** Its only "test" greps the
  source file for a string. Worth fixing before the next change to that route.
- **The Gmail-connect path still reads Supabase**, which blocks a clean full
  decommissioning even after Vercel is gone.
- **The Cloudflare app registry's domain list is wrong on two of three rows** for
  the dashboard Worker — the same class of staleness that hid three hostnames
  from the exit gate.

## Overnight state

- **Cutover watcher:** running, 15-minute interval, 8-hour deadline. Log:
  `state/sunbiz_cutover_watch.log`. It will not act on a DNS answer alone — the
  Cloudflare zone must also read `active`, and the Worker must pass a live health
  check first. It will not retry a failed cutover; it reports and stops, with the
  rollback records captured verbatim to Telegram.
- **Gate:** 4 PASS / 0 regressions / 2 pending (sunbizfunding, Plaid).
- **Smoke:** 5 ok / 0 failed.
- **HTTPS:** enforced on all six zones.
- **Immutable asset caching:** live on all five production hostnames; all 12
  OpenNext apps now carry the canonical `_headers`, enforced by
  `scripts/tests/test_worker_asset_headers.py`.
