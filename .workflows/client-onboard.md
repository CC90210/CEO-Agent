---
description: Onboard a new OASIS AI client, generate NDAs/Invoices natively, create a Stripe link, and send the onboarding email.
---
# Client Onboarding Automation

1. Inform the user you are onboarding the client using the native Python billing engine.
// turbo-all
2. Execute the python generator script with the correct parameters, replacing the placeholders with the actual provided information:
```bash
python scripts\contract_generator\generator.py --name "CLIENT_NAME" --email "CLIENT_EMAIL" --upfront UPFRONT_FEE --monthly MONTHLY_RETAINER
```
3. Wait for the command to finish executing using the command_status tool.
4. Update the `memory/LEAD_TRACKER.csv` to mark the lead as 'Closed/Onboarded' if they were on the sheet.
5. Notify the user that the custom invoice, NDA, and Stripe link have been successfully dispatched.
