# SunBiz Cloud Portal Architecture

Date: 2026-05-13
Status: production planning

## Decision

SunBiz should launch as a cloud-first client portal with a dedicated SunBiz agent API behind it. The Command Center is the control plane. The SunBiz API/worker is the execution plane. The client data store is the data plane.

Do not run the production client portal by SSH-ing into a server and driving a CLI from the web app. A CLI can stay available for admin/debug work, but the dashboard should call authenticated HTTPS APIs and durable background jobs.

## Recommended Shape

1. `apps/command-center` stays on Vercel as the shared multi-tenant dashboard.
2. SunBiz gets a dedicated profile/manifest that controls copy, navigation, enabled agents, and integration labels.
3. `SunBiz-Agent` runs as a hosted service on a VPS or app platform.
4. The hosted service exposes a small API contract:
   - `GET /health`
   - `GET /integrations/status`
   - `POST /forms/jotform`
   - `POST /lead/intake`
   - `POST /sms/send`
   - `POST /agent/run`
   - `POST /documents/search`
5. Command Center calls that API with server-side credentials only.
6. Provider credentials for JotForm, Text Torrent/Twilio, Gmail, OpenRouter, Anthropic, OpenAI, or Gemini are stored server-side and encrypted at rest.
7. Client browser sessions never receive raw provider keys.

## Hostinger Guidance

Hostinger is acceptable only if it is a real VPS/container environment with:

- HTTPS termination through Caddy, Nginx, or a managed proxy.
- A process manager such as systemd, PM2, or Docker Compose.
- Health checks and restart policy.
- Environment-secret storage outside git.
- Log rotation.
- Firewall rules that expose only required ports.

Shared web hosting is not the right fit for an always-on agent runtime.

## CLI vs API

Use an API for production execution. Use the CLI for operator/admin work.

The Command Center should not depend on an interactive shell session, local terminal state, or human-run commands. It should send explicit API requests, receive structured responses, and show status in the UI.

## Desktop Boundary

The desktop app is for local-machine permissions: approved files, local tools, browser actions, local providers, and offline-adjacent workflows.

The SunBiz client portal does not need desktop mode for the normal hosted workflow. It should work through cloud APIs first. Add desktop only when the client specifically needs local computer access.

## Provider Modes

The client-facing setup should present two clean options:

- Account connection: OAuth/subscription style provider login where available.
- API key: paste a key from OpenRouter, Anthropic, OpenAI, Gemini, or another supported provider.

Both modes should feed the same agent runtime contract. The difference is how credentials are obtained and billed, not what the agent can do.

## Production Checklist

- Public SunBiz demo route uses demo data only.
- Real SunBiz account provisioning sets `command_center_profile_slug = "sun"`.
- Real profile sets `primary_agent = "sunbiz"`.
- SunBiz API has HMAC or signed bearer authentication between Vercel and the hosted runtime.
- JotForm webhooks are signature-checked.
- Text Torrent/Twilio actions are rate-limited and audited.
- Provider keys are encrypted and never sent to the browser.
- Agent runs have trace IDs, logs, status, and retry behavior.
- Pulse checks report integration health back to Command Center.
- Demo, staging, and production credentials are separated.

## Next Build Order

1. Finalize public SunBiz review portal.
2. Stand up SunBiz API staging runtime.
3. Add Command Center server routes that proxy to the SunBiz API.
4. Add integration status cards backed by the API.
5. Add provider setup UI for OAuth/API-key modes.
6. Run a full fake-lead JotForm to Text Torrent to dashboard acceptance test.
