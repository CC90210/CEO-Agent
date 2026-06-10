# Regression: Antigravity Outreach Sent Raw `{{company}}` Placeholders (2026-05-13)

## What went wrong
Antigravity/Gemini sent 6 OASIS outreach emails with raw `{{company}}` placeholders in the subject/body between 3:21 and 3:24 PM ET. There were 5 unique burned leads, and Collingwood Charters received the broken email twice.

## The behavior that must NOT recur
1. `scripts/integrations/email_engine.py` now has strict template rendering: missing or blank placeholders raise `TemplateRenderError`, with a safe `company_name -> company` alias for common caller spelling.
2. `scripts/integrations/send_gateway.py` now blocks any email field that still contains `{{...}}` before SMTP and before the critic.
3. The draft critic is fail-closed by default again. Explicit fail-open only applies to critic unavailability, never to a real rejection.
4. Email default cooldown is restored to 72 hours; manual operator overrides must be explicit per send.
5. Regression tests added: `scripts/test_email_engine.py`, plus placeholder and fail-open rejection cases in `scripts/test_send_gateway.py`.
