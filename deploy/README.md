# VPS auto-sync — "Vercel for the SunBiz VPS"

Keeps the VPS daemon repos in sync with GitHub so they never drift again. The
dashboard (oasis-command-center) auto-deploys via Vercel; this is the equivalent
for `/srv/sunbiz/ceo-agent` + `/srv/sunbiz/sunbiz-agent`.

`scripts/vps_autosync.sh` runs every ~15 min and, **per repo**, only acts when it
is safe:

| Repo state | Action |
|---|---|
| dirty (uncommitted) | skip + WARN — never discards local edits |
| ahead (unpushed commits) | skip + WARN — surfaced so you push them; never lost |
| diverged (ahead + behind) | skip + ERROR — manual reconcile |
| behind + clean | `git pull --ff-only` → `pm2 reload` only this repo's daemons → doctor |

`--ff-only` is the safety latch: it can only fast-forward, never merge/clobber.
Daemon names are derived live from `pm2 jlist` (matched by working dir), not
hardcoded. Logs to `/srv/sunbiz/deploy.log`.

## Install (run in the Claude Code session ON the VPS, as root/sudo)

```bash
chmod +x /srv/sunbiz/ceo-agent/scripts/vps_autosync.sh

# dry-run first — see what it WOULD do, change nothing:
sudo -u <SUNBIZ_USER> /srv/sunbiz/ceo-agent/scripts/vps_autosync.sh --dry-run

# install the timer (edit User=<SUNBIZ_USER> in the unit first):
sudo cp /srv/sunbiz/ceo-agent/deploy/vps_autosync.service /etc/systemd/system/
sudo cp /srv/sunbiz/ceo-agent/deploy/vps_autosync.timer   /etc/systemd/system/
sudo sed -i "s/<SUNBIZ_USER>/<SUNBIZ_USER>/" /etc/systemd/system/vps_autosync.service
sudo systemctl daemon-reload
sudo systemctl enable --now vps_autosync.timer
systemctl list-timers vps_autosync.timer
```

### Cron alternative (no root, runs as the PM2 user)

```bash
( crontab -l 2>/dev/null; echo "*/15 * * * * /srv/sunbiz/ceo-agent/scripts/vps_autosync.sh >> /srv/sunbiz/deploy.log 2>&1" ) | crontab -
```

## Operate

- Watch it: `tail -f /srv/sunbiz/deploy.log` or `journalctl -u vps_autosync.service -f`
- A `WARN ahead N` line means the VPS has local commits to push to origin (the
  inverse drift — back them up). A repo authored on the VPS should be pushed so
  the sync can fast-forward it cleanly from then on.
