> ⚠️ **SUPERSEDED 2026-07-09** — do NOT paste `ANTHROPIC_API_KEY` into any env.
> Auth = `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` (see memory `reference_claude_code_headless_vps_auth`).
> MRR reporting is Atlas-owned.

# VPS Finalization Prompt — close the gap from 65% → 100%

> Paste everything between the triple-dashes into your VPS Claude Code
> chat. The agent runs through CC's decisions on the readiness-report
> blockers and ships. No SSH-from-Windows needed.

---

You are a Claude Code agent on CC's SunBiz Funding VPS (Ubuntu 22.04,
srv1723601). A prior diagnostic + repair pass already landed three
patches on the branch `fix/vps-readiness-patches` of
`/srv/sunbiz/ceo-agent` and `/srv/sunbiz/sunbiz-agent`. It reported
~60-65% production readiness with six blockers. CC has now decided
each blocker and provided the missing secret values. Your job: close
every blocker in this one pass and reach a fully live-sending state.

## Scope — strictly SunBiz infrastructure

Touch ONLY:
- `/srv/sunbiz/ceo-agent` + `/srv/sunbiz/sunbiz-agent` (the bridge +
  Solara/Helios daemons)
- `/srv/sunbiz/ceo-agent/.env.agents` (the shared secrets file)
- The `cloudflared` systemd service + the `claude-bridge`, `event-router`,
  and `sunbiz-*` PM2 daemons
- The Supabase rows scoped to `tenant_id=aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110`

Do NOT touch:
- Anything under `~/CMO-Agent`, `~/APPS/CFO-Agent`, or any non-SunBiz repo
- The dashboard repo `oasis-command-center` (lives on Vercel, not here)
- The cold-outreach runner for the prior client's lead list (retired)

## CC's decisions on the six blockers

### Blocker 1 — open public bridge (THE #1 RISK)

CC generated a new 256-bit bearer token and stored it in Vercel's
production env. Provision the same value on this VPS and restart the
bridge so it enforces `Authorization: Bearer …` on every request.

Steps:

1. Pull the latest CEO-Agent so the bearer-provision helper is current:
   ```
   cd /srv/sunbiz/ceo-agent && git fetch origin && git status --short && git log --oneline origin/main..HEAD
   ```
   If a clean fast-forward, `git pull --ff-only origin main`.
   If dirty / unpushed commits, STOP and report — never discard work.

2. Run the bearer-provision helper with the value below:
   ```
   BRIDGE_BEARER_TOKEN_VALUE='oasis_bridge_FV5jYKH9xe0FTaEOZkIeJXYHVM1v1eJURsT8zKlLvXc' sudo bash /srv/sunbiz/ceo-agent/scripts/vps_bearer_provision.sh
   ```

3. Verify the bridge now enforces:
   ```
   curl -sS -o /dev/null -w "no-auth: %{http_code}\n" -X POST -H "Content-Type: application/json" -d '{}' http://127.0.0.1:9100/chat
   ```
   Expect 401. If still 200, check the bridge's env handling — the
   value may be in the file but the daemon didn't reload it
   (`pm2 restart claude-bridge --update-env`).

4. Verify external reachability ALSO enforces:
   ```
   curl -sS -o /dev/null -w "external no-auth: %{http_code}\n" https://bridge.oasisai.work/chat -X POST -d '{}' -H 'Content-Type: application/json'
   ```
   Expect 401.

5. Verify a request WITH the bearer reaches the agent:
   ```
   curl -sS -w "\n" -X POST -H "Content-Type: application/json" -H "Authorization: Bearer oasis_bridge_FV5jYKH9xe0FTaEOZkIeJXYHVM1v1eJURsT8zKlLvXc" -d '{"messages":[{"role":"user","content":"reply with the word verified"}],"agent":"solara"}' http://127.0.0.1:9100/chat
   ```
   Expect a real agent response.

### Blocker 2 — daily_plans data-model mismatch

CC's call: **create a new `daily_plan_items` table.** Less risk than
rewriting the generator (which is well-tested), and gives operators a
queryable per-item view future agents can read.

Steps:

1. Inspect the generator to confirm the columns it writes per-row:
   ```
   grep -n "daily_plans\|upsert\|insert" /srv/sunbiz/sunbiz-agent/scripts/daily_plan_generator.py | head -30
   ```

2. Write a new migration at
   `/srv/sunbiz/ceo-agent/database/095_daily_plan_items.sql` matching the
   shape the generator already upserts. Required columns at minimum:
   `id uuid pk default gen_random_uuid()`,
   `tenant_id uuid not null references tenants(id) on delete cascade`,
   `lead_id uuid references tenant_records(id) on delete set null`,
   `category text not null`,
   `plan_date date not null default current_date`,
   `priority int`,
   `payload jsonb default '{}'::jsonb`,
   `created_at timestamptz default now()`,
   `updated_at timestamptz default now()`.
   Add `UNIQUE (tenant_id, lead_id, category, plan_date)` so the
   generator's upsert remains idempotent. Add a RLS policy that lets
   tenant members SELECT their own rows; service-role passes through.

3. Apply via the Supabase Management API. The required env var is
   `SUPABASE_ACCESS_TOKEN` in `.env.agents`. POST to
   `https://api.supabase.com/v1/projects/phctllmtsogkovoilwos/database/query`
   with `{"query": "<the SQL>"}` and a User-Agent header set to a normal
   browser string (the WAF blocks the default urllib UA). Expect HTTP 201.

4. Modify `daily_plan_generator.py` to write to `daily_plan_items`
   (changing the table name in the upsert). Run it once and confirm
   `0 errors`:
   ```
   /srv/sunbiz/ceo-agent/.venv/bin/python /srv/sunbiz/sunbiz-agent/scripts/daily_plan_generator.py --json | head -5
   ```

5. Commit + push the migration + generator change in
   `/srv/sunbiz/ceo-agent`. Commit message:
   `feat(sunbiz): daily_plan_items table + generator routed to it`.

### Blocker 3 — outbound dry-run flip

Hold off on flipping `BRAVO_FORCE_DRY_RUN` until blockers 1 + 4 are
done AND CC has confirmed the SMS namespace decision (blocker 5). When
ready, edit `/srv/sunbiz/ceo-agent/.env.agents` to set
`BRAVO_FORCE_DRY_RUN=0` and `pm2 restart sunbiz-sequence-runner
sunbiz-cold-outreach-runner --update-env`. Watch the next live drip
with `pm2 logs sunbiz-sequence-runner --lines 50` for ~3 minutes.

### Blocker 4 — empty secrets

CC has provisioned values for two. The others are external creds CC
will paste in a follow-up if/when needed.

Append (or replace if present) in `/srv/sunbiz/ceo-agent/.env.agents`:

```
SUNBIZ_AGENT_HMAC_SECRET=719c54383d9626aeb1ad48b8fb7f5497b4f62cc1e37c0b40fefa60d1461c01f1
```

After writing, `chmod 600` and `pm2 restart all --update-env`.

NOT in scope this round (waiting on CC):
- `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` — CC
  will paste from his Twilio console. Until provisioned, leave
  `BRAVO_FORCE_DRY_RUN=1` (blocker 3) so SMS sends are no-ops.
- `KIXIE_API_KEY` — CC says he already pasted this; just confirm it's
  on the live env and not a stale empty value.
- `TEXTTORRENT_API_KEY` — CC says already pasted. Also rename any
  `TEAXTTORRENT_*` typo to `TEXTTORRENT_*` (single fix while editing).
- `ANTHROPIC_API_KEY` — CC will paste; needed for backend automation
  paths that call Claude server-side.

DO NOT prompt CC for `JOTFORM_API_KEY`. SunBiz uses the dashboard's
native /forms designer + /f/<tenant>/<form>/<lead_token> public flow.
JotForm was removed from the codebase 2026-06-06 (doctor.py, the
integrations registry, the SunBiz manifest seed, the env template).

### Blocker 5 — SMS namespace split

CC's call: **use `SUNBIZ_TWILIO_*` (tenant-prefixed).** The
unprefixed gateway-side keys were a transitional shape; the
multi-tenant convention is per-tenant prefixes so a future client gets
their own namespace.

Steps:

1. Find every reference to unprefixed `TWILIO_*` in the gateway and
   doctor:
   ```
   grep -rn "TWILIO_ACCOUNT_SID\|TWILIO_AUTH_TOKEN\|TWILIO_FROM_NUMBER" /srv/sunbiz/ceo-agent/scripts/ /srv/sunbiz/sunbiz-agent/scripts/ | grep -v ".env.agents.template"
   ```
2. For each gateway-side hit, prefer reading
   `SUNBIZ_TWILIO_<KEY>` first and falling back to the unprefixed name
   (so legacy callers don't crash mid-roll-out). Example:
   ```python
   sid = os.environ.get("SUNBIZ_TWILIO_ACCOUNT_SID") or os.environ.get("TWILIO_ACCOUNT_SID")
   ```
3. Update `doctor.py` to check the SUNBIZ-prefixed names FIRST so its
   PASS/FAIL aligns with the gateway. Don't remove the unprefixed
   checks — make them warn-only.
4. Commit on `fix/vps-readiness-patches` (same branch as the prior
   agent's work): `fix(sms): prefer SUNBIZ_TWILIO_* tenant namespace,
   keep unprefixed fallback`.

### Blocker 6 — warm pool dead under root

CC's call: **create a dedicated non-root `sunbiz` user and migrate
the bridge to run as that user.** $0.20 per cold spawn at any
meaningful chat volume is real money; warm pool needs a non-root
parent.

Steps:

1. Create the user and give it ownership of the SunBiz paths:
   ```
   sudo useradd -m -s /bin/bash sunbiz
   sudo chown -R sunbiz:sunbiz /srv/sunbiz/ceo-agent /srv/sunbiz/sunbiz-agent
   sudo chmod 750 /srv/sunbiz
   ```
2. Reinstall pm2 + cloudflared as the sunbiz user. Easiest path: stop
   the root-owned daemons (`pm2 stop all && pm2 delete all && pm2 kill`
   as root), then as the sunbiz user re-`pm2 start ecosystem.config.js`
   from each repo's directory. `pm2 startup` + `pm2 save` so the new
   user-scoped daemons restart on reboot.
3. Verify the warm-pool guard is now happy:
   ```
   curl -sS -H "Authorization: Bearer oasis_bridge_FV5jYKH9xe0FTaEOZkIeJXYHVM1v1eJURsT8zKlLvXc" -X POST -H "Content-Type: application/json" -d '{"messages":[{"role":"user","content":"hi"}],"agent":"solara"}' http://127.0.0.1:9100/chat | head -1
   ```
   And check `pm2 logs claude-bridge --lines 10` for the warm-pool
   "spawned warm" log line. If still cold every turn, fall back to
   accepting the cost — CC can revisit.

## After everything above lands

Run `python /srv/sunbiz/sunbiz-agent/scripts/doctor.py --json` once
more. Every check should report `"status": "ok"`.

Then review `fix/vps-readiness-patches`:
```
cd /srv/sunbiz/ceo-agent && git log --oneline main..fix/vps-readiness-patches
cd /srv/sunbiz/ceo-agent && git diff main fix/vps-readiness-patches --stat
```

If the diff is clean and the new commits this round are also there,
merge to main:
```
git checkout main && git merge --no-ff fix/vps-readiness-patches -m "Merge fix/vps-readiness-patches: bearer + daily_plans + SMS namespace"
```

DO NOT push yet — CC pushes the merge from his PC after his own diff
review. Report that the branch is merged locally and ready for him to
push.

## Final report

Write a Markdown report to `/srv/sunbiz/final-readiness.log` in this
exact shape:

```
=== SunBiz VPS Finalization — {ISO timestamp} ===

[1] Bridge bearer enforced        : YES / NO — {curl probe result}
[2] daily_plan_items live          : YES / NO — {row count after first run}
[3] BRAVO_FORCE_DRY_RUN            : 0 / 1 — {if 0, log line from first live drip}
[4] SUNBIZ_AGENT_HMAC_SECRET set  : YES / NO
[5] SMS namespace                  : SUNBIZ_TWILIO_* / unprefixed / both
[6] Bridge running as              : sunbiz / root
[7] Doctor check                   : ALL OK / FAILING — {list failing}
[8] fix/vps-readiness-patches      : merged locally / unmerged

Readiness estimate: {%}
```

Plus a one-paragraph plain-English summary addressed to CC: what's now
operational, what still needs his action, and which of the still-
external creds (Twilio, JotForm, Kixie, TextTorrent) is the most
valuable to unblock next.

## Constraints — non-negotiable

1. NEVER push to git from this VPS. Commit local merges only — CC pushes.
2. NEVER mint or guess secrets. The two values in this prompt are the
   only secrets you should write today.
3. NEVER trigger an outbound send in your diagnostic curls. The
   "verified" smoke test in blocker 1 step 5 is a chat-only request —
   no send_email / send_sms tool invocation in the body.
4. NEVER flip `BRAVO_FORCE_DRY_RUN=0` until blockers 1 + 4 + 5 are
   done. Flip it last, watch one drip, then stop.
5. If any blocker can't be closed cleanly, leave it open and surface
   in the report — partial progress is better than a broken state.

Begin Blocker 1 now.
