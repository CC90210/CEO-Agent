# Regression: Almost Wired an Auto-Sync That Would Have Reverted CC's MRR from $371 to $3,322 (2026-05-18)

## What went wrong
When CC asked to build a daily MRR auto-sync, I almost wired `revenue_engine.calculate_mrr() → user_profiles.mrr_current_usd` immediately. A dry-run before enabling caught that `revenue_engine` was still computing **$3,322** because Bennett's `subscription_start` row in `revenue_events` was untouched by the morning's cleanup (which only fixed `user_profiles` + `custom_fields`). Had I skipped the dry-run, tomorrow's 06:30 ET fire would have silently overwritten our $371 with $3,322, undoing the morning's work and lying to every downstream consumer (dashboard widget, ceo_pulse, snapshots).

## The behavior that must NOT recur
Pre-automation cleanup audit pattern logged in `memory/PATTERNS.md` [P]. Before wiring "fact X auto-flows from A to B," dry-run the canonical compute path and assert it equals the manually-known truth. If they disagree, find the upstream store you missed. Generalizable to any compute-then-write automation (Stripe webhook → CRM sync, pulse republish, n8n flow refire). Reference: `scripts/core/sync_mrr.py --dry-run` output 19:08 UTC (showed $371) vs the same compute at 19:15 UTC before the `subscription_cancel` insert (would have shown $3,322).
