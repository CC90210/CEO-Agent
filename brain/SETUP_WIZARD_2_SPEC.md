---
title: Setup Wizard 2.0 — Spec
date: 2026-05-15
phase: 8 (of SunBiz CRM build)
status: SPEC — implementation deferred to after SunBiz beta
last_updated: 2026-06-09
freshness_threshold_days: 90
verified: 2026-06-09
---
# Setup Wizard 2.0

## Context

CC's framing on 2026-05-15 about the existing onboarding flow:

> "Someone finds Oasis AI on the internet and wants to download it
> themselves, so they use the setup wizard. The setup wizard builds
> them whatever computer they are downloading it on, whether it is a
> local computer or a hosting service like Hostinger. The setup
> wizard then scaffolds and forks and copies the repo we built for
> that specific use case. They fill out a bunch of credentials and
> questions to personalize the system. The setup wizard should also
> connect them to the agent command center."
>
> "In a sense, these CLI and API differences are pretty irrelevant if
> one of them just works correctly. We need to rethink how this
> process and user flow are presented."

Today's onboarding (Phase 1) creates a tenant **manifest** only. The
end-to-end "from URL to working dashboard" experience is not in one
place — bridge install, credentials, hosting choice, chat-mode picker
are scattered across separate surfaces operators have to discover.

## What Setup Wizard 2.0 ships

A single linear wizard at `/install` (NOT `/onboarding/wizard` — that
URL stays as the manifest-only flow for tenants that already exist in
the OASIS SaaS plan). The new wizard answers:

1. **Where does this install run?**
   - **Hosted by OASIS** (default — uses CC's Supabase + the shared
     SaaS dashboard). Lowest friction, no operator infrastructure.
   - **Local install** (operator's laptop / desktop) — PM2 stack on
     their machine; OASIS hosts the dashboard but the bridge runs
     locally.
   - **Self-hosted** (Hostinger / Railway / Coolify / VPS) — full
     stack on operator infrastructure with optional Turso for data
     sovereignty.

2. **What's the agent's purpose?**
   - Pick from industry templates (existing): real_estate,
     business_funding, ecommerce, agency, custom.
   - Or "Fork an existing client agent" — scaffolds a per-client repo
     from `templates/agent-scaffold/` baked with the picked agent's
     prompts + manifest.

3. **What credentials do you have?**
   - Required: Anthropic API key.
   - Optional (per industry): Stripe, Twilio, TextTorrent, Kixie,
     Gmail OAuth, Supabase key (if self-hosted), Turso key (if
     self-hosted with data sovereignty).
   - The wizard encrypts each via `BRAVO_FIELD_ENCRYPTION_KEY` and
     stores in `agent_model_config` keyed by (tenant, agent).

4. **Brand the shell** (existing — name, logo, footer).

5. **Pair this machine** — the wizard mints a bridge pair code and
   runs the curl one-liner OVER SSH (when hosted) or shows the local
   one-liner to copy-paste. No separate "now go to Settings → Devices"
   step; the wizard owns the full handoff.

## What it doesn't do

- **Mode picker** is hidden by default (`ui.advanced_picker: false`).
  Auto-mode handles CLI vs API silently. Only OASIS HQ flips the
  flag.
- **CLI subscription auth** is opt-in via a "use my Claude subscription
  to save API costs" checkbox in step 3. Default off so first-time
  operators don't get the OAuth dance until they explicitly want it.

## Architecture pieces to build

| Piece | File | Notes |
|---|---|---|
| Hosting target picker | `/install/page.tsx` step 1 | Three radio cards |
| Client repo fork | `skills/agent-forge/SKILL.md` extension | Generate `templates/agent-scaffold/` with baked manifest |
| Hosting deploy scripts | `infra/deploy/{hostinger,railway,vercel}.sh` | One-touch deploy per target |
| Credentials questionnaire | `/install/page.tsx` step 3 | Per-integration form rendering from `KNOWN_INTEGRATIONS` |
| Encrypted credentials store | `lib/credentials/store.ts` | Wraps `lib/field-encryption.ts`; routes through `agent_model_config` table |
| Auto-pair on completion | `/install/page.tsx` step 5 + `/api/install/pair` | Mints + runs the bridge curl one-liner over the chosen hosting target's SSH |

## Why deferred

This is ~2 weeks of CC+Bravo time and the highest-value moments come
from Phases 5/6/7 actually being USED. CC needs SunBiz beta operators
to break the existing UX in specific ways before we commit to a wizard
2.0 design. Three weeks of beta data + a follow-up meeting decides:
- Which industries actually self-serve vs need done-for-you?
- Which credentials does an operator have at signup time vs needs to
  collect later?
- Is "fork the repo" actually wanted, or is hosted-SaaS the dominant
  path?

## What's already in place toward 2.0

- `ui.advanced_picker` manifest flag exists (Phase 1)
- Install bridge wizard at `/settings/devices/install` (Phase 1 added
  the PM2 persistence step)
- Onboarding wizard "done" step links to bridge install (Phase 1)
- `agent_model_config` table + encryption (pre-Phase-1)
- 8 PM2 daemons in `ecosystem.config.js` for the local-install path
- `infra/docker-compose.yml` Hetzner deploy for the self-hosted path

## What changes if SunBiz beta says "hosted SaaS is dominant"

Wizard 2.0 collapses to:
1. Sign up (Supabase auth — exists today)
2. Industry picker + brand (current `/onboarding/wizard` — minor copy
   polish)
3. Credentials (NEW form, ~20 min to build)
4. Connect a machine? (Optional — link to `/settings/devices/install`)

That's ~3 days, not 2 weeks. Worth waiting for the data.

---

**Implementation owner:** Bravo
**Next action:** SunBiz beta runs Phases 1-7 for ~3 weeks. Reconvene
2026-06-05 with operator feedback. Decide between full 2.0 vs the
collapsed version above.
