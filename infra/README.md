---
tags: [infra]
last_updated: 2026-05-21
---

# Bravo V6.0 — Infra Runbook

> Deployment, operation, and recovery instructions for the Bravo production VPS.
> Everything in this folder ships the V6.0 headless autonomy described in
> [[docs/V6_ARCHITECTURE]] §Q3. **Nothing here is active yet — this folder is
> the shippable plan, not a live deploy.**

---

## 0. What this stack does

Runs 5 long-lived Python daemons in containers on one VPS:

| Container | Command | Role |
|---|---|---|
| `bravo-core` | `python scripts/autonomous_agent.py daemon` | The reasoning loop |
| `bravo-scheduler` | `python scripts/scheduler.py` | Cron-like recurring jobs |
| `bravo-inbox` | `python scripts/integrations/email_engine.py check-inbox --daemon` | Gmail polling |
| `bravo-webhook` | `uvicorn hooks.webhook_listener:app …` (working_dir=/app/scripts) | Stripe/N8N/Telegram webhooks |
| `bravo-event-reaper` | `scripts/core/event_bus.py reap` + `drain` loop | Unsticks stuck events |

Plus two infra containers:

| Container | Image | Role |
|---|---|---|
| `pgbouncer` | `edoburu/pgbouncer:1.23.1` | Pool Supabase connections |
| `caddy` | `caddy:2.8-alpine` | TLS + reverse proxy |

---

## 1. Before first deploy

### 1.1 Pick a VPS

Recommended: **Hetzner CX32** (Falkenstein, €6.90/mo, 4 vCPU / 8 GB RAM / 80 GB SSD).
Alternatives: OVH Beauharnois (Canadian data residency), DigitalOcean Premium AMD.

### 1.2 VPS hardening (run once, as root)

```bash
# 1. Non-root user
adduser --disabled-password --gecos "" bravo
usermod -aG sudo bravo
mkdir -p /home/bravo/.ssh
cp /root/.ssh/authorized_keys /home/bravo/.ssh/
chown -R bravo:bravo /home/bravo/.ssh
chmod 700 /home/bravo/.ssh
chmod 600 /home/bravo/.ssh/authorized_keys

# 2. SSH: key-only, no root
sed -i 's/#\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh

# 3. UFW firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # consider restricting to Tailscale IPs only
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# 4. fail2ban
apt install -y fail2ban
systemctl enable --now fail2ban

# 5. Unattended upgrades
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades

# 6. Docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker bravo

# 7. Tailscale (recommended — public SSH can then be closed)
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up --ssh
# After this step: ufw delete allow 22/tcp   # (only if Tailscale works)
```

### 1.3 Clone + env

```bash
# as `bravo` user
cd /srv
git clone git@github.com:CC90210/Business-Empire-Agent.git bravo
cd bravo

# Copy .env.agents (manually — do NOT commit)
scp your-local:.env.agents ./.env.agents
chmod 600 .env.agents
```

`.env.agents` needs (plus everything Bravo already uses):

```
OPS_DOMAIN=ops.oasisai.work
CADDY_ACME_EMAIL=Konamak@icloud.com
PGBOUNCER_DB_HOST=db.<ref>.supabase.co
PGBOUNCER_DB_NAME=postgres
PGBOUNCER_DB_USER=postgres
PGBOUNCER_DB_PASSWORD=<from Supabase settings>
```

### 1.4 DNS

Point `ops.oasisai.work` A record at the VPS IP. Caddy will issue a TLS cert
on first request (may take 30-90s).

---

## 2. First deploy

### 2.1 Pre-deploy gate (V6.8.3 — required)

Before touching production, the gate must pass on the build host:

```bash
# All-in-one verification (tests + compile + health + security + entry-point
# consistency + docker config + env vars + bridge manifest)
python scripts/deploy/verify_deploy.py
# → exit 0 = SAFE_TO_DEPLOY
# → exit 2 = DEPLOY_WITH_CAUTION (warnings; review)
# → exit 1 = DO_NOT_DEPLOY (critical fail; fix first)

# Quick gate (critical checks only, ~15s)
python scripts/deploy/verify_deploy.py --quick

# Belt-and-braces health snapshot
python scripts/state/health_aggregator.py

# Take a state backup BEFORE you flip
python scripts/state/backup_db.py backup --keep 7
```

### 2.2 Compose up

```bash
cd /srv/bravo
docker compose -f infra/docker-compose.yml --env-file .env.agents up -d --build
docker compose logs -f bravo-core   # watch the brain loop come up
```

### 2.3 Verify the deploy

```bash
# Public health (Caddy → bravo-webhook /healthz)
curl -fsS https://ops.oasisai.work/healthz
# → ok

# State-API local health (the V6.8.3 enriched endpoint with sub-checks)
curl -fsS http://localhost:8500/health | python -m json.tool
# → {"status": "healthy", "checks": {"database": {"status": "ok", ...}, ...}}

# Container status
docker compose ps
# → all services "running (healthy)"

# Re-run the aggregator against the live system
python scripts/state/health_aggregator.py
# → Overall: HEALTHY
```

---

## 3. Continuous deploy

Once the initial stack is up, push to `main` triggers `.github/workflows/deploy-vps.yml`:
tests run → SSH pulls + rebuilds → smoke test → Telegram notify.

Required GitHub secrets: `VPS_HOST`, `VPS_USER`, `VPS_SSH_PRIVATE_KEY`,
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

---

## 4. Common operations

```bash
# Tail all logs
docker compose logs -f --tail=100

# Restart one service
docker compose restart bravo-webhook

# Apply a Supabase migration from the VPS
docker compose exec bravo-core python scripts/apply_migration.py database/014_v6_pgvector_memory.sql

# Full ingest (V6 RAG)
docker compose exec bravo-core python scripts/core/memory_ingest.py

# Event bus stats
docker compose exec bravo-core python scripts/core/event_bus.py stats

# Reap stuck events manually
docker compose exec bravo-core python scripts/core/event_bus.py reap
```

---

## 4.1 V6.8.3 production-hardening tools

| Need | Command |
|---|---|
| Backup all state DBs (cron-compatible) | `python scripts/state/backup_db.py backup --keep 7` |
| Restore from a specific backup | `python scripts/state/backup_db.py restore --file <name>` |
| Verify a backup file's integrity | `python scripts/state/backup_db.py verify --file <name>` |
| Aggregate health across 10 subsystems | `python scripts/state/health_aggregator.py` |
| Pre-deploy gate (full) | `python scripts/deploy/verify_deploy.py` |
| Pre-deploy gate (quick) | `python scripts/deploy/verify_deploy.py --quick` |
| Run full security audit | `python scripts/security_audit.py scan` |
| Single security scan | `python scripts/security_audit.py {secrets,injection,perms,evals,traversal,deps,guards}` |
| Parse logs → suggest MISTAKES.md entries | `python scripts/core/error_knowledge_pipeline.py suggest` |
| Generate CHANGELOG draft from git log | `python scripts/generate_changelog.py` |

The nightly cron `state_backup` (registered in `cron_engine.SEED_JOBS`) runs
03:00 daily; backups go to `state/backups/` (gitignored).

---

## 5. Rollback

```bash
cd /srv/bravo
git log --oneline -n 10           # find last known-good SHA
git reset --hard <sha>
docker compose -f infra/docker-compose.yml --env-file .env.agents up -d --build
```

The GitHub Actions workflow captures PRIOR_SHA in its deploy step — grab it
from the Actions run log if you need to revert the previous release.

---

## 6. What's NOT on the VPS (intentional)

- **Claude model weights** — LLM calls go out to Anthropic API. Don't self-host.
- **Supabase** — stays on supabase.com. We use pgbouncer to pool connections.
- **Obsidian vault** — lives on CC's laptop. Syncs via git.
- **Client production data for regulated tenants** — gets its own isolated
  Supabase project + optional self-hosted LLM VPS (Hetzner GEX44, €189/mo).

---

## 7. Migration path from V5.7 local → V6.0 VPS

1. **Shadow mode** (Week 2) — VPS receives webhooks but does NOT send outbound.
   Local Mac keeps running as primary. Compare logs.
2. **Cutover** (Week 3) — DNS flip. Stop local scheduler + telegram-bot.
   VPS becomes primary. Local = dev only.
3. **Decommission** (Week 4) — PM2 stop on Mac. Keep laptop as dev workstation.

---

## Obsidian Links
- [[docs/V6_ARCHITECTURE]] | [[brain/STATE]] | [[brain/ORCHESTRATION]]
- [[memory/SESSION_LOG]] | Claude durable memory: `reference_vercel_deploy`
