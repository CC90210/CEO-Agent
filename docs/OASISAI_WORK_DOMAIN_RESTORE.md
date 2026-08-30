---
tags: [domain, cloudflare, dns, vercel, incident, oasisai]
---

# Restoring oasisai.work

> Written 2026-08-07 after the new card was added. Renewal is step 1 of 3 —
> **renewing alone will not bring the site back**, because the DNS records are
> gone. Related: [[docs/SUPABASE_CANCELLATION_RUNBOOK]] · [[brain/APP_REGISTRY]]

## What is actually wrong

Verified via Cloudflare's DNS-over-HTTPS resolver (JSON, no output guessing):

| Record | State | Consequence |
|---|---|---|
| `A oasisai.work` | `172.64.80.1` — Cloudflare parking | site serves a "Cloudflare Registrar" page |
| `A www.oasisai.work` | `172.64.80.1` | same |
| `MX oasisai.work` | **does not exist** | external mail to @oasisai.work cannot be delivered |
| `TXT oasisai.work` | **does not exist** | SPF/DKIM/DMARC gone; sent mail fails auth |
| `NS` | `damian` + `sydney.ns.cloudflare.com` | zone itself is intact — only the records are missing |

Vercel's own domain config API reports `misconfigured: true` for both hostnames.

The zone surviving while the records vanished is why renewal is not enough.

## Step 1 — renew (you, Cloudflare dashboard)

Cloudflare → **Domain Registration** → **Manage Domains** → `oasisai.work` →
confirm the new card is the payment method → **Renew**.

Check afterwards that auto-renew is ON. This lapsed because the card on file
expired; renewing without fixing auto-renew just resets the clock.

## Step 2 — restore DNS (you, ~5 minutes)

Cloudflare → `oasisai.work` → **DNS** → **Records**.

### Website (values from Vercel's API, not remembered)

Delete the parking `A`/`AAAA` records on `@` and `www` first, then add:

| Type | Name | Value | Proxy |
|---|---|---|---|
| A | `@` | `216.150.1.1` | **DNS only (grey cloud)** |
| A | `@` | `216.150.16.1` | **DNS only** |
| CNAME | `www` | `73042cb4ab35cb0e.vercel-dns-017.com` | **DNS only** |
| TXT | `_vercel` | `vc-domain-verify=www.oasisai.work,0f5cd83c301ada0e4adf` | n/a |

**Grey cloud, not orange.** Proxying through Cloudflare in front of Vercel is
what puts a Cloudflare IP in the A record, and it is how the parking page ends
up served instead of the app. Vercel terminates TLS itself.

The `_vercel` TXT is required — Vercel currently reports `www.oasisai.work` as
`verified: false` and will not serve it without that record.

### Mail

`GMAIL_USER` is an `@oasisai.work` address, so this domain is a Google Workspace
mail domain and needs MX restored. **Get the exact records from Google Admin**
(admin.google.com → Domains → Manage domains → your domain → Activate Gmail) —
Google has moved from the five legacy `ASPMX` hosts to a single `smtp.google.com`
record and which one applies depends on when the tenancy was created. Do not
copy MX values from a blog post.

You will also need the SPF TXT (`v=spf1 include:_spf.google.com ~all`), plus the
DKIM TXT that Google Admin generates for this domain, and a DMARC TXT if one was
in place before.

## Step 3 — verify (me, once you say go)

```bash
python scripts/fleet_health_check.py --project agent-dashboard
```

Expect `agent-dashboard -> ok` with `oasisai.work` returning `ok` on all six
probes instead of `PARKED`. DNS may take a few minutes; Cloudflare's own edge
usually updates within one.

Mail is verified separately by sending to the address and confirming delivery —
DNS resolving is not proof that a mailbox accepts mail.

## What this outage did and did not cause

**Did:** every client hitting `oasisai.work` since ~2026-07-07 got a parking
page — including the SunBiz form URLs. That is the breakage that was reported.

**Did not:** the Turso migration. The identical forms render and both API routes
validate correctly on the Vercel hostname; post-migration submissions land in
Turso complete and tenant-stamped, with zero missing a tenant.

**RESOLVED 2026-08-07.** The harness had been down since
**2026-08-05 14:41 UTC**. Its logs ended mid-cycle with no crash trace, and both
the scheduler and the telegram agent stopped at the same second — consistent with a
reboot without `pm2 resurrect`, not a fault. Inbound email processing stopped
with it (50–113/day through 2026-08-05, then nothing). This predated the
migration session by ~33 hours and was unrelated to it.

Root cause found during restore: the reboot fired the `PM2 Resurrect`
scheduled task via S4U (no interactive logon), where neither `HOME` nor
`HOMEPATH` is set — so PM2 silently defaulted to `pm2_home=C:\etc\.pm2`,
found no `dump.pm2` there, and left an **empty elevated daemon squatting on
the global `\\.\pipe\rpc.sock`**. Every user-session `pm2` call then failed
with `connect EPERM //./pipe/rpc.sock` and spawned another wedged daemon
(34 had piled up). Fix shipped in `scripts/pm2_resurrect_hidden.vbs` +
`scripts/pm2_resurrect_hidden.cmd`: pin `PM2_HOME`/`HOME`, `pm2 kill` first,
then resurrect + save. 10 apps + pm2-logrotate restored and `pm2 save`d.

**Still open (needs one elevated action from CC):** the task's RunLevel is
`Highest`, so after the next reboot the daemon runs elevated again and
unelevated `pm2` clients get EPERM. From an elevated PowerShell:

```powershell
$t = Get-ScheduledTask -TaskName 'PM2 Resurrect'
Set-ScheduledTask -TaskName 'PM2 Resurrect' -Principal `
  (New-ScheduledTaskPrincipal -UserId $t.Principal.UserId -LogonType S4U -RunLevel Limited)
```

That is safe to run as-is: the Turso cutover flag in `ecosystem.config.js` is
opt-in. `pm2 start` restores the harness exactly as it ran before, on Supabase.
Moving it to Turso is a separate, deliberate command:

```bash
EMPIRE_TURSO_CUTOVER=1 pm2 restart bravo-scheduler bravo-telegram bravo-coord     claude-bridge claude-bridge-ping event-router --update-env
pm2 save
```

(An earlier version of this file told you to comment the flag out first. That
was a footgun — recovering from an unrelated outage should never risk flipping
the data plane, so the config now gates it instead.)
