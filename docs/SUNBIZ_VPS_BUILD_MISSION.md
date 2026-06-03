# SunBiz VPS — Build Mission (3 backend builds + gap closure), turnkey

> Paste the block below into a **Claude Code** session on the SunBiz VPS, launched from
> `/srv/sunbiz/sunbiz-agent`. It is code-grounded (every file:line / event / stage key
> below was verified against the live repos on 2026-06-03). Do the **bring-up first**
> (`docs/SUNBIZ_VPS_TURNKEY_SYSTEM_MESSAGE.md`), then these builds. Keep
> `BRAVO_FORCE_DRY_RUN=1` until CC approves real sends. Verify each build before moving on.

---

```text
You are on the SunBiz production VPS (/srv/sunbiz: ceo-agent + sunbiz-agent). You are Solara's
builder. First: cd /srv/sunbiz/ceo-agent && git pull && cd /srv/sunbiz/sunbiz-agent && git pull
to get the latest (email guards, smtp_send chokepoint guard, provision_secrets, the Phase-3d
conversations/campaigns/send-mode cluster, advanced_picker). Read sequence_runner.py,
scripts/core/event_bus.py, scripts/integrations/send_gateway.py, and database/071_stage_model_v3.sql
before editing. Keep BRAVO_FORCE_DRY_RUN=1. Never print secrets. Report evidence after each build.

Canonical facts you MUST honor (verified):
- Deal stage lives in tenant_records.data->>'deal_stage' (migration 071). Canonical values:
  'Application In','Missing Info','Shopping','Funded','Declined','Dead'. ACTIVE = the first three.
  Use deal_stage, NOT the legacy 'stage' key, or queries miss rows.
- Contact is logged in lead_interactions (lead_id, tenant_id, direction 'inbound'|'outbound',
  type 'sms_received'|'email_received'|'sms_sent'|'email_sent', created_at UTC, metadata JSONB).
- Drips: drip_sequences + sequence_state (migration 043). sequence_runner.enrollment_tick() reads
  agent_events WHERE event_type == drip_sequences.trigger_event, shallow-matches trigger_filter, then
  _enroll_step(). execution_tick() claims due rows + _send_step() -> CEO send_gateway.send().
- Events: scripts/core/event_bus.py publish() (~line 117-188) with idempotency_key + offline fallback
  to tmp/events_offline.jsonl. Today's trigger event is BRAVO_RECORD_STATUS_CHANGED.
- send_gateway.send() (send_gateway.py ~1777) takes sms_provider=None|'texttorrent'|'twilio'|'kixie';
  _send_sms_via_provider (~1560) routes it. If BOTH TT + Twilio are configured and no sms_provider is
  passed, it defaults to TextTorrent — so an explicit provider is REQUIRED to force Twilio.
- agent_source must be in KNOWN_AGENT_SOURCES (send_gateway.py ~209-218) or send() rejects the call.

================ BUILD 1 — Active-deal 24h-no-contact follow-up (auto-stop + revert) ================
Goal: an active deal with ZERO inbound contact for 24h auto-enrolls in an escalating SMS->email
re-engagement drip; ANY inbound (text/call/email) cancels the drip and reverts the deal to active.
Steps (mostly reuse; ~1 new daemon, NO schema change):
1. New daemon SunBiz-Agent/scripts/no_contact_24h_monitor.py. Mirror sequence_runner.py structure
   (_supabase, _read_cursor/_write_cursor at state/no_contact_24h.cursor, _log). Each tick (default
   1800s): SELECT lead_id,tenant_id,deal_stage FROM tenant_records WHERE deal_stage IN
   ('Application In','Missing Info','Shopping') AND NOT EXISTS (SELECT 1 FROM lead_interactions li
   WHERE li.lead_id=tenant_records.id AND li.direction='inbound' AND li.created_at > NOW()-'24h'::interval).
   For each, event_bus.publish('NO_CONTACT_24H', {lead_id, tenant_id, deal_stage, last_contact_at_iso},
   idempotency_key=f'no_contact_24h:{lead_id}:{run_date}'). Implement the same offline fallback as event_bus.
   CLI: `loop --interval 1800` and `once`.
2. sequence_runner.enrollment_tick() (~line 471): make the sequence lookup match trigger_event in
   {'BRAVO_RECORD_STATUS_CHANGED','NO_CONTACT_24H'}. For NO_CONTACT_24H, read lead_id from
   payload['lead_id']. Reuse _filter_matches, _has_active_state, _enroll_step unchanged.
3. Seed the drip in oasis-command-center/lib/sunbiz-default-sequences.ts: 9th SUNBIZ_DEFAULT_SEQUENCES
   entry, trigger_event='NO_CONTACT_24H', trigger_filter={}, one_per_lead=true, enabled_on_seed=false
   (operator opts in). Steps: SMS @0 ("Hey {{lead.contact_name}}, checking in on {{lead.business_name}}
   — still working on options for you"), then SMS @ ~1 day ("Can you give me a call when you get a
   chance? Want to know where your head's at"), from_label='Solara'. Add the row to buildSunbizSequenceRows.
4. AUTO-STOP on inbound: in the inbound webhooks (oasis-command-center app/api/webhooks/texttorrent/
   sms-inbound/route.ts ~213, the Kixie inbound handler, and the email reply path) AFTER inserting the
   lead_interactions row, cancel in-flight drips for that lead:
   db.from('sequence_state').update({status:'cancelled'}).eq('lead_id',leadId).eq('tenant_id',tenantId)
   .in('status',['scheduled','failed']). (sequence_runner._cancel_drips_for_lead at ~349 is the daemon-side
   equivalent — reuse its semantics; don't double-cancel.)
5. REVERT stage on inbound: ONLY if current deal_stage is active (Application In/Missing Info/Shopping)
   AND it was put there by the no-contact flow (guard against un-declining). Prefer a Supabase RPC
   rpc_revert_deal_stage(p_lead_id,p_to) that does jsonb_set(data,'{deal_stage}', ...) AND emits
   BRAVO_RECORD_STATUS_CHANGED {entity:'lead',record_id,field:'deal_stage',from,to,tenant_id} atomically,
   then notify the assigned rep for manual takeover.
GOTCHAS: idempotency_key prevents the monitor-emit vs inbound-cancel race double-enrolling; created_at is
UTC; sequence_runner may have already CLAIMED a due row before the cancel lands (accept one possible last
send, or check status at fire time in _send_step); event_bus offline fallback must be mirrored in the monitor.
VERIFY (dry-run): insert a test active lead with last inbound >24h ago; run `no_contact_24h_monitor once`;
confirm a NO_CONTACT_24H agent_events row + a sequence_state row; insert an inbound lead_interactions row;
confirm sequence_state flips to cancelled and deal_stage reverts. No real SMS (BRAVO_FORCE_DRY_RUN=1).

================ BUILD 2 — Twilio as a 3rd channel on the signed_application bank-statement nag ============
Goal: the signed-application bank-statement nag fires over email + TextTorrent + Twilio.
NO migration needed (drip_sequences.steps is JSONB; sms_provider is an app-level field).
1. lib/drips/types.ts (~20-39): add optional `sms_provider?: 'texttorrent'|'twilio'|'kixie'` to DripStep.
   Validate it in BOTH parsers: the dashboard step parser (parseDripSteps in app/api/sequences) and
   sequence_runner's step parse — code-layer validation is the hard gate.
2. sequence_runner._send_step (~542): when the step has sms_provider, pass it into
   send_gateway.send(channel='sms', sms_provider=step['sms_provider'], ...). Log metadata.sms_provider
   on the lead_interactions row for audit.
3. lib/sunbiz-default-sequences.ts signed_application sequence (~216-240): the SMS step that nags for
   bank statements — duplicate it / add a step with sms_provider='twilio' (email step unchanged). Keep
   the existing TextTorrent SMS step too if you want both SMS providers; otherwise set the SMS step's
   provider explicitly so it's deterministic (don't rely on auto-detect when TT+Twilio are both set).
ENV (VPS): TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER (or the brand-specific
TWILIO_FROM_NUMBER_*). A Twilio from-number must be registered for brand 'sunbiz'.
GOTCHAS: provider is STEP-level not sequence-level; cooldown/daily-cap are CHANNEL-level ('sms', 30/day
shared across TT+Twilio); old steps without sms_provider keep working (fall back to env/auto-detect).
VERIFY (dry-run): a lead entering signed_application enrolls and the SMS step logs metadata.sms_provider='twilio'.

================ BUILD 3 — Outbound blast scheduler (email + SMS, scheduled cold outreach) =================
Reuse: cold_outreach_campaigns + cold_outreach_recipients (migration 069, has scheduled_for + channel
'email'|'sms_texttorrent'|'sms_twilio'); cold_outreach_runner.py; the dashboard /email-blast page (currently
a ComingSoon placeholder) + POST /api/manifest/[slug]/cold-outreach/campaigns (already accepts scheduled_for).
1. FIRST: add 'cold_outreach_runner' to KNOWN_AGENT_SOURCES (send_gateway.py ~209-218) — without it,
   send() rejects every call. (This is the #1 silent failure.)
2. cold_outreach_runner.py: add `_promote_scheduled_campaigns()` run at the TOP of each tick — UPDATE
   cold_outreach_campaigns SET status='queued' WHERE status='draft' AND scheduled_for IS NOT NULL AND
   scheduled_for <= now() (UTC). The existing tick() (~427-480) already drains 'queued' one-per-tick with
   daily_cap; promotion just feeds it. (A promoted campaign is picked up on the NEXT tick, not the same one.)
3. Twilio path: cold_outreach_runner already calls send_gateway.send(); for channel='sms_twilio' pass
   sms_provider='twilio' (channel arg to send_gateway is always 'sms'; provider distinguishes). Check
   result['status'] != 'error' (send_gateway returns a status dict, never raises) before marking the
   recipient 'sent'.
4. Dashboard: replace app/email-blast/page.tsx ComingSoon with an Email + SMS blast composer (list/segment
   picker, body/subject, optional schedule time) + a campaign history table; POST to
   /api/manifest/sun/cold-outreach/campaigns with scheduled_for. Owner/admin gate. `next build` must pass.
5. PM2: register cold_outreach_runner as a persistent daemon (loop --interval 30, restart_delay 30000ms)
   in SunBiz-Agent/ecosystem.config.js next to sunbiz-sequence-runner; pm2 save.
GOTCHAS: scheduled_for is timestamptz (compare in UTC); a Twilio from-number must be registered per brand;
daily-cap is enforced in BOTH the runner and send_gateway (intentional defense-in-depth).
VERIFY (dry-run): create a campaign with scheduled_for=now()+1min; confirm the runner promotes draft->queued
at that time and drains recipients via send_gateway in dry-run (no real sends).

================ GAP CLOSURE (config + small fixes; mostly not on the VPS) ================
- Employee chat (Jordan/Alex/Emily): the dashboard already uses the full ChatWidget. To turn it on:
  (a) flip the live manifest — run from oasis-command-center where service-role creds exist:
      node scripts/set-manifest-flag.mjs --tenant sun --flag advanced_picker --value true --apply
  (b) set NEXT_PUBLIC_BRIDGE_CHAT_BASE on Vercel to this VPS's bridge URL (https://portal.sunbizfunding.com),
      expose bridge_chat_server :9100 via nginx/TLS, and CORS-allow the dashboard origin so the browser
      probe + exec-tool proxy reach it.
  (c) set a tenant-default AI provider key in Settings -> AI Setup (else non-operators get "not connected").
- TextTorrent auth: the Python send path reads TEXTTORRENT_API_KEY as a Bearer token, but the TS client
  expects api_sid + api_public_key. CONFIRM with TextTorrent which scheme is correct; if SID+public-key,
  add TEXTTORRENT_API_SID + TEXTTORRENT_API_PUBLIC_KEY to provision_secrets ENV_MAP + send_gateway, or SMS
  via TT will fail auth. Do not guess.
- Migrations: SunBiz-Agent high-water is 077; only Build 1/2/3 optional doc-migrations would be 078+ (none
  are required — all three builds use existing schema).

If anything here conflicts with the live code, trust the code and tell CC the discrepancy before building.
```
