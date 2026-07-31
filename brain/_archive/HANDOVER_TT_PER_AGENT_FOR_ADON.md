---
description: "Historical handover for the completed SunBiz per-agent Text Torrent SMS implementation"
tags: [sunbiz, sms, texttorrent, handoff, archived]
last_updated: 2026-06-24
freshness_threshold_days: 365
status: archived
archived_on: 2026-07-19
archived_from: brain/HANDOVER_TT_PER_AGENT_FOR_ADON.md
archive_reason: "Implementation handoff completed; shipped commits and remaining live checks are recorded in the session log."
superseded_by: memory/SESSION_LOG.md
---
# Handover — SunBiz Per-Agent Text Torrent SMS

**From:** Bravo (CC's agent) → **To:** APEX (Adon's agent)
**Date:** 2026-06-24 · **Repo:** `CC90210/oasis-command-center` (shared) · **Branch:** `main`
**Commits:** `d9e04c4` (feature) + `4247f51` (audit fixes) — both authored CC90210, pushed, Vercel auto-deploying.

Goal: let each SunBiz rep (Matt/owner, Jordan, Alex) send Text Torrent SMS **from their own number** off the one shared Text Torrent API key, with the right person credited on the Activity feed. Mirrors the existing Kixie per-rep pattern. Please cross-reference, debug adversarially, and push it to production quality with us.

---

## 1. The model (how it works)

- **One shared TT API key** at the tenant level (already `set` in Settings → Business app keys). It is transmissible across all reps — unchanged.
- **Per-rep sending number** is the new thing. Each rep sets their OWN number; it overrides a tenant **"Default Business Number"** (the old single `from_number`, relabeled).
- **Manual 1:1 send** (a rep clicking send) → goes out from THAT rep's number → attributed to the **human rep** (Matt/Jordan/Alex) via `actor_user_id`.
- **Automated send** (sequences / campaigns / daemon) → goes out from the **owner number (Matt)** → attributed to **Helios** (the SunBiz SMS agent) via `agent_source`.
- Attribution machinery already existed — `lib/audit/activity-feed.ts → resolveAgent()` maps `texttorrent`/`sequence`/`cold_outreach` → Helios; `actor_user_id` → the human. We did NOT change it.

### Storage (no DB migration)
- **Tenant-shared:** `tenant_integration_credentials` service `texttorrent` → `api_key` + `from_number` (now "Default Business Number" / owner fallback).
- **Per-rep:** `user_integration_credentials` service `texttorrent` field **`texttorrent_from_number`** (encrypted, AES-256-GCM, same table Kixie's per-rep number uses). No migration needed — generic KV.

### The resolver (the heart of it)
`lib/integrations/texttorrent-sender.ts` → `resolveTextTorrentSenderId({ tenantId, userId })`
Precedence ladder: **rep's own `texttorrent_from_number` → tenant `from_number` → undefined (TT account default)**. Pure precedence split into `texttorrent-sender-core.ts` (`pickTextTorrentSenderId`) and unit-tested. Soft-fails: a store error never blocks a send; it degrades to the tenant default (and now logs a warning).

---

## 2. Send-surface map (what we wired, what we didn't, and WHY)

| Surface | File | Manual or Automated | Per-rep `sender_id`? |
|---|---|---|---|
| Conversations inbox reply (defaults provider=texttorrent) | `app/api/conversations/reply/route.ts` | Manual | ✅ wired (rep's number) |
| Chat-tool TT send | `lib/cloud-tool-runner.ts` `toolTextTorrentSend` | Operator-in-loop | ✅ wired (operator's number) |
| Chat-tool TT inbox reply | `lib/cloud-tool-runner.ts` `toolTextTorrentInboxReply` | Operator-in-loop | ✅ wired |
| Lead/Applications drawer "Send SMS" | `components/leads/LeadDetailDrawer.tsx` | Manual | N/A — hardcoded **Kixie** (already per-rep via `kixie_from_number`) |
| Drawer "Text Torrent" button | `LeadDetailDrawer.tsx` `TextTorrentPicker` | Automated | sequence ENROLL → VPS daemon sends (owner + Helios) |
| TT-native bulk campaign | `app/api/campaigns/route.ts`, `toolTextTorrentBlast` | Automated | ❌ impossible — TT `/campaign/create` has NO per-send sender field; sends from the TT **account default** (owner). Documented as an invariant. |
| Cold-outreach campaign | `app/api/manifest/[slug]/cold-outreach/campaigns/route.ts` | Automated | Queues only; `cold_outreach_runner.py` (VPS) sends. |
| Inbound webhook | `app/api/webhooks/texttorrent/sms-inbound/route.ts` | (inbound) | **FIXED — see §4** |

---

## 3. Files changed (cross-reference index)

**New:**
- `lib/integrations/texttorrent-sender.ts` — server-only resolver (`resolveTextTorrentSenderId`).
- `lib/integrations/texttorrent-sender-core.ts` — pure precedence + field constant `TEXTTORRENT_FROM_NUMBER_FIELD`.
- `app/api/integrations/personal/texttorrent/route.ts` — per-rep GET/POST/DELETE (1:1 mirror of `app/api/integrations/personal/kixie/route.ts`).

**Edited:**
- `lib/tenant-integration-schemas.ts` — relabel TT `from_number` → "Default Business Number" (KEY unchanged; only label/hint).
- `components/settings/PersonalIntegrationsPanel.tsx` — self-service "Text Torrent from-number" row.
- `app/api/conversations/reply/route.ts` — pass resolved `sender_id` on the TT branch.
- `lib/cloud-tool-runner.ts` — pass `sender_id` on the 2 chat-tool TT sends + document the bulk invariant.
- `app/api/webhooks/texttorrent/sms-inbound/route.ts` — resolve inbound by per-rep DID (the fix).
- `tests/user-credential-resolver.test.ts` — precedence ladder + schema-relabel lock.

---

## 4. The one bug we caught + fixed (PLEASE don't re-break)

Enabling per-rep SENDING numbers means prospect replies come back to those per-rep DIDs. The inbound webhook (`sms-inbound/route.ts`) originally resolved the tenant ONLY by the tenant-default `from_number`, so a reply to a rep's own number matched no tenant → `ignored: no_tenant_mapping` → **silently dropped**. Fixed `resolveTenantByInboundNumber` to ALSO match `user_integration_credentials.texttorrent.texttorrent_from_number`, return the owning rep, and stamp `metadata.routed_to_user_id`.
**General rule for both of us:** any per-user outbound identity (number/email/sender) needs a matching inbound-resolution path, or replies vanish.

---

## 5. Verification done

- `tsc --noEmit` clean · `npm run test:sunbiz` **28/28 green** (incl. new precedence cases).
- **Codex adversarial review** + a **4-lens Workflow** (credential isolation / send-surface coverage / soft-fail safety / attribution) both ran against the real diff. Consensus: **code is safe** — per-rep isolation airtight, all manual send sites pass the resolved number, everything fails safe to the account default, attribution unchanged, no cross-rep leak.

---

## 6. OPEN ITEMS (where we need your eyes / the work that remains)

1. **[CONFIRM — highest priority] `sender_id` is the field TT actually reads.** `lib/integrations/texttorrent.ts → sendSms()` posts `{ number, message, sender_id }` to `/inbox/message/send`. `sender_id` is pre-existing in that client but UNVERIFIED against TT's live API (their docs are JS-rendered; we couldn't extract §5.9). **Worst case = silent no-op (sends from account default), NOT a leak.** One live non-dry-run send confirms it; if wrong, it's a one-line rename in `texttorrent.ts`. If Adon has the TT API PDF or a sub-account to test, that closes it fastest.
2. **[MEDIUM] DID ownership / spoofing.** With a shared key, TT has no per-rep number ownership, so a rep could save a teammate's number. Same posture Kixie has shipped since June; acceptable for 3 trusted reps. **Proper fix = admin-assigned numbers** (the deferred admin Team view). Open question for both teams: build admin-assignment, or accept self-service?
3. **VPS automated side (Adon's domain).** Sequences/cold-outreach send via `send_gateway.py` / `cold_outreach_runner.py` on `srv1723601`. They should send automated SMS from the **owner number + Helios**. Needs `SUNBIZ_TT_OWNER_NUMBER` (Matt's) in `/srv/sunbiz/ceo-agent/.env.agents` and a check that the daemon stamps a Helios-mapping `agent_source`.

---

## 7. Deployment & config truth (READ THIS — it's not what it looks like)

- **Per-rep numbers do NOT go in `.env.agents` or Vercel.** Each rep logs into THEIR OWN SunBiz command-center profile → **Settings → Personal integrations → "Text Torrent from-number" → type number → Save**. Stored in the DB. (Self-service because reps don't share logins.)
- **`.env.agents` (VPS `/srv/sunbiz/ceo-agent/.env.agents`) only needs MATT'S owner number** (`SUNBIZ_TT_OWNER_NUMBER`) — and only for the AUTOMATED daemon. Not all three reps.
- **Vercel env that matters:**
  - `DASHBOARD_LIVE_SEND=1` — REQUIRED to actually send. The dashboard defaults to **dry-run** (`lib/integrations/send-mode.ts`); without this flag every send is logged but NOT delivered. This is the real "go live" switch.
  - `BRAVO_FORCE_DRY_RUN=1` — hard kill-switch (forces dry-run even if live is on).
  - `TEXTTORRENT_WEBHOOK_SECRET` — required for inbound reply routing (likely already set).

---

## 8. Coordination

We both edit `oasis-command-center`. Files we touched this round are in §3 — please pull latest before editing them so we don't collide. Bravo posts status to the `agent_activity` table (the agent↔agent channel). Let's adversarially debug each other's work toward a turnkey result — flag anything you find and we'll do the same.

## Obsidian Links
- [[brain/INDEX]]
- [[brain/STATE]]
