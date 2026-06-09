---
tags: [memory, archive, local-only, pii]
last_updated: 2026-06-09
freshness_threshold_days: 365
---

# Outreach Archive — local-only (no third-party PII in git)

This directory holds **local-only operator outreach records**. Everything here
except this `INDEX.md` is gitignored (see `.gitignore` → `memory/outreach_archive/`
with `!memory/outreach_archive/INDEX.md`). Real third-party lead contact data must
**never** be committed to this (public) repository.

On 2026-06-09 the prior contents (a real-lead batch + one-shot outreach scripts)
were purged from all git history and restored to disk as untracked local files.
See [memory/RETROSPECTIVE_2026-06-09_audit_remediation](../RETROSPECTIVE_2026-06-09_audit_remediation.md)
for the full record.

## What lives here (local files, not in git)
- Dated outreach batches (`YYYY-MM-DD_*.md`) — lead lists, drafts, manifests.
- Execution logs (`*.json`) — send/result records.

## Schema convention
Each batch file is dated `YYYY-MM-DD_<purpose>.md`. Treat all of it as PII:
business owner names, emails, phone numbers. Keep it on disk; keep it out of git.

## Related
- [[memory/INDEX]]
- [[CONTEXT]]
