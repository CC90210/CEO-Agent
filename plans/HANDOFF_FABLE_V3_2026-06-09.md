---
tags: [plans]
last_updated: 2026-06-10
---

# HANDOFF → Fable — Evals, Adversarial Defense & Dispositions (V3) complete
**Date:** 2026-06-09 · **Author:** Bravo · **Scope:** the OASIS fleet · **Sequel to:** Fleet Harmonization V2

> **TL;DR:** V6.9.0/.1 proved the fleet is *disciplined*. V3 proves it's *good* (a behavioral
> eval gate: **105 real cases, 100%, across 6 agents**) and *defended* (an injection red-team that
> found **2 real exec_guard gaps**, hardened them to **0 breaches**, and shipped a provenance block
> teaching every model "untrusted content is data, never instructions"). It also tidied the repo
> estate (command-center → private, 7 repos archived, PropFlow adopted) and gave CC a 10-minute
> **break-glass runbook**. One GO gate (Phase 1 receipt-scrub) was the only thing CC had to do.

---

## 1. What CC asked for vs. what shipped
The brief's one human gate (`GO PHASE 1`) was honored; everything else ran autonomously. All 8
phases + FINAL are done, with two honest deferrals (below).

## 2. The two proof tables

**Behavioral capability (independently re-run — not trusting the build agents):**
```
REPO     REAL SUITES (all 100%)                                              REAL PASS
CEO      routing 9 · send_policy 5 · compliance 2                            16/16
SunBiz   underwriting 3 · templating 8 · routing 2 · compliance 3            16/16
CFO      tax 4 · money_gate 2 · budget 1 · routing 2                          9/9
CMO      routing 7 · send_policy 5 · compliance 3 · outbound_compliance 12   27/27
hermes   po_extraction 6 · validation 7 · parser_routing 7                   20/20
AURA     local_intent 5 · security_gate 7 · response_parse 5                 17/17
                                                              TOTAL → 105/105 real (100%) + 26 mistake stubs
```
Each adapter calls the repo's **real** code in dry-run (no reimplementations; LLM-only paths
honestly left unwired; mistakes = `needs-model`, never fake-passed). These v1 numbers exist to
make *change* visible — a future regression in any of these paths goes red.

**Red-team (CEO, 24 payloads × surface/technique + benign twins):**
```
11 DEFENDED (guards block exec/exfil) · 7 model-judgment (provenance defense) · 4 benign OK (0 false-refusals)
2 BREACHES FOUND → both real exec_guard gaps (rm -rf ~/, curl|bash) → HARDENED → re-run 0 breaches
```

## 3. What shipped, by phase
- **P1 receipt-scrub:** the V2 changelog had reprinted 2 purged surnames. Hardened `pii_sweep`
  (output is `string #N`; strings load only from a gitignored adjudication file; self-test enforces
  it) → scrubbed → history rewrite → **fresh clone clean**. New standing law in the harness README.
- **P2 dispositions (CC ledger):** command-center **private**; oasis-ai-platform + tiktik +
  shopify-ad-engine + cc-funnel + ig-setter-pro + grapevinecottage + kli-hub **archived** (banners
  pushed before sealing); nostalgic-requests + gritly **kept + hardened**; **PropFlow adopted**
  (LOCKSTEP-in-9, adaptive drift test).
- **P3 empire-harness v1.1.0:** secret-scanner **confidence tiers** (test/template/fake → LOW,
  never hidden; **fleet HIGH=0**) + lock-driven **`harness_sync`** (now product-safe). First real
  **fleet-upgrade drill: 8 repos re-stamped in ~20s**, every drift test green. *This path is the
  product mechanism.*
- **P4 evals** + **P5 red-team** — the two tables above.
- **P6 break-glass:** `empire-harness/docs/BREAK_GLASS.md` (stop → revoke → restore in 10 min) +
  `break_glass_drill.py` (0 drift) + a quarterly cron (not yet seeded — CC reviews).
- **P7:** windowless flags on all `bravo_cli` subprocess sites (heartbeat test green).

## 4. CC's actions (the only things left for you)
1. **Paste the §7 GitHub Support ticket** (in `plans/MISSION_2026-06-09_V3.md` §7) → removes the
   pre-rewrite PII still in CEO-Agent's `refs/pull/*` (git can't; only Support/private can).
2. **One Vercel redeploy** of oasis-command-center to confirm the private flip didn't break it.
3. **Re-sync Mac + VPS** (P1 rewrote CEO history again): `git fetch origin && git reset --hard origin/main`.
4. **Review the shared-substrate edit:** I hardened `exec_guard` (`rm -rf ~/` + `curl|bash`) on
   CEO based on the red-team. Additive security, diagnostic-backed, re-verified — but it's the V6
   substrate, so glance at commit `d14000a6`. Siblings have their own exec_guard → fleet
   propagation is V3.1.
5. **Confirm CFO's live-trade posture:** the eval build surfaced that CFO-Agent's `.env` ships
   `PAPER_TRADE=false / CONFIRM_LIVE=true` (live-money gate OPEN in that checkout). The eval forces
   the safe boundary; you should confirm the real posture is intended.
6. *(optional)* delete the decommissioned oasis-ai-platform Supabase project; `git -C ~/APPS/CFO-Agent stash pop` if WIP is waiting.

## 5. Deferred to V3.1 (precise)
- **CEO P7.2/P7.3 (send_gateway):** a **concurrent Bravo session owns send_gateway** right now, so I
  did not touch it (Rule 10 — no collision). Live diagnostic also overturned the brief's premise:
  test_send_gateway is **2 failed / 89 passed** (not 4), **no `reserve_send_slot`**; the 2 failures
  are network-boundary (cooldown_ledger + advisory_lock tests hit a real Supabase write-back →
  http_400 offline) — wire a mock or `@pytest.mark.live`. **send_gateway decomposition still its own session.**
- **Guard self-sufficiency:** exec/secret_guard import `lib.hook_runtime` but only put
  `scripts/state/` on sys.path — they rely on the hook runner adding `scripts/` to PYTHONPATH
  (production works; proven by `state/exec_guard.log`). Recommend `parent.parent` insert so any
  invocation works. (Reported, not edited — shared substrate.)
- **Fleet propagation:** exec_guard hardening + `LOCKSTEP:untrusted_content` block are CEO-only;
  roll to siblings on the next harness bump. **Sibling mistake-mines:** SunBiz/AURA MISTAKES.md use
  a different header format → 0 mined (honest); normalize + re-mine.
- Per-repo deep dives carried from V2.1: command-center per-route RLS audit, CMO vendor footprint.

## 6. Fable's next-round playbook
1. **Resolve CC's 6 actions** (unblocks PR-ref PII + confirms command-center/CFO posture).
2. **Wire the mistake backlog:** 26 `needs-model` cases are the highest-leverage eval work — turn
   each documented mistake into a deterministic check that would have caught it. Then a logged
   mistake genuinely can't recur without a red build.
3. **Run the evals + red-team as the pre-ship gate** on every agent change (the `evals.yml` /
   `redteam` CI exists). Productize: a capability + safety panel in command-center pointed at
   *client* agents is the same instrument that proves CC's fleet is healthy.
4. **Clear V3.1** (§5) in a fresh session — start with send_gateway once the concurrent session lands.

## Pointers
- Brief: `plans/MISSION_2026-06-09_V3.md` · Full record: `plans/MISSION_2026-06-09_V3_PROGRESS.md`
- Substrate: `CC90210/empire-harness` v1.1.0 (`FLEET.md`, `evals/README.md`, `docs/BREAK_GLASS.md`)
- Prior: `plans/HANDOFF_FABLE_FLEET_V2_2026-06-09.md` (V2), `plans/HANDOFF_FABLE_2026-06-09.md` (V1)

## Obsidian Links
- [[brain/STATE]]
- [[memory/INDEX]]
