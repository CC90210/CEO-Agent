---
title: "Real Estate Suite — white-label plan (de-Mandy, keep the product)"
date: 2026-09-02
author: Bravo
repo: CC90210/real-estate-marketing-suite (private, VPS-only at /srv/listing-studio)
tags: [white-label, listing-studio, rems, real-estate, skeleton]
---

# White-label plan — turn the Listing Studio into a reusable skeleton

Keep: listings, media/rendering, **leads, pipeline, inbox**, SMS follow-ups,
Zillow handoff, approvals, digest. Remove: every trace of one named client.

## The good news, measured

The product is already ~80% multi-tenant. `migrations/0001_init.sql:23`:

```sql
company_name TEXT DEFAULT 'Real Estate Marketing Suite',
```

There is a real `organization` table and the brand is read from it at runtime.
"Mandy Management" is **never the schema default** — it only appears as a
hardcoded *fallback* when the org row is blank, plus some copy and comments.

So this is not a rebuild. It is: delete six fallbacks, move four hardcoded
values into the org row, and clean the docs.

## Blast radius, measured 2026-09-02 on `main` @ 237 files

| Term | Hits | Severity |
|---|---|---|
| `Mandy` | 53 | code fallbacks + comments + docs |
| `New Haven` | 26 | **one is in an outbound SMS template** |
| `773-9710` | 5 | client's Twilio number |
| `8627602216` | 2 | the client's personal Telegram chat id |
| `Sexyrapeezra` | 2 | **the EMPIRE bot serving client data — cross-tenant leak** |

28 files. No database schema change is required.

## 1 · Kill the hardcoded brand fallbacks

Six sites mention the client name, but only **two are live fallbacks** — the
rest are comments and operator-facing error strings. The distinction matters,
because only the first two can put a former client's name in front of a new
client's prospect:

**Behavioural (must change):**

- `worker/sms-daemon.ts:59` — `String(org.rows[0]?.company_name ?? '').trim() || 'Mandy Management'`
- `scripts/sms-once.ts:47` — the same expression, copy-pasted

**Cosmetic (change for hygiene, no runtime effect):**

- `lib/sms/config.ts:19` — comment
- `lib/sms/config.ts:40` — operator error text ("Buy the Mandy Management number…")
- `scripts/sms-doctor.ts:63` — operator error text
- `.env.example:99` — comment

**Change:** extract one helper, `lib/brand.ts`:

```ts
/** The operating company's name, from the organization row.
 *  There is no client-named default: a blank org row must read as an
 *  unconfigured install, not as somebody else's company. */
export async function brandName(db): Promise<string> {
  const row = await db.execute("select company_name from organization limit 1");
  const name = String(row.rows[0]?.company_name ?? "").trim();
  return name || "Real Estate Marketing Suite";   // matches the schema default
}
```

The fallback becomes the same neutral string the schema already uses, so a fresh
install is self-consistent instead of silently branded as a former client. Both
daemons and both scripts import it — that also removes the duplicated
`String(org.rows[0]?...)` expression currently copy-pasted in two workers.

## 2 · The outbound SMS template is the urgent one

`lib/sms/templates.ts:98` hard-codes the city into a message sent to prospects:

> `...New Haven. Tell me what you're after and I'll send matches.`

A new client would text *their* prospects about New Haven. This must come from
the org row. Add `organization.service_area TEXT` (nullable) and interpolate it;
when it is blank, use a sentence that needs no city rather than printing an
empty one.

## 3 · Move the remaining client constants into the org row

| Hardcoded now | Becomes |
|---|---|
| Twilio number `773-9710` (`lib/sms/config.ts`) | already env-driven — delete the client-named comments only |
| Telegram chat id `8627602216` (`lib/zillow/handoff.ts:253`) | comment only; rewrite the example generically |
| `@Sexyrapeezra_bot` | **per-tenant bot token in env.** See §5 — this is a security fix, not cosmetics |
| "New Haven Apartments" DM profiles (`lib/dm/ingest.ts`, `worker/dm-daemon.ts`, `lib/dm/policy.ts`) | `organization.dm_profile_handles` (JSON array), read at poll time |

## 4 · Tests and fixtures

`tests/dm-ingest.test.ts` asserts *"only recognises the New Haven profiles"*.
Re-aim it at the configured handles rather than the literal city, so the test
still proves profile scoping without pinning a client. Same for
`tests/followups.test.ts:73` and `worker/python/tests/test_zillow_run.py` —
those are fixture addresses and can stay as obvious fake data, but should not
read as a real client's inventory. Use a clearly-fictional street.

## 5 · The cross-tenant leak — fix this regardless of white-labelling

`@Sexyrapeezra_bot` is the **empire** Telegram bot. It was serving this client's
data, which means a client's leads were flowing through a bot that also carries
SunBiz and empire traffic. That was flagged on 2026-08-24 and is still open.

The white-label makes it structural: the bot token must be a per-install env
value with **no default**, so a new tenant cannot inherit the empire bot by
omission. Fail loud on a missing token rather than falling back.

## 6 · Data reset — how, and what NOT to do

**SUPERSEDED 2026-09-02 — do not hand-write this. Use `scripts/reset-tenant.ts`**
(shipped in the suite repo, commit `272df77`, five tests):

```
npx tsx scripts/reset-tenant.ts                              # dry run, counts only
npx tsx scripts/reset-tenant.ts --yes                        # wipe
npx tsx scripts/reset-tenant.ts --yes --keep-owner you@x.com # keep one account
```

**The hand-written order that used to be here was wrong in two ways, and both
would have silently left client data behind** — recorded because the mistakes
are the reason the script has a guard:

- `instagram_messages` / `instagram_conversations` **do not exist**. Migration
  0012 created them under those names and **0013 RENAMEd them to `dm_messages`
  and `dm_conversations`**. A list derived from `CREATE TABLE` alone misses the
  rename and leaves both tables full of the former client's DMs.
- `publishing_jobs_v` is a **phantom** — a truncated grep match on
  `publishing_jobs_v2` / `publishing_jobs_v3`, which 0002 and 0008 create as
  temporary rebuild tables and rename away.

The script re-reads `sqlite_master` after deleting and **refuses to report
success** if any table is unaccounted for, so the next migration that adds a
table fails loudly instead of quietly carrying rows into the next client's
install. It also backs up first via `backupDatabase()` or does not run, and
upserts the organization row — a freshly migrated database has **zero**
organization rows, so a bare `UPDATE` would configure nothing and still claim
success.

**Take a Turso dump first.** The database `real-estate-marketing-suite` is
dedicated and off-VPS, so the VPS decommission does not touch it; that is
deliberate. Do not drop the database — the schema plus 14 migrations *is* the
skeleton being kept.

## 7 · Hosting

Currently Vercel (`real-estate-marketing-suite.vercel.app`, auto-deploy on
`main`). Moving to Cloudflare Workers is possible via OpenNext — the empire
already runs that path for oasis-command-center and the tooling exists
(`wrangler_tool.py`). It is a genuine port, not a switch: `worker/` uses `tsx`
and long-lived PM2 polling, which does not translate to Workers directly. **The
five workers would still need a host.** Recommend: keep Vercel for the app,
decide the worker host separately. Flagged rather than assumed.

## Order of work

1. §5 bot token (security, independent of everything else)
2. §1 + §2 + §3 code changes, with §4 tests re-aimed
3. Turso dump
4. §6 data reset
5. Rename the repo / Vercel project last, once nothing references the old name

## Open decisions for CC

- **New name** for the skeleton. Everything above uses the neutral schema
  default "Real Estate Marketing Suite" as a placeholder.
- **Keep one user account** (an owner seed) or wipe `users` entirely and
  re-invite on first boot?
- **Worker hosting** if Cloudflare is wanted (§7).
