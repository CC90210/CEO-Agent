---
description: "Archived SunBiz Command Center handoff: completed bank-statement upload and FICO work, architecture decisions, and DB-driven form re-seeding instructions"
tags: [sunbiz, handoff, completed, archived]
last_updated: 2026-06-23
freshness_threshold_days: 365
status: archived
archived_on: 2026-07-19
archived_from: memory/CODEX_HANDOFF.md
archive_reason: "Both P0 handoff tasks shipped in oasis-command-center commit a55d1cd and the live forms were re-seeded."
superseded_by: memory/SESSION_LOG.md
---

# SunBiz Command Center — Codex Handoff (2026-06-23)

**Repo:** `C:\Users\User\APPS\oasis-command-center` (Next.js 15, tenant `submissions`).
**Rules:** commit author = **CC90210** (else Vercel blocks). Coordinate via OASIS `agent_activity` (APEX is active here). Gate before push: `npm run typecheck && npm run lint`.

> **Archived outcome:** Both TODOs below shipped on 2026-06-23 in
> `oasis-command-center` commit `a55d1cd`; the live SunBiz forms were re-seeded and
> production verification passed. The TODO wording is retained only as historical context.

**✅ Done by Bravo (pushed, `698802e`) — don't redo:** (1) clickable Stage on the pipeline board → `/api/leads/[id]/set-stage`; (2) removed the APPLICANT block from the application PDF.

---

## TODO 1 — P0: merchants can't upload bank statements

**Cause:** the upload field (`bank_statements`, `file_upload_multi`) only exists in the standalone **`bank-statement-upload`** form, on **step 1**. The uploader needs an HMAC token that's only minted *after* step 0 submits — but step 1 *is* the upload, so anonymous merchants have no token and it blocks ("open from the personalized link"). The main app forms (`full-application`, `funding-pre-application`) have **no upload field at all**.

**Decision for CC/Ezra:** put bank-statement upload as a step *inside* the main application form, or keep it a separate tokenized form?

**Recommended fix:** add a `file_upload_multi` "Upload bank statements" step to the main form seed **after step 0** (token already minted), then re-seed. Reuses the working uploader, nothing else changes.

**Files:** `components/forms/MultiFileDropzone.tsx` (token gate ~L187) · `FormPublicClient.tsx` (token mint ~L325) · `app/api/forms/upload-url/route.ts` (signed-URL minter — fine, no change) · `lib/forms/sunbiz-templates.ts` (seed) · `scripts/run_reseed_sunbiz_forms.py --apply`.

## TODO 2 — add FICO / credit score to the application

`applicant_fico` is **already** in `lib/forms/application-upsert.ts` whitelist + `create-from-lead.ts`, so the record and the PDF auto-pick it up. Just add a field **`applicant_fico`** (label "Credit Score (FICO)", number or 600-650 buckets — ask Ezra) to the application form seed (`lib/forms/sunbiz-templates.ts`), then re-seed.

## Gotchas
- Forms are **DB-driven** — seed edits are inert until `python scripts/run_reseed_sunbiz_forms.py --apply`.
- A pre-existing failing test (`sunbiz-import-routing`, imported "Approved" → wrong stage) is APEX's `approved`-stage side effect, **not** these changes. 24/25 sunbiz tests pass.

## Obsidian Links
- [[brain/INDEX]]
- [[brain/STATE]]
