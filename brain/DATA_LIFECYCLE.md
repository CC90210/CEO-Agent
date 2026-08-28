---
tags: [brain, operations, retention, data-lifecycle]
last_updated: 2026-08-28
---

# Data Lifecycle

> Every store in this system, how long it is kept, and what enforces that.
> Written 2026-08-28 because the policy existed only as three unrelated scripts
> and a paragraph in a handover — so nothing could be checked against it, and
> two stores had grown unbounded without anyone deciding they should.

Related: [[EXECUTION_RULES]] · [[V6_ARCHITECTURE]] · [[STATE]]

## The rule that produced this file

**Capture was comprehensive; lifecycle was not.** Every subsystem here logs
well. Almost none of them expire anything. The failure mode is not a crash — it
is a 43 MB/day log, a 9,533-row queue of events waiting on a consumer that was
never coming, and a table nobody remembered adding.

When you add a store, decide its lifecycle in the same commit. An unbounded
store is a decision too; it is just an unexamined one.

## Keep forever — append-only evidence

These answer "what actually happened", and their value is precisely that they
are complete. Never prune.

| Store | Why it is permanent |
|---|---|
| `state/harness_eval_history.jsonl` | The accuracy time-series. Trimming it destroys the week-over-week comparison that `scripts/core/accuracy_trend.py` exists to make. |
| `task_outcomes` (state DB) | Review-gate verdicts. The record of what shipped and what was refused. |
| `session_log` (state DB) | Cross-session continuity. |
| `memory/MISTAKES.md`, `PATTERNS.md`, `DECISIONS.md` | The learning loop. A pruned mistake gets repeated. |
| `evals/reports/*.json` | Per-suite scores over time. Gitignored, but not disposable — this is how drift becomes visible. |
| git history | — |

## Rotate — bounded by size, contents disposable

| Store | Policy | Enforced by |
|---|---|---|
| `state/*.log` (all) | 5 MB, 5 gzipped backups | `scripts/hooks/rotate_logs.py`, fired by SessionStart **and** the Daily Log Rotation Audit cron (04:00 ET) |
| `~/.pm2/logs/*` | daily rotation | `pm2-logrotate` (legacy; PM2 is no longer the supervisor — see [[V6_ARCHITECTURE]]) |

**Rotation is the backstop, not the fix.** `state/secret_access.log` reached
43 MB/day *with* rotation working correctly, because the write volume outran a
5 MB cap several times over. The fix was at the source — `secret_loader` was
logging all 204 env key names on every call (~5.2 KB/record); it now records a
marker plus the key actually read (~250 B). **If a log is hitting the rotation
cap repeatedly, the log is wrong, not the rotation.**

## Age out — time-bounded

| Store | Retention | Enforced by |
|---|---|---|
| `tmp/` (top level) | 30 days | Weekly tmp/ Hygiene cron (Sun 03:00 ET) → `scripts/utilities/tmp_hygiene.py` |
| `tmp/cron_failures/*` | **90 days, per file** | same job, `_prune_cron_failures` |
| `agent_events` rows still `pending` | **30 days → status `dead`** | Weekly Event Bus Retention cron (Sun 03:30 ET) → `scripts/core/event_retention.py` |

Two traps live in this section, both of which have already bitten:

1. **`tmp_hygiene` scans top-level only** (`TMP_DIR.iterdir()`). A subdirectory
   is judged by its own mtime. For `cron_failures/` that mtime only moves when a
   job *fails*, so a quiet 90-day stretch — the outcome we are working toward —
   would have deleted the whole failure archive in one pass. It is now
   allowlisted as a directory, with its *contents* aged separately. The
   allowlist's note on `snapshots` documents the identical trap; the reasoning
   simply had not been extended one entry down.
2. **Event retention MARKS, never deletes.** `agent_events` is the Bravo↔APEX
   coordination channel and a shared audit trail. `dead` is a schema-valid
   terminal state (`015_v6_event_bus_extensions.sql` constrains status to
   pending/processing/done/failed/dead) and means exactly "no consumer will
   process this". Deleting rows out of a shared channel is not a unilateral call.

## Unbounded and undecided — needs an operator decision

Listed because an undecided store must be *visible*, not silently growing.

| Store | Size (2026-08-28) | Question |
|---|---|---|
| `state_transaction` (state DB) | 13,152 rows, growing | No retention. Is this evidence (keep) or churn (age out)? Not yet decided. |
| `override_request` (state DB) | 397 rows | Feature removed 2026-05-22. Drop candidate — but `exec_guard` hard-blocks `DROP TABLE` by design, so it needs a deliberate, backed-up, operator-approved action. |
| `memory_chunks*` (state DB) | 0–2 rows | Vestigial; the real FTS index is `state/memory_index.db`. Same approval batch as above. |

## When you add a store

1. Decide which section above it belongs in, and add the row.
2. If it ages out, **schedule the sweep in the same commit.** A retention tool
   nobody runs is not a retention policy — `event_retention.py` was written,
   run once by hand, and left unscheduled, and 40 rows crossed its cutoff within
   two hours. The eval suites went eleven weeks unmeasured for exactly this
   reason.
3. If it is a JSON store, use `scripts/lib/json_ledger.py` rather than
   hand-rolling load/save. It is the one implementation of that idiom.
