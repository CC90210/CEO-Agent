# VPS Finish Prompt — last-mile paste to finalize Adon Phase 2 deploy

> Use this prompt AFTER the unified deploy prompt
> (`VPS_PHASE1_DEPLOY_PROMPT.md`) ran and paused for inputs.
> Fill in the 3 placeholders inline (<FILL_IN_*>), then paste the whole
> thing in your VPS Claude Code chat.
>
> Migration 078 is ALREADY applied to production (CC ran it via
> Supabase Management API from his PC) — this prompt skips it.

---

You are continuing the SunBiz deploy from your previous run. Steps 1, 2,
8b, 8c from `VPS_PHASE1_DEPLOY_PROMPT.md` are done. Migration 078 is
ALREADY applied to production — SKIP step 5 entirely. The earlier
"`tenant_forms` doesn't exist" anomaly was a typo in the prior prompt;
the real table is `forms` (fixed in the current revision).

Here's what to finish.

## Step A — write Anthropic key + BRAND_IDENTITY values

CC has provided the three values inline below. Substitute them
literally, write to the secrets file, never echo them back to chat.

```bash
sudo -u sunbiz bash -c 'cat >> /srv/sunbiz/ceo-agent/.env.agents <<EOF
BRAVO_ANTHROPIC_API_KEY=<FILL_IN_ANTHROPIC_KEY>
ANTHROPIC_API_KEY=<FILL_IN_ANTHROPIC_KEY>
EOF'
sudo chmod 600 /srv/sunbiz/ceo-agent/.env.agents
```

Then patch the SunBiz BRAND_IDENTITY block in send_gateway.py to remove
the two placeholder TODOs:

```bash
sudo -u sunbiz sed -i \
  -e 's|"sender_name": "Sun Biz Funding Team",  # TODO: confirm with Ezra|"sender_name": "<FILL_IN_SENDER_NAME>",|' \
  -e 's|"business_address": "Sun Biz Funding",  # TODO: confirm address with Ezra|"business_address": "<FILL_IN_BUSINESS_ADDRESS>",|' \
  /srv/sunbiz/ceo-agent/scripts/integrations/send_gateway.py
```

Also remove "Sun Biz Funding" from the PLACEHOLDER_BUSINESS_ADDRESSES
frozenset (it should only contain the empty string now):

```bash
sudo -u sunbiz sed -i 's|    "Sun Biz Funding",$||' /srv/sunbiz/ceo-agent/scripts/integrations/send_gateway.py
```

Verify:

```bash
grep -A 6 '"sunbiz":' /srv/sunbiz/ceo-agent/scripts/integrations/send_gateway.py
```

Should show non-placeholder sender_name + business_address.

## Step B — restart pm2 with new env

```bash
sudo -u sunbiz pm2 restart all --update-env
sudo -u sunbiz pm2 list
```

All daemons should return to `online`. Surface any errored ones.

## Step C — register the Sentinel daemon

```bash
cd /srv/sunbiz/sunbiz-agent
sudo -u sunbiz pm2 start /srv/sunbiz/ceo-agent/.venv/bin/python \
  --name sunbiz-sentinel \
  --interpreter none \
  -- scripts/sentinel.py loop --interval 60
sudo -u sunbiz pm2 save
sleep 5
sudo -u sunbiz pm2 logs sunbiz-sentinel --lines 5 --nostream
```

Expect a "sentinel: starting loop interval=60s window=5 tenant=aa04fa1f.."
line in the log.

## Step D — smoke test the Anthropic key with Sentinel

```bash
sudo -u sunbiz /srv/sunbiz/ceo-agent/.venv/bin/python \
  /srv/sunbiz/sunbiz-agent/scripts/sentinel.py score \
  --text "stop emailing me you idiots" --json | head -10
```

Expect `source: "llm"` and score around -100. If `source: "fallback"`,
the Anthropic key from Step A is wrong — halt and tell CC.

## Step E — final report

Write `/srv/sunbiz/full-deploy.log`:

```
=== SunBiz Final Deploy — {ISO timestamp} ===

[A] Anthropic key written         : YES (len + prefix only)
[A] BRAND_IDENTITY resolved        : YES — sender + address non-placeholder
[B] pm2 restart all               : N/N online, errored=[list]
[C] sunbiz-sentinel registered    : online / errored
[D] Sentinel LLM smoke            : PASS / FAIL — source=llm + score
[E] Production-readiness          : %

Remaining (CC's browser action): flip enabled=true on
"Adon Agent 1 — Inquiry Welcomer" via oasisai.work/sequences when ready.
```

## Constraints

- Never echo the Anthropic key back to chat.
- Never push to git from this VPS.
- Never flip the Inquiry Welcomer enabled=true — that's CC's
  browser action after he sanity-checks the template content.

Begin Step A now.

---

## CC: the 3 values to substitute before pasting

1. `<FILL_IN_ANTHROPIC_KEY>` — your real Anthropic API key (starts `sk-ant-api03-`, ~100+ chars). Get it from https://console.anthropic.com/settings/keys. Paste the same value in both spots in Step A.

2. `<FILL_IN_SENDER_NAME>` — the human name SunBiz emails sign off as. Most likely just `Ezra` (the operator on Submissions@sunbizfunding.com).

3. `<FILL_IN_BUSINESS_ADDRESS>` — SunBiz's legal mailing address for the CASL footer. Format like `Sun Biz Funding, 123 Main St, City, ST 12345, USA`. Without this, SunBiz commercial emails will keep getting blocked at the placeholder check.

Substitute those 3 strings inline, then paste the whole block (everything between the dashes) to your VPS Claude Code chat. The agent will run Steps A–E and write you a final report.
