# VPS — paste Monday-meeting credentials (Twilio + Anthropic)

> When the Monday onboarding meeting hands you the live Twilio creds
> and the production Anthropic API key, replace the four `<FILL_IN>`
> placeholders below with the real values, then paste the entire
> block (between the triple-dashes) into your VPS Claude Code session.
>
> The VPS agent writes them to `.env.agents`, restarts the right
> daemons, and verifies. Nothing else CC needs to do on the VPS.

## Before pasting

Replace these four placeholders inline:

| Placeholder | Where it came from |
|---|---|
| `<TWILIO_SID>` | Twilio Console → Account SID (starts with `AC...`) |
| `<TWILIO_AUTH>` | Twilio Console → Auth Token |
| `<TWILIO_FROM>` | Twilio Console → Phone Numbers → the SunBiz number, in E.164 (`+1NPANXXXXXX`) |
| `<ANTHROPIC_KEY>` | Anthropic Console → API Keys → SunBiz production key (starts with `sk-ant-`) |

## Paste into VPS Claude Code

---

You are the Claude Code agent on CC's SunBiz Funding VPS. CC just
came out of the onboarding meeting with live production credentials
for Twilio (outbound SMS) and Anthropic (bridge chat brain). Your job:
write them to `.env.agents`, restart the dependent daemons, verify
both are live. Strictly SunBiz scope.

## The four values

- Twilio Account SID: `<TWILIO_SID>`
- Twilio Auth Token: `<TWILIO_AUTH>`
- Twilio From number (E.164): `<TWILIO_FROM>`
- Anthropic API key: `<ANTHROPIC_KEY>`

## Step 1 — Back up `.env.agents` before editing

```bash
sudo cp /srv/sunbiz/ceo-agent/.env.agents /srv/sunbiz/ceo-agent/.env.agents.bak.$(date +%Y%m%d-%H%M)
```

If `.env.agents` is at a different path on this VPS (some installs
keep it at `/srv/sunbiz/.env.agents`), find it first with
`sudo find /srv/sunbiz -name '.env.agents' -not -path '*backup*'` and
use that path consistently below.

## Step 2 — Update Twilio block

Use `sudo sed -i` to overwrite each line in place (these keys already
exist with placeholders from the finalization pass — you're replacing
the values, not appending):

```bash
ENVFILE=/srv/sunbiz/ceo-agent/.env.agents

sudo sed -i "s|^SUNBIZ_TWILIO_ACCOUNT_SID=.*|SUNBIZ_TWILIO_ACCOUNT_SID=<TWILIO_SID>|" "$ENVFILE"
sudo sed -i "s|^SUNBIZ_TWILIO_AUTH_TOKEN=.*|SUNBIZ_TWILIO_AUTH_TOKEN=<TWILIO_AUTH>|" "$ENVFILE"
sudo sed -i "s|^SUNBIZ_TWILIO_FROM=.*|SUNBIZ_TWILIO_FROM=<TWILIO_FROM>|" "$ENVFILE"
```

If any `sed` reports zero substitutions (key missing), append it
instead:

```bash
echo "SUNBIZ_TWILIO_ACCOUNT_SID=<TWILIO_SID>" | sudo tee -a "$ENVFILE"
# etc.
```

## Step 3 — Update Anthropic key

```bash
sudo sed -i "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=<ANTHROPIC_KEY>|" "$ENVFILE"
```

## Step 4 — Verify the file looks right (don't print the values)

```bash
sudo grep -E "^(SUNBIZ_TWILIO_ACCOUNT_SID|SUNBIZ_TWILIO_AUTH_TOKEN|SUNBIZ_TWILIO_FROM|ANTHROPIC_API_KEY)=" "$ENVFILE" \
  | sed 's|=.*|=<set>|'
```

Expect 4 lines, each ending `=<set>`. Don't `cat` or `grep` the raw
values back to chat — keep secrets out of the conversation log.

## Step 5 — Restart the dependent daemons

```bash
pm2 restart sunbiz-send-gateway   # picks up Twilio
pm2 restart sunbiz-bridge          # picks up Anthropic
pm2 restart sunbiz-cron            # picks up both (for any cron-scheduled SMS)
pm2 save
```

## Step 6 — Live verification

Bridge can call Anthropic:

```bash
curl -s -H "Authorization: Bearer oasis_bridge_FV5jYKH9xe0FTaEOZkIeJXYHVM1v1eJURsT8zKlLvXc" \
  https://bridge.oasisai.work/health
```

Expect `{"ok":true,...}`. Then:

```bash
pm2 logs sunbiz-bridge --lines 30 --nostream | grep -iE "anthropic|ready|listening|error"
```

Expect a "ready"/"listening" line and no anthropic-auth errors.

Twilio is wired (don't send a live SMS as part of verify — just confirm
the gateway booted):

```bash
pm2 logs sunbiz-send-gateway --lines 30 --nostream | grep -iE "twilio|ready|listening|error"
```

Expect "ready" / "listening" and no `auth` / `401` errors.

## Step 7 — Report back to CC

Tell CC:
- All 4 env vars updated (with `<set>` confirmation from step 4)
- Three daemons restarted clean (any restart-loop counter increments — flag them)
- Bridge `/health` returned `{"ok":true}`
- No auth errors in the daemon logs after restart
- If ANYTHING was off (sed reported 0 substitutions, a daemon
  errored, /health didn't return 200), name it precisely. Don't
  paper over it.

---

## Rollback (only if something explodes)

```bash
sudo cp /srv/sunbiz/ceo-agent/.env.agents.bak.<timestamp> /srv/sunbiz/ceo-agent/.env.agents
pm2 restart sunbiz-send-gateway sunbiz-bridge sunbiz-cron
```

The backup was made in step 1.
