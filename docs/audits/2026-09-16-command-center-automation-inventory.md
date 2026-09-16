# Command Center Automation Inventory — 2026-09-16

Read-only inventory captured before the ownership migration and missing-seed installation. Times in `cron_jobs` and `tenant_cron_jobs` are interpreted in `America/Toronto` by their local runners unless a row explicitly says UTC.

## Reconciliation summary

| Registry | Before | Registered source | Difference | Runtime field / consumer |
|---|---:|---:|---|---|
| `cron_jobs` (CC tenant) | 36 total / 33 active | 37 seeds / 34 active | `Carousel Media Retention` was registered in source but never inserted | `is_active`; `scripts/scheduler.py` |
| `tenant_cron_jobs` (CC tenant) | 4 total / 1 active | 4 live rows | none | `enabled`; Command Center bridge poller |
| Command Center API/UI | 4 total / 1 active | 40 live rows before install | operator gate omitted all 36 Empire rows | merged GET `/api/cron-jobs` |
| Expected after repair | 41 total / 35 active | 37 Empire + 4 tenant | complete | same two runtime lanes, normalized once |

All 36 pre-change Empire rows already carried CC's tenant ID `ef8d389e-3f15-43f2-ae00-3660f69a1452`. No tenant backfill was required. The exact production fault was `OPERATOR_EMAIL` replacing, rather than augmenting, canonical operator identity `conaugh@oasisai.work`; the API consequently skipped the Empire query and returned the four Atlas tenant rows as a plausible success.

The production Turso migration is `bravo__108_cron_owner_agent_key.sql`. The explicit `supabase_legacy` rollback receives the same owner backfill plus a service-role-only, row-locked state-and-audit RPC in `bravo__109_cron_owner_atomic_toggle.sql`; the application deploy depends on that rollback migration being applied first.

## Empire schedules (`SEED_JOBS`)

Source of truth: `scripts/core/cron_engine.py`. Runtime registry: Turso `cron_jobs`. Local schedule zone: `America/Toronto`.

| Job | Owner | Schedule | Enabled | Runner |
|---|---|---|---|---|
| Booking Reminders | bravo | `0 18 * * *` | on | `booking_reminder` |
| Bravo — Cross-Agent Review Scan | bravo | `0 9,17 * * *` | on | `scripts/cross_agent_review.py scan --json` |
| Bravo — Hourly Cron Health Check | bravo | `0 * * * *` | on | `scripts/core/cron_health_check.py --alert` |
| Bravo — Nightly Harness Eval | bravo | `30 3 * * *` | on | `scripts/harness_eval.py --source cron` |
| Bravo — Review Harvest | bravo | `*/15 * * * *` | on | `scripts/review_loop.py --seed-open --once --json` |
| Bravo — Sleep Agent (Memory Consolidation) | bravo | `0 4 * * *` | on | `scripts/bravo_sleep.py run` |
| Break-Glass Drill (quarterly) | bravo | `0 9 1 */3 *` | off | `scripts/break_glass_drill.py` |
| Carousel Media Retention | maven | `50 3 * * *` | on | `C:\Users\User\CMO-Agent\scripts\prune_carousel_media.py --apply --json` |
| Cross-Agent Self-Improvement Sweep | bravo | `0 4 * * *` | on | `agent_self_improvement` |
| Daily Automation Register | bravo | `30 5 * * *` | on | `scripts/core/generate_automations.py` |
| Daily Bravo Brief | bravo | `0 6 * * *` | on | `daily_brief` |
| Daily Briefing Snapshot | bravo | `57 5 * * *` | on | `scripts/snapshots/briefing_snapshot.py` |
| Daily Client Alerts Snapshot | bravo | `0 7 * * *` | on | `scripts/snapshots/client_alerts_snapshot.py` |
| Daily Log Rotation Audit | bravo | `0 4 * * *` | on | `scripts/hooks/rotate_logs.py --force` |
| Daily MRR Auto-Sync | bravo | `30 6 * * *` | on | `scripts/core/sync_mrr.py` |
| Daily Memory Index Rebuild | bravo | `30 4 * * *` | on | `scripts/core/memory_retriever.py build` |
| Daily Pulse Mechanical Refresh | bravo | `45 7 * * *` | on | `scripts/pulse_publish.py autorefresh` |
| Daily State DB Backup | bravo | `0 3 * * *` | on | `scripts/state/backup_db.py backup --keep 7` |
| Event Bus Offline Drain | bravo | `*/10 * * * *` | on | `scripts/core/event_bus.py drain` |
| Funnel Fast-Poll | bravo | `*/1 * * * *` | off | `funnel_fast_poll` |
| Inbound Email Sweep | bravo | `*/5 * * * *` | on | `email_inbox_check` |
| LanceDB Compaction (weekly) | bravo | `0 3 * * 6` | on | `scripts/core/state_compact.py --retain-days 2 --json` |
| Library Post Linker | maven | `17 * * * *` | on | `scripts/link_library_to_posts.py --execute` |
| Loud Failures Weekly Probe | bravo | `30 8 * * 1` | on | `scripts/system_health.py --json --notify` |
| Marketing Publish Drain | maven | `* * * * *` | on | `scripts/marketing_publish_drain.py` |
| Maven — Carousel Post | maven | `0 8 * * *` | on | `C:\Users\User\CMO-Agent\scripts\run_posting_cron.py` |
| Monthly Inventory Sync | bravo | `0 3 1 * *` | on | `scripts/core/generate_inventory.py` |
| Nurture Sequence Check | bravo | `0 10 * * MON-FRI` | off | `nurture_check` |
| OASIS Auto-Score Leads | bravo | `45 5 * * *` | on | `auto_score_leads` |
| Post Analytics Sync | maven | `17 * * * *` | on | `scripts/sync_post_analytics.py` |
| Training Corpus Ingest | maven | `*/5 * * * *` | on | `scripts/ingest_training_link.py` |
| Weekly Eval Suites | bravo | `0 5 * * SUN` | on | `evals/run_suites.py --json` |
| Weekly Event Bus Retention | bravo | `30 3 * * SUN` | on | `scripts/core/event_retention.py --apply --days 30 --json` |
| Weekly Full-Truth Health Digest | bravo | `0 7 * * SUN` | on | `scripts/weekly_truth_digest.py` |
| Weekly Pipeline Review | bravo | `0 10 * * MON` | on | `pipeline_review` |
| Weekly Receipts Reconciliation | bravo | `23 4 * * 1` | on | `scripts/receipts_audit.py reconcile` |
| Weekly tmp/ Hygiene | bravo | `0 3 * * SUN` | on | `scripts/utilities/tmp_hygiene.py --apply --json --days 7` |

The six Maven ownership assignments were verified from their runners and descriptions. All other current Empire definitions belong to Bravo. There are no verified Empire `cron_jobs` owned by Atlas or Aura; Atlas uses the tenant lane below.

## CC tenant schedules

Source of truth and runtime registry: Turso `tenant_cron_jobs`. Runner: the Command Center bridge poller.

| Job | Owner | Schedule | Enabled | Runner |
|---|---|---|---|---|
| Atlas — Daily Tax Deadline Scan | atlas | `0 7 * * *` | off | `tools/threshold_scanner.py` |
| Atlas — Inbound Financial Email | atlas | `*/15 * * * *` | on | `tools/financial_handoff_consumer.py once --limit 5` |
| Atlas — Pulse Refresh | atlas | `0 */4 * * *` | off | `tools/pulse_publish.py refresh` |
| Atlas — Wealthsimple Balance Nudge | atlas | `0 18 * * SUN` | off | `tools/wealthsimple_nudge.py --stale-days 7` |

## Hosted scheduler surfaces

| Surface | Owner | Schedule | Enabled | Runner / source of truth |
|---|---|---|---|---|
| Vercel production crons | Command Center | — | none | Production deployment exposes zero configured Vercel cron triggers |
| Cloudflare cron Worker | Bravo | `* * * * *` UTC | on | Worker `oasis-cc-cron`; `config/cron-registry.json` contains 29 forwarded application routes |

Cloudflare is the hosted dispatcher; it is not an additional copy of `cron_jobs`. A live simulation at `2026-09-16T17:35:00Z` found forwarding enabled and six routes due. Stale Vercel arrays in old feature worktrees are not production runners.

## Windows Task Scheduler

| Task | Owner | Trigger | Enabled | Action / source of truth |
|---|---|---|---|---|
| Bravo Fleet Watchdog | Bravo | every 5 minutes + logon | on | `.venv\Scripts\pythonw.exe scripts\ops\fleet_watchdog.py up`; Task Scheduler |
| OASIS Chrome Audio Guard | Bravo | every 5 minutes | on | `.venv\Scripts\pythonw.exe scripts\repair_chrome_audio_silent.py 100`; Task Scheduler |
| BravoSystemHealth | Bravo | legacy 30-minute loop | off | `scripts\system_health_check.py`; Task Scheduler |
| MavenSchedulePosts | Maven | daily 08:00 local | **off** | `CMO-Agent\scripts\daily_posting_cron.bat`; Task Scheduler |
| PM2 Resurrect | Bravo | boot/logon legacy | off | `scripts\pm2_resurrect_hidden.vbs`; Task Scheduler |
| PM2 Resurrect on Login | Bravo | logon legacy | off | `pm2 resurrect`; Task Scheduler |

`MavenSchedulePosts` remains deliberately disabled. Its action ultimately calls the same `run_posting_cron.py` chain, so enabling it would create a duplicate trigger.

## Long-running processes

PM2 currently supervises no business applications; only the `pm2-logrotate` module is online. `scripts/ops/fleet_watchdog.py`, driven by the Windows watchdog task, is the current process supervisor and reported 12/12 running:

| Process | Owner | Cadence | Runner | Source of truth |
|---|---|---|---|---|
| bravo-telegram | Bravo | continuous | `telegram_agent.js` | fleet watchdog manifests |
| claude-bridge | Bravo | continuous | `pythonw -m bravo_cli.bridge_chat_server` | fleet watchdog manifests |
| claude-bridge-ping | Bravo | continuous | `pythonw -m bravo_cli.local_bridge _loop` | fleet watchdog manifests |
| event-router | Bravo | 3-second loop | `scripts/core/event_router.py loop --interval 3` | fleet watchdog manifests |
| bravo-coord | Bravo | continuous | `coordination_agent.js` | fleet watchdog manifests |
| bravo-scheduler | Bravo | continuous scheduler poll | `scripts/scheduler.py` | fleet watchdog manifests |
| breeze-live-watch | shared OASIS | 300-second loop | `scripts/breeze_live_watch.py loop --interval 300` | fleet watchdog manifests |
| bravo-ig-dm | Bravo | continuous | `scripts/integrations/ig_dm_daemon.py` | fleet watchdog manifests |
| dashboard-email-consumer | Bravo | 10-second loop | `scripts/dashboard_email_consumer.py loop --interval 10` | fleet watchdog manifests |
| dashboard-email-queue-monitor | Bravo | 300-second loop | `scripts/dashboard_email_queue_monitor.py loop --interval 300` | fleet watchdog manifests |
| atlas-telegram | Atlas | continuous | `C:\Users\User\APPS\CFO-Agent\telegram_app\bot.py` | fleet watchdog sibling manifest |
| maven-telegram | Maven | continuous | `C:\Users\User\CMO-Agent\telegram_agent.js` | fleet watchdog sibling manifest |

These belong in Background Workers, not as duplicate active cron cards. The Command Center intentionally displays 11 OASIS worker rows because `breeze-live-watch` is outside that UI list.

## Maven GEN-10 runner contract

`Maven — Carousel Post` is one operator toggle for the full safe chain:

1. `verify-published`
2. `watch`
3. `author-carousels`
4. `unstick`
5. `generate`
6. `plan`
7. `deliver-renders`
8. `library-sync`

The registered trigger is daily 08:00 `America/Toronto`; its internal posting plan uses 13:00 and 19:00 UTC. The six accepted families are `briefing-grid`, `tide-editorial`, `constellation-map`, `proof-file`, `split-signal`, and `kinetic-poster`. Scheduling prefers distinct families within a day, but the verified implementation may reuse one at its final fallback tier instead of leaving a slot empty. The two prepared decks remained queued and unbooked during this audit.

## Evidence commands

- `python scripts/integrations/turso_tool.py select cron_jobs --tenant ef8d... --json` → 36 rows / 33 active before change.
- `python scripts/integrations/turso_tool.py select tenant_cron_jobs --tenant ef8d... --json` → 4 rows / 1 active.
- Importing `SEED_JOBS` → 37 definitions / 34 active, with `Carousel Media Retention` absent live.
- `python scripts/ops/fleet_watchdog.py status --json` → 12/12 running.
- `pm2 list --no-color` → zero business applications; `pm2-logrotate` only.
- `Get-ScheduledTask` + `Get-ScheduledTaskInfo` → two relevant tasks enabled, four disabled; `MavenSchedulePosts` disabled.
