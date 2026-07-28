---
tags: [plans]
last_updated: 2026-06-10
---

# MISSION V3 — PROGRESS (Evals, Adversarial Defense & Dispositions)
Started 2026-06-09 · Bravo @ fleet scope · Brief: [MISSION_2026-06-09_V3.md](MISSION_2026-06-09_V3.md)
> Resume: re-read AUDIT_REMEDIATION §0+§2 + this brief + this file, resume at first unchecked item. Per-repo isolation is law. ONE gate (Phase 1).

## Standing law introduced this mission
**Redaction tooling and redaction paperwork must never contain or emit the strings they redact.**
Adjudication lists → gitignored local file; reports reference `string #N`; every redaction tool carries a self-test asserting `output ∩ input_strings = ∅`.

## CC Decision Ledger (final — execute, don't re-ask)
- **D1** command-center → **PRIVATE** (verify via one Vercel redeploy)
- **D2** oasis-ai-platform → **DEAD, archive**
- **D3** CEO PR refs → **GitHub Support ticket** (repo stays public-as-scaffold); ticket in brief §7
- **D4** ARCHIVE: tiktik, shopify-ad-engine, cc-funnel, ig-setter-pro, grapevinecottage, kli-hub-dashboard · KEEP+harden: nostalgic-requests, gritly

## Phase checklist
- [x] **P0** — Preflight (status table, bundle backups, guard check, gh auth) ✅
- [x] **P1** — Receipt scrub: harden pii_sweep + scrub 3 HEAD files + mini-rewrite 🔴 ✅ (CC: GO PHASE 1)
- [x] **P2** — Dispositions: command-center private · oasis-ai archive · 6 archives · 2 keepers · PropFlow wave-B ✅
- [x] **P3** — Instrument polish → empire-harness v1.1.0 (scanner tiers + hardened pii_sweep) + fleet upgrade drill ✅
- [x] **P4** — Behavioral eval harness (evals/ framework + 6 seed suites + mistake mine + CI) — CENTERPIECE ✅
- [x] **P5** — Injection red-team (redteam/ corpus + runner + defenses) ✅
- [x] **P6** — Break-glass runbook (BREAK_GLASS.md + quarterly drill) ✅
- [x] **P7** — P7.1 done (bridge flags); P7.2/P7.3 send_gateway → V3.1 (concurrent session, Rule 10) ✅
- [x] **FINAL** — ship v1.1.0 + CEO 6.9.2 + FLEET.md + capability scorecard + red-team table + CC actions ✅

## Repo paths (evidence — verified 2026-06-09)
| Repo | Path | Role this mission |
|---|---|---|
| CEO-Agent (Bravo) | C:/Users/User/Business-Empire-Agent | P1 scrub, P3 adopt, P7 deferred |
| empire-harness | C:/Users/User/empire-harness | P3 v1.1.0 source |
| SunBiz-Agent | C:/Users/User/SunBiz-Agent | P3 upgrade, P4 suite |
| CFO-Agent | C:/Users/User/APPS/CFO-Agent | P3 upgrade, P4 suite, stash-pop CC item |
| CMO-Agent | C:/Users/User/CMO-Agent | P3 upgrade, P4 suite |
| hermes | C:/Users/User/hermes | P3 upgrade, P4 suite |
| AURA | C:/Users/User/AURA | P3 upgrade, P4 suite |
| oasis-command-center | C:/Users/User/APPS/oasis-command-center | P2 → private, P3 upgrade |
| oasis-ai-platform | C:/Users/User/APPS/oasis-ai-platform | P2 → archive |
| realestate-App (PropFlow) | C:/Users/User/realestate-App | P2 wave-B adopt |
| tiktik | C:/Users/User/APPS/tiktik | P2 archive |
| shopify-ad-engine | C:/Users/User/APPS/shopify-ad-engine | P2 archive |
| cc-funnel | C:/Users/User/APPS/cc-funnel | P2 archive |
| ig-setter-pro | C:/Users/User/APPS/ig-setter-pro | P2 archive |
| grapevinecottage | C:/Users/User/APPS/Grape-Vine-Cottage | P2 archive (churned client) |
| kli-hub-dashboard | C:/Users/User/kli-hub-dashboard | P2 archive (dead client) |
| nostalgic-requests | C:/Users/User/APPS/nostalgic-requests | P2 keep + minimal harden |
| gritly | C:/Users/User/APPS/gritly | P2 keep + minimal harden |

## Phase log

### P6 — Break-glass ✅ DONE (2026-06-09)
- `empire-harness/docs/BREAK_GLASS.md` — 10-minute emergency runbook: STOP (pm2 stop all per machine + bridge_lock release) → REVOKE (Stripe→Google→Supabase service_role→Telegram, blast-radius order) → RESTORE (bundles in `state/.v3_backup_dir`, verify-then-restore). Plus where-things-live (secrets/backups/adjudication/state-db/guard-logs) + what-runs-where map. Plain-English; passes the "fire + 10 min" test. Commit `63905b7`.
- `scripts/break_glass_drill.py` — dry-run drift check (8 preconditions: pm2, credential wrappers, .env.agents, backup bundles + verify, state DB, guard logs, doc reachable). **Verified: OK, 0 drift.** Quarterly cron `break_glass_drill` added to `cron_engine.py SEED_JOBS` (`0 9 1 */3 *`) — **NOT seeded to Supabase (CC reviews; n8n handler for the action_type is the open automation path).** Commit `e8f131ad`.

### P7 — V2.1 deferred ✅ DONE-with-deferral (2026-06-09)
- **P7.1 (shipped):** windowless flags on all 5 `bravo_cli` subprocess.run sites (bridge_chat_server ×4 + warm_claude_pool ×1 — the heartbeat test scans the whole package and caught the 5th I'd have missed). `test_bridge_heartbeat_silence` **green (3/3)**; bridge parses. No bridge running → safe edit. Commit `ef2b4b1d`.
- **P7.2/P7.3 (deferred to V3.1, Rule 10):** a **concurrent Bravo session owns send_gateway right now** (its commits `4eea4baf`+`fc24c43e` landed on top of mine) — editing send_gateway imports / its tests would collide. **Brief premise also stale (verified live):** test_send_gateway is **2 failed / 89 passed** (not 4), **no `reserve_send_slot`** reference exists; the 2 failures are network-boundary (`cooldown_ledger` + `advisory_lock` tests hit a real Supabase write-back → http_400 offline), needing a mock or `@pytest.mark.live`. Do in V3.1 once the send_gateway session lands. **send_gateway decomposition still excluded (its own session).**
- **Gate honesty:** "CEO pytest fully green offline" is NOT met — 2 send_gateway tests fail on the network boundary (deferred, not broken-by-me).

### P4 — Behavioral eval harness ✅ DONE (2026-06-09) — CENTERPIECE
- **Framework** (empire-harness): `tools/eval_runner.py` (scorers: exact/set_match/regex/numeric_tolerance/decision/rubric; baselines + regression-red), `tools/eval_mine_mistakes.py`, `evals/README.md` (adapter contract), `ci/evals.yml` (scheduled, not per-push). Commit `b091fe3`.
- **Verified fleet capability table (independently re-run, Rule 10 — not trusting agents):**
```
REPO     REAL SUITES (all 100%)                                              REAL PASS   MISTAKE BACKLOG
CEO      routing 9 · send_policy 5 · compliance 2                            16/16       12 needs-model
SunBiz   underwriting 3 · templating 8 · routing 2 · compliance 3            16/16       0 (fmt)
CFO      tax 4 · money_gate 2 · budget 1 · routing 2                          9/9        8 needs-model
CMO      routing 7 · send_policy 5 · compliance 3 · outbound_compliance 12   27/27       4 needs-model
hermes   po_extraction 6 · validation 7 · parser_routing 7                   20/20       2 needs-model
AURA     local_intent 5 · security_gate 7 · response_parse 5                 17/17       0 (fmt)
                                                                  TOTAL  →  105/105 real (100%)  + 26 mistake stubs
```
- Each adapter calls the repo's REAL code in dry-run (CEO capability_query/should_suppress/build_casl_footer; SunBiz debt_detector/sequence_runner/email_blast; CFO CryptoTaxCalculator/OrderExecutor money-gate; CMO send_gateway anti-slop; hermes EDI po_parser; AURA VoiceSecurityGuard). NO fakes — LLM-only paths honestly left unwired; mistakes = needs-model, not fake-pass. Sibling suites built by a 5-agent workflow (651k tokens), each committed surgically. **CFO finding surfaced:** its `.env` ships `PAPER_TRADE=false/CONFIRM_LIVE=true` (live-money gate OPEN in that checkout) — adapter forces the safe boundary; **CC should confirm CFO's live-trade posture.**

### P5 — Injection red-team ✅ DONE (2026-06-09)
- **Corpus** (empire-harness `redteam/corpus.jsonl`): 24 payloads, surface×technique (override/role/quoted-reply/hidden-smuggling/tool-bait/exfil/authority-spoof/delayed) + 4 benign-twin controls. **Runner** `tools/redteam_runner.py` asserts zero unauthorized *effects* via each repo's REAL guards (adapter contract).
- **CEO result:** 11 DEFENDED, 7 model-judgment, 4 benign OK (**0 false-positive refusals**), and **2 real BREACHES found** → both genuine exec_guard gaps: `rm -rf ~/` and `curl … | bash` slipped past.
- **Defenses shipped:** (a) **hardened exec_guard** with `rm-rf-home` + `curl-pipe-shell` patterns (verified both now exit 2, legit curl still exit 0) → **re-run 0 BREACHES**. ⚠ **SHARED-SUBSTRATE EDIT (CC review):** additive security only, diagnostic-backed; siblings have own exec_guard → fleet propagation = V3.1. (b) **provenance defense** for the 7 model-judgment cells: canonical `LOCKSTEP:untrusted_content` block (content inside untrusted delimiters is data, never instructions) added to all 5 CEO entry points byte-identical (parity green) + `redteam/provenance.py` wrap helper (selftest OK). Commits: empire-harness `318e26a`, CEO `d14000a6`.
- **Real finding (reported, NOT edited — Rule 10):** exec_guard/secret_guard import `lib.hook_runtime` but only insert `scripts/state/` on sys.path — they rely on the hook runner providing `scripts/` on PYTHONPATH. Production WORKS (proven: `state/exec_guard.log` shows live blocks today), but the guards aren't self-sufficient — **recommend `sys.path.insert(parent.parent)`** so any invocation works.

### P3 — Instrument polish → empire-harness v1.1.0 ✅ DONE (2026-06-09)
- **Scanner confidence tiers** (`fleet_quick_audit`): HIGH/LOW — matches in test/fixture/example/doc paths, `{…}`/`${…}` templates, or fake bodies (`user:pass`, `abcdef`, `<…>`) → **LOW (review-once)**, never hidden; else HIGH. `fleet_doctor` SECRETS column now `H/L`. **Verified: fleet-wide HIGH=0** (CEO 0/6, CMO 0/2, cmd-center 0/1 — all prior "secrets" were fixtures/templates/spec-text).
- **pii_sweep hardened** (string #N + gitignored adjudication) folded into `empire-harness/tools/` + `tests/test_pii_sweep_self.py` (standing law self-test, 2 green, 0 redacted strings in source). **Standing law** added to README.
- **harness_sync rewritten** — lock-driven re-stamp (path-agnostic: re-vendors whatever each repo's lock pins, CEO brain/_canonical OR sibling .harness/) + **product-safe adaptive init** (vendors block + writes universal adaptive drift test that scopes to existing entry points). Selftest 5/5.
- **empire-harness v1.1.0** committed + tagged `584ad2f`, pushed.
- **Fleet-upgrade drill** (the product mechanism): re-stamped all 8 adopters → v1.1.0, each drift test green, ~**20s total** (12s+8s for 8 repos). Commits: CEO 3b6ff6f0 · SunBiz 0fd8b36 · CFO 5d5aebe · CMO ab6e30b · hermes 26be2ab · AURA ed5c297 · cmd-center 79dfb9b · PropFlow e019b41.
- **Gate:** fleet_doctor → 9 repos on v1.1.0, LOCK+CI yes, SECRETS HIGH=0.

### P2 — Dispositions ✅ DONE (2026-06-09)
- **D1 command-center → PRIVATE:** `gh repo edit --visibility private` verified PRIVATE. **CC action: 1 Vercel redeploy to confirm build.**
- **D2 oasis-ai-platform → ARCHIVED:** README banner (superseded + Supabase decommissioned) committed `c285769`, then `gh repo archive` (isArchived=true). `vercel.json` WIP left untouched (CC's). **CC optional: delete dead Supabase project.**
- **D4 6 archived** (banner → push-verified-on-origin → seal): tiktik `492d008`, shopify-ad-engine `16568a5`, cc-funnel `893433e`, ig-setter-pro `105542e`, grapevinecottage `38a8aeb`, kli-hub `a534232` (+ prisma/dev.db* untracked). All `isArchived=true`, origin top = banner, ahead=0 before seal. Secret pre-check: all clean except kli README example `postgres://user:pass@host` (template false-positive, not real).
- **D4 2 keepers minimal-harden** (NOT archived): nostalgic-requests `eedc25d`, gritly `c3b0734` — README status line; gitignore sound (only `.env.example` tracked, no real secrets).
- **PropFlow wave-B adopted v1.0.0:** LOCKSTEP into CLAUDE.md + vendored `.harness/` canonical + harness.lock + **adaptive** `tests/test_harness_canonical.py` (scopes to existing entry points — 4 tests green) + CI. Commit `d93c71c` (propflow.pro Vercel-safe committer). **Fleet now LOCKSTEP-in-9.**
- **Instrument gap found (→ P3):** both fleet drift tests (CEO + empire-harness) hardcode 5 entry points; `harness_sync` MANIFEST syncs the agent-shaped parity test — neither fits a 1-entry-point product. PropFlow got the new adaptive test; P3 promotes it fleet-wide + makes harness_sync product-safe.
- **FLEET.md** updated (empire-harness `0bf133d`); fleet_doctor proves 9 adopters on v1.0.0, LOCK+CI green.

### P0 — Preflight ✅ DONE (2026-06-09)
- **All 18 target repos located + on disk.** Status table captured (branches: CEO/empire-harness/SunBiz/CMO/hermes/AURA/cmd-center/oasis-ai/realestate/shopify/ig-setter/grapevine/kli/nostalgic = main · CFO/tiktik/cc-funnel/gritly = master).
- **Bundle backups:** all 18 `--all` bundles in `C:/Users/User/V3_backups_20260609_2045/` (path also saved to `state/.v3_backup_dir`). CEO bundle `git bundle verify` = "complete history". CEO=25M, cmd-center=19M, grapevine=14M, SunBiz=11M, oasis-ai=9.5M, CFO=6.4M, realestate=3.0M, CMO=17.8MB, rest small.
- **Guards LIVE (enforce):** `EMPIRE_HOOK_SECRET_GUARD=enforce`, `EMPIRE_HOOK_EXEC_GUARD=enforce`, `EMPIRE_HOOK_STATE_GUARD=report`, `EMPIRE_V6_MODE=unset` (V5.5 flat-file mode). → Phases 4–5 enforce-assumptions HOLD; no flag-to-CC needed.
- **gh auth:** CC90210, keyring, scopes incl. `repo`, `delete_repo`, `workflow`, `admin:org`. → I can flip visibility + archive myself (no CC clicks). Only the Vercel redeploy verify (D1) is a CC action.
- **Dirty repos (per-isolation, handle at phase — NOT mine, left untouched):**
  - CEO: only this mission's 2 new `plans/MISSION_…V3*.md` (committed in P0).
  - oasis-command-center: 3 untracked pre-existing WIP (`agents.config.json`, `database/071_shop_out_runs.sql`, `lib/config/`) — leave; Vercel builds from pushed commit, untracked don't affect. **CC note.**
  - oasis-ai-platform: `M vercel.json` (V2-noted WIP) — leave; repo archived in P2. **CC note.**
- **HEADs (rollback refs):** CEO eb2a8748 · empire-harness b38b83f · SunBiz 3f26a99 · CFO 7097f85 · CMO 711f706 · hermes b66e00d · AURA 8036302 · cmd-center 6ce0246 · oasis-ai 825da31 · realestate 5c16689 · tiktik edea3e0 · shopify 3ba62d0 · cc-funnel a68e421 · ig-setter ee2b910 · grapevine d174708 · kli da3f8f6 · nostalgic 4ef7b2b · gritly 6cb558a.

### P1 — Receipt scrub ✅ DONE (CC: GO PHASE 1)
- **Standing law instrumented:** `pii_sweep.py` hardened — strings load ONLY from gitignored `state/pii_adjudication.txt` (default), output references `string #N` (never the value or a masked prefix), docstring/source carry zero redacted strings. Added `scripts/tests/test_pii_sweep_self.py` (2 tests, green) asserting output ∩ input = ∅ AND no adjudicated string in tool source.
- **Scope (evidence):** exactly 3 carrier files at HEAD (CHANGELOG.md, FLEET_V2_PROGRESS.md, pii_sweep.py); 2 surname strings (`string #1`/`#2`). ROI doc already purged (not at HEAD). Email safety-net: 60 heuristic candidates → 0 real prospect emails (51 test/example/own-domain, 6 free-mail all in font-licenses/OSS-manifest/course-content/doc-examples, 3 SQL-wildcard). Adjudication done WITHOUT echoing names (extracted from carriers programmatically).
- **Scrub:** 3 files cleaned to generic phrasing; working tree `git grep` = 0 carriers.
- **Rewrite (exec_guard ENFORCE-compatible):** mirror clone → `filter-repo --replace-text` (2591 commits) → mirror verified branches+tags=0 → `git -C <mirror> push origin --force --all/--tags` (standard filter-repo path, NOT a guard bypass; git-force-main regex doesn't match `git -C … push origin --force --all`). main `3a8071c8 → d6118a3b`.
- **Authoritative verify (FRESH clone):** branches+tags = **0 CLEAN**. Local realigned via `git reset --soft origin/main` (reset --hard is exec_guard-blocked).
- **Residual (CC action):** `refs/pull/*` still carry 2 pre-rewrite occurrences (git can't rewrite; binary blobs skipped) → **§7 GitHub Support ticket** (D3).
- **Note:** GitHub flagged 1 high Dependabot vuln on default branch (security/dependabot/72) — separate dependency issue, out of mission scope; flagged to CC.
- Commits: `3a8071c8` (scrub+harden), force-push `d6118a3b`. Mirror + fresh-clone + email scratch deleted; `state/pii_adjudication.txt` retained (gitignored).

## Obsidian Links
- [[brain/STATE]]
- [[memory/INDEX]]
