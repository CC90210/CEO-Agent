---
description: "Historical Mac chat catch-up for the completed SunBiz CLI document-extraction rollout"
tags: [sunbiz, mac, extraction, handoff, archived]
last_updated: 2026-06-26
freshness_threshold_days: 365
status: archived
archived_on: 2026-07-19
archived_from: brain/MAC_SUNBIZ_CHAT_UPDATE_2026-06-26.md
archive_reason: "Point-in-time chat bootstrap was superseded by maintained VPS deployment documentation."
superseded_by: docs/VPS_SETUP_HANDOFF.md
---
# Mac SunBiz chat — catch-up message (2026-06-26)

> Paste into the Mac SunBiz Claude Code chat so it's current before Montreal. This
> layers on top of brain/MONTREAL_HANDOVER_2026-06-25.md.

---

Status update — you are Bravo continuing SunBiz work. Since the last handover, one major
feature shipped. Get current, then verify any claim against live code before acting.

**SHIPPED TODAY — document extraction moved off the metered API onto the Claude Code CLI
(CC's subscription).** When an operator drops/creates a SunBiz application, the dashboard no
longer calls the Anthropic vision API. It queues a `document_extraction_jobs` row; a VPS
daemon (`extraction-consumer`, PM2, Linux-only) reads the doc with `claude` on CC's
subscription (OAuth, not the API key), and POSTs the fields back (HMAC) to
`/api/internal/apply-extraction`, which fills the application + regenerates the branded PDF
via the existing pipeline. The API is a break-glass fallback only (subscription cap).

- **Commits:** dashboard `CC90210/oasis-command-center` → `1dc38be` (feat), `1c55963` (Codex
  hardening — atomic claim, no-stub new-deal, redirect), `4367965` (middleware fix), `119b6c2`
  (docs). CEO-Agent → `5de2a830` (daemon), `09a35faf` (hardening), handoff + VPS prompt docs.
- **Migration 104** (`document_extraction_jobs`) applied to the dashboard DB
  (`phctllmtsogkovoilwos`). Table live.
- **Proven (by me, live):** the subscription CLI extracts fields from both PNG and PDF apps
  (incl. locating the signature box); the cross-language HMAC callback works against the
  deployed route; the atomic CAS claim SQL is valid.
- **Caught + fixed a critical blocker:** the dashboard middleware was 401'ing the HMAC
  callback (no session) BEFORE its signature check — which would have silently broken every
  apply. Fixed by adding `/api/internal/apply-extraction` to `PUBLIC_PATH_PREFIXES` in
  `middleware.ts` (HMAC-gated inside, same pattern as `/api/outbound/log`). Re-tested live:
  the callback now returns `job_not_found` for a fake job (middleware passes + HMAC verifies).
- **State:** the daemon is LIVE on the VPS ("live but unproven"). The only unproven piece is
  the full chain with a REAL dropped application — **Ezra / Jordan / Alex test that tomorrow.**
  If a job sticks at "reading…", check `document_extraction_jobs.status` + the daemon log
  (`pm2 logs extraction-consumer`); `used_fallback=true` means the VPS subscription OAuth is
  missing (`claude setup-token`).

**Key files:** dashboard — `app/api/internal/apply-extraction/route.ts` (callback),
`app/api/extraction-jobs/[job_id]/route.ts` (poll), `app/api/leads/[id]/autofill-application`
+ `new-from-document` (now queue), `components/leads/AutofillDropzone.tsx` (poll + confirm),
`database/104_*.sql`, `middleware.ts`. CEO-Agent —
`scripts/integrations/extraction_consumer.py` (daemon), `scripts/lib/claude_auth.py`
(subscription auth), `ecosystem.config.js`. Docs:
`brain/HANDOFF_EXTRACTION_CLI_FOR_SUNBIZ.md`, `brain/VPS_EXTRACTION_DEPLOY_AGENT_PROMPT.md`.

**Still pending across SunBiz (unchanged):**
1. **Text Torrent go-live** — in Vercel: `DASHBOARD_LIVE_SEND=1` (currently OFF → all dashboard
   sends are dry-run) + `TEXTTORRENT_WEBHOOK_SECRET` (unset → inbound TT replies rejected).
   Then reps set their own TT numbers; set `SUNBIZ_TT_OWNER_NUMBER` on the VPS.
2. **Shop-out address removal** — committed (`e7f6c713`), needs the VPS to pull + reload.
3. **Signature feature** — real-document e2e QA + confirm the Vercel native-dep build is green.
4. **Latency backlog** — JSONB expression indexes (needs a migration + live-DB check).

**Working rules:** commit oasis-command-center as **CC90210**; `git pull --rebase` before every
push (main is shared with APEX); Codex audit anything touching money/legal/the send substrate;
verify against live code, don't trust a snapshot.

---

## Obsidian Links
- [[brain/INDEX]]
- [[brain/STATE]]
