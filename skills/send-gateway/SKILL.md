---
name: send-gateway
description: The single outbound chokepoint for every autonomous action Bravo performs on behalf of CC. Enforces CASL compliance, cooldown windows, daily caps, and cross-engine idempotency architecturally — callers cannot bypass it.
disable-model-invocation: true
triggers: ["send gateway", "use send gateway", "run send gateway"]
---

# Send Gateway — the only outbound path

> **Rule of law:** If code sends email, a DM, or any outbound message on CC's behalf, it goes through `scripts/send_gateway.py`. Direct `smtplib.SMTP_SSL()` calls from a business engine are a regression and must be reverted in review.

## Why this skill exists

Before 2026-04-20, four Python engines and one N8N workflow could contact the same lead on the same day without seeing each other. They wrote to three different tables. No engine could answer "was this lead contacted in the last 72 hours?" before acting. That is the root cause of the duplicate-email bug CC described in the 2026-04-19 audit.

This skill encodes the rule that closes that bug: every send goes through `send_gateway.send()`. Idempotency is not a library callers must remember to invoke — it is architecturally enforced because the smtplib call lives inside the gateway and nowhere else.

## When to use the gateway

Use the gateway whenever your code:

- Sends an outbound email (cold, nurture, confirmation, reminder, template-based)
- Sends an outbound DM / Instagram / LinkedIn message
- Logs a call or meeting as outbound activity
- Delivers anything on CC's behalf to anyone outside his organization

**Do NOT bypass the gateway** just because a send is "simple" or "one-time." The whole point is that the cooldown ledger remains whole.

## Quick reference

### From Python (importable)

```python
from send_gateway import send

result = send(
    channel="email",                         # email | instagram | linkedin | phone | skool
    agent_source="outreach_engine",          # identify the caller (free text, stay on known values)
    to_email="jane@acme.example",            # for email channel
    lead_id=None,                            # auto-resolved or auto-created from to_email
    subject="Quick question about your HVAC scheduling",
    body_text="Hi Jane, ...",
    body_html=None,                          # optional
    brand="oasis",                           # oasis | conaugh_mckenna | nostalgic
    intent="commercial",                     # commercial | transactional | internal
    cooldown_hours=None,                     # None = DEFAULT_COOLDOWNS[channel]
    metadata={"campaign": "hvac-q2-2026"},   # free-form dict persisted in ledger
    ics_content=None,                        # .ics string for calendar invites
    ics_filename="meeting.ics",
    dry_run=False,
)

# result is always a dict with the same keys:
# {"status": "sent"|"blocked"|"suppressed"|"dry_run"|"error",
#  "reason": str, "lead_id": str|None, "interaction_id": str|None,
#  "cooldown_until": str|None, "daily_count": int|None}
```

`send()` **NEVER raises.** On any error it returns `status="error"` with a reason string. Callers can rely on the return shape.

### From the CLI (scheduler, Telegram, manual)

```
python scripts/send_gateway.py --json send --channel email \
    --to jane@acme.example --subject "..." --body "..." \
    --agent-source manual_cc

python scripts/send_gateway.py can-act --lead-id <uuid> --channel email --json
python scripts/send_gateway.py history --lead-id <uuid> --limit 10
python scripts/send_gateway.py stats --json
```

## Intent semantics

| Intent | Suppression check | CASL footer | List-Unsubscribe | Example use |
|---|---|---|---|---|
| `commercial` | **enforced** (fail-closed) | added | added | cold outreach, nurture, sales |
| `transactional` | skipped (CASL s.10(9)) | added | added | booking confirmations, reminders, password resets |
| `internal` | skipped | **skipped** | skipped | internal test mail, CC-to-self notifications |

## Brand identity

The `brand` keyword selects CASL footer sender name + business name + address. Add a brand to `BRAND_IDENTITY` in `scripts/send_gateway.py` when CC wants a new one to share the chokepoint.

| Brand | Business name | Sender | Use for |
|---|---|---|---|
| `oasis` (default) | OASIS AI Solutions | Conaugh McKenna | Agency outreach, client comms |
| `conaugh_mckenna` | Conaugh McKenna | CC (Conaugh McKenna) | Personal brand, content, DJ inquiries |
| `nostalgic` | Nostalgic Requests | Conaugh McKenna | Nostalgic Requests product mail |

## Cooldown defaults

Conservative by default — CC is still building reputation; better to under-send than look spammy.

| Channel | Cooldown | Daily cap |
|---|---|---|
| email | 72h (3 days) | 50/day |
| instagram | 48h | 30/day |
| linkedin | 72h | 20/day |
| phone | 168h (7 days) | 15/day |
| skool | 24h | — |
| telegram | 0 (internal) | — |

Override per-call with `cooldown_hours=<int>`. Daily caps are hard — gateway refuses over-cap sends with `status="blocked"`.

## Engine wire-up (2026-04-20 rewire)

All five outbound Python engines now route through the gateway:

| Engine | Function that calls `send()` |
|---|---|
| [outreach_engine.py:send_outreach()](../../scripts/outreach_engine.py) | cold outreach with Meet invite .ics |
| [outreach_batch.py:send_approved_draft()](../../scripts/outreach_batch.py) | Telegram-approved batch sends |
| [email_engine.py:cmd_send() / cmd_send_template() / cmd_sequence_run()](../../scripts/email_engine.py) | one-off, templated, and sequence sends |
| [funnel_nurture.py:send_email()](../../scripts/funnel_nurture.py) | Day 2 / Day 5 follow-ups |
| [booking_engine.py:_send_booking_confirmation() / _send_reminder_email()](../../scripts/booking_engine.py) | transactional confirmations + reminders |

## What the gateway writes

Every successful send writes to three places:

1. **`lead_interactions`** (architectural truth — cooldown_until + agent_source + metadata)
2. **`email_log`** (legacy SMTP-layer truth — keeps analytics and report tooling working)
3. **`leads.last_contacted_at`** (keeps CRM pipeline view fresh)

Failed sends write only to `email_log` with `status='failed'` for forensics.

## Related

- **Migration:** [database/003_unified_interaction_ledger.sql](../../database/003_unified_interaction_ledger.sql) — adds `cooldown_until`, `agent_source`, `metadata` columns + indexes. Apply via `python scripts/apply_migration.py`.
- **Context builder:** [scripts/context_builder.py](../../scripts/context_builder.py) — `get_entity_context(lead_id)` returns the full relationship context for persona-aware LLM drafting.
- **Tests:** [scripts/test_send_gateway.py](../../scripts/test_send_gateway.py) — 17 golden + negative path tests. MUST pass before any gateway change ships.
- **CASL module:** [scripts/casl_compliance.py](../../scripts/casl_compliance.py) — suppression list + footer + List-Unsubscribe helpers the gateway composes.

## When adding a new channel

1. Add the channel name to `KNOWN_CHANNELS` (frozenset).
2. Add a default cooldown to `DEFAULT_COOLDOWNS`.
3. If there's a daily cap, add it to `DAILY_CAPS`.
4. In `send()`, add a channel-specific branch that performs the physical send — route it through a `_send_<channel>()` helper that is the ONLY place where the real client call lives.
5. Add tests for the new channel to [test_send_gateway.py](../../scripts/test_send_gateway.py).
