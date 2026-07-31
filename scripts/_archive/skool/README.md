---
name: skool-automation-archive
description: Archived Skool community comment/reply automation — paused 2026-05-18, preserved for revival when CC launches their own Skool community.
type: archive
archived_on: 2026-05-18
archived_reason: Primary retainer ended 2026-05-18; CC does not own the Skool community the automation was posting into. Will be revived for CC's own community in the future.
tags: [scripts]
last_updated: 2026-05-18
---

# Skool Automation — Archived

Paused 2026-05-18. The daemon was posting replies/comments into a Skool community that CC no longer manages. Code is preserved here so CC can revive it cleanly when they launch their own Skool community.

## What's in here

| File | Purpose |
|------|---------|
| `skool_engine.py` | Main daemon. Modes: `login`, `auto` (one cycle), `daemon` (continuous). Playwright-based posting + comment replies + Telegram escalation for hot topics. |
| `skool_watchdog.py` | Windows watchdog. Heartbeat check, orphan kill, stale-process detection, .pyc cache clear. |
| `RESTART_SKOOL_DAEMON.bat` | Double-click restart. |

## What was left in place (intentional)

- `scripts/skool_watchdog_silent.pyw` — stays at its original path because the Windows scheduled task `\SkoolWatchdog` calls it by absolute path. The file is now a no-op (exits immediately). The scheduled task still fires every 5 min and lands on the no-op.
- `tmp/skool_*.json`, `tmp/skool_daemon.pid`, `tmp/skool_daemon.heartbeat`, `tmp/skool-browser/` — left in place. They are gitignored runtime state; if CC ever wants a clean slate before revival, just delete them.

## Revival steps (future Skool community)

1. `git mv scripts/_archive/skool/skool_engine.py scripts/skool_engine.py`
2. `git mv scripts/_archive/skool/skool_watchdog.py scripts/skool_watchdog.py`
3. `git mv scripts/_archive/skool/RESTART_SKOOL_DAEMON.bat RESTART_SKOOL_DAEMON.bat`
4. Restore `scripts/skool_watchdog_silent.pyw` from git history (the archived version of that file is at `git log --diff-filter=M --follow scripts/skool_watchdog_silent.pyw`).
5. Re-enable the scheduled task: `schtasks /Change /TN "SkoolWatchdog" /ENABLE` (needs admin).
6. Re-login the Skool browser session: `python scripts/skool_engine.py login`.
7. Update `skools/SKOOL_REGISTRY.md` with the new community URL/slug.
8. Restore the skill: `git mv skills/_archive/skool-automation skills/skool-automation`.
9. Restore the workflows: `git mv .agents/workflows/_archive/skool-edit.md .agents/workflows/skool-edit.md` and same for `skool-push.md`.
10. Re-add the entries to `brain/CAPABILITIES.md` (look at the diff that archived them — search for "Skool" in the git log around 2026-05-18).
11. Rebuild the capability graph: `python scripts/build_capability_graph.py`.
12. Re-enable the dashboard tile in `oasis-command-center/app/api/automations/background-workers/route.ts` (flip `archived: true` → `archived: false`).

## What was NOT archived

The Skool *content publishing* path (skill `skool-automation` for editing lessons + About page, and the `/skool-edit` and `/skool-push` workflows) is the same Playwright session as the comment daemon. They're archived together — restore as a unit.

## Obsidian Links
- [[brain/CAPABILITIES]]
- [[brain/QUICK_REFERENCE]]
