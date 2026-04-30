# OASIS Inbound Poller — VPS Deployment

24/7 inbound classification on Hetzner. Replaces the local-machine cron that only ran when CC's laptop was on.

## What it does

Every 5 minutes:
1. Connects to Gmail IMAP using `GMAIL_USER` / `GMAIL_APP_PASSWORD`
2. Fetches unread messages
3. Classifies each via `inbound_classifier.py` (Claude Haiku)
4. Writes to `lead_interactions` via the `record_inbound_from_n8n` RPC
5. Pings `integrations_health` so the Command Center green dot stays live
6. Marks the message as read

## Why it's separate from the dashboard

- Dashboard runs on Vercel serverless — no persistent process model
- Poller needs a long-lived loop with consistent IMAP connection
- Hetzner Germany VPS is the cheapest reliable option (€6.90/mo) per `docs/V6_ARCHITECTURE.md`
- Domain isolation: poller can run even if Vercel deploy is broken

## Deployment (one-time, ~15 min)

### Prerequisites
- Hetzner Cloud account ([https://www.hetzner.com/cloud](https://www.hetzner.com/cloud))
- SSH key uploaded
- Domain DNS — not required (poller only outbound; no inbound HTTPS)

### Provision the VPS

```bash
# From your laptop, with hcloud CLI installed:
hcloud server create \
    --name oasis-inbound-poller \
    --type cx22 \
    --image debian-12 \
    --ssh-key your-key-name \
    --location nbg1
```

### Bootstrap the host

```bash
ssh root@<vps-ip>
apt update && apt upgrade -y
apt install -y docker.io docker-compose-plugin git
systemctl enable --now docker
```

### Pull repo + secrets

```bash
git clone https://github.com/CC90210/CEO-Agent.git /opt/oasis
cd /opt/oasis

# Copy your .env.agents to the VPS (do this securely; don't commit)
# From your laptop:
#   scp .env.agents root@<vps-ip>:/opt/oasis/.env.agents
```

### Start the poller

```bash
cd /opt/oasis/infra/inbound-poller
docker compose up -d --build
docker compose logs -f
```

### Verify it's working

Within 5 minutes:
- `docker compose logs` should show `email_engine.py check-inbox` running
- The Command Center → Settings → Integrations should show `n8n_inbound: healthy`
- The `last_ping_at` should refresh every 5 minutes

### Update the deployment

```bash
ssh root@<vps-ip>
cd /opt/oasis
git pull
cd infra/inbound-poller
docker compose up -d --build
```

## Environment variables required

The container reads from `.env.agents` (mounted via `env_file`). Required keys:

| Key | Purpose |
|---|---|
| `BRAVO_SUPABASE_URL` | Supabase project URL |
| `BRAVO_SUPABASE_SERVICE_ROLE_KEY` | Service role key for RPC writes |
| `GMAIL_USER` (or `GMAIL_ADDRESS`) | OASIS Gmail address |
| `GMAIL_APP_PASSWORD` | Gmail app password (2FA) |
| `ANTHROPIC_API_KEY` | For inbound_classifier (Claude Haiku) |
| `OPERATOR_EMAIL` | Defaults to `conaugh@oasisai.work` |

## Migration from local machine

Once the VPS poller is verified healthy:

1. Stop the local scheduler: `pm2 stop bravo-scheduler` (Windows machine)
2. Remove the `Email Inbox Monitor` cron from `scheduler.py` (already disabled per `memory/ACTIVE_TASKS.md`)
3. Confirm Settings → Integrations shows `n8n_inbound: healthy` with a fresh timestamp from the VPS

The local Python code remains as a fallback for development testing — running both is harmless (idempotent via Gmail's UID tracking).

## Cost

- Hetzner cx22 VPS: **€6.90/mo**
- Bandwidth: included (20 TB/mo)
- Total: **~$8 USD/mo**

## Monitoring

Container logs go to journald via Docker's json-file driver. To stream:

```bash
docker compose logs -f --tail 100
```

Container restarts on crash. To check uptime:

```bash
docker compose ps
```

For deeper telemetry, pipe `integrations_health.last_ping_at` to a Grafana panel or Telegram alert (future).

## Security

- VPS firewall: deny all inbound except SSH (UFW recommended)
- No public HTTP exposure
- Secrets never in image; `.env.agents` mounted at runtime
- Docker logs rotated (10 MB × 5 files)

## Troubleshooting

| Symptom | Check |
|---|---|
| Logs show `IMAP login failed` | Rotate `GMAIL_APP_PASSWORD` |
| `integrations_health.n8n_inbound` stuck on old timestamp | `docker compose ps` — container may have crashed |
| RPC errors | `BRAVO_SUPABASE_*` env vars correct? Service role key still valid? |
| Container won't start | `docker compose logs` — usually missing env var |
