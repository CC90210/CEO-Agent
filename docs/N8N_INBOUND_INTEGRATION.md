# N8N Inbound → Bravo Ledger Integration

> **One-time setup. ~3 minutes. Zero code changes to your existing workflow.**
> After this, every email your N8N "OASIS Inbound Qualifier (Bravo Aware)"
> workflow classifies will also land in Bravo's unified `lead_interactions`
> ledger — closing the inbound blind spot without touching any classifier
> logic.

---

## What this does

Before: N8N classifies inbound email in the cloud. That classification lives inside N8N's execution log only.

After: N8N still does the classification. At the end of the flow, one extra node calls `record_inbound_from_n8n()` in Supabase. That function atomically:

1. Upserts the sender into `leads` (creates a new row if first contact)
2. Inserts a row into `lead_interactions` with `agent_source='n8n_inbound'` — now Bravo's gateway, the reasoning loop, and the dashboard can all see inbound
3. Publishes an `inbound.classified` event on `agent_events` — the autonomous reasoning loop subscribes to this

---

## Step 1 — Open the workflow

- Open N8N
- Open workflow **`OASIS Inbound Qualifier (Bravo Aware)`** (ID: `1cGIN32alM8sf8OV`)

---

## Step 2 — Add the node

At the end of your flow — **after** the `textClassifier` node and **after** whichever agent node (Oasis Chat / Business Opportunities / Internal / SENTINEL) handled the email — add a **Supabase node**.

Node configuration:

| Field | Value |
|---|---|
| **Resource** | `Function` |
| **Operation** | `Call` |
| **Function** | `record_inbound_from_n8n` |
| **Credentials** | (use your existing Bravo Supabase credentials — the same ones the workflow already uses for other tables) |

### Function parameters (paste values in this order)

Use N8N expression syntax `={{ ... }}` to pull from upstream nodes.
Replace the node names in `$('...')` with whatever you actually named your Gmail trigger and classifier nodes in your workflow.

| Parameter | Type | Example value (N8N expression) |
|---|---|---|
| `p_from_email` | text | `={{ $('Gmail Trigger').item.json.from.value[0].address }}` |
| `p_from_name` | text | `={{ $('Gmail Trigger').item.json.from.value[0].name }}` |
| `p_subject` | text | `={{ $('Gmail Trigger').item.json.subject }}` |
| `p_content` | text | `={{ $('Gmail Trigger').item.json.text || $('Gmail Trigger').item.json.snippet }}` |
| `p_classification` | json | `={{ { "category": $('textClassifier').item.json.category, "intent": $('textClassifier').item.json.intent || null, "priority": $('textClassifier').item.json.priority || null, "sentiment": $('textClassifier').item.json.sentiment || null, "confidence": $('textClassifier').item.json.confidence || null, "handled_by_agent": $json.agent_name || null } }}` |
| `p_thread_id` | text | `={{ $('Gmail Trigger').item.json.threadId }}` |
| `p_message_id` | text | `={{ $('Gmail Trigger').item.json.id }}` |

The last parameter `p_received_at` can be left empty — the function defaults it to `NOW()`.

> **Note on `p_classification`:** that's a JSON object — pass whatever shape your classifier actually produces. If your current node doesn't output keys like `intent` or `priority`, leave them as `null` (the expression above does that). The fields Bravo cares about most are:
>
> - `intent` — one of `booking`, `pricing`, `objection`, `info_request`, `unsubscribe`, `out_of_office`, `spam_bounce`, `reply_positive`, `reply_negative`, `referral`, `other`
> - `priority` — `hot`, `warm`, `cold`, `low`
> - `sentiment` — `positive`, `neutral`, `negative`, `mixed`
> - `confidence` — number 0.0 to 1.0
> - `category` — whatever your textClassifier outputs
>
> Bravo's downstream consumers degrade gracefully when fields are missing — you won't break anything by omitting them.

---

## Step 3 — (Optional) Add branching on the return value

The function returns a JSON object:

```json
{
  "status": "ok",
  "lead_id": "uuid",
  "lead_was_new": true,
  "interaction_id": "uuid",
  "event_id": "uuid",
  "severity": "warn" | "info"
}
```

You can branch on `lead_was_new` to send yourself a Telegram ping whenever a fresh contact appears, or on `severity=warn` for hot replies. Entirely optional — the unified ledger works without any branching.

---

## Step 4 — Verify it's working

After saving the workflow and enabling it, send yourself a test email from any address you haven't used before. Then:

```bash
cd c:/Users/User/Business-Empire-Agent
.venv/Scripts/python.exe -c "
from scripts.send_gateway import get_supabase
db = get_supabase()
# Show the last 5 N8N-sourced inbound interactions
rows = (db.table('lead_interactions')
          .select('created_at,channel,subject,agent_source,metadata')
          .eq('agent_source', 'n8n_inbound')
          .order('created_at', desc=True)
          .limit(5)
          .execute().data)
import json; print(json.dumps(rows, indent=2, default=str))
"
```

If you see your test email in the list, the integration is live. If you don't, check the N8N execution log — the Supabase node will show the error directly.

---

## Troubleshooting

**"function record_inbound_from_n8n does not exist"** — migration 012 didn't apply. Run `python scripts/apply_migration.py database/012_inbound_rpc.sql` from the repo.

**"permission denied for function"** — your N8N Supabase credential is using the anon key instead of the service_role key. The function is locked to service_role. Update the N8N credential to use `BRAVO_SUPABASE_SERVICE_ROLE_KEY`.

**"from_email is required and must look like an email"** — the upstream Gmail Trigger node didn't pass a valid sender address. Common cause: bounce messages or calendar invites use `from.value[0].address=null`. You can add an IF node before the RPC call to skip these.

**Everything ran but nothing shows in the ledger** — check `agent_source` filter: the query uses `'n8n_inbound'` exactly. If N8N's Supabase node set it to something else, adjust the filter.

---

## What happens next (after Build #3 — the reasoning loop)

Once you've added this node and the reasoning loop is live, every hot inbound will trigger a chain:

1. Email arrives → N8N classifies → calls `record_inbound_from_n8n`
2. Function publishes `agent_events.inbound.classified` with `severity=warn`
3. The reasoning loop's subscriber sees the event, reads the full context via `context_builder`, drafts a reply through the `draft_critic`, and either sends through `send_gateway` or escalates to you in Telegram based on the policy file (Build #3 deliverables)

You go from "N8N auto-replied something generic" to "hot reply was triaged, drafted, critiqued, and either sent or flagged for my review — all within 30 seconds."

---

*Related: [database/012_inbound_rpc.sql](../database/012_inbound_rpc.sql) — the function itself. [skills/send-gateway/SKILL.md](../skills/send-gateway/SKILL.md) — the outbound counterpart.*
