# OASIS Command Center — Final Auth Setup

Three things you need to do **once**, in order. ~10 minutes total. After this, everything works.

---

## What's actually shipped (vs. what's nominally "merged")

The honest version: **two Vercel projects still exist** under the hood —
`oasisai-platform` (Vite marketing site) and `agent-dashboard` (Next.js
Command Center). Different stacks, different bundlers, different Vercel
deploys.

What I did ship is a **transparent proxy**: `oasisai.work/app/*` → the
Command Center URL, via a Vercel rewrite in the platform repo. From your
perspective and your clients' perspective, it's one product at one URL —
`oasisai.work` for marketing, `oasisai.work/app` for the dashboard. Both
share the same Supabase project, so cookies set on `oasisai.work` are
visible to both sides.

A *real* one-Vercel-project merge (single deployment, one build pipeline)
would require either porting the marketing site to Next.js or porting the
dashboard to Vite — that's a 4-8 hour refactor. The proxy gets you 95% of
the user-facing benefit at zero refactor risk. Future session if you want
to consolidate.

---

## 1. Set Supabase Auth Site URL + Redirect URLs (3 min)

### Where
[Supabase Dashboard → bravo project → Authentication → URL Configuration](https://supabase.com/dashboard/project/phctllmtsogkovoilwos/auth/url-configuration)

### What to set

**Site URL** (one field):
```
https://oasisai.work/app
```

**Redirect URLs** (paste all of these into the "Redirect URLs" allow-list, one per line):
```
https://oasisai.work/app/**
https://agent-dashboard-cc90210.vercel.app/**
http://localhost:3100/**
```

Click **Save**.

### Why
- The Site URL is what Supabase uses as the base for password-reset emails. Pointing it at `oasisai.work/app` means the link in your inbox sends you to the merged URL.
- The redirect allow-list is Supabase's safety check — it refuses to send you back to a URL that isn't on the list.

---

## 2. Enable Google OAuth (4 min)

### Step A — Get a Google OAuth client

1. Open [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials)
2. **Create Credentials** → **OAuth client ID** → **Web application**
3. Name it `OASIS Command Center`
4. Under **Authorized redirect URIs** add this **exactly**:
   ```
   https://phctllmtsogkovoilwos.supabase.co/auth/v1/callback
   ```
5. Click **Create**
6. Copy the **Client ID** and **Client secret** that appear

### Step B — Paste into Supabase

1. Open [Supabase Dashboard → Authentication → Providers](https://supabase.com/dashboard/project/phctllmtsogkovoilwos/auth/providers)
2. Find **Google**, click to expand
3. Toggle **Enable Sign in with Google** to ON
4. Paste **Client ID (for OAuth)** and **Client Secret (for OAuth)**
5. Click **Save**

Done. "Sign in with Google" on the login page now works.

---

## 3. Reset your password (1 min) — fixes the broken link from earlier

The page that the reset email linked to didn't exist when you clicked it
(just shipped now: `/auth/reset-password`). The flow:

1. Go to [https://oasisai.work/app/forgot-password](https://oasisai.work/app/forgot-password)
2. Enter `conaugh@oasisai.work`
3. Click the link in your inbox — now lands on a working form at
   `/auth/reset-password` (Step 1's Site URL config makes it route there)
4. Set your password
5. You're signed in

OR — once Step 2 is done — just click "Sign in with Google" and skip the
password entirely.

**One important note**: the reset form depends on Supabase's recovery token
arriving via the URL fragment. If Step 1 (Site URL) isn't completed, the
old reset emails will still send you to a non-existent URL. Do Step 1
*before* requesting a new reset email.

---

## SSO — does signing in on `oasisai.work` automatically sign me in on `/app`?

**Probable yes, but not verified.** Both sides share:
- The same Supabase project (`phctllmtsogkovoilwos`)
- The same domain (`oasisai.work`) — because of the rewrite, the dashboard's
  cookies are scoped to `oasisai.work`, the same domain the marketing site
  uses

In theory, signing into one signs you into the other. To verify:
1. Sign into `oasisai.work` (marketing site auth flow)
2. Visit `oasisai.work/app/` directly — should NOT redirect you to /login
3. If it does, the marketing site's auth helpers and the Command Center's
   `@supabase/ssr` aren't reading the same cookie. Fix in next session.

---

## VPS provisioning (whenever you're ready, ~15 min)

Per `infra/inbound-poller/README.md`. The TL;DR:

```bash
# On your laptop:
hcloud server create --name oasis-inbound-poller --type cx22 --image debian-12 --ssh-key your-key --location nbg1

# SSH in:
ssh root@<vps-ip>
apt update && apt install -y docker.io docker-compose-plugin git
git clone https://github.com/CC90210/CEO-Agent.git /opt/oasis
scp .env.agents root@<vps-ip>:/opt/oasis/.env.agents   # from your laptop
cd /opt/oasis/infra/inbound-poller && docker compose up -d --build
```

Within 5 minutes Settings → Integrations should show **n8n_inbound: healthy**
with a fresh `last_ping_at` from the VPS, and you can shut down your local
laptop without losing inbound classification.
