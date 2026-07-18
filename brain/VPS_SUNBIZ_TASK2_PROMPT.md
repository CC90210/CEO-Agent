---
description: "SunBiz VPS Agent paste-prompt: form→lead self-test verification and SMS E.164 normalization fix for welcome sequence"
tags: [vps, sunbiz, bridge, paste-prompt, task]
last_updated: 2026-06-22
---
# VPS Agent — Task 2 (close the self-test gap + fix the SMS-step defect)

> **CC:** paste the fenced block into the SunBiz VPS Claude session. It answers its two open
> questions: yes to the SMS fix, and here's how to self-test the form→lead chain (no Vercel proxy
> or auth needed). Paste-prompt only.

```text
TASK 2 — DO THESE TWO NOW, then report. (Your verification was great — the website→CRM→auto-reply
pipeline is confirmed GREEN: your live send From submissions@ + the 3 production
form_intake_next_steps interactions prove the chain. These two follow-ups close the loop.)

A. CLOSE THE FORM→LEAD SELF-TEST GAP — you do NOT need the Vercel proxy or any auth.
   You got `no_auth_provided` because the request omitted anonymous_init. The anonymous form-submit
   path mints its OWN token (that's exactly what the website contact form uses). Replay the full
   chain yourself:
     POST https://oasisai.work/api/forms/submit     (content-type: application/json)
     {
       "step_index": 0,
       "payload": { "business_name": "VPS E2E TEST", "contact_name": "VPS Test",
                    "email": "<your test mailbox>", "phone": "+1<real 10-digit test number>" },
       "anonymous_init": { "tenant_slug": "submissions", "form_slug": "initial-lead-capture" }
     }
   Expect 200 { ok:true, minted_token, ... }. Then confirm:
     (1) a NEW lead at stage intent_inquiry_submitted in the SunBiz tenant;
     (2) the "Your next steps with SunBiz" auto-reply lands in your test mailbox, From submissions@.
   That fully closes the one segment you couldn't test. Use a +1 E.164 phone so it also exercises
   the SMS step you're fixing in B.

B. FIX THE WELCOME-SEQUENCE SMS DEFECT (approved by CC — proceed).
   Seq 8fc506b2's first SMS step fails every lead ("sms channel requires to_phone (E.164) and
   body_text") because lead phones aren't E.164. Make the smallest change that does BOTH:
     1. E.164-normalize the recipient phone right before the SMS send: strip non-digits; 10-digit
        US → "+1"+digits; 11-digit "1XXXXXXXXXX" → "+1XXXXXXXXXX"; already "+…"/valid → leave as-is.
     2. If it still isn't valid E.164 after normalization, SKIP the SMS step gracefully (no-op +
        advance the sequence) — do NOT raise/burn the 5 retries. Email touches MUST keep firing.
   Verify: one lead with a valid US phone → SMS sends (to_phone = +1…); one lead with no/junk phone
   → step skips cleanly, sequence continues, email still goes; no more "requires to_phone (E.164)"
   in the runner logs. Run the typecheck/tests, restart ONLY the sequence-runner, confirm with one
   real lead before declaring done.

REPORT (four lines): Changed / Why / Proof (paste: the submit 200 response, the new lead's stage,
the received email's From header, and runner-log lines showing SMS sent for a valid phone +
skip-not-fail for an invalid one) / Needs from CC.

GUARDRAILS: SunBiz tenant only. No secrets in output. No destructive ops; restart only the
sequence-runner (not the bridge). The "VPS E2E TEST" lead is a REAL CRM row — label it and delete
it after, or note it for cleanup. The earlier loopback row under the OASIS tenant is benign — leave it.
```

[[VPS_SUNBIZ_BRIDGE_PROMPT]] · [[project_sunbiz_funding_website]] · [[feedback_vps_paste_prompt_not_ssh]]
