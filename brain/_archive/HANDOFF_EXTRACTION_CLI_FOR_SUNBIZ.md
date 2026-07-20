---
description: "Handoff: SunBiz document extraction moved from metered API to VPS Claude subscription; VPS daemon setup, config doctor command, PM2 persistence, and end-to-end verification steps"
tags: [sunbiz, extraction, vps, handoff, archived]
last_updated: 2026-06-26
freshness_threshold_days: 365
status: archived
archived_on: 2026-07-19
archived_from: brain/HANDOFF_EXTRACTION_CLI_FOR_SUNBIZ.md
archive_reason: "One-time rollout handoff completed; reusable operating guidance moved into the maintained VPS setup handoff."
superseded_by: docs/VPS_SETUP_HANDOFF.md
---

# Handoff — Document extraction moved to the VPS Claude subscription (off the API)

> **For: the SunBiz agent / whoever runs the VPS.** What changed, how it works, the
> ONE setup step to make it live, and what's next. (CC 2026-06-26.)

## What we accomplished

When an operator drops/creates a SunBiz application, the dashboard **no longer calls the
metered Anthropic vision API** to read it. It now:

1. **Files the doc + queues a job** (`document_extraction_jobs`, migration 104 — already
   applied to the dashboard DB `phctllmtsogkovoilwos`). Returns "reading…" immediately.
2. **A VPS daemon** (`scripts/integrations/extraction_consumer.py`, PM2 `extraction-consumer`)
   reads the doc with the **Claude Code CLI on CC's SUBSCRIPTION** (OAuth, not the API key —
   `scripts/lib/claude_auth.py` strips `ANTHROPIC_API_KEY`), extracts the fields + signature
   box, and **falls back to the metered API only on a quota/auth cap**.
3. It **POSTs the result back (HMAC-signed)** to the dashboard at
   `/api/internal/apply-extraction`, which fills the application + regenerates the branded
   PDF via the existing pipeline (`applyExtractedApplication` + the signature crop — all
   unchanged). The dropzone polls `/api/extraction-jobs/[job_id]` and shows the deferred
   signature-confirm.

Net: the per-application **vision cost is off the API, on the flat-rate subscription**. The
PDF render + signature crop were already free. The API is now a break-glass fallback only.

Commits: dashboard `1c55963`/`1dc38be` (CC90210/oasis-command-center) · CEO-Agent
`09a35faf`/`5de2a830`. Verified: `tsc` 0 errors, daemon py_compile + unit tests green, one
Codex adversarial pass (3 findings — atomic claim, no-stub new-deal, new-mode redirect — all
fixed). Migration applied + the table is live.

## The ONE setup step to make it live (on the VPS)

```bash
ssh root@srv1723601
cd /srv/sunbiz/ceo-agent && git pull --ff-only

# 1) Authenticate the CLI on CC's SUBSCRIPTION (so it doesn't use the metered API):
claude setup-token        # only if ~/.claude/.credentials.json is missing/expired

# 2) Verify config (must show: claude OAuth YES, HMAC yes, supabase ok):
python scripts/integrations/extraction_consumer.py doctor

# 3) Start the daemon (Linux-gated in ecosystem.config.js) + persist:
pm2 start ecosystem.config.js --only extraction-consumer && pm2 save
```

**Critical env (VPS `.env.agents`):** `OASIS_OUTBOUND_HMAC_SECRET` MUST equal the dashboard's
Vercel value (it's the shared callback secret) · `BRAVO_SUPABASE_URL` + service-role key ·
a dashboard URL (`PUBLIC_APP_URL` or `OASIS_DASHBOARD_URL`). `doctor` confirms all of these.

If `claude OAuth` shows **NO**, the daemon still works but every extraction hits the metered
API — defeating the purpose. Re-run `claude setup-token`.

## Verify end-to-end

Drop a real signed application (PDF + a photo) on a lead. Watch:
`select status, used_fallback, error from document_extraction_jobs order by created_at desc`
→ `queued → processing → extracted → applied`, `used_fallback = false` (subscription was
used). The daemon log (`pm2 logs extraction-consumer`) shows the run. The application fields
+ branded PDF populate; the signature-confirm appears in the dropzone. Then check the
Anthropic API dashboard shows ~zero extraction calls.

## What's next (broader SunBiz pending — unchanged by this work)

1. **Text Torrent go-live** — set in Vercel: `DASHBOARD_LIVE_SEND=1` (currently OFF → all
   dashboard sends are dry-run) and `TEXTTORRENT_WEBHOOK_SECRET` (currently unset → inbound
   TT replies are rejected). Then each rep enters their own TT number in Settings, and set
   `SUNBIZ_TT_OWNER_NUMBER` on the VPS for automated/Helios sends.
2. **Shop-out address removal** — committed (`e7f6c713`) but needs the VPS to pull + reload
   the bridge: `git pull --ff-only` → `python scripts/tests/test_address_suppression.py` →
   reload.
3. **Signature feature** — real-document e2e QA + confirm the Vercel build is green (native
   deps `sharp`/`pdfjs-dist`/`@napi-rs/canvas` — now also exercised by this async path).
4. **Latency backlog** — JSONB expression indexes (highest-leverage; needs a migration +
   live-DB check).

## Tuning knobs (in `extraction_consumer.py`)

`MAX_ATTEMPTS=3` · `CLI_TIMEOUT_SEC=200` · `STALE_PROCESSING_MIN=10` (crashed-job recovery) ·
loop interval `8s`. Raise the timeout if real applications are large/multi-page; tune attempts
to the real per-day volume.
