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

**Separate, and also open:** the PM2 harness has been down since
**2026-08-05 14:41 UTC**. Its logs end mid-cycle with no crash trace, and both
the scheduler and the telegram agent stop at the same second — consistent with a
reboot without `pm2 resurrect`, not a fault. Inbound email processing stopped
with it (50–113/day through 2026-08-05, then nothing). This predates the
migration session by ~33 hours and is unrelated to it.

To bring it back:

```bash
pm2 resurrect          # or: pm2 start ecosystem.config.js
pm2 save
```

Note that `ecosystem.config.js` now carries `EMPIRE_DATA_BACKEND=turso_cloud`,
so starting it fresh WILL move the harness to Turso. If you want it back on
Supabase first, comment that line out before starting, then restart with
`--update-env` when you are ready to cut over.
