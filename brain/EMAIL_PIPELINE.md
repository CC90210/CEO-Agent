---
tags: [runbook, email, inbound, automation, atlas]
related: ["[[STATE]]", "[[QUICK_REFERENCE]]", "[[AGENTS]]"]
last_updated: 2026-07-26
---

# Inbound Email Pipeline — Runbook

The native replacement for the n8n **"OASIS Inbound Qualifier"** workflow
(`1cGIN32alM8sf8OV`, now inactive). Classifies every inbound email into 4 brains
and acts under a hybrid/guarded autonomy policy — entirely on the subscription
Claude CLI, **no metered API keys**. Durable memory: `[[project_native_email_pipeline]]`.
See also the outbound twin: `scripts/integrations/send_gateway.py` (`scripts/integrations/send_gateway.py`).

## The chain (every 5 min)
`bravo-scheduler` (PM2) → cron **"Inbound Email Sweep"** (`*/5`, `email_inbox_check`)
→ `scripts/integrations/email_engine.py:cmd_check_inbox` (Gmail IMAP UNSEEN):

1. `extract_body_full()` — full body, HTML fallback, UTF-8, newlines kept.
2. **Idempotency guard** — skip if RFC `Message-ID` already in
   `tmp/inbound_processed_msgids.json` (no re-classify/LLM/hand-off; does NOT
   mark read, so held mail stays visible). Record after processing.
3. **Sender triage** (`email_playbook.classify_sender`): owner / sibling-agent /
   security / automated / human. **no-reply = classify-but-never-reply**, never a
   delete (vendor receipts = deductible expenses).
4. **Forward parsing** — classify on the ORIGINAL sender; unresolvable → review.
5. `inbound_classifier.classify_category()` → technical_support /
   business_opportunity / financial_legal / low_priority.
6. `email_brain.process_email()` → `decide_action()` (pure policy) → dispatch.
7. Ledger row (`record_inbound_from_n8n` RPC) with the routing contract → shows
   in the Command Center inbound card.

## Autonomy policy (`email_brain.decide_action`)
| Brain | Action |
|---|---|
| technical_support | auto-reply ONLY: known client + conf ≥ `REPLY_THRESHOLD` (0.7) + critic/lint pass; else draft-hold |
| business_opportunity | always draft-and-hold (CC's eyes on hot leads) |
| financial_legal | hand off to **Atlas** if conf ≥ `FINANCIAL_THRESHOLD` (0.5) + valid Message-ID+sender; else review; never auto-reply |
| low_priority | archive at conf ≥ `ARCHIVE_THRESHOLD` (0.6); else review |

**Hard guards (deterministic, override routing):** outage / frustrated / strategic
(VC·press) / opt-out → never auto-reply; money-in-thread → draft only; automated/
sibling/security/owner sender → never reply.

## Controls — `ecosystem.config.js` (bravo-scheduler `env`)
```
EMAIL_BRAIN_ENABLED=1        # master switch (off = legacy notify-and-mark-read)
EMAIL_BRAIN_AUTO_SEND=1      # allow the ONE guarded auto-reply path
EMAIL_BRAIN_REPLY_THRESHOLD / _ARCHIVE_THRESHOLD / _FINANCIAL_THRESHOLD  # optional
```
**Apply / KILL:** edit the file, then
`pm2 delete bravo-scheduler && pm2 start ecosystem.config.js --only bravo-scheduler`.
(NOT `--update-env` — that re-reads the shell env, not the file.)

## Verify
- `python scripts/core/cron_engine.py list | grep -i "inbound email"` — active + run count.
- `python scripts/integrations/email_engine.py --json check-inbox` — one live sweep (honors flags).
- Tests: `python -m pytest scripts/tests/test_email_*.py scripts/tests/test_inbound_category.py -q` (Bravo) · `pytest tests/test_financial_handoff_consumer.py` (Atlas). Tests never fire real Telegram (notify no-op under pytest).

## Atlas side (CFO-Agent)
`scripts/tools/financial_handoff_consumer.py` consumes `email.financial_handoff`
events (cron "Atlas — Inbound Financial Email", `*/15`): fetches the emailed
PDFs by Message-ID, reads them with the scoped-Read vision path
(`[[pattern_untrusted_document_scoped_read]]`), decides paid-vs-received from the
DOCUMENT, books `data/receipts_cache.json`, labels Gmail, dead-letters after 3
tries with ONE alert.

## Guarantees / gotchas
- Idempotency + notify dedup stop cron loops — see `[[pattern_inbound_idempotency_and_notify_dedup]]`.
- Every reply routes through `scripts/integrations/send_gateway.py` (CASL/critic apply; non-operator source).
- State files `tmp/inbound_processed_msgids.json` + `tmp/notify_dedup.json` are
  allowlisted from tmp-hygiene — do not purge.

## Open (CC-gated)
Land branches → main/master · reclassify 8 mis-booked ledger rows (161.03 CAD) ·
Codex independent audit (quota) · delete the inactive n8n workflow.
