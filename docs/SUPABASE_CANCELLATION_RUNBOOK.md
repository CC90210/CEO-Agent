---
tags: [turso, supabase, migration, runbook, cancellation]
---

# Supabase cancellation runbook

> Status as of **2026-08-07**. Written to be executed top to bottom. Every step
> has a verification command; do not advance on a step whose check did not pass.
>
> Related: [[skills/turso-patterns/SKILL]] · [[CONTEXT]] · [[brain/APP_REGISTRY]]

## Where things stand

**Do not cancel yet.** Four items remain and three of them need CC. Everything
else is built, deployed, and verified by execution.

| Layer | State | Evidence |
|---|---|---|
| **Data** | ✅ complete | `migration_completeness_audit.py` — bravo 161/161, breeze 46/46, oasis 17/17, propflow 43/43, nostalgic 8/8. `DATA VERDICT: ALL DATA ACCOUNTED FOR` |
| **Auth** | ✅ built + executed | `verify_turso_auth.py` 20/20 against the live db, **with the Supabase service-role key absent from the process** |
| **Storage** | ✅ code done, ⛔ needs R2 keys | 4,118 objects archived + hash-verified; R2 adapter in all 4 apps; SigV4 checked against AWS's published vector |
| **Realtime** | ✅ replaced | `verify_nudge_poll.py` 8/8, including scope isolation |
| **n8n** | ⛔ needs CC | 5 nodes in 3 ACTIVE workflows still write to Supabase |
| **PM2 harness** | ⛔ needs CC | **also DOWN since 2026-08-05 14:41 UTC** (unrelated reboot). Cutover flag is opt-in via `EMPIRE_TURSO_CUTOVER=1`, so `pm2 start` recovers on Supabase |
| **PropFlow prod** | ⛔ needs CC | PR #3; production env vars are preview-only |

## Step 1 — R2 credentials (CC, ~5 minutes)

The only genuinely missing credential. Cloudflare dashboard → **R2** →
*Manage API tokens* → **Create API token** (Object Read & Write). The account id
is on the R2 Overview page.

Add to the agents env:

```
CLOUDFLARE_ACCOUNT_ID     R2_ACCESS_KEY_ID     R2_SECRET_ACCESS_KEY
R2_BUCKET                 R2_PUBLIC_BASE_URL
```

Verify: `python scripts/etl_storage_to_r2.py --check` → `READY`

## Step 2 — publish the objects (agent, ~10 min for 3.1 GB)

```bash
python scripts/etl_storage_to_r2.py --project bravo --plan
python scripts/etl_storage_to_r2.py --project bravo --apply
python scripts/etl_storage_to_r2.py --project bravo --verify
```

Repeat for `propflow` and `nostalgic` (breeze and oasis have zero objects).

`--verify` fetches an object through the **public URL** and re-hashes it —
"the object exists" and "the URL the apps use serves it" are different claims.
Do not proceed unless `public_url_serves_correct_bytes` is true.

Then set the same R2 vars on each Vercel project:

```bash
python scripts/integrations/vercel_env_tool.py set --project <slug> --key R2_ACCOUNT_ID --value ... --env production
```

Storage stays on Supabase until these exist — that is the deliberate fallback.

## Step 3 — n8n (CC approves, agent executes)

Three ACTIVE workflows insert into `automation_logs` in the oasis project via
credential *"Oasis SupaBase"*: **Shopify Automation**, **Oasis Voice Agent**,
**GrapeVine Cottage Automations** (a paying client).

**No env var, no deploy, and no rollback flag touches n8n.** It must be edited.
The replacement endpoint already exists and was proven end-to-end:
`POST /api/ingest/automation-log` on the dashboard.

Mitigating detail: all five nodes are terminal — downstream of the Sheets
append / SMS send / webhook response — so a failure there does not stop the
client-visible action. But every execution goes red, because all five have
`onError=None`.

This is a production mutation on a paying client's automations, so it waits for
an explicit yes.

## Step 4 — the Bravo harness (CC, one command)

The harness is currently DOWN (since 2026-08-05 14:41 UTC, an unrelated reboot
without `pm2 resurrect`). Recover it first with a plain `pm2 start
ecosystem.config.js` — that restores it on Supabase, exactly as it ran before.

The cutover is a separate, deliberate command:

```bash
EMPIRE_TURSO_CUTOVER=1 pm2 restart bravo-scheduler bravo-telegram bravo-coord     claude-bridge claude-bridge-ping event-router --update-env
pm2 save
```

The flag is OPT-IN: without `EMPIRE_TURSO_CUTOVER=1` the config starts the
harness on Supabase. That keeps outage recovery (`pm2 start`) independent of the
migration cutover — a plain restart must never move the data plane by accident.

A plain `pm2 restart` re-uses the environment captured at spawn and will **not**
pick this up — `--update-env` is required. Verify the patch actually took,
rather than trusting the flag:

```bash
python -c "import supabase; print(supabase.create_client.__module__)"
# lib.turso_supabase_compat  -> patched
# supabase._sync.client      -> NOT patched
```

Do **not** put this variable in the agents env file: `sitecustomize.py` reads
`os.environ` at interpreter start, and that file loads later — the flag would
read as set while the harness quietly kept using Supabase.

## Step 5 — PropFlow production (CC decides)

Merge PR #3, then set the three flags on the **production** target (they are
preview-only today) and push the propflow credential pair:

```bash
python scripts/integrations/vercel_turso_sync.py --project real-estate-app --db propflow --env production
```

Before flipping, run the tenant-boundary proof — 627 RLS policies were replaced
by a route, and this is what shows the boundary held:

```bash
python realestate-App/scripts/verify_tenant_isolation.py
```

## Step 6 — final gate, immediately before cancelling

```bash
python scripts/migration_completeness_audit.py          # ALL DATA ACCOUNTED FOR
python scripts/etl_storage_to_r2.py --all --verify      # objects + public URL
python scripts/etl_supabase_to_turso.py --project bravo --allow-overwrite   # final delta
python scripts/etl_supabase_to_turso.py --project oasis --allow-overwrite
```

The last two matter because Supabase keeps receiving writes until every writer
has moved. Run them **after** n8n and PM2 are switched, not before — otherwise
they capture a moment that is already stale.

Take a final export while the project still exists. Every export tool needs
`SUPABASE_ACCESS_TOKEN` and dies with the project; there is no second chance.

## Rollback, at every point above

Unset `EMPIRE_DATA_BACKEND` / `EMPIRE_AUTH_BACKEND` (or the R2 vars) and the
affected app returns to Supabase with no deploy. **That is why Supabase must
stay paid until the last item above is green** — the rollback path runs through
it.

## Things that will NOT be true after cancellation

Stated so nobody is surprised:

- **Supabase Auth admin tooling is gone.** Password reset, invites and OAuth run
  through the `turso-*` routes. There is no Supabase dashboard to click.
- **`storage.list()` is not implemented** on the R2 adapter — deliberately. It
  refuses rather than returning an empty array, because an empty list is
  indistinguishable from "this merchant has no documents".
- **Live refresh is polled, not pushed.** Seconds, not ~100ms.
- **`rpc()` fails closed** under Turso mode. PL/pgSQL did not migrate; an
  unported RPC raises `TURSO_RPC_BLOCKED` rather than silently splitting writes
  across two databases.
