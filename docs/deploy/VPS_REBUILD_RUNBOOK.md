---
tags: [docs, deploy]
last_updated: 2026-06-18
---

# SunBiz VPS — Rebuild Runbook

**Purpose:** rebuild the entire SunBiz VPS from scratch after total box loss.
**Target RTO:** ≤ 60 minutes (experienced operator, backups + secrets in hand).
**Scope:** SunBiz only (tenant `aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110`). The
shared Supabase + Vercel dashboard are managed services and survive a VPS loss;
this box only runs the daemon fleet + the bridge + the Cloudflare tunnel.

> **The one thing you MUST have off-box:** `BACKUP_GPG_PASSPHRASE`
> (in CC's password manager). Without it, every encrypted backup —
> including the `.env.agents` snapshot — is undecryptable and this runbook
> cannot proceed. It is the root of the whole recovery chain.

---

## 0. What's where

| Asset | Durable location | Notes |
|---|---|---|
| Daemon code | GitHub `CC90210/CEO-Agent` + `CC90210/SunBiz-Agent` | both branches `main` |
| Secrets (`.env.agents`) | encrypted in `/srv/sunbiz/backups/secrets/` (+ off-box repo once provisioned) | decrypt key = `BACKUP_GPG_PASSPHRASE` |
| Supabase data + PDFs | encrypted in `/srv/sunbiz/backups/supabase/` (+ off-box repo) | SunBiz-scoped logical export |
| DB schema | the `database/NNN_*.sql` migrations in `SunBiz-Agent` | applied via `ceo-agent/scripts/apply_migration.py` |
| Cloudflare tunnel token | Cloudflare Zero Trust dashboard | re-copied into the systemd unit |
| `BACKUP_GPG_PASSPHRASE` | **CC's password manager (off-box)** | the master recovery key |

---

## 1. Provision host (~10 min)
- Ubuntu host, root shell. Install runtime deps:
  `apt-get update && apt-get install -y git python3 python3-venv gpg curl gzip tar`
- Install Node + pm2: `npm i -g pm2` (or the version pinned in `harness.lock`).
- Install cloudflared (`/usr/bin/cloudflared`).
- `mkdir -p /srv/sunbiz`

## 2. Clone both repos (~5 min)
```
cd /srv/sunbiz
git clone https://github.com/CC90210/CEO-Agent.git ceo-agent
git clone https://github.com/CC90210/SunBiz-Agent.git sunbiz-agent
```

## 3. Restore secrets (`.env.agents`) (~5 min)
- Retrieve `BACKUP_GPG_PASSPHRASE` from CC's password manager.
- Get the newest `env-agents-*.tar.gz.gpg` (from the off-box backups repo, or the
  surviving `/srv/sunbiz/backups/secrets/` if the disk was recovered).
```
gpg --batch --pinentry-mode loopback --passphrase '<BACKUP_GPG_PASSPHRASE>' \
    -d env-agents-<TS>.tar.gz.gpg | tar -xz -C /tmp/envrestore
install -m600 /tmp/envrestore/.env.agents /srv/sunbiz/ceo-agent/.env.agents
ln -sf /srv/sunbiz/ceo-agent/.env.agents /srv/sunbiz/sunbiz-agent/.env.agents
```
- Recreate each repo's venv and install deps:
  `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (both repos).

## 4. (Only if the Supabase project was also lost) restore data
The shared Supabase normally survives. If it did NOT:
1. Re-apply schema: for each `sunbiz-agent/database/NNN_*.sql` in order,
   `ceo-agent/.venv/bin/python ceo-agent/scripts/apply_migration.py <file>`.
2. Decrypt the newest `sunbiz-<TS>.tar.gz.gpg` and re-import the NDJSON per table
   (service-role upsert) and re-upload `storage/` objects to the `lead-documents`
   bucket. The export is SunBiz-scoped, so no other tenant is touched.

## 5. Start the daemon fleet (~5 min)
```
pm2 start /srv/sunbiz/ceo-agent/ecosystem.config.js      # event-router, claude-bridge, claude-bridge-ping
pm2 start /srv/sunbiz/sunbiz-agent/ecosystem.config.js   # sequence-runner, lender-response-classifier, cold-outreach-runner, sentinel
pm2 save && pm2 startup    # persist across reboot
```
Expected: 7 daemons `online` in `pm2 list`.

## 6. Cloudflare tunnel (~5 min)
- Copy the tunnel token from the Cloudflare Zero Trust dashboard into a systemd
  unit (`ExecStart=/usr/bin/cloudflared --no-autoupdate tunnel run --token <TOKEN>`),
  `systemctl enable --now cloudflared`.
- Verify: `systemctl is-active cloudflared` → `active`; the public hostname
  `bridge.oasisai.work` resolves to the bridge.

## 7. Re-arm ops timers (~5 min)
```
cp /srv/sunbiz/ceo-agent/deploy/*.service /srv/sunbiz/ceo-agent/deploy/*.timer /etc/systemd/system/
# set User=root in each .service if templated, then:
systemctl daemon-reload
systemctl enable --now vps_autosync.timer sunbiz-supabase-backup.timer sunbiz-env-backup.timer sunbiz-liveness-pager.timer
```

## 8. Verify green (~5 min)
- `cd /srv/sunbiz/sunbiz-agent && .venv/bin/python scripts/doctor.py --json` → SMTP + Supabase keys configured.
- `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:9100/health` → `401`.
- `scripts/ops/liveness_pager.sh` → "all healthy".
- `scripts/ops/supabase_backup.sh` → restore drill PASSES.

---

## Off-box gap (open — 2026-06-18)
The off-box backup repo (`CC90210/sunbiz-backups`) is **not yet provisioned**:
the automated push was held when the safety guard flagged pushing PII (even
gpg-encrypted) to a new external repo. Until an operator provisions it, the only
copies of the encrypted backups live on THIS box — a single-point-of-failure for
the data itself (the code + schema are already safe on GitHub). To close it:
1. Operator creates the private repo `CC90210/sunbiz-backups`.
2. `git -C /srv/sunbiz/backups init && git remote add origin <url>` and an
   initial push; `scripts/ops/backups_push.sh` replicates every run thereafter.
3. Only `*.gpg` artifacts are tracked (`/srv/sunbiz/backups/.gitignore`), so
   GitHub only ever stores ciphertext.

## Managed PITR
Supabase Managed Point-In-Time-Recovery could not be read/toggled from the box
(no `SUPABASE_ACCESS_TOKEN` Management-API credential present). Verify the plan's
PITR tier in the Supabase dashboard and enable it if available — it complements
(does not replace) these tenant-scoped logical backups.

## Obsidian Links
- [[docs/INDEX]]
- [[brain/STATE]]
