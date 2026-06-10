# Regression: Daily Outreach Batch — Broken Cron Pinged CC for 39 Days (2026-05-16)

## What went wrong
An operator-created `cron_jobs` row (`Daily Outreach Batch`, action_type `lead_outreach_batch`) fired daily at 08:00 UTC for 5+ weeks from 2026-04-07 through 2026-05-16. It auto-drafted cold-email approval prompts to CC's Telegram. Every approval CC tapped failed silently with a `send_gateway` block (`oasis commercial sends require body_html`) because the script's `send_approved_draft()` passed only `body_text` — the 2026-04-27 OASIS-HTML-required gate retired this whole code path but the cron + script were never removed. Compound failure: `brain/DAILY_SCHEDULE.md` had documented this cron as "Disabled by CC's request 2026-04-12" since April — docs and reality drifted apart for 34 days while CC kept getting noise.

## The behavior that must NOT recur
1. **DB row deleted, script removed end-to-end** (cron_jobs row, `scripts/outreach_batch.py`, `tmp/outreach_drafts*`, Telegram callbacks in both bridges, bridge-manifest entry, KNOWN_AGENT_SOURCES entry, doc references in 13 files).
2. **Stub guard:** `scripts/scheduler.py` keeps the `lead_outreach_batch` action_type but routes it to a `"retired:..."` marker so any future orphan row no-ops cleanly instead of resurrecting the loop.
3. **Anti-pattern regex:** `memory/ANTI_PATTERNS.json` now blocks any code path that references `outreach_batch.py` or recreates `lead_outreach_batch` cron rows. `anti_pattern_hook.py` flags this on every Bash invocation.
4. **Orphan-cron self-check:** `scripts/scheduler.py` startup now logs a warning if any `cron_jobs` row's `action_type` is in the RETIRED_ACTIO
