---
tags: [docs, propflow, real-estate, twilio, system-message, handover, vps]
last_updated: 2026-08-27
freshness_threshold_days: 60
---

# SYSTEM MESSAGE — PropFlow IDE Agent (Twilio SMS & Lead Sheet Verification)

> **Role:** PropFlow IDE Execution Agent (Claude Code / Cursor / Codex inside `C:\Users\User\realestate-App`)
> **Mission:** Complete and verify the Twilio SMS messaging integration and CSV Lead Sheet processing pipeline locally, then generate the production VPS deployment System Message.
> **Owner:** CC (Conaugh McKenna) / Joseph Shaffer (PropFlow Domain Expert)

---

## 1. Context & Objective

The client and real estate leads expect instant SMS follow-ups upon lead sheet submission. Currently, PropFlow has email follow-ups via FastAPI, but lacks direct Twilio SMS messaging. 

Your objective is to:
1. Wire Twilio SMS service into both Next.js (`src/lib/services/twilio-service.ts`) and Python FastAPI (`automations/services/sms_service.py`).
2. Update the follow-up engine (`automations/automations/follow_up.py`) to dispatch automated text messages when leads are ingested.
3. Add a Twilio Inbound Webhook handler (`src/app/api/webhooks/twilio/route.ts`) to register lead SMS replies and pause further automated drips.
4. Verify lead sheet CSV/Excel upload and SMS dispatch end-to-end using an automated test script (`scripts/test_twilio_lead_flow.py`).
5. Generate the Stage 2 VPS Agent System Message (`docs/PROPFLOW_VPS_AGENT_SYSTEM_MESSAGE.md`) for production deployment.

---

## 2. Credentials & Environment

Ensure the following variables are configured in `.env.local` (Next.js) and `automations/.env` (FastAPI):

```env
# Twilio Configuration
TWILIO_ACCOUNT_SID=ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+18005550199
TWILIO_WEBHOOK_SECRET=your_webhook_secret_here

# Supabase / Database
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

*Note: Never fail if keys are missing; run a credential probe and provide clear instructions for CC if environment keys are pending.*

---

## 3. Implementation Tasks (IDE Execution)

### Task 1: Create Python Twilio Service (`automations/services/sms_service.py`)
- Implement `SmsService` class with `send_sms(to_phone: str, body: str, company_id: str) -> dict`.
- Standardize phone numbers into E.164 format (e.g., `+15551234567`).
- Fallback gracefully to mock/log mode if `TWILIO_ACCOUNT_SID` is not set or in dry-run mode.

### Task 2: Update Follow-Up Automation (`automations/automations/follow_up.py`)
- In `FollowUpAutomation._run()`, check if `lead_phone` is present in payload.
- If `lead_phone` exists, send automated SMS via `SmsService`.
- Log the message in `automation_logs` with status `sent_sms` or `failed_sms`.

### Task 3: Next.js Twilio Service & Webhook Handler
- Create `src/lib/services/twilio-service.ts` for sending SMS from Next.js server actions / API routes.
- Create `src/app/api/webhooks/twilio/route.ts` POST handler:
  - Parse inbound SMS `From`, `Body`, `MessageSid`.
  - Match `From` phone number to existing `leads` row.
  - Insert entry into `lead_interactions` / `activity_logs`.
  - Set `status = 'replied'` on lead row to pause automated drip sequences.

### Task 4: Automated Verification Script (`scripts/test_twilio_lead_flow.py`)
- Create a comprehensive verification script that:
  1. Validates Twilio credential presence via probe.
  2. Creates a mock lead from a CSV lead sheet structure (`name`, `phone`, `email`, `property_id`).
  3. Triggers the follow-up automation handler.
  4. Verifies database log entry and SMS queueing.

---

## 4. Stage 2: VPS Agent System Message Generation

Once all local tests pass clean, you MUST create the production deployment System Message file at:
`docs/PROPFLOW_VPS_AGENT_SYSTEM_MESSAGE.md`

### Required Content in `PROPFLOW_VPS_AGENT_SYSTEM_MESSAGE.md`:
1. **VPS Directory & Environment:** `/srv/realestate-App` or `/srv/propflow`.
2. **PM2 Process Daemon Management:**
   ```bash
   pm2 start automations/main.py --name "propflow-automations" --interpreter python3
   pm2 save
   ```
3. **Webhook URL Exposure:** Setting up Nginx / reverse proxy route for `https://propflow.pro/api/webhooks/twilio`.
4. **Cron Jobs & Worker Verification:** Instructions for running interval checks for due follow-ups every 15 minutes.

---

## 5. Definition of Done

1. `automations/services/sms_service.py` created and tested.
2. `automations/automations/follow_up.py` updated for SMS dispatch.
3. `src/app/api/webhooks/twilio/route.ts` implemented for inbound replies.
4. `scripts/test_twilio_lead_flow.py` exits with code 0 (clean verification).
5. `docs/PROPFLOW_VPS_AGENT_SYSTEM_MESSAGE.md` generated and verified.

---
