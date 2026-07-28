---
name: resource-radar
description: Free-tier service & free-API lookup — consult the TOOL_SHED Free-Tier Radar before adding/paying for any external service; enforces closed-slot conflict rules and the keyed-adoption path
tier: tool
owner: bravo
risk: low
triggers: ["free tier", "free API", "what service for", "replace paid tool", "do we pay for", "cheaper alternative", "uptime monitoring", "error tracking", "need a service"]
tags: [free-tier, radar, catalog, cost-reduction, integrations]
status: '[NEW]'
created_at: 2026-07-17T21:35:26.083403+00:00
last_updated: 2026-07-17
---

# Resource Radar

> Before adding, paying for, or recommending ANY external service or API: consult the Free-Tier Radar. It already knows what's free, what's a real gap, and which slots are closed.

## When to use

- A task surfaces a capability need with no current tool ("we need uptime monitoring", "is there an API for X?").
- CC asks about cost ("do we pay for this?", "is there a cheaper/free alternative?").
- You're about to recommend signing up for a new external service — check the Radar FIRST so you don't duplicate a closed slot or re-derive a decision already made.

## How it works

1. **Consult the catalog:** read `brain/TOOL_SHED.md` § "Section 9: Free-Tier Radar" (or query it: `python scripts/capability_query.py resolve "<need>" --kind resource`). A matching row gives you the service, free-tier limit, auth model, status, and any conflict — answer from it, don't re-research.
2. **Enforce the closed slots (hard rules, from the 2026-07-17 services audit):** DNS=Cloudflare · hosting=Vercel+Hostinger · DB=Supabase · payments=Stripe · SMS=TextTorrent/Twilio/Kixie (never a 4th) · email=send_gateway→Gmail ONLY (Resend/SendGrid/SES/Mailgun banned) · scraping=Firecrawl/Playwright/bs4 · TTS=ElevenLabs · vector=LanceDB · CI=GitHub Actions. Consolidation beats addition — never propose a new provider for a covered slot.
3. **Not cataloged? Fetch upstream on demand** (never mirror): `python scripts/research_fetch.py "https://raw.githubusercontent.com/ripienaar/free-for-dev/master/README.md"` (jump to the relevant `##` category) or the public-apis raw README. Spot-check any row live before trusting it (upstream curation has slowed; api.publicapis.org is dead).
4. **Present the candidate** with: free-tier limit, auth model, what it replaces/conflicts with, and the adoption path. Then add/update its Radar row (status `candidate`) so the next lookup starts warmer.
5. **Adoption path for keyed services (operator-gated):** Radar row → `docs/ENV_KEYS_TEMPLATE.md` entry → **CC signs up and hand-adds the key to `.env.agents`** (agents never handle keys) → `scripts/integrations/<name>_tool.py` wrapper via `lib.secret_loader` (copy `stripe_tool.py` shape: subcommand verbs, shared `--json` parent parser, `@retry`) → `integration_health.ping('<service>')` → SEED_JOBS health row if it's a live dependency. No-auth APIs skip the key steps but still get the wrapper + Radar row (see `scripts/integrations/email_validate_tool.py`).

## Degradation (ADR-0001: all dependencies SOFT)

- Radar section missing → fall back to live upstream fetch (step 3).
- Offline → answer from the catalog only, flag staleness.
- Graph has no `resource:` nodes → read the TOOL_SHED table directly.

## Tools used

- `scripts/capability_query.py` — `resolve "<need>" --kind resource` against the graph's `resource:` nodes
- `scripts/research_fetch.py` — on-demand upstream fetch (auto-escalating ladder)
- `scripts/integrations/email_validate_tool.py` — the reference no-auth adoption (Disify)

## Related skills

- [[skills/research-fetch/SKILL]] — the fetch ladder this skill uses for upstream lookups
- [[skills/security-protocol/SKILL]] — key handling rules the adoption path must obey
- [[brain/TOOL_SHED]] — the catalog this skill fronts
