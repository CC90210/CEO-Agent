---
tags: [docs]
last_updated: 2026-07-19
---

# n8n Inbound Webhook → OASIS Command Center

> One-pager. Wires the OASIS Inbound Qualifier workflow (n8n ID `1cGIN32alM8sf8OV`) into the Command Center so every classified email shows up live in Pipeline + bumps the green dot in Settings → Integrations.

## What this fixes

The dashboard's `n8n_inbound` integration is showing **unconfigured** because n8n's classifier currently posts nowhere. Once you complete this 5-minute setup, every classified email becomes a row in `lead_interactions`, intent/sentiment/priority show up in Pipeline → Recent inbound, and the green dot lights up.

## What you need

- n8n access (Hostinger cloud)
- The OASIS Command Center deployment URL (e.g. `https://oasisai.work`)
- 5 minutes

---

## Step 1 — Issue a webhook secret (Bravo can do this)

```bash
python scripts/integrations/n8n_webhook_secret.py issue --profile-email conaugh@oasisai.work
```

You'll see something like:

```
=== HEADERS — paste into n8n HTTP Request node ===

  x-oasis-profile-id:  abc12345-67de-...-1234567890ab
  x-oasis-secret:      Tx8aB9cD-eF...long-random-string
```

**Save the secret immediately** — only the hash is stored, the raw string can't be recovered. If you lose it, just `issue` a new one and revoke the old one.

## Step 2 — Open the n8n workflow

In n8n, open: **OASIS Inbound Qualifier (Bravo Aware)** — workflow ID `1cGIN32alM8sf8OV`.

## Step 3 — Add an HTTP Request node after the Classifier

After the node that produces the `{intent, sentiment, priority}` classification (the AI Agent Classifier output), add a new **HTTP Request** node.

Configuration:

| Field | Value |
|-------|-------|
| **Method** | `POST` |
| **URL** | `https://oasisai.work/api/inbound/n8n` |
| **Authentication** | `None` (we use custom headers, not n8n's built-in auth) |
| **Send Headers** | `On` |
| **Send Body** | `On` |
| **Body Content Type** | `JSON` |
| **Specify Body** | `Using JSON` |

**Headers (add 2):**

| Name | Value |
|------|-------|
| `x-oasis-profile-id` | `<paste profile_id from Step 1>` |
| `x-oasis-secret` | `<paste secret from Step 1>` |

**JSON Body** (paste this verbatim, replacing `={{ ... }}` references with whatever your classifier node names them):

```json
{
  "from_email": "={{ $json.from_email }}",
  "subject": "={{ $json.subject }}",
  "body": "={{ $json.body_text }}",
  "classification": {
    "intent": "={{ $json.intent }}",
    "sentiment": "={{ $json.sentiment }}",
    "priority": "={{ $json.priority }}",
    "category": "={{ $json.category }}"
  },
  "received_at": "={{ $json.received_at }}"
}
```

Adjust the field names (`$json.from_email` etc.) to whatever your existing classifier node outputs them as. Use n8n's expression editor to drag-drop the right path.

## Step 4 — Test the wiring

In n8n, click **Execute workflow** with one of the existing test inbound emails. Check:

- The HTTP Request node returns `200 OK` with body `{"ok": true, "interaction_id": "..."}`.
- The OASIS Command Center → Pipeline → Recent inbound shows the email within 20 seconds.
- The OASIS Command Center → Settings → Integrations shows `n8n_inbound: healthy` with last-ping timestamp.

If the response is `401 invalid secret`, double-check that you pasted the headers correctly and that the secret hasn't been revoked.

If `400 from_email and subject are required`, your classifier output paths don't match the JSON body — fix the `={{ ... }}` references.

## Step 5 — Save + activate

Save the workflow. Make sure it's **active** (not just saved). Done.

---

## Troubleshooting

### "I get a 401"
- Re-issue the secret: `python scripts/integrations/n8n_webhook_secret.py issue --profile-email conaugh@oasisai.work`
- Make sure both headers are sent (n8n sometimes drops empty headers — check the actual request log).

### "I get a 400 with `from_email is required`"
- Your classifier's output field is named differently. Look at what fields actually exist in the n8n node's "Output Data" panel and update the JSON body's `={{ }}` paths.

### "Settings → Integrations still shows n8n_inbound as unconfigured"
- The first successful POST flips it to healthy automatically. Until then, run a single test execution in n8n.

### "I want to revoke a secret"
```bash
# List secrets
python scripts/integrations/n8n_webhook_secret.py list --profile-email conaugh@oasisai.work

# Revoke by id
python scripts/integrations/n8n_webhook_secret.py revoke --secret-id <uuid>
```

### "I want a separate secret per workflow / per environment"
Issue more than one. The `--label` flag lets you tag each secret:

```bash
python scripts/integrations/n8n_webhook_secret.py issue \
    --profile-email conaugh@oasisai.work \
    --label "OASIS Qualifier · production"
```

Each secret has its own ID + last-used timestamp + use count, so you can tell them apart in `list`.

---

## What happens server-side

1. Vercel `/api/inbound/n8n` route handler receives the POST.
2. Validates the headers (UUID format + presence).
3. SHA-256 hashes the secret and calls the `record_inbound_from_n8n_v2` Postgres RPC.
4. The RPC verifies the hash against `n8n_webhook_secrets`, finds-or-creates a `leads` row by email, inserts a `lead_interactions` row with full classification metadata, and pings `integrations_health` to keep the green dot live.
5. Returns `{ok: true, interaction_id}` so n8n can log the success.

The raw secret never lives anywhere on the server — only the SHA-256 hash. If the database leaks, the secrets are still safe.

## Related

- [[docs/INDEX]]
- [[docs/AGENT_RUNNER_DESIGN]]


## Related (graph)

- [[docs/INDEX]]
- [[docs/AGENT_RUNNER_DESIGN]]
- [[docs/AI_WORKSTATION_ROADMAP]]
