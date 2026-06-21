# VPS Kixie Agent Turnkey — Paste into Claude Code on the SunBiz VPS

> **For CC:** Copy the fenced block below into the Claude Code session running
> on the SunBiz VPS (`/srv/sunbiz`). This wires up per-agent Kixie phone
> numbers, verifies the Kixie integration end-to-end, and makes click-to-call
> operational from the dashboard lead drawer.
>
> **Date:** 2026-06-19
> **Prerequisite:** VPS is already running (PM2 daemons online, bridge paired,
> `.env.agents` has `KIXIE_API_KEY` + `KIXIE_BUSINESS_ID`).
> **Missing:** Jordan (Adon) Kixie number — CC to provide separately.

---

```text
You are Solara running on the SunBiz production VPS (/srv/sunbiz: ceo-agent + sunbiz-agent).
Scope: SunBiz tenant ONLY (tenant_id=aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110).
Do NOT touch Maven, Atlas, Aura, or any non-SunBiz repo/tenant.

CONTEXT — Kixie Integration Turnkey (2026-06-19):
CC has obtained per-agent Kixie phone numbers. The goal is to make click-to-call
fully operational: when an agent clicks a lead in the dashboard, Kixie dials from
that agent's specific number. The front-end click-to-call UI is already built into
the lead drawer — it needs the backend wiring completed.

AGENT ROSTER (SunBiz team):
  - Ezra (also known as Matt) — OWNER
    Kixie number: 3236458570
  - Ethan (also known as Alex) — MEMBER
    Kixie number: 17543243727
  - Jordan (also known as Adon) — ADMIN
    Kixie number: PENDING (CC will provide)

PHASE 1 — VERIFY CURRENT KIXIE ENV STATE (read-only):

1. Check which Kixie env vars exist (key names ONLY, never print values):
   grep -c '^KIXIE_' /srv/sunbiz/ceo-agent/.env.agents
   grep '^KIXIE_' /srv/sunbiz/ceo-agent/.env.agents | cut -d= -f1

   Required keys: KIXIE_API_KEY, KIXIE_BUSINESS_ID.
   If either is missing, STOP and tell CC — these are the Kixie account credentials
   that must be entered manually.

2. Check user_profiles for the SunBiz tenant:
   /srv/sunbiz/ceo-agent/.venv/bin/python -c "
   from lib.secret_loader import load_env
   import os
   for k,v in load_env().items(): os.environ.setdefault(k,v)
   from supabase import create_client
   sb = create_client(os.environ['BRAVO_SUPABASE_URL'], os.environ['BRAVO_SUPABASE_SERVICE_ROLE_KEY'])
   r = sb.table('user_profiles').select('id, email, display_name, role, phone').eq('tenant_id', 'aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110').execute()
   for u in r.data or []: print(f'{u.get(\"display_name\",\"?\")} | {u.get(\"email\",\"?\")} | role={u.get(\"role\",\"?\")} | phone={u.get(\"phone\",\"?\")}')
   "

   Record each agent's user_profile.id and email — needed for Phase 2.

3. Report findings before proceeding.

PHASE 2 — UPDATE .env.agents WITH PER-AGENT KIXIE NUMBERS:

Add the following to /srv/sunbiz/ceo-agent/.env.agents (append, do not overwrite
existing KIXIE_API_KEY or KIXIE_BUSINESS_ID):

   # Kixie per-agent phone numbers (2026-06-19)
   # These are the Kixie outbound caller-ID numbers assigned to each SunBiz agent.
   # The click-to-call flow in the dashboard uses these to dial from the
   # correct agent line.
   KIXIE_AGENT_EZRA_NUMBER=3236458570
   KIXIE_AGENT_ALEX_NUMBER=17543243727
   # KIXIE_AGENT_JORDAN_NUMBER=<PENDING — CC to provide>

   # Default Kixie agent email — used for automated drip SMS when no specific
   # agent is acting. Set to Ezra (owner) as fallback:
   KIXIE_DEFAULT_AGENT_EMAIL=<Ezra's email from user_profiles — fill from Phase 1 step 2>

After writing:
   chmod 600 /srv/sunbiz/ceo-agent/.env.agents
   ls -la /srv/sunbiz/ceo-agent/.env.agents   # confirm -rw-------

PHASE 3 — UPDATE user_profiles WITH KIXIE PHONE NUMBERS:

The dashboard lead drawer's click-to-call button looks up the logged-in agent's
phone from user_profiles.phone (or a kixie-specific field if one exists in
user_integration_credentials). Update each agent's phone number in user_profiles:

   /srv/sunbiz/ceo-agent/.venv/bin/python -c "
   from lib.secret_loader import load_env
   import os
   for k,v in load_env().items(): os.environ.setdefault(k,v)
   from supabase import create_client
   sb = create_client(os.environ['BRAVO_SUPABASE_URL'], os.environ['BRAVO_SUPABASE_SERVICE_ROLE_KEY'])
   tenant = 'aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110'

   # Get all SunBiz user profiles
   r = sb.table('user_profiles').select('id, email, display_name').eq('tenant_id', tenant).execute()
   for u in r.data or []:
       print(f'  {u[\"display_name\"]} ({u[\"email\"]}) → id={u[\"id\"]}')
   "

Then update each agent's phone:

   For Ezra (match by email or display_name from above):
   sb.table('user_profiles').update({'phone': '3236458570'}).eq('id', '<EZRA_USER_ID>').execute()

   For Alex/Ethan (match by email or display_name):
   sb.table('user_profiles').update({'phone': '17543243727'}).eq('id', '<ALEX_USER_ID>').execute()

   Skip Jordan — number pending.

Verify updates:
   sb.table('user_profiles').select('display_name, phone').eq('tenant_id', tenant).execute()

PHASE 4 — VERIFY KIXIE API CONNECTIVITY (no real calls):

Test that the Kixie API key works without placing an actual call:

   /srv/sunbiz/ceo-agent/.venv/bin/python -c "
   from lib.secret_loader import load_env
   env = load_env()
   key = env.get('KIXIE_API_KEY', '')
   bid = env.get('KIXIE_BUSINESS_ID', '')
   print(f'API key present: {bool(key.strip())} (len={len(key)})')
   print(f'Business ID present: {bool(bid.strip())} (len={len(bid)})')
   if key.strip() and bid.strip():
       print('Kixie credentials configured — ready for click-to-call')
   else:
       print('ERROR: Missing Kixie credentials')
   "

If available, also verify with the kixie_tool.py status command:
   /srv/sunbiz/ceo-agent/.venv/bin/python /srv/sunbiz/sunbiz-agent/scripts/kixie_tool.py status --json 2>/dev/null || echo "kixie_tool.py not available — API key check above is sufficient"

PHASE 5 — RESTART DAEMONS + VERIFY:

   pm2 restart all --update-env
   pm2 list
   pm2 logs --lines 10 --nostream

All daemons should be online with no restart loops.

PHASE 6 — REPORT:

Append to /srv/sunbiz/diagnostic.log:

   === Kixie Turnkey — {ISO timestamp} ===
   [1] KIXIE_API_KEY present        : YES / NO
   [2] KIXIE_BUSINESS_ID present    : YES / NO
   [3] Ezra phone set (3236458570)  : YES / NO — user_profiles.id=<id>
   [4] Alex phone set (17543243727) : YES / NO — user_profiles.id=<id>
   [5] Jordan phone set             : PENDING — CC to provide number
   [6] KIXIE_DEFAULT_AGENT_EMAIL    : <value> (no secret)
   [7] PM2 daemons post-restart     : N/N online
   [8] Kixie API connectivity       : OK / MISSING CREDS

   Operational status: Click-to-call is READY / BLOCKED on [reason]

Report to CC in plain English:
- What's now wired up
- That Jordan's Kixie number is still needed
- That the front-end lead drawer click-to-call should work for Ezra and Alex
  once they log into the dashboard — the portal reads their phone from
  user_profiles and initiates the Kixie click-to-call API
- Any issues found

CONSTRAINTS (non-negotiable):
1. Never echo secret values (API keys, tokens). Key names only.
2. Never push to git from this VPS.
3. Never place a real call or send a real SMS — dry verification only.
4. Never modify user_profiles for any tenant other than SunBiz.
5. If KIXIE_API_KEY or KIXIE_BUSINESS_ID is missing, STOP and ask CC.
6. Keep BRAVO_FORCE_DRY_RUN at its current value — do not flip it.

Begin Phase 1 now.
```

---

## After the VPS run — what CC still needs to do

1. **Jordan's Kixie number:** Get from Adon and re-run this prompt with the
   number added, or manually append `KIXIE_AGENT_JORDAN_NUMBER=<number>` to
   `.env.agents` and update his `user_profiles.phone` via the dashboard Settings.

2. **Front-end portal (input manually):** The dashboard's lead drawer click-to-call
   is already built. Each agent's Kixie number is pulled from `user_profiles.phone`.
   Once the VPS agent writes those numbers, clicking a lead's phone in the dashboard
   should trigger a Kixie click-to-call through the API.

3. **Verify live:** Log in as each agent (Ezra, Alex), open a lead, click the
   phone number → the Kixie widget should initiate the call from their assigned
   number.
