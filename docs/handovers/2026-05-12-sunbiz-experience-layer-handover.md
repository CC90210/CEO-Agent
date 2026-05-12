# SunBiz Experience Layer Handover

Date: 2026-05-12
Primary repo: `Business-Empire-Agent`
Related repo: `SunBiz-Agent`
Authoring agent: Codex

## Objective

Finish the Sun Biz "experience layer" so the client sees a polished digital-employee onboarding instead of raw infrastructure:

- Solara framed as the primary digital employee
- plain-English credential handoff for JotForm and Text Torrent
- first post-pairing landing page is `Welcome to your Command Center`
- Playbook foregrounds a client-facing `Unified Onboarding Manual`
- chat proactively greets the operator as Solara
- client-facing UI avoids raw backend jargon like `Turso`, `Dispatch`, and `Substrate`
- same framing synced into `SunBiz-Agent`

## Final shipped commits

`Business-Empire-Agent`

- branch: `main`
- commit: `b8089373a1b2803c68a5b1d34ea3456217e43a7b`
- pushed to: `https://github.com/CC90210/CEO-Agent`

`SunBiz-Agent`

- branch: `main`
- commit: `867d06622763f5446964b088eedf42971492d1a5`
- pushed to: `https://github.com/CC90210/SunBiz-Agent`

## Production access

Stable public URL:

- `https://agent-dashboard-cc90210.vercel.app`

Verified on 2026-05-12:

- root responds with `307 -> /welcome`
- latest production deployment was `Ready`
- Vercel deployment URL for the pushed `main` build at verification time:
  - `https://agent-dashboard-p7xbfwrrl-cc90210.vercel.app`

Recommended first-time client account URL for Sun Biz:

- `https://agent-dashboard-cc90210.vercel.app/signup?brand=Sun%20Biz%20Funding`

Why this matters:

- I patched Google signup so the `brand` query param survives OAuth callback provisioning.
- Without that hint, a first-time Google signup could provision as generic OASIS instead of the Sun shell.

## What changed in Business-Empire-Agent

### 1. Wizard and pairing flow

Files:

- `bravo_cli/wizard.py`
- `bravo_cli/local_bridge.py`
- `bravo_cli/bridge_chat_server.py`

Behavior:

- Sun Biz setup is framed around onboarding Solara as a digital employee.
- JotForm and Text Torrent show up as plain-English integration steps.
- Local data setup is described as Solara's Local Brain.
- Sun Biz launch checks and pulse-check messaging were added.
- Bridge integration health now recognizes JotForm and Text Torrent.

### 2. Sun Biz landing experience

Files:

- `apps/command-center/app/page.tsx`
- `apps/command-center/components/sunbiz/SunBizDashboard.tsx`
- `apps/command-center/components/Sidebar.tsx`
- `apps/command-center/lib/client-profiles.ts`

Behavior:

- Sun tenants render a dedicated home experience.
- Hero headline is `Welcome to your Command Center`.
- The top of the page positions Solara as the operator's digital employee.
- JotForm, Text Torrent, Local Brain, and Automation status are surfaced in plain English.
- Sun and Suga brand marks were tightened up in the sidebar.

### 3. Playbook handoff

Files:

- `apps/command-center/app/playbook/page.tsx`
- `apps/command-center/lib/playbooks.ts`
- `apps/command-center/content/playbooks/INDEX.md`
- `apps/command-center/content/playbooks/01-getting-started.md`
- `apps/command-center/content/playbooks/02-safe-interaction.md`
- `apps/command-center/content/playbooks/03-when-to-call-cc.md`
- `apps/command-center/content/playbooks/04-pause-and-rollback.md`

Behavior:

- Sun tenants now get a client-facing Playbook index instead of the generic operator-heavy view.
- `Unified Onboarding Manual` is the primary content surface.
- Manual content is plain-English and written for the client, not the internal team.
- Audience detection for playbooks now respects explicit `Audience:` metadata.

### 4. Agent chat handoff

Files:

- `apps/command-center/components/ChatWidget.tsx`
- `apps/command-center/app/agent/page.tsx`
- `apps/command-center/lib/agents.ts`

Behavior:

- Chat widget can seed agent-specific welcome messages.
- Sun Biz agent page now injects a Solara opener.
- If JotForm is healthy, the greeting says:
  - `Hello <name>, I'm Solara. I've successfully connected to your JotForm and I'm ready to begin processing your funding pipeline.`

### 5. Integrations and supporting pages

Files:

- `apps/command-center/app/integrations/page.tsx`
- `apps/command-center/app/leads/page.tsx`
- `apps/command-center/app/renewals/page.tsx`
- `apps/command-center/lib/integrations-registry.ts`

Behavior:

- Sun tenants see a narrower, client-relevant integrations view.
- Integration labels surface `JotForm`, `Text Torrent`, and `Local Brain`.
- Demo/supporting copy on leads and renewals now references Solara's workflow in plain English.

### 6. Signup path hardening for first-time Google users

Files:

- `apps/command-center/app/signup/page.tsx`
- `apps/command-center/app/auth/callback/route.ts`

Behavior:

- `/signup?brand=Sun%20Biz%20Funding` now pre-seeds the brand field.
- Clicking `Sign up with Google` preserves that brand through the OAuth callback.
- The callback now honors `brand` and `full_name` hints from the redirect URL when provisioning the tenant/profile.

This is the main production hardening change needed for a clean first-time Sun Biz account creation flow.

## What changed in SunBiz-Agent

Files:

- `README.md`
- `dashboard/INTEGRATION.md`
- `dashboard/tenant.manifest.json`
- `docs/DUAL_AGENT_STACK.md`
- `docs/UNIFIED_ONBOARDING_MANUAL.md`
- `scripts/setup.py`
- `scripts/doctor.py`

Behavior:

- Repo docs now mirror the digital-employee framing.
- Dashboard contract explicitly expects:
  - `Welcome to your Command Center`
  - `Unified Onboarding Manual`
  - `Local Brain` language
  - Solara as primary digital employee
- Repo-local setup and doctor copy are more client-friendly.

## Verification completed

### Business-Empire-Agent

Commands run:

- `python -m py_compile bravo_cli/wizard.py bravo_cli/local_bridge.py bravo_cli/bridge_chat_server.py`
- `npm run build` from `apps/command-center`
- `npm run typecheck` from `apps/command-center`
- `npx vercel ls`
- `npx vercel alias ls`
- `curl.exe -I https://agent-dashboard-cc90210.vercel.app`
- Playwright public-page smoke on `https://agent-dashboard-cc90210.vercel.app/signup?brand=Sun%20Biz%20Funding`

Results:

- Python compile passed.
- Next.js build passed.
- Typecheck passed.
- Latest production deployment was `Ready`.
- Stable public URL redirects to `/welcome` as expected.
- Public Sun Biz signup URL resolves successfully and the `Brand or company name` field pre-fills as `Sun Biz Funding`.

### SunBiz-Agent

Commands run:

- `python -m py_compile scripts/setup.py scripts/doctor.py`
- JSON parse check for `dashboard/tenant.manifest.json`
- `python scripts/doctor.py --json`

Results:

- Python compile passed.
- Manifest JSON passed.
- Doctor runs successfully.
- Doctor reports `UNHEALTHY` on a fresh clone only because live `.env.agents` credentials are not present yet:
  - Twilio / Text Torrent
  - Gmail
  - JotForm
  - `SUNBIZ_AGENT_HMAC_SECRET`

That is a credential state issue, not a code issue.

## What still needs live operator action

These are the remaining real-world steps before a client can use the full flow:

1. Client creates their dashboard account.
2. Client signs in with Google.
3. Their local machine is paired to the dashboard via the bridge install flow.
4. Live credentials are pasted for:
   - JotForm
   - Text Torrent
   - email
5. Pulse checks are run against those live credentials.

## Recommended first-time launch flow

### Path A — simplest first-time client signup

Use this exact URL:

- `https://agent-dashboard-cc90210.vercel.app/signup?brand=Sun%20Biz%20Funding`

Then:

1. Client clicks `Sign up with Google`.
2. OAuth callback provisions their tenant/profile.
3. Because the brand hint is `Sun Biz Funding`, provisioning should assign the Sun shell and `sunbiz` primary agent.
4. Client is redirected into onboarding.
5. Onboarding saves provider + primary agent and can open the bridge install modal.

### Path B — wizard-led account pre-provisioning

If the installer or operator wants to create the account before the client signs in:

- `install/bootstrap.py` supports `/api/auth/provision-cli`
- `prefer_oauth=true` creates the auth user without sending a password invite
- the user can then sign in with Google afterward

This path is useful when the machine install happens first and the dashboard account should already exist.

## Exact pages another agent should verify

### Public / auth

- `/welcome`
- `/signup?brand=Sun%20Biz%20Funding`
- `/login`
- OAuth callback provisioning path in `app/auth/callback/route.ts`

### Signed-in Sun shell

- `/`
  - expect `Welcome to your Command Center`
- `/playbook`
  - expect `Unified Onboarding Manual`
- `/agent`
  - expect Solara greeting
- `/integrations`
  - expect `JotForm`, `Text Torrent`, `Local Brain`
- `/onboarding`
  - pairing status and install bridge modal
- `/settings/devices`
  - mint pair code and install bridge

## Browser verification status

What was verified:

- local build/typecheck and route wiring
- production deployment readiness
- stable URL behavior

What was not fully completed:

- a final signed-in browser walkthrough under a real Sun client account

Why:

- Chrome attach was unreliable during the prior session
- unauthenticated demo checks were blocked by the normal auth gate
- no real Sun client account existed yet during the session

So the remaining verification step is a real operator acceptance pass after account creation and bridge pairing.

## Suggested acceptance checklist for the next agent

1. Create a fresh Sun Biz account via:
   - `https://agent-dashboard-cc90210.vercel.app/signup?brand=Sun%20Biz%20Funding`
2. Sign in with Google using the client's real email.
3. Confirm in Supabase or app behavior that:
   - tenant `custom_fields.command_center_profile_slug = "sun"`
   - profile `primary_agent = "sunbiz"`
   - profile `agents_enabled` includes `sunbiz` and `suga_sean`
4. Complete `/onboarding`.
5. Pair the machine from `/settings/devices`.
6. Confirm bridge shows up in `/api/devices`.
7. Paste live credentials for:
   - JotForm
   - Text Torrent
   - email
8. Re-check:
   - `/` headline
   - `/playbook` manual
   - `/agent` greeting
   - `/integrations` status
9. Run a final pulse check and capture screenshots.

## Current local repo notes

At the time this handover was written:

- `Business-Empire-Agent` had a local `brain/STATE.md` modification from required `state_sync.py` logging.
- Product code changes were already committed and pushed before this handover work.

If another agent sees `brain/STATE.md` dirty, treat that as state logging, not an unshipped product diff.
