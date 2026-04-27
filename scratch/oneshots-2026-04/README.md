# One-shot scripts — April 2026

These scripts ran exactly once for a specific historical event. Kept for
reference and audit trail; never re-run, never imported by active code.

| Script | What it did | Date |
|---|---|---|
| `_post_call_update.py` | Suppressed test accounts, deleted bad-data leads, marked Basque Landscaping qualified, marked dead leads lost. | 2026-04-20 |
| `_tremont_email_and_updates.py` | Sent personable post-call follow-up to Emon at Tremont Cafe + post-call CRM updates. | 2026-04-20 |
| `_warm_revival_batch2.py` | Warm-revival email batch #2 — 10 leads emailed 6+ weeks ago with industry-varied templates through send_gateway. | 2026-04-20 |

Reusable utilities (`_audit_usage.py`, `_call_sheet_v2.py`, `_write_call_sheet.py`,
`_reconcile_gmail_sent.py`) stay in `scripts/` because they're idempotent
and intended to be re-run on new data.
