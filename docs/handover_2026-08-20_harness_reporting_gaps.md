# Handover — Harness Reporting Gaps & Remediation Backlog (2026-08-20)

**Author:** Bravo (OpenCode diagnosing session), for operator CC
**Status:** DIAGNOSIS COMPLETE — remediation pending. The diagnosing session modified **no repo files**; its only writes were the eval tool's own untracked history log (`state/harness_eval_history.jsonl`, gitignored) and `.pytest_cache`.
**Review contract for the next AI:** verify every claim in this document against live state before acting (AGENTS.md RULE 9.5 — inherited claims are archived context, not verified state). Each task lists its verification command and expected outcome. If a live check contradicts a claim here, surface it before acting.

---

## 0. Evidence baseline (verified 2026-08-20 ~16:00 UTC by the diagnosing session)

| Eval | Score | Note |
|---|---|---|
| `python scripts/harness_eval.py` | 11/11 (12/12 with `--with-model`) | ALL GREEN banner |
| `python scripts/agent_genome.py` | 10/10 | fully expressed |
| `python scripts/core/self_audit.py` | **84/100 — WARNING** | mandatory gates FAILED (below) |
| `python -m pytest scripts -q` | **1633 passed / 8 failed** | 6 deterministic + 2 order-dependent flakes |
| `python scripts/fleet_health.py` | bravo pulse **STALE 211.9h**; **6 urgent + 1 normal** unread inbox | 4/5 repos present |
| `python scripts/core/memory_aging.py stale --json` | 0 stale | clean |
| `python scripts/check_brain_freshness.py` | 58 fresh, 2 missing-date (`INVENTORY.md`, `VERCEL_TO_CLOUDFLARE_MIGRATION.md`) | minor |
| `python scripts/capability_probe.py list` | 11/15 authorized | cloudflare, lendsaas, openai, openrouter unconfigured |
| `python scripts/codex_health.py` | **Grade B (11/13)** | global + local hooks MISSING |

**Self-audit mandatory-gate failures (the real red):**
- `SCRIPTS MISSING GRAPH NODES (1)`: `scripts/run_seed_oasis_forms.py` (added by tip commit `2ec358b4`, 2026-08-20, never graph-registered)
- `GRAPH DRIFT (2)`: 1 node added, totals differ
- `GENERATED DOCS DRIFT (1)`: `brain/INDEX.md`

**Why the flagship banner lies:** the nightly cron runs `harness_eval` WITHOUT `--with-model` (11 checks, live Claude-CLI probe skipped), and `self_audit`, `fleet_health`, and the test suite are **not cron-wired at all**. `harness_eval`'s "capability graph fresh" check only compares *skill* count vs disk (162==162) — a different, weaker definition than self_audit's script-node coverage, so they disagree. The banner you trust is the narrowest of the five evals.

**Reporting gap in the brief itself:** the 2026-08-20 06:00 daily brief rendered "ceo_dashboard.py briefing timed out after 45s — dashboard tooling is broken, needs a fix" and `harness_eval` still passed its brief check (only asserts "Pipeline" present and `": —"` absent). A live re-run at 16:22 rendered the dashboard fine ($6,263 MRR / 62.6%, 11 leads, 39/22 posts) — so it was a transient timeout mislabeled as a broken tool.

---

## 1. Mission

Restore a single source of truth for CC's health view so a green banner means healthy. Two halves:
- **A. Fix the concrete defects** (Tier 1, autonomous — no approval needed).
- **B. Close the reporting blind spots** (Tier 2 — each needs a CC decision, flagged).

Work Tier 1 first, then bring Tier 2 decisions to CC.

---

## 2. Tier 1 — autonomous fixes (no approval needed)

### T1. Register `scripts/run_seed_oasis_forms.py` in the capability graph (+ regenerate generated docs → also fixes T4)

- **Why:** fixes self_audit's two mandatory-gate failures (missing node + graph drift) and the `brain/INDEX.md` doc drift in one command.
- **Do:**
  ```
  python scripts/build_capability_graph.py --emit-docs
  ```
  (`--emit-docs` regenerates `brain/INDEX.md`, `brain/WHEN_TO_USE_SKILLS.md`, `memory/INDEX.md`, `memory/MEMORY_INDEX.md` from the rebuilt graph. Read `scripts/build_capability_graph.py` first if anything surprises you — do not hand-edit the generated files.)
- **Verify:**
  - `python scripts/core/self_audit.py` → no "SCRIPTS MISSING GRAPH NODES", no "GRAPH DRIFT", no "GENERATED DOCS DRIFT".
  - `python -m pytest scripts/tests/test_generated_docs_fresh.py -q` → passes.
  - `python scripts/harness_eval.py` → still 11/11.

### T2. Fix the 6 failing tests in `scripts/tests/test_db_resilience.py`

- **Root cause (verified, not assumed):** the tests build a **retired** Supabase client via `create_client("https://x.supabase.co")` / `"https://xxxxxxxxxxxx.supabase.co"`. `scripts/lib/turso_supabase_compat.py:1191` (`_project_for_url`) now raises `ValueError` for unresolvable URLs, so the fixture throws before the test body runs. One test (`test_install_patches_the_class_exactly_once`) imports `supabase._sync.client.Client`, which the installed supabase package no longer exports (now `AClient`).
- **Approach:** read `scripts/lib/db_resilience.py` and `scripts/lib/turso_supabase_compat.py` first. Update the tests to a resolvable project fixture or a mock matching the Turso path. **Surgical — touch only these tests** (RULE 7). This is Turso-migration test debt that has been silently red for ~a month.
- **Verify:**
  - `python -m pytest scripts/tests/test_db_resilience.py -q` → all pass.
  - `python -m pytest scripts -q` → 8 failures gone (modulo T3 flakes).

### T3. Root-cause and fix the test order-dependence (flaky failures)

- **Evidence:** in the full-suite run, `scripts/tests/test_security_invariants.py::test_point_1_scanner_detects_a_planted_remote_credential` and the `brain/INDEX.md` subtest of `test_generated_docs_fresh.py` FAILED; both **pass in isolation and on `--lf` re-run**. That is test pollution, not a real regression.
- **Approach:** reproduce with `python -m pytest scripts -q --tb=long` and capture the real traceback, then bisect ordering (binary-search with `--deselect`) to find which earlier test mutates shared state (env vars set without restore, cwd, or `GIT_CONFIG_*`) that the scanner/`scan_secrets.py` or the doc-freshness check depends on. Fix with `monkeypatch` isolation.
- **Verify:** `python -m pytest scripts -q` green **twice consecutively**.

### T4. Regenerate generated docs (folded into T1 — `--emit-docs`)

### T5. Tighten `check_brief_renders` so a degraded brief FAILS the eval — **needs CC's yes first (shared substrate, RULE 9.5)**

- **Why:** the 2026-08-20 morning brief told CC "dashboard tooling is broken, needs a fix" (transient timeout) while the eval still passed. The check is too weak to catch the very failure it exists for.
- **Proposed change (present to CC verbatim, get yes, then edit):**
  - In `scripts/harness_eval.py::check_brief_renders`, fail on degraded markers in the dry-run output: `"timed out"`, `"broken"`, `"needs a fix"`, `"unavailable"`.
  - In `scripts/daily_brief.py` (around line 130–160), raise the `ceo_dashboard` sub-call timeout so a slow morning doesn't mislabel (currently the dashboard brief times out at 45s; the wrapper budget is 85s).
- **Verify:** `python scripts/harness_eval.py` still 11/11; stub the dashboard subprocess to time out and confirm the check now goes red.

### T6. Codex hooks MISSING (global + local) — `scripts/codex_health.py` Grade B

- **Investigate:** read `scripts/codex_health.py` to see exactly what hooks it expects, then check `~/.codex/config.toml` (global) and `.claude/plugins/codex/` (local). Add the missing hooks so the Codex delegation lane gets guard parity. Read-only investigation first; only edit with CC's OK if it touches `~/.codex` (machine-level config).
- **Verify:** `python scripts/codex_health.py` → 13/13.

---

## 3. Tier 2 — needs a CC decision (bring these back, do not self-authorize)

### R1. Wire a weekly "full truth" digest cron (self_audit + fleet_health + pytest summary → Telegram)

- **Why:** the only cron-paged eval is `harness_eval`; pulse staleness, inbox backlog, test debt, and the 84/100 self-audit are invisible unless someone runs them manually.
- **Gate:** seeding crons is a production-scheduling mutation (AGENTS.md — `python scripts/core/cron_engine.py seed` only after CC reviews). **Draft the SEED_JOBS entry (Appendix A) and present it to CC. Do NOT seed without his OK.**
- **Proposed shape:** `script_run`, weekly Sunday 07:00, runs `scripts/core/self_audit.py` + `scripts/fleet_health.py` + a pytest summary, posts to Telegram **always** (not just on failure).

### R2. Resume `state_sync` at session end, or retire pulse staleness — CC's call

- **Evidence:** RULE 0 (continuous state sync) has been silently off since **2026-08-11**: `STATE.md` `last_updated: 2026-08-11`, `data/pulse/ceo_pulse.json` `updated_at: 2026-08-11T20:15Z`, last `SESSION_LOG` auto-sync entry 2026-08-11. Sessions since only git-commit "sync — session" (e.g. `33d38015`, 2026-08-20) — they never write the pulse.
- **Design tension:** `scripts/pulse_publish.py autorefresh` (cron `258d3b45`, active, daily 07:45) intentionally "never moves updated_at; judgment stays as stale as it is" — so `fleet_health`'s STALE flag on bravo is a **standing false alarm by design**.
- **Options for CC:** (a) add `python scripts/state/state_sync.py --pulse-note "..."` (or `--heartbeat`) to the session-end protocol — **recommended**; (b) have autorefresh move `updated_at` for machine sections; or (c) retire pulse freshness as a signal. Recommend (a).

### R3. gh auth / push blocked — credentials task, CC must run

- **Evidence:** `gh auth status` reports a stale/expired token since ~Aug 14; `capability_probe` lists github OK only via `git_push_tool.py` (the gh CLI login itself is stale; plain `git push` cannot authenticate). Current branch `feat/v7.6-evidence-gated-refinement` is **ahead 4** unpushed, and **219 ahead / 15 behind `origin/main`** (diverged).
- **Do NOT attempt to fix credentials.** Hand CC: `gh auth login` (or rotate the token). Confirm push works afterward (`git push`).

### R4. 6 unread high-priority Maven messages — business decision, not code

- **Evidence:** `tmp/agent_inbox/inbox/` holds 7 unread for bravo (6 high, 1 normal), all from Maven, 2026-08-14 → 08-17: founders Marketing-tab reorg + library taxonomy handovers, "your 2 asks", and the LinkedIn-gap id-based fix. Unread ~6 days.
- **Action:** surface to CC. Draft replies for review, or CC responds — his call. The Claude Code session-start hook shows urgent mail at boot, but other runtimes (OpenCode, etc.) do not.

---

## 4. Tier 3 — deferred / informational (no action unless triggered)

- **D1. Tenant advisory (13 candidates).** `harness_eval` appends "13 candidate unstamped tenant-table INSERTs (heuristic)". All 13 were traced 2026-08-08: 5 were real gaps (since stamped), the rest stamp upstream of the 16-line regex window or are deliberately tenantless. **Act only if the count GROWS.** Widening to blocking is CC's call (it would page on the current state).
- **D2. Unconfigured capability lanes.** cloudflare (missing `CLOUDFLARE_API_TOKEN`), lendsaas, openai, openrouter. Configure only if CC needs those lanes. `openai` is the Codex-delegation lane (`codex-companion.mjs`) — relevant only if CC wants direct Codex delegation from this chassis.
- **D3. INVENTORY.md vs graph count.** INVENTORY (generated 08-19 23:37) says 163 skills; graph says 162. Re-run `python scripts/core/generate_inventory.py` after T1 if accuracy matters. The `Monthly Inventory Sync` cron (`7ea6b09a`) is active with 0 runs — expected (created 08-01, next run 09-01).
- **D4. Unscoped cron_jobs read.** `cron_engine.py list` runs a deliberate unscoped `SELECT * FROM cron_jobs` (WARNING logged). The table now carries `tenant_id`. Leave as-is (cross-tenant by design) unless CC wants scoping.

---

## 5. Open questions for CC (decision list — plain English)

1. **Approve tightening `harness_eval`'s brief check** (T5)? — Recommended: yes.
2. **Approve the weekly full-truth digest cron** (R1, draft in Appendix A)? — Recommended: yes.
3. **state_sync: resume session-end pulse writing, or retire pulse staleness** (R2)? — Recommended: resume.
4. **gh auth** is yours to run (R3) — confirm when done.
5. **The 6 Maven messages** (R4) — want me to draft replies for your review, or will you respond?
6. **cloudflare / lendsaas / openai / openrouter lanes** (D2) — needed, or leave unconfigured?

---

## 6. Definition of done (gate)

After Tier 1 (all autonomous): 
- `python -m pytest scripts -q` fully green **twice consecutively**;
- `python scripts/core/self_audit.py` → no mandatory-gate failures (100/100 or PASS);
- `python scripts/harness_eval.py` → 11/11 with the tightened brief check;
- `python scripts/codex_health.py` → 13/13.

After Tier 2 (post-CC approval): weekly digest delivers on schedule; pulse fresh or explicitly retired; pushes unblocked.

## 7. End-of-task reporting

Close with the four-line report (AGENTS.md): **Changed** (paths) / **Why** (one sentence per change) / **Proof** (commands + actual output) / **Needs from CC**. Then update `memory/SESSION_LOG.md` and, if state changed, `python scripts/state/state_sync.py --note "<summary>"`.

---

## Appendix A — Draft SEED_JOBS entry for R1 (for CC review; do NOT seed without approval)

```python
{
    "name": "Weekly Full-Truth Health Digest",
    "schedule": "0 7 * * SUN",
    "job_type": "script_run",
    "active": False,  # flip to True only after CC approval
    "description": "Weekly: run self_audit + fleet_health + pytest summary, post to Telegram always.",
    "action_config": {
        "script": "scripts/weekly_truth_digest.py",  # NEW script to author (see below)
        "notify_channel": "telegram",
        "notify_on": "always",
    },
}
```

The new `scripts/weekly_truth_digest.py` should: (1) run `scripts/core/self_audit.py`; (2) run `scripts/fleet_health.py`; (3) run `python -m pytest scripts -q` with a hard timeout and summarize pass/fail counts; (4) compose a Telegram digest. **Author it in `scripts/` and register it in the capability graph** (or Tier 1's build will flag it next run — feed the gate you built).

## Appendix B — Verification cheat-sheet (re-run all at start of your session)

```bash
python scripts/harness_eval.py --with-model
python scripts/agent_genome.py
python scripts/core/self_audit.py
python scripts/fleet_health.py
python scripts/core/memory_aging.py stale --json
python scripts/check_brain_freshness.py
python scripts/capability_probe.py list
python scripts/codex_health.py
python -m pytest scripts -q
```