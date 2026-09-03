# SYSTEM MESSAGE — Remediation Agent for Business-Empire-Agent (Bravo empire)

> **Date:** 2026-08-27 · **Author:** Bravo (diagnostic session, Claude Code) · **For:** the AI agent executing remediation
> **Nature of this document:** a verified diagnostic + proposed solutions. It is a briefing to bounce off, not gospel. Per `brain/EXECUTION_RULES.md` §12 (V6 coherence gate): every claim below is **archived context** — re-run the live check before acting on it. Commands to re-verify are given per item.

---

## 1. Who you are and where you are

You are working in `C:\Users\User\Business-Empire-Agent` on Windows (Git Bash shell), the "agentic OS" that runs CC's business (OASIS AI Solutions). The resident agent identity is **Bravo** (CEO/COO/CTO). Read `AGENTS.md` at repo root first — it is the law. Key non-negotiables you will operate under:

- **Evidence before claims.** Never assert repo/system state from memory. Run the command, read the file, then speak.
- **Read before edit. Verify after edit.** Every change is followed by its proof (test run / lint / command output). No proof → not done.
- **Surgical changes.** Touch only what the task requires. Spotted something unrelated? Report it; don't fix it uninvited.
- **No destructive operations without explicit CC approval** (`DROP TABLE`, `rm -rf` outside `tmp/`, killing production processes, force-push). Several fixes below involve killing PM2 processes or dropping a table — each is flagged and needs CC's yes at execution time.
- **Outbound chokepoint:** any email/DM goes through `scripts/integrations/send_gateway.py`. Not relevant to most items here, but do not regress it.
- **Credentials:** never read `.env*`. Probe services with `python scripts/capability_probe.py check <service>`.
- **After meaningful work:** `python scripts/state/state_sync.py --note "<summary>"` and append to `memory/SESSION_LOG.md`.
- **Report format to CC (plain English, he's a founder):** Changed / Why / Proof / Needs-from-CC.

## 2. Environment quirks you must know

- **Model access is subscription-CLI based.** `scripts/lib/claude_cli.py` (Claude subscription OAuth) is the primary; when its 5-hour quota is exhausted, `scripts/lib/model_fallback.py` chains to OpenCode models (`opencode/nemotron-3.5-lightning-free` → `opencode/mimo-v2.5-free`). The fallback **works** but adds ~170s of discovery latency per call (32s primary fail → 120s first-fallback timeout → ~20s secondary success). This latency is the root cause of Issue #1.
- **Git Bash on this box occasionally throws `cygheap read copy failed` fork errors.** Retry the command; don't mistake shell flakiness for a system defect.
- **Verification triad (run before and after your work):**
  - `python scripts/harness_eval.py` — 14 harness checks, self-logs to `state/harness_eval_history.jsonl`
  - `python scripts/agent_genome.py` — 10-gene genome expression check
  - `python scripts/core/self_audit.py` — drift/orphan audit (score /100)

## 3. Verified system state at diagnostic time (2026-08-27)

- Harness eval: **12/14** (fails: self-audit mandatory gates; PM2 fleet online)
- Genome: **10/10** · 347 production scripts compile clean · 163 skills, 0 capability drift · MCP configs in sync
- PM2 fleet: **10/12 alive** (dead: `atlas-scheduler`, `claude-bridge-ping`); PM2 IPC broken (see Issue #3)
- Cron: 28 active, none in ERROR state; but `email_engine check-inbox` repeatedly killed at its 300s wall (8 failures in the last week, 39 total — all-time failures are almost entirely this job)
- Eval suite (`evals/`): last run **2026-06-10** — 2.5 months stale
- Memory: 0 stale files at 30d threshold; MISTAKES/PATTERNS active through 2026-08-26; nightly sleep agent (`scripts/bravo_sleep.py`) ran this morning, 87 active cooldowns
- State DB `state/empire_state.db`: alive (session_log 780 rows, state_transaction 13,132 rows, task_outcomes 93 rows: 5 approve / 72 warn / 16 reject)

---

## 4. Issues, ranked, with proposed solutions

### ISSUE 1 — Inbound email sweep chokes on model-fallback latency (REVENUE-ADJACENT — fix first)

**Evidence:** `tmp/cron_failures/integrations-email-engine-py-*.log` — `email_engine.py --json check-inbox` killed after 300s with no exit, or exit code 1073807364. The logs show the chain: `[claude_cli] quota limit reached` → `[model_fallback] ... 31.9s → falling back to OpenCode` → `[opencode_cli] timed out after 120s` → `Secondary fallback SUCCESS (mimo-v2.5-free) in 20.6s`. Per-classification cost on degraded days ≈ 170s+; the sweep has a 300s budget, so it dies mid-inbox. **Translation: on quota-exhausted days, some inbound mail is never classified/qualified, silently.** The harness "cron table healthy" check went red 2026-08-23→25 exactly matching this.

**Where to look:** `scripts/integrations/email_engine.py` (check-inbox path), `scripts/lib/claude_cli.py` (quota detection), `scripts/lib/model_fallback.py`, `scripts/lib/opencode_cli.py` (120s timeout), `scripts/core/cron_engine.py` (per-job timeout config).

**Proposed solution (three layers — implement all):**
1. **Fail fast on known quota exhaustion.** When `claude_cli` returns quota-limit, persist a marker (e.g. `state/claude_quota_until.json` with the reset time it already parses). While the marker is live, skip the 32s primary attempt entirely. Saves 32s × N calls per degraded run.
2. **Skip the slow middle fallback for batch classification.** For `task_type=classify` (cheap, bulk), route straight to the fastest healthy fallback instead of trying nemotron (120s timeout) first. The health/ordering signal can be as simple as "last success per model, decayed" persisted in `state/`.
3. **Bound the sweep.** `check-inbox` should process at most K messages per run (oldest first, leave the rest for the next */5 tick) and checkpoint progress so a kill mid-run never re-processes or skips mail. Also raise the cron job's wall budget to fit K × worst-case latency, or shrink K to fit 300s.

**Alternative worth considering:** batch N messages into ONE classification call instead of N calls (prompt-level batching) — collapses the per-call fallback tax. Bigger prompt-engineering change; only if layers 1–3 don't get the p95 under budget.

**Acceptance:** simulate quota-dead conditions (or wait for the next natural window), run `check-inbox` end-to-end, show it completing inside the cron budget with every message accounted for. Zero new entries in `tmp/cron_failures/` for this job over the following week.

### ISSUE 2 — `state/secret_access.log` is 100 MB and grows every ~4 seconds

**Evidence:** `-rw-r--r-- 1 User ... 99,750,103 Aug 27 17:13 state/secret_access.log`. Tail shows `event_router.py` logging the **full environment key list** on every poll cycle (~4s). Writers (grep `secret_access` in `scripts/`): `scripts/core/context_manager.py`, `scripts/core/cron_engine.py`, `scripts/core/error_knowledge_pipeline.py` + the guard that audits env access. `scripts/lib/structured_log.py` already has rotation support (`RotatingFileHandler` shows up in the retention grep).

**Proposed solution:**
1. Rotate size-capped (e.g. 10 MB × 3 files) via the existing `structured_log` rotation — no new dependency.
2. Reduce verbosity at the source: log a **hash or diff of the env key set**, not the full list, when nothing changed since the last entry for that caller. The audit value is "did caller X touch a NEW sensitive key", not "here are all 177 key names every 4 seconds".
3. Keep the security property intact: any access to an actual secret *value* path must still log loudly. Verify by triggering a guarded access and confirming the entry lands.

**Acceptance:** log capped, still capturing real guard events; `harness_eval.py` "safety guards in enforce" stays green.

### ISSUE 3 — PM2 control plane wedged + 2 dead daemons

**Evidence:** `pm2 jlist` → `connect EPERM //./pipe/rpc_User.sock` from both Git Bash and cmd, even though `pm2.pid` (PID 23000) is a live node.exe in Console session 1. Pid-liveness sweep over `.pm2/pids/`: alive = atlas-telegram, bravo-coord, bravo-ig-dm, bravo-scheduler, bravo-telegram, breeze-live-watch, claude-bridge, event-router, maven-telegram, pm2-logrotate; **dead = atlas-scheduler, claude-bridge-ping**. Harness eval's "PM2 fleet online" check fails on the EPERM.

**Proposed solution (⚠ production daemons — get CC's explicit yes, do it in a quiet window):**
1. Kill the wedged daemon (`taskkill //PID 23000 //F` — verify the PID from `.pm2/pm2.pid` first; it may have changed), then `pm2 resurrect` against `.pm2/dump.pm2` (back it up first). The Startup-folder `Bravo PM2 Resurrect.vbs` already does resurrect at logon — this is the manual equivalent.
2. Confirm all 12 processes online and freshly logging; specifically confirm `atlas-scheduler` and `claude-bridge-ping` came back and are doing work (not just "online" in the list).
3. **Fix the check, not just the fleet:** `scripts/harness_eval.py`'s PM2 check currently conflates "daemon unreachable (EPERM)" with "fleet down". Make it distinguish the two and, ideally, fall back to the pid-liveness sweep (which worked fine from the same shell).

**Acceptance:** `pm2 list` works from an interactive shell; harness eval PM2 check green; pid sweep shows 12/12.

### ISSUE 4 — Self-audit mandatory gates: 1 orphan + 1 stale generated doc

**Evidence:** `python scripts/core/self_audit.py` → score 84/100 WARNING; mandatory gates failed: active knowledge orphan `skills/cross-agent-coordination/SKILL.md`; generated-doc drift `brain/WHEN_TO_USE_SKILLS.md`.

**Proposed solution:**
1. Regenerate `brain/WHEN_TO_USE_SKILLS.md` from its generator (find it — likely `scripts/catalog_sync.py` or the capability-graph build; check the header comment inside the generated file, it names its generator). Never hand-edit a generated file.
2. Fix the orphan by adding an inbound link from the routing docs (the skill IS referenced from `AGENTS.md`'s coordination block — the orphan checker's notion of "linked" may not count that file; read `self_audit.py`'s orphan logic before deciding whether the fix is a link or an index entry).

**Acceptance:** `self_audit.py` reports no mandatory-gate failures; `harness_eval.py` back to 14/14 (with Issue 3 also fixed).

### ISSUE 5 — Event bus spam: unrouted `TEXTTORRENT_UNMAPPED_DID` warnings

**Evidence:** `state/event_router.log` (3.4 MB) tail shows repeated `{"event_type": "TEXTTORRENT_UNMAPPED_DID", "source_agent": "unknown", "severity": "warn", "status": "pending"}` bursts.

**Proposed solution:** trace the producer (TextTorrent = SunBiz SMS provider; likely an inbound webhook for a phone number/DID not mapped to a tenant). Either map the DID, or have the producer stop publishing for known-unmapped DIDs after the first warning, and make the router's consumption mark events handled so `pending` doesn't accumulate. If it's SunBiz-side, note that repo boundary: Bravo owns the substrate, Sun Biz Agent owns its runtime — a substrate-side dedup/routing fix is in scope here, business-logic fixes are a handoff note.

**Acceptance:** no repeating identical `pending` warns in the tail over a 24h window.

### ISSUE 6 — No scheduled accuracy measurement → "prove improvement" is impossible today

**Evidence:** `evals/reports/` newest files are `2026-06-10_*` (routing, routing_nl, send_policy, mistakes, compliance, redteam). `evals/baselines.json` holds static scores (all 1.0, tolerance 0.1). Meanwhile `state/harness_eval_history.jsonl` has **578 scored runs since 2026-07-17** and `task_outcomes` has 93 gate verdicts — the raw time-series data exists but nothing aggregates it.

**Proposed solution (this is the "prove accuracy increases" deliverable):**
1. **Weekly eval cron** running the existing suites (`evals/adapter.py` suites: compliance, routing, routing_nl, send_policy, mistakes + `redteam_adapter.py`), writing JSON to `evals/reports/YYYY-MM-DD_<suite>.json`, and failing loudly (notification via `python scripts/notify.py`) when any suite regresses beyond its `baselines.json` tolerance. Add the job to `cron_engine.py SEED_JOBS` — but note: `cron_engine.py seed` pushes to the shared Turso registry and is a production-scheduling mutation; stage it, show CC the entry, run seed only on his yes.
2. **One trend command** (e.g. extend `scripts/harness_eval.py --trend` or a small `scripts/core/accuracy_trend.py`) that renders, from data that already exists: harness score by week (from `harness_eval_history.jsonl`), gate verdict mix by week (from `task_outcomes`), eval suite scores vs baseline (from `evals/reports/`). Output: a short table CC can read in 10 seconds.
3. **Hallucination metric:** the Validator (`.claude/agents/validator.md`) already emits VERIFIED/REFUTED/UNVERIFIABLE per claim. Ensure those outcomes land in `task_outcomes` with a parseable verdict, then surface "REFUTED claims per week" in the trend report. That is the anti-hallucination number.

**Acceptance:** after two weekly runs, one command prints week-over-week movement for: harness score, eval suites vs baseline, gate verdict mix, REFUTED-claim count. If the number goes red, the system says so itself — that's the proof-of-improvement loop CC asked for.

### ISSUE 7 — Retention policy exists nowhere as code

**Diagnostic conclusion:** capture is comprehensive; lifecycle is not. Recommended policy (already reviewed with CC):

| Store | Policy to implement |
|---|---|
| `task_outcomes`, `harness_eval_history.jsonl`, `session_log` (DB), `MISTAKES/PATTERNS/DECISIONS.md`, git history | Keep forever (append-only evidence) |
| `state/event_router.log`, `~/.pm2/logs/*` | Rotate (PM2 side already daily-rotates via pm2-logrotate; add same for event_router.log) |
| `tmp/cron_failures/` | Keep ~90 days |
| `state/secret_access.log` | Rotate 10 MB × 3 (Issue 2) |
| `override_request` table (397 rows, feature deleted 2026-05-22) | Drop — ⚠ destructive, needs CC approval |
| Stale PM2 stdout for daemons that log elsewhere (see Issue 8) | Document the real log location; stop treating PM2 stdout as source of truth for those |

**Proposed solution:** implement as one "data lifecycle" pass — rotation configs where they belong, a `state_compact.py`-style cleanup for `tmp/cron_failures/` on the existing weekly hygiene cron, and a documented table in `brain/` (e.g. append to `brain/EXECUTION_RULES.md` or a new `brain/DATA_LIFECYCLE.md` linked from the router) so every future agent inherits the policy.

### ISSUE 8 — Observability gap: live daemons with 5-month-silent PM2 logs

**Evidence:** `bravo-telegram` (pid alive) and `bravo-scheduler` (pid alive) last wrote to `~/.pm2/logs/*-out.log` on **2026-03-21**, `event-router` on 2026-06-05 — yet the session log shows Telegram T2 replies today and cron jobs run today. They either log elsewhere now or hold stale pids.

**Proposed solution:** find where each daemon actually writes today (likely repo-local logs or the state DB), then either re-point PM2 at the real streams or document the real location in `memory/OPERATIONAL_STATE.md`. An operator should never have to do the pid-vs-log archaeology this diagnostic needed.

### ISSUE 9 — Minor: FTS memory index lag

**Evidence:** `state/memory_index.db` (13 MB FTS index) last modified 2026-08-24; `state/empire_state.db`'s own `memory_chunks*` tables look vestigial (0–2 rows) while the real index lives in `memory_index.db`.

**Proposed solution:** confirm the indexer (`scripts/core/memory_index.py`) runs on a schedule that matches how fresh retrieval needs to be (daily is probably fine); if the `memory_chunks*` tables in empire_state.db are confirmed dead, note them for the same cleanup approval as `override_request`.

---

## 5. Suggested execution order

1. **Issue 1** (email sweep) — revenue-adjacent, actively failing.
2. **Issue 2** (secret_access.log) — mechanical, biggest hygiene win.
3. **Issue 3** (PM2) — needs CC approval for process kills; restores fleet manageability.
4. **Issue 4** (self-audit gates) — mechanical, gets harness to 14/14.
5. **Issue 6** (eval cron + trend command) — the strategic deliverable: turns existing data into the accuracy proof.
6. **Issues 5, 7, 8, 9** — batch as a cleanup pass; the destructive bits (table drops) need one CC approval, grouped.

## 6. Definition of done for the whole engagement

- `python scripts/harness_eval.py` → 14/14, and the history file shows it staying green
- `python scripts/core/self_audit.py` → no mandatory-gate failures
- Zero new `tmp/cron_failures/` entries for `email_engine` across a week that includes a quota-exhausted window
- `state/secret_access.log` bounded; guards still green
- `pm2 list` works; 12/12 alive
- The trend command prints week-over-week: harness score, eval-vs-baseline, gate verdicts, REFUTED claims
- Every change reported to CC in the four-line format: **Changed / Why / Proof / Needs from CC**

## 7. What NOT to do

- Don't refactor anything not named above. Don't "improve" the fallback chain's architecture beyond what Issue 1 requires.
- Don't edit `brain/SOUL.md`, `.env*`, or MCP configs.
- Don't hand-edit generated files (`brain/WHEN_TO_USE_SKILLS.md`, the bridge manifest, STATE.md's MANIFEST block) — regenerate them.
- Don't claim a fix works without running its acceptance check. The diagnostic this brief is based on found multiple places where "process exists" ≠ "process works" — that distinction is the whole game here.
- Don't treat this brief as current truth if the live checks disagree. Quote the disagreement to CC and let him adjudicate.
