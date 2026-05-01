---
tags: [session-log, template]
description: Append-only log of Bravo work sessions. Live version is gitignored.
---

# SESSION LOG (TEMPLATE)

> Copy this file to `memory/SESSION_LOG.md` and let Bravo append to it.
> Live version is gitignored — your client/deal data stays local.

## Format

```
### YYYY-MM-DD — [Session topic]
**Done:** [1-2 sentence summary of what shipped]
**Files:** [key files touched]
**Next:** [follow-up the next session should pick up]
```

## Example

```
### 2026-01-15 — Outreach loop deployment
**Done:** Wired daily-batch scraper into Telegram approve flow. 24 leads scored, 8 drafts queued.
**Files:** scripts/outreach_batch.py, scripts/draft_critic.py
**Next:** Verify reply handling on first inbound batch.
```

## Live entries below

<!-- Bravo appends here every session. Older entries roll into memory/archive/ when this file exceeds 500 lines. -->
