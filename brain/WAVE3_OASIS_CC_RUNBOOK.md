---
last_updated: 2026-08-30
tags: [cloudflare, migration, cron, oasis-command-center, wave-3]
---

# Wave 3 Runbook — OASIS Command Center → Cloudflare Workers

> Cron-focused execution runbook (CC-requested 2026-08-29). App-level blockers
> (@napi-rs/canvas, pdfjs-dist, libsql→/web, bundle size) are scoped in
> [[brain/VERCEL_TO_CLOUDFLARE_MIGRATION]] §Wave 3 and the approved plan; this
> document owns the **28-cron migration with zero dropped ticks**.
> Related: [[config/cloudflare/apps.json]] · gap report
> `state/cloudflare_baselines/2026-08-29/secret_gaps.md`.

## Entry criteria (all required before Phase A)
1. Waves 1–2 gates passed (soak + zone-diff clean).
2. oasisai.work **auto-renew confirmed ON** (blocked on zone-account token or CC dashboard check).
3. The `OASIS_COMMAND_CENTER__*` FILL lines completed in the agents env store.
   **26 -> 16 outstanding as of 2026-08-30** (disk hunt + derivation; see
   `secret_disk_hunt.py`). ⚠ `CRON_SECRET` is FILLED BUT ROTATED — see the
   alignment step in Phase C, which is now mandatory.
4. **APEX coordination:** `coord_claim.py acquire --repo oasis-command-center --paths "vercel.json,next.config.js,package.json,.github/workflows/**,app/api/**,lib/cron-auth.ts" --task "CF Workers migration"` + `agent_activity.py post` announce ("Vercel production deploys on oasisai.work" is a declared shared domain).
5. App worker (`oasis-command-center`) verified green on workers.dev (parity e2e), BEFORE any cron work — crons fan out to the app, so the app moves first.

## ⚠ CORRECTION 2026-08-30 — the thing being replaced is NOT Vercel's scheduler

**Vercel's cron scheduler stopped executing for this project on 2026-08-06**
(documented in `.github/workflows/cron-driver.yml`: crons registered, enabled,
pinned, reachable, Pro plan — the scheduler alone was at fault; the dispatcher
had not claimed a row in four days and 230 steps sat overdue while everything
reported healthy). Since then the REAL firer is a **GitHub Actions
`cron-driver.yml`**: one workflow schedule per distinct vercel.json expression,
routes selected by `github.event.schedule` (not wall clock — a late run still
knows which tick it is), with `tests/cron-driver-coverage.test.ts` asserting it
cannot drift from vercel.json.

**Consequences for this runbook (supersedes Phase C step 3 as originally
written):**
1. Removing `crons` from vercel.json disables **nothing** — it is already inert. (Done in PR #347; the list now lives in `config/cron-registry.json`.)
   The cutover must disable **`.github/workflows/cron-driver.yml`** instead
   (delete the `schedule:` triggers, keep `workflow_dispatch` as the manual
   fallback). Doing the vercel.json edit alone would leave the GH driver and
   the Worker BOTH firing indefinitely.
2. The Phase A dry-tick comparison baseline is the **GH Actions run history**,
   not the Vercel cron log (which has been empty since 08-06).
3. Production runs with **`CRON_ALLOW_LOCAL=1`**, so today's second auth leg is
   effectively bypassed and the routes are bearer-only. The `CRON_ATTEST_SECRET`
   leg added to `lib/cron-auth.ts` restores a real second factor; **unset
   `CRON_ALLOW_LOCAL` at cutover** once the Worker sends the attest header.
4. **Schedule source of truth moved (PR #347, 2026-08-30):** it is now
   `config/cron-registry.json`, NOT vercel.json — whose `crons` key is deleted
   and must never come back (a second registry is a silently-wrong one). Both
   firers are pinned to the registry: the GH driver by
   `tests/cron-driver-coverage.test.ts`, and the Worker's `CRON_TABLE` by
   transcription (verified 2026-08-30 against 4 live dry ticks by an
   independent matcher — 28/28 exact).
5. Keep `cron-driver.yml` in the repo, triggers removed — it is the proven
   fallback if the Worker path ever needs to be rolled back after Vercel exit.

## The 28 crons — classification table (NOT a source of truth)

> **`config/cron-registry.json` is the schedule of record.** The paths and
> schedules below are reproduced for reading convenience only; if they ever
> disagree with the registry, **the registry wins and this table is stale**.
> Nothing tests this copy, which is exactly how the original vercel.json/driver
> split drifted. The one column that is NOT derivable from the registry — and
> so the only reason this table exists — is **Class**, which drives the Phase B
> overlap-safety audit.

| # | Path | Schedule (UTC) | Class |
|---|---|---|---|
| 1 | /api/cron/materialize-plans | 0 3 * * * | write, verify claim |
| 2 | /api/cron/collect-outreach-intel?write=1 | 0 * * * * | collector (idempotent upsert) |
| 3 | /api/cron/collect-cc-metrics?write=1 | 15 * * * * | collector |
| 4 | /api/cron/dispatch-scheduled-sends | */5 * * * * | SEND — **CAS claim + stale reclaim (verified in header)** |
| 5 | /api/cron/dispatch-founder-meeting-reminders | */5 * * * * | SEND, verify claim |
| 6 | /api/cron/enroll-drips | */15 * * * * | write (caps: DRIPS_ENROLL_*) |
| 7 | /api/cron/scan-lender-replies?write=1 | */10 * * * * | scanner |
| 8 | /api/cron/dispatch-drips | */5 * * * * | SEND — **CAS row-claim, "additional invocation harmless" (verified)** |
| 9 | /api/cron/reconcile-drip-telemetry | 17 * * * * | reconciler |
| 10 | /api/cron/reconcile-website-sales-payments | 17 * * * * | reconciler |
| 11 | /api/cron/dispatch-scheduled-calls | */5 * * * * | SEND, verify claim |
| 12 | /api/cron/sync-tt-inbox | */30 * * * * | scanner |
| 13 | /api/cron/sync-tt-inbox?account=followup | */30 * * * * | scanner |
| 14 | /api/cron/operator-email-agent?write=1 | */10 * * * * | SEND-capable, verify claim |
| 15 | /api/cron/scan-bounces?write=1 | */30 * * * * | scanner |
| 16 | /api/cron/scan-bounces?write=1&brand=bluerise | */30 * * * * | scanner |
| 17 | /api/cron/scan-funmate-replies?write=1 | */30 * * * * | scanner |
| 18 | /api/cron/sweep-stale-sent-app | 0 13 * * * | sweep |
| 19 | /api/cron/kixie-compliance-scan | 10 13 * * * | scanner |
| 20 | /api/cron/kixie-compliance-scan?mode=weekly | 40 13 * * 1 | scanner |
| 21 | /api/cron/enroll-accelerated | */15 * * * * | write (ACCELERATED_ENROLL_LIVE gate) |
| 22 | /api/cron/tps-enroll?write=1 | */10 * * * * | write, verify claim |
| 23 | /api/cron/tps-backlog-watch | 0 */6 * * * | watch |
| 24 | /api/cron/renewal-thresholds | 15 13 * * * | alerting |
| 25 | /api/cron/health-check | */15 * * * * | read-only |
| 26 | /api/cron/sync-sms-numbers | 0 6,18 * * * | sync |
| 27 | /api/cron/reconcile-sms | */15 * * * * | reconciler |
| 28 | /api/cron/dispatch-bulk-email | */5 * * * * | SEND, verify claim |

Both platforms run cron in **UTC** — expressions carry over verbatim, no
timezone drift. (`:17` and `:40` offsets exist deliberately; keep them.)

## ⚠ MANDATORY AT CUTOVER — align the rotated CRON_SECRET

`CRON_SECRET` could not be recovered (sensitive-type in Vercel, absent from
disk, write-only in GitHub), so on 2026-08-30 a fresh value was minted and set
**on the Cloudflare Worker only**. That was safe precisely because
`.github/workflows/cron-driver.yml` still targets the VERCEL deployment, so the
two sides are independent today.

**The moment the driver is repointed at the Worker, they stop being
independent.** The GitHub secret `OASIS_CRON_SECRET` still holds the OLD Vercel
value. Repointing without aligning them means every one of the 28 routes
answers 401 and the fleet goes quiet — no error, no alert, exactly the shape of
the 2026-08-06 outage this runbook exists to prevent.

So, in the SAME change that repoints the driver:

```bash
# push the rotated value from the agents store into the GitHub secret
# (value flows store -> gh stdin; it is never printed or placed on argv)
python - <<'EOF'
import subprocess, sys
sys.path.insert(0, "scripts")
from lib.secret_loader import load_env
v = load_env()["OASIS_COMMAND_CENTER__CRON_SECRET"]
subprocess.run(["gh", "secret", "set", "OASIS_CRON_SECRET",
                "--repo", "CC90210/oasis-command-center"],
               input=v, text=True, check=True)
EOF
```

Then prove it rather than assume: one `workflow_dispatch` run of cron-driver
must come back 2xx, not 401, before the Vercel deployment is retired.

## Architecture — `oasis-cc-cron` companion worker

- **Own tiny repo dir** `workers/oasis-cc-cron/` inside oasis-command-center
  (claimed paths) — NOT a separate repo; versioned with the app it drives.
- **One trigger: `* * * * *`** (every minute). `scheduled()` evaluates the
  28-entry table with a small cron-expression matcher (minute/hour/dom/mon/dow,
  supports `*/n`, lists, single values — ~40 lines, unit-tested against every
  expression above). Rationale: Workers caps cron triggers per worker (the
  28 entries hold 14 distinct expressions — over the cap); a minute tick +
  matcher keeps the table verbatim, one worker, exact Vercel fidelity.
  1,440 invocations/day is noise. (Verify the current per-worker trigger cap
  at execution — the minute-tick design is cap-independent either way.)
- **Fan-out:** for each due entry, `fetch` the app's production URL with
  `Authorization: Bearer ${CRON_SECRET}` + `x-oasis-cron-attest: ${CRON_ATTEST_SECRET}`.
  `ctx.waitUntil` per call; per-call timeout generous (Workers has no
  maxDuration knob to inherit; the routes already self-budget — see
  dispatch-scheduled-sends' soft time budget).
- **Kill switch:** `CRON_FORWARD` secret checked first. Accepts
  `on|true|1|yes` (case/whitespace-insensitive); **anything else — including
  unset, `off`, `false`, or a typo — is a DRY tick**: log the due list, call
  nothing. Unit-tested both directions. Flipping it is a secret update —
  seconds, no rebuild.
- **Telemetry:** every tick logs `{minute, due:[paths], forwarded, status[]}`
  to Workers observability; non-2xx forwards also POST to the existing
  alerting lane (same one the Vercel crons' failures surface in — audience
  parity, per the alert-lane pattern).

## Auth change (surface: `lib/cron-auth.ts` + its tests, inside the APEX claim)

Vercel's trust model = `CRON_SECRET` bearer (operator secret) AND
`x-vercel-cron: 1` (platform-injected, unforgeable from outside). Cloudflare
has no injected header, so the second leg becomes a **second operator secret**:

```
accept if: bearer CRON_SECRET  AND  (x-vercel-cron: 1  OR  x-oasis-cron-attest === CRON_ATTEST_SECRET)
```

Two independent secrets ≈ the old secret+platform pair; both legs stay
required; `CRON_ALLOW_LOCAL` escape unchanged. The `x-vercel-cron` branch is
kept until Vercel retirement, then deleted. `CRON_ATTEST_SECRET` is minted at
Phase A (`set-random` style), lives only in the two workers' secrets.

## Tick-continuity choreography (the no-drop core)

**Phase A — build + dry-run.** Implement worker + matcher + tests. Deploy with
`CRON_FORWARD=off`. **Gate: 24h of dry ticks with the due-list matching the
table 28/28** — every entry observed due at its exact minutes, zero misses
(compare worker logs against Vercel's cron log for the same day).

**Phase B — double-fire audit.** The two heaviest senders are already
double-fire-safe by design (verified in code 2026-08-29: dispatch-drips CAS
row-claim; dispatch-scheduled-sends conditional-UPDATE claim + stale reclaim).
Audit the remaining SEND/write rows (#1, 5, 11, 14, 22, 28) for the same
claim shape. Any route without one gets the **tick-lease helper**
(`lib/cron-tick-lease.ts`: `INSERT OR IGNORE (job, scheduled_minute)` into a
Turso table; second firer sees the row and no-ops — ~20 lines, also protects
against Vercel's own duplicate invocations). Gate: all 28 rows classified
overlap-safe.

**Phase C — overlap cutover (zero gap, ≤1 duplicated tick, duplicates
harmless by Phase B).**
1. Flip `CRON_FORWARD=on` (instant). Both platforms now fire every job.
2. Watch one full cycle of the densest schedule (5 min) — claims arbitrate,
   telemetry shows both firers, sends stay single (drip/send counts flat).
3. Merge the PR that removes the `schedule:` triggers from
   `.github/workflows/cron-driver.yml` (prepared in advance, inside the claim;
   keep `workflow_dispatch` + the file itself as the rollback path). **This —
   not the vercel.json edit — is what stops the current firer**; see the
   2026-08-30 correction above. vercel.json's inert `crons` were already removed by PR #347. Unset `CRON_ALLOW_LOCAL` once the Worker's attest
   header is confirmed accepted.
4. Overlap window = minutes; gap = **zero** by construction.

**Phase D — 24h dual verification.** Vercel cron log shows zero fires after
step 3; worker observability shows 28/28 schedules green 2xx over 24h; drip
and SMS send counts match the trailing 7-day baseline (no double, no drop).
Mail-flow test on @oasisai.work unaffected.

**Phase E — retire.** Delete the `x-vercel-cron` auth branch; release the
APEX claim; runbook + register updated.

## Rollback (any phase)
`CRON_FORWARD=off` (seconds) → if the GH driver's triggers were already
removed, either dispatch it manually (`workflow_dispatch`, retained for exactly
this) or `git revert` the trigger PR (schedules resume on the next matching
tick). Both levers are independent; there is no state to unwind because every
route is overlap-safe by Phase B. Note Vercel's scheduler is NOT a rollback
option — it has been dead since 2026-08-06.

## Exit criteria
28/28 firing from the worker over 24h · zero Vercel fires · send counts at
baseline · tunnels + Google-mail records byte-identical to zone baseline ·
claim released · Codex adversarial review of the cron worker + cron-auth diff.
