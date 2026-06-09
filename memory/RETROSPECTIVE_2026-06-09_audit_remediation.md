---
tags: [retrospective, audit, security, harness, v6.9.0]
last_updated: 2026-06-09
freshness_threshold_days: 365
---
# Retrospective — Audit Remediation V1 (2026-06-09, V6.9.0)

A 10-phase remediation against an external architecture + security audit. Theme:
**harness reliability** — structural fixes that make any model (incl. lower-tier
OpenCode/Gemini) more accurate, replicable to Maven/Atlas/SunBiz. Full per-phase
record: `plans/MISSION_2026-06-09_PROGRESS.md`.

## What changed (shipped, on `main`)

| Phase | Outcome |
|---|---|
| 0 Preflight | Full bundle backup (`../BEA_backup_*.bundle`) + local copy; pre-mission tag. |
| 1 PII purge | **Scope corrected mid-flight** — `goldstorm` is CC's test addr, not prospect data. Purged 11 *real* third-party lead emails + 5 lead files from all history. Branches+tags clean. |
| 2 Email compliance | `dashboard_email_consumer` applies CASL at send time; `email_doctor` check #5 structural + reorg-path fix (restored 7 dead checks). 8 new tests. |
| 3 Guards | secret+exec → enforce, state → report; tracked `settings.json`; `SECURITY_MODEL.md` §9–10. |
| 4 Migration ledger | `schema_migrations` table + `apply_migration --status/--backfill-ledger` + checksum guard. Safe mode (no blind backfill). |
| 5 Version | single-sourced in `STATE.md:architecture_version`; version-agnostic entry points; parity test. |
| 6 Routing docs | generated from the capability graph (`--emit-docs`); freshness test. |
| 7 Wiki-links | 125 dangling → 0; checker + template stubs + APPS_CONTEXT README. |
| 8 Hygiene + LOCKSTEP | 12 deploy prompts → `docs/deploy/`; removed forensic log + `app/`; `.gitignore` deduped; byte-identical LOCKSTEP block ×5. |
| 9 Brain freshness | 52 brain docs dated; `check_brain_freshness.py` (0 stale). |
| Final | `pytest -q` runnable from root (`--import-mode=importlib`); 6.9.0; this retro. |

## What was deliberately deferred (NOT done — by design)

- **Phase 10 (send_gateway 163KB decomposition):** per the brief, a money-path refactor
  belongs in its own session a day after the rest is stable. Ready-to-run plan is in the
  Fable handoff. NOT started.
- **Prod migration-ledger seed:** CC didn't confirm prod-current + no live DB this session.
  One-command CC step in `database/MIGRATION_NOTES.md`. No blind backfill.
- **GitHub PR-ref PII:** old emails persist in `refs/pull/*` (git can't rewrite). CC: GitHub
  Support purge, or private repo. Default clones are clean.
- **`.env.agents` guard-mode lines + `.env.agents.template`:** the harness blocks AI writes
  to `.env*` (correct). CC appends 3 lines per machine (in progress file).
- **`bridge_chat_server.py` windowless-flags bug:** pre-existing (4 `subprocess.run` missing
  `creationflags`), surfaced only because the importlib fix made the test collectible. Real
  Windows-window-pop bug; left for a verified bridge session (don't edit the live bridge blind).
- **exec_guard "soak":** unneeded — 14-day would-block count was 0, so enforce shipped directly.

## Lessons

1. **Trust the repo over the brief — and the operator over both.** The audit's `goldstorm`
   canary was CC's own test address. A pre-push sweep + one clarifying question saved a
   half-purge that would have over-redacted CC's data while missing the real spread. *Verify
   before the irreversible step; ask when scope is genuinely the operator's call.*
2. **The harness guards are real.** secret_guard correctly blocked AI writes to `.env*` (Phase 0
   backup, Phase 3 template) — respected it (security model wins), handed those to CC.
3. **A broken test harness hides failures.** Fixing the `pytest -q` collision surfaced 2
   previously-invisible failing tests. Make the suite runnable, *then* you can trust it.
4. **Generate, don't hand-maintain.** Routing docs + indexes now derive from the capability
   graph; drift is a test failure, not a slow rot.
5. **Surface, don't silently fix, shared-substrate issues.** The bridge subprocess bug + the
   ~6 stale `send_gateway` imports were logged as follow-ups, not unilaterally rewritten.

## Replication note (for Fable → Maven/Atlas/SunBiz)
The *patterns* are universal (single-source version + parity test, graph-generated routing,
wiki-link/freshness checkers, guard enforce-modes, LOCKSTEP block, importlib pytest). The
*content* is per-agent. See `plans/HANDOFF_FABLE_2026-06-09.md`.

## Related
- [[plans/MISSION_2026-06-09_PROGRESS]]
- [[brain/SECURITY_MODEL]]
- [[CHANGELOG]]
