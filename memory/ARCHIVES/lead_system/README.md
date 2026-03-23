# OASIS Lead System

> Complete lead generation, reactivation, and nurturing system.
> Built for OASIS AI Solutions — replicable for any client, any industry.

## Deployed Workflows (n8n)

| Workflow | ID | Nodes | Purpose | Status |
|----------|-----|-------|---------|--------|
| **Lead Reactivation Engine** | `PL0WJTkHMKdbZtPi` | 26 | 3-touch AI email sequence for dead leads | Inactive |
| **Speed-to-Lead Responder** | `pmY40eokEN0mMqVZ` | 9 | < 60s AI response to new leads | Inactive |
| **Reputation & Referral Engine** | `ITytnJNiEjLtl93h` | 7 | Auto review requests + referral offers | Inactive |

## Architecture

### Module 1: Lead Reactivation Engine
**Sell:** "Give me your old lead list. I'll get 5-10% back as paying customers."

Flow: Google Sheet (old leads) → AI personalization (GPT-4o-mini) → Gmail Touch 1 → Wait 3 days → Check reply → If yes: Telegram hot lead alert → If no: AI Follow-up Touch 2 → Wait 4 days → Final check → Touch 3 last chance → Log completion

**Credentials used:** Gmail, Google Sheets, OpenAI, Telegram

### Module 2: Speed-to-Lead Responder
**Sell:** "Every new lead gets a personalized response in under 60 seconds."

Flow: Webhook (from forms/ads/CRM) → Normalize data → AI instant response → Gmail + Sheet log + Telegram alert

**Credentials used:** Gmail, Google Sheets, OpenAI, Telegram

### Module 3: Reputation & Referral Engine
**Sell:** "Automatically get Google reviews and referrals after every service."

Flow: Webhook (service complete) → Wait 2h → Review request email → Wait 3d → Referral offer email → Log

**Credentials used:** Gmail, Google Sheets

## Setup for New Client

1. **Create Google Sheet** with columns: name, email, business_name, service, industry, last_contact
2. **Configure workflow** — update sheet_id and sheet_name in Campaign Config node
3. **Set Telegram chat ID** in alert nodes
4. **Test** with Manual Test trigger
5. **Activate** when ready: `python scripts/n8n_tool.py activate <ID>`

## CLI Tools

```bash
# n8n management (full API access)
python scripts/n8n_tool.py list                    # List all workflows
python scripts/n8n_tool.py get <id>                # Workflow details
python scripts/n8n_tool.py activate <id>           # Activate
python scripts/n8n_tool.py deactivate <id>         # Deactivate

# Deploy workflows
python lead_system/build_workflows.py all          # Deploy all
python lead_system/build_workflows.py reactivation # Deploy one
```

## Pricing (OASIS Clients)

| Module | Setup Fee | Monthly Retainer | Performance Option |
|--------|-----------|------------------|--------------------|
| Lead Reactivation | $500 | $297/mo | $50-100/reactivated lead |
| Speed-to-Lead | $497 | $297/mo | — |
| Reputation & Referral | $297 | $197/mo | — |
| Full Suite | $997 | $497/mo | Custom |
