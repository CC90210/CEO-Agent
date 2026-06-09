# VPS — make VERIFY 3 miss-proof + diagnose bridge cycling

> Paste into the same VPS Claude Code session you just used. ~3 minutes
> of work. Goal: protect the 9:12 AM EDT fire and surface the bridge
> restart cause for tomorrow.

---

## Why this matters

The `claude-bridge` daemon restarted ~16 times in the few hours before
you stabilized. If it's mid-restart at exactly 13:12 UTC today, the
`cron_runner.poll_once` tick misses, and the one-shot schedule
`12 13 9 6 *` never fires again (cron has no catch-up — the next match
would be June 9 of NEXT year).

We mitigate by widening the schedule to **every day at 13:12 UTC** so a
missed fire today simply retries tomorrow. CC manually disables the row
after first green.

---

## Step 1 — Widen the schedule to daily

```bash
cd /srv/sunbiz/ceo-agent
python scripts/integrations/supabase_tool.py update tenant_cron_jobs \
  '{"schedule": "12 13 * * *"}' \
  --filter "id=eq.9e4c3ae0-f9fc-45ef-be2c-0edfc86695af"
```

Verify:

```bash
python scripts/integrations/supabase_tool.py select tenant_cron_jobs \
  --filter "id=eq.9e4c3ae0-f9fc-45ef-be2c-0edfc86695af" \
  --columns "id,schedule,enabled,last_run_at,last_run_status"
```

Expected: `schedule="12 13 * * *"`, `enabled=true`, `last_run_at=null`.

---

## Step 2 — Surface the bridge restart root cause (diagnostic only — DO NOT FIX)

```bash
# Last 50 lines around each restart timestamp the VPS agent named
for ts in "05:10" "05:44" "06:18" "06:28"; do
  echo "===== $ts UTC ====="
  pm2 logs claude-bridge --lines 200 --nostream --raw 2>/dev/null \
    | grep -A 3 -B 3 "$ts" | head -30
  echo
done

# Then: pm2's own restart log
pm2 describe claude-bridge | grep -iE "restart|exit code|uptime" | head -20

# Then: any OOMs in dmesg in the same window
sudo dmesg --time-format iso 2>/dev/null | grep -iE "oom|killed|claude-bridge" | tail -20
```

Capture whatever's there. **DO NOT attempt to fix at 3 AM** — restart
chasing is a tomorrow task. Just paste the patterns you see so CC has a
starting point when he wakes up.

---

## Step 3 — Report back

Use this shape:

```
VERIFY 3 — miss-proof + restart diagnostic

Step 1 — schedule widened ✅
- id 9e4c3ae0-f9fc-45ef-be2c-0edfc86695af
- schedule: 12 13 * * *  (every day 13:12 UTC, fires today at 9:12 AM EDT, then retries daily)
- enabled=true, last_run_at=null

Step 2 — bridge restart root cause (NOT patched)
- pm2 describe: [exit codes / restart counter]
- Log pattern around 05:10/05:44/06:18/06:28 UTC: [one-line summary]
- OOM in dmesg? [yes/no — paste if yes]
- Hypothesis: [your best read in one line, e.g. "PTB 409 backoff", "OOM kill", "network blip"]

After first green tomorrow, CC disables the row with:
  python scripts/integrations/supabase_tool.py update tenant_cron_jobs \
    '{"enabled": false}' \
    --filter "id=eq.9e4c3ae0-f9fc-45ef-be2c-0edfc86695af"

Solara out.
```

Then run state sync + say "Miss-proof complete. Sleep tight."

```bash
python scripts/state/state_sync.py --note "solara: VERIFY 3 widened to daily + bridge restart diagnostic captured"
```
