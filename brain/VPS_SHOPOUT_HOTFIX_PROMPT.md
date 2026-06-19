# VPS Shop-Out Hotfix — paste this whole block into the Claude Code session running ON the SunBiz VPS

> **For CC:** copy everything inside the fenced block below into the Claude Code chat that is already
> running on the SunBiz VPS (the session at `/srv/sunbiz`). Do **not** SSH from Windows.
>
> **Two root causes:**
> 1. **Dead Gmail App Password (the auth_failed wall).** Ezra changed the submissions@sunbizfunding.com
>    Google **account** password last night. Google **revokes all app passwords when the account
>    password changes** — so the app password the VPS used is now invalid, which is why every shop-out
>    send today returns `auth_failed`. **FIX (CC):** generate a NEW app password at
>    https://myaccount.google.com/apppasswords (needs 2-step verification on that Google account), then
>    paste it where the VPS agent asks (the `<FILL_IN>` in Phase 3). This is NOT an "API credits" issue —
>    these sends are SMTP, which has no API quota; a quota problem would say "limit exceeded," not auth.
> 2. **draft_critic blocking lender submissions.** The `shop_out_sender.py` cron sends them through the
>    **cold-outreach** path (non-operator `agent_source`), so the critic rejects them. Fixed below by
>    making the cron operator-initiated (agent_source only; intent stays commercial so CASL still applies).

---

```
You are Bravo running on the SunBiz VPS. Scope: SunBiz only. Do NOT touch Maven, Atlas,
oasis-ai-platform, or any non-SunBiz tenant. This is a VERIFY-FIRST hotfix — re-run every diagnostic
live before you change anything; do not trust a description, fix what the code actually shows.

CONTEXT (claims to verify, not to act on blindly):
- The OASIS dashboard "Shop Out a Deal" queues application_lender_threads rows at status='pending',
  then triggers send. Two senders can pick up those pending rows:
  (a) the bridge tool _tool_shop_out_send_batch (operator-initiated: agent_source="manual_cc"), and
  (b) the cron `shop_out_sender.py` (this repo, /srv/sunbiz/sunbiz-agent or wherever it lives).
- send_gateway's draft-critic gate fires ONLY when the send is NOT operator-initiated AND
  intent=="commercial". OPERATOR_INITIATED_SOURCES is a frozenset in send_gateway.py.
- Hypothesis: shop_out_sender.py sends with a non-operator agent_source and/or intent=commercial, so
  the critic rejects lender submissions ("New Deal (...) — app + statements attached") as cold
  outreach. AND GMAIL_APP_PASSWORD is expired.

PHASE 1 — DIAGNOSE LIVE (read-only; report findings before editing):
1. Locate the cron: `find /srv/sunbiz -name shop_out_sender.py -not -path '*/node_modules/*'`.
2. In shop_out_sender.py, find every call into send_gateway (gateway_send/send/subprocess). Report the
   exact `agent_source=` and `intent=` it passes for each lender send. Quote the lines.
3. Open the VPS send_gateway.py. Quote `OPERATOR_INITIATED_SOURCES` (the frozenset) and the
   `critic_should_fire = (...)` gate. Confirm the gate is: intent=="commercial" AND
   DRAFT_CRITIC_ENABLED AND not _is_operator_initiated(agent_source).
4. Confirm whether shop_out_sender.py honors an atomic `pending -> sending` claim before sending (so
   it can't double-send a row the bridge tool already claimed). Quote the claim/update.
5. Check the live Gmail credential WITHOUT printing it: which env var the SunBiz brand uses
   (GMAIL_USER / GMAIL_APP_PASSWORD for submissions@sunbizfunding.com), and run a single auth probe
   (e.g. a send_gateway dry-run or smtplib login test) that returns only ok/auth_failed — never echo
   the password.
6. STOP and report: the cron's agent_source/intent, the gate text, the claim status, and the auth
   probe result. If any finding contradicts the hypothesis above, say so and propose the corrected fix
   before proceeding.

PHASE 2 — FIX THE CRON (only after Phase 1 confirms the diagnosis):
7. Make shop_out_sender.py send lender submissions as OPERATOR-INITIATED so they bypass the
   cold-outreach draft critic, WITHOUT disabling any compliance gate:
   - Fix the agent_source ONLY. Add a dedicated "shop_out_sender" entry to the
     OPERATOR_INITIATED_SOURCES frozenset in the VPS send_gateway.py, and have the cron pass
     agent_source="shop_out_sender" (matches the change already made in the Business-Empire-Agent
     ancestor copy). That alone makes critic_should_fire == False — the critic gate keys on
     `not _is_operator_initiated(agent_source)`.
   - DO NOT change intent. Leave it at the default "commercial". The CASL suppression gate
     ("Gate 1: commercial suppression") fires ONLY when intent=="commercial", so switching to
     transactional would silently stop honoring lender opt-outs. Operator-initiated already bypasses
     the HYGIENE gates (cooldown / cap / reply-since-last) by design; the COMPLIANCE gates (CASL
     suppression, kill-switch, manual-pause, empty-recipient) must stay active. (Codex audit
     2026-06-19 flagged the intent change as a critical compliance regression — do not reintroduce it.)
8. If Phase 1 showed the cron does NOT honor the pending->sending atomic claim, add it: UPDATE the row
   to 'sending' WHERE id=? AND status='pending' and only proceed if exactly one row was updated;
   otherwise log "claimed_by_other_sender" and skip. This is what stops the cron and the dashboard
   batch from double-sending the same lender.
9. Keep changes surgical. Do not rewrite the file. Show me the diff before saving.

PHASE 3 — SET THE NEW GMAIL APP PASSWORD:
10. The submissions@sunbizfunding.com Google account password was changed last night, which revoked the
    old app password — that's the auth_failed wall. CC has generated a NEW app password. Set it in the
    SunBiz .env.agents (the file the SunBiz daemons load — reuse CEO-Agent's .env.agents if that's the
    shared one) as GMAIL_APP_PASSWORD (16 chars, spaces removed). New value: <FILL_IN>
    Edit the env file directly on the VPS; never paste the password into chat output or a log. Then
    re-run the auth probe from step 5 — it must return OK now. (If GMAIL_USER also needs to be
    submissions@sunbizfunding.com, confirm it matches.)

PHASE 4 — RESTART + VERIFY:
11. Restart the affected daemons (pm2 restart the SunBiz shop-out sender + bridge as needed). Confirm
    they come up green (`pm2 status`, no restart loop).
12. End-to-end test (use a controlled test inbox you own as the lender recipient, NOT a real lender):
    - queue or reuse one pending application_lender_threads row,
    - run the cron / send path once,
    - confirm: ZERO "draft_critic rejected", ZERO "auth_failed", the thread row flips to status='sent',
      and the test inbox actually receives the email with the app + statements attached.
13. Re-run once more to confirm idempotency: the already-'sent' row is NOT re-sent, and a second sender
    pass logs "claimed_by_other_sender" / skip rather than double-sending.

PHASE 5 — REPORT:
14. Append a dated entry to /srv/sunbiz/diagnostic.log and report back here in plain English:
    - Changed: files + the exact agent_source/intent now used, and the auth-probe result (no rotation).
    - Proof: the test-inbox receipt + the 'sent' row + the idempotency re-run result (paste the actual
      output, not a summary).
    - Anything still broken or any finding that contradicted the hypothesis.

Constraints: SunBiz-scoped only. Never echo the Gmail password. Don't bypass exec_guard / secret_guard.
Surgical edits only; show diffs before saving.
```

---

## After the VPS run (Bravo / dashboard side — already shipped separately)

The dashboard half of this hotfix lands in `oasis-command-center` (Vercel), independent of the VPS:
clean human-readable thread errors, a first-class per-row **Retry** + "Retry all failed", and a
business-name fallback so the subject is never "New Deal ()". The send-pipeline critic fix is purely
the operator-initiated `agent_source` (`shop_out_sender` added to `OPERATOR_INITIATED_SOURCES` in the
ancestor `bravo_cli`/`send_gateway.py`); intent stays `commercial` everywhere so CASL suppression keeps
applying to lender submissions (a Codex audit caught an earlier intent=transactional attempt as a
compliance regression).
