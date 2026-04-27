---
name: email-safety
description: Mandatory contract for sending email/outreach from any AI (Claude, Gemini, Antigravity, Codex). Read this before invoking any send command. Disable-model-invocation false — ANY model that sends mail must read this first.
disable-model-invocation: false
---

# Email Safety — One Rulebook for Every AI

You are about to invoke an email or outreach command. Before you do, read
this entire file. It applies to **every AI** that drives this repo —
Claude Opus, Claude Sonnet, Claude Haiku, Gemini 3 Flash, Gemini 3 Pro,
Antigravity native chat, Codex, GPT-anything, and any future model.

Sending email is the single most expensive thing you can do wrong here.
A bad send burns a real client, a real reputation, and a real revenue
stream. There is no "undo".

## The one rule

**All outbound goes through `scripts/send_gateway.py`. Period.**

If you find yourself reaching for `smtplib`, the Gmail API, the SES API,
Mailgun, SendGrid, or any other transport — **stop**. The gateway is the
only safe path. It enforces:

- CASL compliance (suppression list, footer, List-Unsubscribe headers)
- Per-channel cooldown (email 72h, IG 48h, LinkedIn 72h, phone 168h)
- Daily caps (email 50, IG 30, LinkedIn 20, phone 15)
- Hourly caps + per-domain caps + bounce circuit breaker
- A draft critic (adversarial AI review of the body before send)
- Idempotency via the `lead_interactions` ledger

Skipping it skips all of that.

## When in doubt, dry-run

Every send command accepts `--dry-run`. The gateway returns
`{"status": "dry_run"}` with all gates evaluated but no actual send.

```bash
# Preview an email without sending
python scripts/email_engine.py send \
  --to test@example.com \
  --subject "Test" \
  --body "Hello" \
  --dry-run

# Same for templates
python scripts/email_engine.py send-template \
  --template-id <uuid> \
  --to test@example.com \
  --vars '{"first_name":"Alex"}' \
  --dry-run

# And for outreach
python scripts/outreach_engine.py send \
  --lead-id <uuid> \
  --dry-run

# And for batch approvals
python scripts/outreach_batch.py --send-draft <path> --dry-run
```

If you are reasoning about whether a send is safe: **always dry-run first.**
The cost is one extra command. The benefit is catching the failure before
it lands in a paying client's inbox.

## The killswitch (multi-AI safety)

Set `BRAVO_FORCE_DRY_RUN=1` in your environment, and every send call —
no matter which script, no matter which AI invoked it, no matter what
flags they passed — becomes a dry-run. The gateway honors this BEFORE
suppression / cooldown / DB lookups, so it works even when Supabase is
unreachable.

Use this when:

- You are running a less-capable model that might call the wrong tool
  (Gemini 3 Flash, Antigravity native chat, etc.)
- You are in a sandbox or test environment
- You are debugging and don't want any side effects
- You are doing a multi-step workflow where one step might fire a send
  prematurely

```bash
# In bash / zsh / git-bash
export BRAVO_FORCE_DRY_RUN=1

# In PowerShell
$env:BRAVO_FORCE_DRY_RUN = "1"

# In a single command (bash)
BRAVO_FORCE_DRY_RUN=1 python scripts/email_engine.py send --to ... --subject ... --body ...
```

To resume real sends, unset the variable. There is no override flag — the
killswitch is intentionally one-way: set it on, you get safety; you must
explicitly unset it to send.

## What "messed up the emails" usually means

When a session reports that an AI got an email wrong, the cause is almost
always one of these:

1. **Wrong recipient** — AI used a placeholder, a test email, or a name
   instead of an address. *Mitigation:* the gateway requires `to_email`
   matching `<x>@<y>.<tld>` shape. Bad addresses fail fast with
   `status: error`.
2. **Wrong template** — AI hallucinated a template ID or template name.
   *Mitigation:* `send-template` requires a UUID. Hallucinated UUIDs miss
   the DB and fail loud.
3. **Bypassed cooldown** — AI sent twice to the same lead in 30 minutes.
   *Mitigation:* the gateway enforces 72h email cooldown architecturally.
   Cannot be bypassed from inside the process.
4. **AI-slop content** — body reads like a chatbot apologized for itself.
   *Mitigation:* the draft critic blocks slop patterns + uses a Haiku
   adversarial review.
5. **Wrong brand** — sent as `oasis` when it should have been `kona_makana`.
   *Mitigation:* `--brand` flag is required and validated against
   `BRAND_IDENTITY` keys.

If any of these slip through, **the gateway is the right place to add a
new gate**, not your invocation script. Bring the failure to the gateway
team (= file an issue) — don't paper over it with a wrapper.

## Common safe invocations

```bash
# 1. Preview a one-off email
python scripts/email_engine.py send \
  --to alex@northern-hvac.example.com \
  --subject "Quick thought for Northern HVAC" \
  --body "Hi Alex, ..." \
  --brand oasis \
  --dry-run

# 2. Send a known template (real send)
python scripts/email_engine.py send-template \
  --template-id 7e3a... \
  --to alex@example.com \
  --vars '{"first_name":"Alex","company":"Northern HVAC"}' \
  --brand oasis

# 3. Run a nurture sequence step (real send for step 0)
python scripts/email_engine.py sequence run <sequence_uuid> \
  --lead-id <lead_uuid>

# 4. Send a personalized outreach with calendar invite
python scripts/outreach_engine.py send \
  --lead-id <lead_uuid> \
  --meeting-datetime 2026-04-25T14:00:00 \
  --duration 30

# 5. Approve a Telegram-drafted batch outreach
python scripts/outreach_batch.py --send-draft tmp/outreach_drafts/<file>.json
```

## Common UNSAFE patterns to avoid

```python
# ❌ NEVER do this — bypasses every gate
import smtplib
smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465)
smtp.login(...)
smtp.sendmail(...)

# ❌ NEVER do this — no CASL footer, no cooldown, no ledger
import requests
requests.post("https://api.mailgun.net/...", data={...})

# ❌ NEVER do this — bypasses the draft critic
from email_engine import _send_via_smtp_directly  # (function does not exist for a reason)

# ✅ ALWAYS do this
from send_gateway import send as gateway_send
gw = gateway_send(
    channel="email",
    agent_source="<your_script_name>",
    to_email="...",
    subject="...",
    body_text="...",
    brand="oasis",
    intent="commercial",   # or "transactional" for confirmations
    dry_run=False,         # set True until you've previewed
)
```

## Verification

`scripts/email_doctor.py` is a non-destructive check that any AI can run
before invoking a real send. It:

- Confirms the gateway responds
- Confirms `BRAVO_FORCE_DRY_RUN=1` actually flips behavior
- Lists every send subcommand and confirms each accepts `--dry-run`
- Checks template shapes in Supabase (link counts, placeholders)

```bash
python scripts/email_doctor.py
```

Run this at the start of any session that will involve outbound. If it
fails, do not send. Fix the underlying issue first.

## TL;DR

1. **All outbound goes through `send_gateway.send()`.**
2. **`--dry-run` previews safely. Use it.**
3. **`BRAVO_FORCE_DRY_RUN=1` is the killswitch. Set it when in doubt.**
4. **`scripts/email_doctor.py` confirms the safety surface is intact.**
5. **AI-slop content is caught by the draft critic — but you should still
   read your draft before approving.**

You're a smart AI. Act like the email is going to a paying client at
$2,500/month MRR — because it might be.

## Related
- [[skills/INDEX]]
- [[brain/CAPABILITIES]]
