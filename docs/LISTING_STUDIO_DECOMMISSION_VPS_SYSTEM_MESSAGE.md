---
title: "VPS system message — decommission Listing Studio, keep the software"
date: 2026-09-02
author: Bravo
audience: VPS Claude (paste-in)
host: srv1723601 (Linux) — SHARED HOST
tags: [vps, decommission, listing-studio, rems, cleanup, destructive]
---

# VPS MISSION — decommission the Listing Studio client install

> **Paste this whole message to the VPS agent.** CC does not run these commands
> by hand. Report back with the output of each VERIFY block.

## 0 · READ THIS FIRST — the host is shared

`srv1723601` does **not** belong to this project. It also runs, at minimum:

- **Bravo's own Linux-only daemons** — `dashboard-email-consumer`,
  `dashboard-email-queue-monitor`, `extraction-consumer`. These move CC's real
  email. Killing them silently stops inbound mail processing.
- **SunBiz-Agent / CEO-Agent** workloads.

Therefore:

1. **NEVER delete a global `~/.env.agents` or `/srv/.env.agents`.** It is the
   shared empire credential store. The instruction that produced this document
   said "delete the env.agents file"; the intent is the **Listing Studio's own**
   env, which lives inside `/srv/listing-studio/`. If you find an `.env.agents`
   OUTSIDE that directory, **stop and report it — do not touch it.**
2. **Only ever act on names starting `rems-` and the single directory
   `/srv/listing-studio`.** Anything else is out of scope for this mission.
3. If any VERIFY block disagrees with what is written here, **stop and report**.
   A surprising machine is not a machine to run deletes on.

## 1 · VERIFY — inventory before you touch anything

Run all of these and paste the complete output back. Change nothing yet.

```bash
# Every PM2 process on the host, so we can see what is NOT ours.
pm2 list

# The five processes this mission owns.
pm2 jlist | python3 -c "import sys,json;[print(p['name'],p['pm2_env']['status'],p['pm2_env'].get('pm_cwd')) for p in json.load(sys.stdin)]"

# Confirm the directory and its size.
ls -la /srv/listing-studio 2>/dev/null | head -20
du -sh /srv/listing-studio 2>/dev/null

# CRITICAL: prove no shared credential store sits inside the blast radius,
# and find any that sit outside it (which we must NOT touch).
find / -maxdepth 4 -name '.env.agents' 2>/dev/null

# Any cron or systemd unit referencing this app.
crontab -l 2>/dev/null | grep -i -E 'listing-studio|rems' || echo "no crontab refs"
systemctl list-units --type=service 2>/dev/null | grep -i -E 'listing|rems' || echo "no systemd units"
```

**Expected:** five processes named `rems-render`, `rems-inbox`, `rems-sms`,
`rems-digest`, `rems-publish`, all with `pm_cwd` = `/srv/listing-studio`. Exactly
zero `.env.agents` inside `/srv/listing-studio` is fine; one or more OUTSIDE it
is expected and must be left alone.

**If `pm2 list` shows a `rems-*` process whose cwd is NOT `/srv/listing-studio`,
stop.** That is a different install and this mission does not cover it.

## 2 · BACK UP — before anything is destroyed

The client relationship ended; the data still has to be recoverable for a
reasonable period. There is no undo for step 4.

```bash
mkdir -p /srv/_decommissioned
TS=$(date -u +%Y%m%dT%H%M%SZ)

# Whole app directory, including its env files and any local sqlite.
tar czf "/srv/_decommissioned/listing-studio-${TS}.tar.gz" -C /srv listing-studio

# PM2 process definitions, so the install could be reconstructed if needed.
pm2 jlist > "/srv/_decommissioned/pm2-${TS}.json"

ls -lh /srv/_decommissioned/
```

**VERIFY:** the tarball exists and is non-trivial in size (tens of MB, not zero).
Paste the `ls -lh`. Do not continue until you have seen it.

> The Turso database `real-estate-marketing-suite` is a **separate, dedicated
> database** and is NOT on this host. Wiping it is a separate decision (§6) and
> is not part of this mission.

## 3 · STOP the workers

```bash
for p in rems-render rems-inbox rems-sms rems-digest rems-publish; do
  pm2 stop "$p" 2>/dev/null || echo "  $p not running"
done
pm2 list
```

**VERIFY:** all five show `stopped`. Every other process on the host is still
`online`. Paste `pm2 list`.

**Stop here and report if any non-`rems-*` process changed state.**

## 4 · DELETE the processes and the directory

Only after §1–§3 are verified and the backup exists.

```bash
for p in rems-render rems-inbox rems-sms rems-digest rems-publish; do
  pm2 delete "$p" 2>/dev/null || echo "  $p already gone"
done
pm2 save          # persist the new process list so a reboot does not resurrect them

# The app directory, INCLUDING its own .env / .env.local / .env.agents.
rm -rf /srv/listing-studio
```

**VERIFY:**

```bash
pm2 list                                   # no rems-* rows; everything else intact
ls -la /srv/ | head -20                    # listing-studio gone, _decommissioned present
find / -maxdepth 4 -name '.env.agents' 2>/dev/null   # shared store still present
```

The last command **must still return the shared credential store**. If it
returns nothing and it returned something in §1, you deleted the wrong file —
restore it from the tarball immediately and report.

## 5 · RECLAIM space and confirm the host is healthy

```bash
pm2 flush                       # drop accumulated logs from the deleted apps
rm -rf /root/.pm2/logs/rems-*   # their log files specifically
df -h /                         # disk before/after for the report
free -h
pm2 list                        # final state
```

**VERIFY:** Bravo's daemons (`dashboard-email-consumer`,
`dashboard-email-queue-monitor`, `extraction-consumer`) are still `online`.
**This is the most important check in the document.** If any of them is stopped
or missing, restart it and report before doing anything else.

## 6 · NOT IN SCOPE — do not do these

Listed explicitly so they are not done by inference:

- **Do not** drop or wipe the Turso database `real-estate-marketing-suite`. It
  is off-host, it is the only copy of the lead history, and the reset is being
  handled deliberately (see the white-label plan) rather than by deleting rows.
- **Do not** delete the GitHub repo `CC90210/real-estate-marketing-suite`. The
  software is being kept and white-labelled.
- **Do not** delete the Vercel project. The domain and build config are being
  re-pointed, not discarded.
- **Do not** revoke the Telegram bot `@Sexyrapeezra_bot`. It is the **empire**
  bot and is used elsewhere — it was wrongly serving client data, which is a
  separate fix, not a deletion.
- **Do not** touch `/srv/` siblings, any non-`rems-*` PM2 app, or any file
  outside `/srv/listing-studio` and `/srv/_decommissioned`.

## 7 · REPORT BACK

Four lines:

- **Changed:** what was stopped/deleted, and the backup path + size.
- **Why:** one sentence.
- **Proof:** the actual output of the §4 and §5 VERIFY blocks.
- **Needs from CC:** anything you refused to do and why.

Flag anything in §0–§1 that did not match reality. A mismatch there means this
document was written against a stale picture of the host, and the right response
is to stop, not to improvise.
