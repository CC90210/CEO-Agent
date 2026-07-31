---
tags: [docs]
last_updated: 2026-06-03
---

# SunBiz Session Handoff — 2026-06-03

> **Why this exists:** this chat started as the SunBiz **email-HTML-templates** task and then
> grew into a large **Command Center + VPS** effort spanning all three repos. This doc is the
> clean starting point so the right agent can continue without re-deriving context. Paste it
> as the first message of the continuing chat.
>
> **Repos touched:** `SunBiz-Agent` (templates, email path, drips), `CEO-Agent` (shared runtime:
> send_gateway, provision_secrets, VPS docs), `oasis-command-center` (Vercel dashboard).
> Tenant nuance: SunBiz is `tenants.slug='submissions'` with `custom_fields.command_center_profile_slug='sun'` —
> always resolve by slug OR command_center_profile_slug.

---

## 1. Email HTML templates — ✅ DONE (the original task)
- **v2 Sequence Library: 12 conversion-built templates**, redesigned to match the operator's
  reference screenshots (dark navy + gold rails, real SunBiz logo letterhead, personal letter
  format, green APPLY NOW, the Legacy-style 3-tier factor-rate qualification table, "send 3 bank
  statements" CTA). Cold sequence (T1–T5) + flagship offers + specialized plays.
- **Live:** https://cc90210.github.io/SunBiz-Agent/v2/  (served from `SunBiz-Agent/docs/v2/`).
- **Deploy fix:** Pages now ships via a GitHub Actions workflow (`.github/workflows/pages.yml`) +
  `docs/.nojekyll` — the legacy Jekyll build had been failing since 2026-05-31.
- **Commits (SunBiz-Agent):** `ffa3a97` (v2 library) → `5c76615` (.nojekyll) → `d517072` (Actions deploy) → `e6c2c3c` (full dark redesign).
- **Swap-before-send:** every Apply link points at the existing JotForm `form.jotform.com/253155026259254`
  (one find-replace per file once the Command Center form is live); factor rates/terms are illustrative
  placeholders to confirm with underwriting; footer address is a placeholder.
- **Next for templates:** send Ezra the link for feedback; nothing else pending.

## 2. Email identity bug — ✅ FIXED (was the operator's #1 issue)
Solara sent an email FROM the operator's personal Gmail because `email_blast.send_single_email` did
direct SMTP off the global `GMAIL_ADDRESS`, bypassing `send_gateway`.
- **Guard at the single SMTP chokepoint** `CEO-Agent/scripts/lib/smtp_send.py` — opt-in via
  `EMAIL_REQUIRE_FROM_DOMAIN` (set `sunbizfunding.com` on the SunBiz VPS); exact-domain match (rejects
  subdomains/look-alikes/double-@). Covers send_gateway AND the dashboard drawer (`dashboard_email_consumer`).
  Commits `6e7b7149` → `54561e67` (CEO-Agent).
- **`email_blast.py`** also guarded + honors `GMAIL_USER`; `AGENT_ROUTER.md` + `INTENTS.md` fixed so the
  agent sends via the resolvable `~/Business-Empire-Agent/scripts/integrations/send_gateway.py … --brand sunbiz`
  (kills the 15-tool-call thrash). `doctor.py` reads canonical `GMAIL_USER`. Commits `d6c957e`, `ef9f6e9` (SunBiz-Agent).
- 8/8 guard tests + `test_send_gateway` 58/59 (1 pre-existing) + Node↔Python crypto interop verified.

## 3. Credential isolation — ✅ TOOL SHIPPED, needs to run on VPS
- **`CEO-Agent/scripts/provision_secrets.py`** (`8cd36847`, tenant-resolution hardened in `4347e187`):
  pulls SunBiz's secrets from `tenant_integration_credentials` + `agent_model_config` (decrypt via
  the Node-compatible `field_encryption.py`) and writes the VPS secrets file, preserving operator-only keys.
  Model: operator gives the VPS only Supabase + GitHub; everything else flows from the Command Center.
- **Run on VPS:** `python3 scripts/provision_secrets.py --tenant sun --apply`.

## 4. Dashboard (oasis-command-center) — ✅ DONE + ⚠️ BUILD FIX
- **Settings simplified:** Setup Readiness section removed (`1f1347c`, orphan deleted `e442f07`).
- **Bridge base env-aware:** `BRIDGE_CHAT_BASE` reads `NEXT_PUBLIC_BRIDGE_CHAT_BASE` (`43acd47`).
- **Employee CLI picker:** SunBiz manifest `advanced_picker` flipped to `true` in the seed + a
  `scripts/set-manifest-flag.mjs` tool to flip the LIVE manifest (`be4bfea`). `scripts/set-member-role.mjs`
  for admin grants (`22100b7`); both fixed to resolve tenant by slug OR command_center_profile_slug (`3ce4357`).
- **⚠️ Vercel build fix (`1c6dc83`):** a whole built-but-untracked **Phase-3d cluster**
  (conversations inbox, campaigns, send-mode, lead-interactions, chat-tool-palettes + cloud-tool-runner/
  schema/sequences wiring) was committed — `main` had been un-buildable on a clean clone (committed
  `seeds.ts` imported untracked files). Verified `next build` exit 0 + `test:sunbiz` 15/15.
  *Caveat: committed on build+test verification, not a line-by-line audit of 500+ lines of prior work.*

## 5. VPS bring-up + 3 backend builds — ⏳ PENDING (build on the VPS)
The drip/outbound features are daemon logic that only runs on the VPS, so they must be built + verified
there. Two committed docs + a master prompt drive it:
- **`CEO-Agent/docs/SUNBIZ_VPS_TURNKEY_SYSTEM_MESSAGE.md`** (`e5ebe953`/`db5fb76b`) — bring-up: BRAVO_ secret
  names, `provision_secrets`, run the **repo** `ecosystem.config.js` (NOT the stale bootstrap stub — it omits
  the chat bridge + ping), pair the bridge, set `NEXT_PUBLIC_BRIDGE_CHAT_BASE` on Vercel + nginx/TLS + CORS.
- **`CEO-Agent/docs/SUNBIZ_VPS_BUILD_MISSION.md`** (`940ec179`) — code-grounded mechanics for the 3 builds:
  1. **24h-no-contact follow-up** (active deals): new `no_contact_24h_monitor.py` → `NO_CONTACT_24H` event →
     `sequence_runner` enrolls escalating SMS → ANY inbound (text/call/email) cancels the drip + reverts
     `deal_stage` to active. Uses `deal_stage` values `Application In/Missing Info/Shopping` (migration 071); no schema change.
  2. **Twilio on the signed-app bank-statement nag** — add `sms_provider` to `DripStep`, pass to
     `send_gateway.send(sms_provider='twilio')`. With TT+Twilio both set you MUST pass the provider or it defaults to TT.
  3. **Outbound blast scheduler** — FIRST add `cold_outreach_runner` to `KNOWN_AGENT_SOURCES` (else every send rejects);
     add `_promote_scheduled_campaigns` (draft→queued at `scheduled_for`); build the `/email-blast` UI; register in PM2.
- A **consolidated master prompt** combining bring-up + the 3 builds + gap closure was produced in chat
  (paste into Claude Code from `/srv/sunbiz/sunbiz-agent`); it references the two docs above.

## 6. Config actions to flip things on (operator / CC, not code)
- **Employee chat (Jordan/Alex/Emily) — they already use the full ChatWidget**, just gated off:
  1. `node scripts/set-manifest-flag.mjs --tenant sun --flag advanced_picker --value true --apply`
  2. set `NEXT_PUBLIC_BRIDGE_CHAT_BASE` on Vercel → the VPS bridge URL
  3. set a tenant-default AI key in Settings → AI Setup (else non-operators show "Provider: not connected").
- **Grant Jordan admin:** `node scripts/set-member-role.mjs --email jordan@sunbizfunding.com --role admin --tenant sun --apply`.

## 7. Open questions / latent bugs to verify
- **TextTorrent auth:** Python reads `TEXTTORRENT_API_KEY` as a Bearer token; the TS client expects
  `api_sid` + `api_public_key`. CC entered a "SID." Confirm the real scheme with TextTorrent before trusting SMS.
- **Slug-resolution latent bug:** `SunBiz-Agent/scripts/diag_manifest_drift.py` + `reconcile_sunbiz_sequences.py`
  resolve via `.eq("slug","sun")` on `tenant_manifests` — verify whether that table's `slug` is `'sun'` or
  `'submissions'`; apply the slug-OR-command_center_profile_slug resolver if they miss the row. (Diagnostic only.)
- **Guard fail-safe:** with the FROM guard, worst case is "refuses to send," never "sends as the wrong identity."

## 8. Who picks up what
- **VPS Claude Code session** (from `/srv/sunbiz/sunbiz-agent`): Section 5 — bring-up + the 3 builds. Keep
  `BRAVO_FORCE_DRY_RUN=1`; verify each; ask CC before any real send.
- **Dashboard chat / this lane:** optionally build the `/email-blast` outbound UI (the one piece verifiable
  with `next build` off the VPS).
- **CC / operator:** Section 6 config flips, enter remaining secrets in the Command Center, confirm TextTorrent auth.
- **Templates:** done — just send Ezra https://cc90210.github.io/SunBiz-Agent/v2/.

## Obsidian Links
- [[docs/INDEX]]
- [[brain/STATE]]
