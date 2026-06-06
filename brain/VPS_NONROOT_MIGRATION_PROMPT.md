# VPS Non-Root Migration Prompt

> Paste between the triple-dashes into a Claude Code session running ON
> the SunBiz VPS (`ssh root@srv1723601`, then `claude`). The agent
> migrates the bridge + SunBiz daemons from running as root to running
> as a dedicated non-root `sunbiz` user — the optimization that closes
> Blocker 6 from the prior pass.
>
> **Why this is optional:** chat works today as root via cold-spawn at
> ~$0.20/turn. The migration is a cost/latency win (warm pool wakes
> up). It is NOT a security gate — the bridge already enforces the
> bearer + runs behind Cloudflare Tunnel.
>
> Do NOT paste this until you (CC) have explicitly said the word. The
> prior agent flagged 3 failure modes that would take down the live
> portal if rushed; this prompt closes all 3.

---

You are a Claude Code agent on CC's SunBiz Funding VPS (Ubuntu 22.04,
srv1723601). The prior finalization pass closed 5 of 6 blockers and
deferred the non-root migration deliberately because the runbook's
steps would have broken the live portal in three specific ways. CC has
now explicitly greenlit this migration. Your job is the CORRECTED
procedure the prior agent described, executed with a tested rollback
ready.

## Scope — SunBiz infrastructure only

Touch ONLY:
- `/srv/sunbiz/ceo-agent` + `/srv/sunbiz/sunbiz-agent`
- A new `sunbiz` Linux user (home: `/home/sunbiz`)
- The shared Python venv under `/srv/sunbiz/ceo-agent/.venv`
- The PM2 daemons under that user's scope
- The cloudflared systemd service stays root-owned — out of scope.

Do NOT touch:
- Any other tenant repos, agents, or dashboards
- The dashboard repo `oasis-command-center` (Vercel-hosted, not here)
- The `.env.agents` secrets file values
- The Cloudflare Tunnel config

## Pre-flight — read these before any mutation

1. **Confirm the prior agent's branches are merged + pushed.**
   ```
   cd /srv/sunbiz/ceo-agent && git status --short && git log --oneline -5
   cd /srv/sunbiz/sunbiz-agent && git status --short && git log --oneline -5
   ```
   Both should be on `main`, clean, and `origin/main` should be the same
   commit as `HEAD`. If `origin/main` is behind, STOP — CC needs to push
   from his PC first; that's a separate rollout step.

2. **Snapshot the current PM2 daemon list.** Write it to
   `/srv/sunbiz/pm2-snapshot-pre-migration.txt`:
   ```
   pm2 jlist > /srv/sunbiz/pm2-snapshot-pre-migration.txt
   pm2 list >> /srv/sunbiz/pm2-snapshot-pre-migration.txt
   ```
   This is the rollback source-of-truth if any step fails.

3. **Confirm what's at the three landmines the prior agent flagged.**

   **Landmine A — Claude credentials at /root/.claude:**
   ```
   ls -la /root/.claude/ | head -10
   ```
   Expect `.credentials.json`, `settings.json`, possibly `.config/`. These
   are CC's Claude Code subscription credentials. Without them the chat
   bridge can't reach the model after restart.

   **Landmine B — /srv/sunbiz parent ownership:**
   ```
   ls -ld /srv /srv/sunbiz /srv/sunbiz/ceo-agent /srv/sunbiz/sunbiz-agent
   ```
   The parent `/srv/sunbiz` is likely root-owned. If we chmod 750 the
   children without fixing the parent, the new sunbiz user can't `cd`
   into them.

   **Landmine C — the ~/CEO-Agent symlink:**
   ```
   ls -la /root/ | grep -i ceo
   ```
   The bridge code imports `~/CEO-Agent` as a shared-runtime path. If
   sunbiz's home doesn't have the same symlink, imports fail.

## Procedure — the corrected steps

Run each numbered step in order. Verify the listed expectation BEFORE
moving to the next.

### Step 1 — Create the sunbiz user

```
sudo useradd -m -s /bin/bash sunbiz
id sunbiz
```

Expect: a new user with home `/home/sunbiz`, default shell `/bin/bash`,
and a fresh UID/GID.

### Step 2 — Copy CC's Claude credentials into sunbiz's home

```
sudo cp -r /root/.claude /home/sunbiz/.claude
sudo chown -R sunbiz:sunbiz /home/sunbiz/.claude
sudo chmod 700 /home/sunbiz/.claude
sudo chmod 600 /home/sunbiz/.claude/.credentials.json 2>/dev/null || true
```

Expect: `/home/sunbiz/.claude/.credentials.json` readable by sunbiz
only. The chat bridge will use these when it next spawns claude CLI.

### Step 3 — Recreate the shared-runtime symlink

```
sudo ln -snf /srv/sunbiz/ceo-agent /home/sunbiz/CEO-Agent
sudo chown -h sunbiz:sunbiz /home/sunbiz/CEO-Agent
ls -la /home/sunbiz/CEO-Agent
```

Expect: a symlink pointing at the canonical CEO-Agent repo path.

### Step 4 — Fix the parent + children ownership

```
sudo chown sunbiz:sunbiz /srv/sunbiz
sudo chmod 755 /srv/sunbiz
sudo chown -R sunbiz:sunbiz /srv/sunbiz/ceo-agent /srv/sunbiz/sunbiz-agent
```

Expect: `ls -ld /srv/sunbiz` shows `sunbiz sunbiz` and `755`. The
`/srv` parent stays root-owned (do NOT chown that).

### Step 5 — Stop and remove the root-owned PM2 daemons cleanly

```
pm2 list
pm2 stop all
pm2 delete all
pm2 kill
```

Expect: PM2 daemon shuts down. The cloudflared service is independent;
it stays up.

### Step 6 — Start PM2 fresh as the sunbiz user

```
sudo -iu sunbiz bash -lc 'cd /srv/sunbiz/ceo-agent && pm2 start ecosystem.config.js'
sudo -iu sunbiz bash -lc 'cd /srv/sunbiz/sunbiz-agent && pm2 start ecosystem.config.js'
sudo -iu sunbiz bash -lc 'pm2 save'
sudo -iu sunbiz bash -lc 'pm2 list'
```

Expect: every daemon from the snapshot at pre-flight step 2 is now
running under the sunbiz user, status `online`.

### Step 7 — Register PM2 to restart on reboot under sunbiz

```
sudo env PATH=$PATH:/usr/bin /usr/lib/node_modules/pm2/bin/pm2 startup systemd -u sunbiz --hp /home/sunbiz
sudo -iu sunbiz bash -lc 'pm2 save'
```

(If the pm2 binary path differs on this host, find it with `which pm2`
as the sunbiz user first.) Expect: systemd unit `pm2-sunbiz.service`
exists and is enabled.

### Step 8 — Smoke tests

```
curl -sS -X POST http://127.0.0.1:9100/chat -H 'Content-Type: application/json' -d '{}' -o /dev/null -w "no-auth: %{http_code}\n"
BEARER="$(grep '^BRIDGE_BEARER_TOKEN=' /srv/sunbiz/ceo-agent/.env.agents | cut -d= -f2- | tr -d '\"')"
curl -sS -X POST -H "Authorization: Bearer $BEARER" -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"reply verified"}],"agent":"solara"}' http://127.0.0.1:9100/chat | head -c 300
```

Expect: first curl → 401. Second curl → a real agent reply. Watch
`pm2 logs claude-bridge --lines 20` for a "spawned warm" log line —
that's the warm-pool guard greenlighting (the win we're after).

### Step 9 — External reachability sanity

```
curl -sS https://bridge.oasisai.work/chat -X POST -H 'Content-Type: application/json' -d '{}' -o /dev/null -w "external no-auth: %{http_code}\n"
```

Expect: 401. The Cloudflare Tunnel keeps working because it terminates
at localhost:9100 from cloudflared's perspective, and we didn't touch
cloudflared itself.

## Rollback

If ANY step 4-7 fails AND chat is broken, restore the root daemons:

```
sudo -iu sunbiz bash -lc 'pm2 stop all && pm2 kill' 2>/dev/null || true
cd /srv/sunbiz/ceo-agent && pm2 start ecosystem.config.js
cd /srv/sunbiz/sunbiz-agent && pm2 start ecosystem.config.js
pm2 save
```

Then compare `pm2 jlist` against
`/srv/sunbiz/pm2-snapshot-pre-migration.txt` to confirm every daemon is
back. Surface the failing step in your report so CC knows the diff.

## Report

Write `/srv/sunbiz/nonroot-migration.log`:

```
=== Non-root Migration — {ISO timestamp} ===
[1] sunbiz user created           : YES / NO
[2] /home/sunbiz/.claude copied    : YES / NO
[3] ~/CEO-Agent symlink            : YES / NO — {ls -la output}
[4] /srv/sunbiz ownership          : sunbiz:sunbiz 755 / OTHER
[5] PM2 root daemons removed       : YES / NO
[6] PM2 sunbiz daemons online      : N/N — {names + statuses}
[7] pm2-sunbiz.service registered  : YES / NO
[8] Local bearer-gated probe       : 401 + real reply / FAIL
[9] Warm-pool greenlit             : YES (spawned warm seen) / NO
[10] External 401 enforced         : YES / NO
[11] Rollback fired                : YES / NO + WHICH STEP

```

Plus a one-paragraph plain-English summary for CC: was the warm pool
actually woken? Is the latency win real? Anything weird? Did you have
to roll back, and if so what stopped you?

## Constraints

1. **No `git push` from this VPS.** Code state should match origin/main
   at start; we don't change code.
2. **Never modify `.env.agents` values.** We only read BRIDGE_BEARER_TOKEN
   for the smoke test.
3. **Stop on any step failure.** Don't barrel through a broken step.
4. **Roll back on broken chat.** A working root setup is better than a
   half-migrated sunbiz setup. CC can re-run with a corrected procedure
   later.
5. **Do not touch cloudflared.** It stays root-owned and untouched.
