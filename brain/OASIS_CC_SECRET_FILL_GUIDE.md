---
last_updated: 2026-08-30
tags: [cloudflare, migration, secrets, oasis-command-center]
---

# OASIS CC — the 26 secrets, and where each one actually comes from

> Written 2026-08-30 instead of auto-filling them. Related:
> [[brain/VERCEL_DECOMMISSIONING_READINESS]] ·
> [[brain/DNS_CUTOVER_AND_VERCEL_EXIT_CHECKLIST]].

## Why these were not auto-filled

The ask was to fill them from key aliases, local `.env*` files, and "standard
default fallbacks". Two thirds of that is not available to me, and the last
third would be actively harmful:

1. **`.env*` files are not LLM-readable by design** (RULE 3 / `secret_guard`).
   That is a hard rule, not a limitation to route around.
2. **There are no safe "default fallbacks" for a credential.** Every one of
   these either authenticates to a third party or must byte-match a value held
   by a *counterpart system*. A guessed value does not fail at deploy — it
   deploys clean and fails later, in production, on the first real request.
   That is the worst shape a failure can take, and it is Anti-Slop #3 verbatim.
3. **Alias mapping IS legitimate, and I ran it** (presence-only, no values read).
   The result is below. It does not get us to zero, and pretending otherwise by
   filling the gap with plausible values would convert a blocked deploy into a
   broken one.

## The classification

**A — PAIRED SECRETS (7). A wrong value = a Worker that deploys and then fails
auth.** These must byte-match a value held somewhere else; there is no local
source of truth and no defaulting them.

| key | must match |
|---|---|
| `CRON_SECRET` | the GitHub secret `OASIS_CRON_SECRET` the cron driver sends |
| `BRIDGE_BEARER_TOKEN` | what the VPS bridge accepts |
| `BRIDGE_BEARER_TOKEN_OASIS_AI_CC` | the peer's configured token |
| `TT_PG_BRIDGE_TOKEN` | the TextTorrent bridge's token |
| `CLI_SIGNUP_SECRET` | what the CLI signup flow sends |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | the Supabase project the dashboard reads |
| `OASIS_OUTBOUND_HMAC_SECRET` | itself, historically — **changing it invalidates every outbound link already issued** |

**B — BARE NAME EXISTS IN THE STORE (7), but that is not proof it is the same
credential.** Needs one yes from CC per row, not an assumption:
`BOOKING_LINK`, `BRAVO_SUPABASE_URL`, `BRAVO_SUPABASE_SERVICE_ROLE_KEY`,
`GMAIL_USER`, `GMAIL_APP_PASSWORD`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.

⚠ **Do not take the Google pair from the bare names on their own.**
`GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN` is absent, and **a refresh token is bound
to the client that minted it** — setting a client id/secret that does not match
the refresh token breaks calendar OAuth in a way that looks like a permissions
bug. Take all three from the same place or none.

✅ The two `BRAVO_SUPABASE_*` rows are the one genuinely safe case: Supabase is
retired, and `scripts/run_dashboard_script.py` already ships documented compat
placeholders for exactly these because they only satisfy a startup check.

**C — ABSENT ENTIRELY (12).** Only CC can supply:
`BRAVO_ANTHROPIC_API_KEY`, `BRIDGE_VPS_URL`, `FUNMATE_EMAIL`,
`FUNMATE_APP_PASSWORD`, `GOOGLE_CALENDAR_ID`, `GOOGLE_SYSTEM_CALENDAR_ADDRESS`,
`GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN`, `NEXT_PUBLIC_BOOKING_URL`,
`NEXT_PUBLIC_BRIDGE_CHAT_BASE`, `NEXT_PUBLIC_SUPABASE_URL`, `OPERATOR_EMAIL`,
`PUBLIC_APP_URL`.

## ⚠ CORRECTION 2026-08-30 — these values cannot be read back by ANYONE

An earlier version of this page said to reveal the 26 in the Vercel dashboard.
**That is impossible**, and the correction matters because it changes the work.

Proven three ways:
1. REST API with `decrypt=true` → sensitive vars return no value.
2. **`vercel env pull` via the CLI** (built for this: `vercel_env_pull_sync.py`)
   → authenticated, linked, pulled the file successfully, and **all 26 came back
   EMPTY**. A control run on `listing-studio` returned 17 of 18 values and
   withheld only its single sensitive var — so the mechanism works and the
   sensitivity flag is what withholds.
3. Vercel's own docs: *"values are non-readable once created … Vercel stores the
   variable in an unreadable format"*, and the edit dialog states *"The current
   value is hidden."*

So the dashboard cannot show them either. **There is no extraction path — the
question is recovery or rotation, per key.**

## The actual path, per class

**Just state it** (config, not secret — CC knows these):
`PUBLIC_APP_URL`, `NEXT_PUBLIC_BOOKING_URL`, `BOOKING_LINK`, `OPERATOR_EMAIL`,
`GOOGLE_CALENDAR_ID`, `GOOGLE_SYSTEM_CALENDAR_ADDRESS`, `FUNMATE_EMAIL`,
`GMAIL_USER`, `NEXT_PUBLIC_BRIDGE_CHAT_BASE`, `BRIDGE_VPS_URL`,
`NEXT_PUBLIC_SUPABASE_URL`.

**Re-fetch from the issuing provider** (still readable at the source):
`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` → Google Cloud Console → the OAuth
client. `BRAVO_ANTHROPIC_API_KEY` → Anthropic console (or mint a new one).
`NEXT_PUBLIC_SUPABASE_ANON_KEY` → the Supabase project's API settings.
⚠ `GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN` is **not** re-fetchable — a refresh
token is shown once and is bound to the client that minted it. If it is lost,
re-run the OAuth consent for that client and take all three together.

**Rotate — set the new value on BOTH sides in one change:**
`CRON_SECRET` (Worker secret **and** the GitHub secret `OASIS_CRON_SECRET`),
`BRIDGE_BEARER_TOKEN` + `BRIDGE_BEARER_TOKEN_OASIS_AI_CC` (Worker **and** the
VPS bridge config), `TT_PG_BRIDGE_TOKEN` (Worker **and** the TextTorrent
bridge), `CLI_SIGNUP_SECRET` (Worker **and** the CLI flow),
`GMAIL_APP_PASSWORD` / `FUNMATE_APP_PASSWORD` (Google account → App passwords →
revoke and re-issue).

**Rotate only with eyes open:** `OASIS_OUTBOUND_HMAC_SECRET` — rotating it
**invalidates every outbound link already issued**. Decide deliberately whether
that is acceptable, or recover it from wherever it was originally generated.

**Free, if Supabase stays retired:** `BRAVO_SUPABASE_URL` and
`BRAVO_SUPABASE_SERVICE_ROLE_KEY` only satisfy a startup check —
`scripts/run_dashboard_script.py` already ships documented compat placeholders
for exactly these two.

Then: `wrangler_tool.py secrets-plan --app oasis-command-center` → expect
`missing: 0`, and `deploy_oasis_cc_phase2.py --execute` (still needs Workers
Paid on `e371c0f2…`).
