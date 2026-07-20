# VPS Agent Handoff — SunBiz Production

> Created: 2026-06-01
> Updated: 2026-07-19 (CLI-backed document extraction runbook consolidated here)
>
> Audience: Claude Code, Codex CLI, or Gemini CLI running directly on
> `srv1723601`.
>
> CC should not manually execute the deployment. The agent session should
> inspect the live VPS, make the required changes, verify each stage, and ask CC
> only for secrets, browser logins, DNS changes, or approval before real
> outbound is enabled.

---

## Start Here

CC is setting up the production execution bridge for Sun Biz Funding. You are
running inside the VPS and should complete the setup end to end.

If you are running through Claude Code, Codex CLI, or Gemini CLI, the runtime is
only the terminal interface. The agent harness is `/srv/sunbiz/sunbiz-agent`.
Read its `AGENTS.md` entry point and operate as Solara unless the task explicitly
delegates you into a specialized implementation or review lane.

Before changing anything:

1. Read this file completely.
2. Read `/srv/sunbiz/sunbiz-agent/AGENTS.md`.
3. Read `/srv/sunbiz/sunbiz-agent/docs/ARCHITECTURE.md`.
4. Read `/srv/sunbiz/sunbiz-agent/docs/VPS_BRINGUP.md`.
5. Inspect the live filesystem, Git remotes, branch state, services, PM2 list,
   nginx config, and available environment-key names. Treat this handoff as
   archived context until the live checks confirm it.
6. Keep `BRAVO_FORCE_DRY_RUN=1` until CC explicitly approves live outbound.
7. Never print, read back, or paste secrets into chat. Ask CC to populate them
   interactively when needed.

Do not run destructive database commands, reset Git state, force-push, send a
real email/SMS, place a real call, or enable a production campaign without CC's
explicit approval in the same turn.

---

## Product Scope

SunBiz is the operating system for a merchant-funding shop. It is not a generic
chatbot and it is not only a webhook receiver.

The workflow is:

```text
lead intake
  -> qualification
  -> application collection
  -> underwriting
  -> lender matching and shop-out
  -> lender-response tracking
  -> offer presentation
  -> funded deal
  -> follow-up and renewal
```

There are two SunBiz agents:

- **Solara** owns funding operations: daily plan, applications, underwriting,
  lender shop-out, lender replies, offers, follow-ups, funded deals, renewals.
- **Helios** owns front-of-house sales motion: cold outreach, ghosted-deal
  revival, reply triage, discovery prompts, and sequence testing.

The operator uses the OASIS Command Center dashboard. The VPS is the always-on
execution bridge behind that dashboard.

---

## Architecture: Three Layers

| Layer | Repository | Production location | Responsibility |
|---|---|---|---|
| Dashboard | `oasis-command-center` | Vercel | Next.js operator UI and API routes |
| Shared substrate | `CEO-Agent` / `Business-Empire-Agent` | `/srv/sunbiz/ceo-agent` | Event bus, bridge polling, state, guards, shared `send_gateway.py` |
| SunBiz logic | `SunBiz-Agent` | `/srv/sunbiz/sunbiz-agent` | Funding-shop scripts, schema migrations, Solara brain and skills |

All layers use the shared OASIS Supabase project. Postgres is not hosted on this
VPS. The VPS should remain stateless compute apart from logs, cursors, PM2
process state, and local configuration.

The dashboard is expected to stay on Vercel. Do not deploy a second dashboard on
port `3000` unless CC explicitly changes that architecture decision.

---

## Why Both Backend Repos Are Cloned

`SunBiz-Agent` is the SunBiz agent harness. It must be cloned onto the VPS. It
contains Solara's instructions, funding-shop business logic, SunBiz migrations,
skills, and daemon source.

`CEO-Agent` must also be cloned onto the VPS. It is not a second SunBiz agent.
It provides the shared runtime used by the harness: bridge heartbeat and cron
polling, event router, safety guards, state tooling, secret loader, and the
single outbound `send_gateway.py`.

The required VPS checkout layout is:

```text
/srv/sunbiz/
  ceo-agent/       # shared runtime substrate
  sunbiz-agent/    # SunBiz Solara + Helios agent harness
```

The dashboard repo does not need to be cloned onto this VPS for normal
production operation because it is deployed separately on Vercel.

---

## Terminal Agent CLIs

Install all three terminal agents on the VPS so the bridge host can use the
right runtime for each job:

| CLI | Purpose on this VPS | Launch command |
|---|---|---|
| Claude Code | Primary interactive operator for setup, maintenance, and chat-bridge work | `claude` |
| Codex CLI | Backend implementation, debugging, and independent review | `codex` |
| Gemini CLI | Secondary review and fallback agent lane | `gemini` |

Install them with:

```bash
npm install -g @anthropic-ai/claude-code
npm install -g @openai/codex
npm install -g @google/gemini-cli
```

Then verify:

```bash
claude --version
codex --version
gemini --version
```

Each CLI may require a one-time login. Launch it from
`/srv/sunbiz/sunbiz-agent`, follow its authentication prompt, and complete any
browser confirmation CC is asked to perform.

Do not place provider login tokens in Git. Project runtime API keys belong only
in the protected `.env.agents` file.

---

## Business-Critical Data Flows

### Lead stage change to drip sequence

```text
dashboard stage update
  -> Supabase agent_events row
  -> sequence_runner.py notices event
  -> matches drip_sequences
  -> creates sequence_state row
  -> due message goes through CEO-Agent send_gateway.py
  -> CASL, cooldown, cap, and reservation checks run before send
```

### Application to lender shop-out

```text
dashboard queues approved lender threads
  -> application_lender_threads status=pending
  -> shop_out_sender.py claims rows atomically
  -> lender-facing email is sent
  -> status becomes sent or error
  -> lender_response_classifier.py checks Gmail threads
  -> reply classified as approved / declined / info_requested / unclear
  -> dashboard shows the updated lender state
```

### Underwriting

```text
uploaded bank statement
  -> underwriting_orchestrator.py
  -> statement parser
  -> debt detector
  -> sales-angle generator
  -> application_underwriting row
  -> dashboard underwriting view
```

### Daily operating plan

```text
scheduled bridge job
  -> daily_plan_generator.py
  -> reads pipeline state
  -> writes prioritized daily_plan_items
  -> operator sees today's calls, follow-ups, renewals, and stuck deals
```

---

## Non-Negotiable Boundaries

1. All prospect-facing outbound SMS, calls, and emails must use
   `/srv/sunbiz/ceo-agent/scripts/integrations/send_gateway.py`.
2. `shop_out_sender.py` is the narrow lender-email exception because those
   messages go to lenders, not prospects.
3. Keep tenant scoping intact. Daemons use service-role access but writes must
   remain scoped to the resolved SunBiz tenant.
4. Do not duplicate shared substrate code into `SunBiz-Agent`.
5. Do not start the empire scheduler on the VPS until you verify ownership. A
   second scheduler can fire duplicate jobs.
6. Do not start the Telegram bridge on the VPS while another machine owns the
   same bot token.
7. Do not register Kixie inbound callbacks until a live, verified Kixie webhook
   route exists. As of the local inspection on 2026-06-01, the CEO webhook
   listener exposed Stripe, n8n, and Telegram routes but no verified
   `/webhooks/kixie` handler.
8. Do not infer that the older bootstrap PM2 file is correct. Verify every path
   against the checked-out files before starting processes.

---

## Known VPS State To Verify

Expected host:

```text
hostname: srv1723601
public IPv4: 2.25.159.226
OS: Ubuntu 22.04.5 LTS
deploy root: /srv/sunbiz
```

Expected prior bootstrap work:

- UFW enabled for ports `22`, `80`, and `443`
- fail2ban and unattended upgrades installed
- Python 3.12 installed
- Node 20 and PM2 installed
- nginx installed
- repos cloned to `/srv/sunbiz/ceo-agent` and `/srv/sunbiz/sunbiz-agent`
- Python venv at `/srv/sunbiz/ceo-agent/venv`
- empty or incomplete `/srv/sunbiz/ceo-agent/.env.agents`
- an SSH key may exist under `/root/.ssh/id_ed25519`
- the bootstrap-generated PM2 config may contain stale paths

Verify all of this live. Do not assume it.

---

## Required Setup Sequence

Work through these phases yourself and report concise evidence after each one.

### Phase 1: Inspect Without Mutating

Verify:

- current user, hostname, OS, free disk, memory
- `git`, `python3.12`, `node`, `npm`, `pm2`, `nginx`, `certbot`, `claude`,
  `codex`, and `gemini`
- repo directories and Git remotes
- active branches and dirty worktrees
- service state for nginx, fail2ban, and UFW
- PM2 process list
- existing symlinks
- whether `.env.agents` exists without printing its contents

### Phase 2: Establish GitHub Access

CC may have generated `/root/.ssh/id_ed25519` and added its public key to
GitHub. Verify with:

```bash
ssh -T git@github.com
```

Then verify that both repos can fetch. Do not overwrite local changes. If SSH
ownership should move to a non-root deployment user, migrate access carefully
after confirming the existing state.

### Phase 3: Normalize Paths

The code currently contains historical path conventions. Inspect before
creating links, then make the smallest compatibility changes needed so the
runtime resolves:

```text
/srv/sunbiz/ceo-agent
/srv/sunbiz/sunbiz-agent
~/CEO-Agent
~/SunBiz-Agent
CEO-Agent venv expected as .venv by some configs, but provisioned as venv
```

Prefer compatibility symlinks over broad code rewrites during first boot.

### Phase 4: Install Dependencies

Use the existing CEO venv if healthy. Install requirements from both repos.
Confirm imports before starting PM2.

### Phase 5: Populate Secrets Interactively

Ask CC to fill `/srv/sunbiz/ceo-agent/.env.agents` directly in the VPS terminal.
Do not display its contents. Lock it to mode `600`. Make SunBiz consume the same
secret source using the repo's existing loader contract or a symlink if that is
what the live code expects.

Required groups to confirm by key name only:

- OpenAI and Anthropic API access
- shared Supabase URL, anon key, service-role key, access token, project ID
- Kixie key, business ID, and default agent email
- TextTorrent key and API URL if enabled
- Gmail address and App Password for lender shop-out and reply tracking
- Telegram notification keys only if the intended process needs them
- bridge pairing token and bridge HMAC/encryption keys where required
- sender identity and CASL business fields
- `BRAVO_FORCE_DRY_RUN=1`

Do not claim readiness just because a file exists. Run the repo doctors.

### Phase 6: Database Readiness

Run the SunBiz doctor and setup readiness gate. Determine which migrations from
`042` through `069` are already applied before applying anything. Apply only
missing migrations using the repo's canonical migration tool. Verify the tenant,
operator binding, lender catalog, drip sequences, cron jobs, and bridge state.

Never edit financial truth tables or production rows speculatively.

### Phase 7: Start Only Verified Processes

Start the smallest verified production set. The authoritative process split must
be derived from the live checked-out ecosystem files and
`sunbiz-agent/docs/DAEMON_PLAYBOOK.md`.

Expected long-running responsibilities:

| Responsibility | Expected owner |
|---|---|
| Cross-agent event tail | CEO-Agent `event-router` |
| Dashboard heartbeat and tenant cron polling | CEO-Agent bridge ping loop |
| Drip sequence execution | SunBiz `sequence_runner.py` |
| Lender reply classification | SunBiz `lender_response_classifier.py` |
| Webhook listener | verify the correct app and routes before starting |

Expected cron or on-demand SunBiz work:

- `shop_out_sender.py`
- `renewal_reminder.py`
- `follow_up_generator.py`
- `daily_plan_generator.py`
- `cold_outreach_runner.py`
- `underwriting_orchestrator.py`

Do not start duplicate cron-driven workers as standalone loops unless the live
architecture explicitly calls for that.

After PM2 is stable, persist it with `pm2 save` and configure reboot startup.

#### CLI-Backed Document Extraction

SunBiz application extraction is an asynchronous VPS responsibility. The dashboard queues a
`document_extraction_jobs` row; the CEO-Agent worker
`scripts/integrations/extraction_consumer.py` claims it, uses the locally authenticated Claude
CLI subscription, and posts the result to `/api/internal/apply-extraction` with HMAC
authentication. The metered API is break-glass fallback only.

Before starting the worker:

1. Confirm there is exactly one intended `extraction-consumer` process. Do not start a second
   consumer alongside an already healthy PM2 process.
2. Confirm the VPS `.env.agents` contains, by key name only, `BRAVO_SUPABASE_URL`, the Bravo
   service-role key, a dashboard URL (`PUBLIC_APP_URL` or `OASIS_DASHBOARD_URL`), and
   `OASIS_OUTBOUND_HMAC_SECRET`. The HMAC value must match the dashboard deployment value.
3. Confirm Claude subscription authentication. If the CLI credential is missing or expired, run
   `claude setup-token` interactively; never substitute an Anthropic API key for this path.
4. Run the worker's read-only readiness check:

   ```bash
   cd /srv/sunbiz/ceo-agent
   python scripts/integrations/extraction_consumer.py doctor
   ```

   Do not continue unless it reports Claude OAuth, HMAC configuration, dashboard URL, and
   Supabase access as ready.
5. Start and persist only the verified worker:

   ```bash
   pm2 start ecosystem.config.js --only extraction-consumer
   pm2 save
   ```

For end-to-end verification, submit one operator-approved signed PDF or photo application and
observe the job transition `queued -> processing -> extracted -> applied`. Confirm
`used_fallback = false`, inspect `pm2 logs extraction-consumer` without exposing document PII,
and verify that application fields, the branded PDF, and signature confirmation appear in the
dashboard. A worker process showing `online` is not proof of a functioning HMAC callback.

### Phase 8: Pair The Bridge

The Vercel dashboard must know this VPS is online. Follow the live bridge pairing
flow and restart the bridge ping process. Confirm the dashboard heartbeat becomes
healthy.

### Phase 9: nginx, DNS, And TLS

Expose only required routes. The dashboard itself remains on Vercel.

Before issuing a certificate:

1. Ask CC to confirm the intended hostname.
2. Confirm the DNS A record resolves to `2.25.159.226`.
3. Validate nginx with `nginx -t`.
4. Use Certbot only after DNS is correct.

### Phase 10: Smoke Test Without Live Sends

Verify:

- all intended PM2 processes remain stable without restart loops
- local health endpoint returns success
- event router consumes events
- dashboard sees the paired VPS
- doctor and setup readiness gate pass or clearly report remaining blockers
- outbound remains dry-run
- Kixie and TextTorrent credentials are detected without placing a call or SMS
- Gmail access is validated without sending a real lender email

Ask CC for explicit approval before any real end-to-end message, call, campaign,
shop-out, or DNS mutation.

---

## First Prompt For The VPS Agent Session

Paste this into Claude Code after launching it from
`/srv/sunbiz/sunbiz-agent`. The same prompt also works in Codex CLI or Gemini
CLI:

```text
Read /srv/sunbiz/ceo-agent/docs/VPS_SETUP_HANDOFF.md completely, then read this
repo's AGENTS.md, docs/ARCHITECTURE.md, docs/VPS_BRINGUP.md, and
docs/DAEMON_PLAYBOOK.md. You are running directly on the SunBiz production VPS.
Inspect the live state before changing anything. Complete the handoff end to end:
GitHub access, path normalization, dependencies, interactive secret checklist,
database readiness, selective PM2 startup, bridge pairing, nginx/TLS readiness,
and dry-run smoke tests. Keep BRAVO_FORCE_DRY_RUN=1. Do not send real outbound,
run destructive commands, expose secrets, start a duplicate scheduler, or
register Kixie callbacks without a verified handler. Ask me only when you need a
secret entered, a browser action, DNS change, or explicit approval for a live
action. Report concise evidence after each phase and keep going until the
remaining blockers require my input.
```

---

## CC's Immediate Next Step

From the VPS root terminal, pull the handoff, install the three terminal agents,
and launch Claude Code:

```bash
cd /srv/sunbiz/ceo-agent
git pull
npm install -g @anthropic-ai/claude-code
npm install -g @openai/codex
npm install -g @google/gemini-cli
cd /srv/sunbiz/sunbiz-agent
claude
```

Complete the Claude Code sign-in flow when prompted, then paste the prompt from
the previous section. Claude Code should take over the terminal work from
there. Codex CLI and Gemini CLI remain installed for delegated work and
independent review.

---

## Definition Of Done

The VPS setup is complete only when:

1. Both backend repos fetch cleanly from GitHub.
2. The selected PM2 processes survive restart and reboot startup is configured.
3. The dashboard reports the bridge as online.
4. Supabase schema and SunBiz readiness checks pass or have explicit,
   documented operator-approved exceptions.
5. Health checks pass without crash loops.
6. Secrets remain protected.
7. Real outbound remains disabled until CC deliberately approves activation.
8. Kixie inbound remains disabled until its handler is implemented and verified.
9. The single extraction consumer passes its doctor and a real-document callback test without
   metered-API fallback.
