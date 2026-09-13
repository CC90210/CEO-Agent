---
name: claude-spillover
description: "Claude Code usage-limit failover: at the Claude Max account-wide limit, interactive sessions spill to OmniRoute's bravo-fallback combo until reset, then return to Claude. Use for status, doctor, the kill switch (spillover passthrough), claude-direct, rollback and drills."
triggers: ["usage limit", "claude limit", "claude usage limit", "hit my limit", "hit the limit", "session limit", "switch model", "fallback", "fallback mode", "spillover", "claude spillover", "spillover status", "omniroute", "claude-direct", "is this claude"]
tier: specialized
dependencies: []
tags: [skill, spillover, claude-code, omniroute, failover, model-fallback]
last_updated: 2026-09-12
---

# Claude Spillover — keep working through a Claude usage limit

> **Prerequisite — hard dependency ([[docs/adr/0001-skill-dependency-classification]]).** This skill needs
> the spillover proxy and OmniRoute running. Before anything else:
>
> ```bash
> python scripts/integrations/omniroute_tool.py health --json
> ```
>
> Non-zero exit → run `python scripts/integrations/omniroute_tool.py doctor --json` and read the failing
> check. A dead supervisor restarts when a new Claude Code session opens (SessionStart ensure-hook); until
> then `claude-direct` (below) reaches Claude with no proxy and no Python. Never "fix" a failing health check
> by stopping the proxy or hand-editing `~/.claude/settings.json`.

Contract: [[scripts/spillover/CONTRACT]] · Decision: [[docs/adr/0018-claude-spillover]] · Terms: [[CONTEXT]]
§ Spillover · Radar rows: [[brain/TOOL_SHED]] § 9. Spillover is not the messaging gateway and not
`send_gateway.py`.

## What it does

- Claude Code (IDE panel + CLI) sets `ANTHROPIC_BASE_URL=http://127.0.0.1:20131` and **no credential**, so
  the claude.ai Max login stays the active credential.
- The spillover proxy forwards every request byte-for-byte to `https://api.anthropic.com` — about 99% of
  traffic.
- On an account-wide **subscription usage-limit 429** (`five_hour` or `seven_day` claim; the exact header set
  is in CONTRACT §5), eligible requests go to OmniRoute `127.0.0.1:20128`, combo `bravo-fallback`: GPT-5.6
  through CC's ChatGPT plan first, then Cerebras, then Cloudflare Workers AI models that passed the smoke gate. Haiku-class
  requests use `bravo-fallback-fast`.
- It returns to Claude at `reset_at`, or sooner when the 10-minute probe gets a non-limit reply from
  Anthropic.
- **Who spills:** interactive OAuth sessions only (`cli`, `claude-vscode` entrypoints), including their Task
  subagents. **Never:** `x-api-key` requests, automations (automation pin + `X-Bravo-Lane: automation`), and
  repos that set `X-Bravo-Spill: deny` (SunBiz-Agent).
- **What never triggers a spill:** model-scoped limits (Opus-only, Sonnet-only) and transient 429s / 529s.
  They pass through untouched, so Claude Code's own handling applies.
- OmniRoute never holds a Claude credential.

## Status and doctor

```bash
python scripts/integrations/omniroute_tool.py spillover status   # DIRECT, or SPILLING until <reset>; fallback health; counters; last route
python scripts/integrations/omniroute_tool.py health --json      # quick liveness (the prerequisite)
python scripts/integrations/omniroute_tool.py doctor --json      # every hardening check must pass
```

- **CLI:** the status line shows 5h/7d usage and `DIRECT` or `FALLBACK until 3:45pm`. **IDE panel:** it
  doesn't render status lines — watch for the Windows toast and the Telegram alert.
- **Raw state (read-only):** `%LOCALAPPDATA%\bravo-spillover\state\state.json`, plus one metadata line per
  request in `events.jsonl` (`route` is `direct`, `fallback`, `limit-429`, `overloaded-529` or `local`).
  Neither ever holds an auth header or a body.
- **`doctor` asserts:** OmniRoute listens only on 127.0.0.1; 401 without a key; Next.js ≥ 16.3.3; runtime
  version not denied; no plaintext key in `DATA_DIR/.env`; `log_env` caps present; `requireLogin` true; no
  tunnel processes (cloudflared, ngrok, tailscale); a rebinding Host/Origin probe refused on an API route and
  a management route (OmniRoute has no Host allowlist, so its auth is what refuses it); `POST
  /api/system/version`, `/api/settings/mitm` and `/api/settings/require-login` refused without auth;
  forbidden providers absent; proxy healthy; Claude Code versions allowed; owned settings unchanged; no
  user-level Anthropic credential vars; the ChatGPT training-off attestation present. The pinned sha is
  checked by `install --verify`. Not automated yet: the canary-prompt rotation check (ADR 0018, decision 6).

## What happens at a limit

1. Anthropic returns the subscription usage-limit 429. The proxy records `reset_at` (from
   `anthropic-ratelimit-unified-reset`, skew-corrected, clamped to now + 60 s … now + 8 days), stores a
   sanitized copy of the 429, moves to SPILLING, and alerts "entered fallback" (toast + Telegram).
2. The same request is replayed to the fallback if it is eligible, the fallback is healthy, and it fits.
   Otherwise Claude Code gets the 429 verbatim and shows its normal limit message.
3. While spilling, the turn — its tools, MCP calls and Task subagents — runs on `bravo-fallback`. Thinking
   blocks are dropped, so transcripts never carry unsigned thinking. `count_tokens` returns 404, and Claude
   Code falls back to its own estimate. A context overflow comes back as
   `prompt is too long: N tokens > M maximum`, so Claude Code auto-compacts.
4. **Session too big for the fallback window:** the stored 429 plus an alert — "open a new chat, it will run
   on GPT-5.6".
5. **Fallback trouble:** a short outage returns `529 overloaded_error`, and Claude Code retries. A persistent
   one (over 5 min, or 3 consecutive health failures) returns the stored 429 — the normal limit message —
   and one "fallback down" alert.
6. **Back on Claude:** at `reset_at`, or when the probe gets any reply other than 429, 5xx or 529. The first
   turn back may cost one invisible retry (thinking-signature recovery). Alert: "back on Claude".

## Kill switch — `spillover passthrough`

```bash
python scripts/integrations/omniroute_tool.py spillover passthrough   # forward everything, never reroute
python scripts/integrations/omniroute_tool.py spillover enable        # spilling back on
```

- Passthrough is a hot-reloaded config change, picked up within about 2 s. It freezes the state machine at
  `direct`: every request keeps going to Anthropic, and a limit 429 reaches Claude Code verbatim.
- **Never stop the proxy as a kill switch.** Every open session is pointed at `127.0.0.1:20131`; a stopped
  proxy breaks them all instead of disabling the fallback.

## `claude-direct` — Claude with no proxy at all

```bat
%LOCALAPPDATA%\bravo-spillover\bin\claude-direct.cmd
```

It runs `claude --settings {"env":{"ANTHROPIC_BASE_URL":"https://api.anthropic.com"}}` and works with the
proxy down and without Python. Use it when the supervisor is dead and you can't wait for a SessionStart
restart, or for a session that must not spill.

## Rollback

```bash
python scripts/integrations/omniroute_tool.py rollback
```

1. It changes `ANTHROPIC_BASE_URL` to `https://api.anthropic.com` first: a changed value reaches open
   sessions, a removed key doesn't.
2. It tells CC to restart open sessions.
3. It stops the supervisor and removes the Startup VBS.
4. It removes the keys and hooks it owns (recorded in `state/owned_settings.json`) and restores from backup.

`python scripts/integrations/omniroute_tool.py uninstall --purge` also removes OmniRoute and its data.

## Drills

Fault injection is honoured only while `proxy.allow_fault_injection` is `true` in
`%LOCALAPPDATA%\bravo-spillover\config.json`. Each drill asks for an interactive TTY confirmation, carries a
TTL of at most one hour, and sends a Telegram alert. Set one with
`python scripts/integrations/omniroute_tool.py spillover fault set` (see its `--help` for the mode argument).

| Mode | Expect |
|---|---|
| `force_limit` | The next eligible turn (Bash, Edit, a Task subagent, an MCP tool) runs on GPT-5.6; `events.jsonl` shows `route=fallback`; the toast and Telegram both fire |
| `force_reset` | The next turn goes to Claude; any thinking-signature 400 recovers invisibly |
| `omniroute_down` | A 529 retry, then the normal limit message; `route=limit-429 reason=fallback_down`; exactly one alert |

Also: `--resume` in both states; kill the proxy worker (it respawns in under 1 s); kill the supervisor (a new
session's SessionStart restarts it, and `claude-direct` works meanwhile); during a forced spill,
`python scripts/lib/model_fallback.py "Reply with PONG."` is served direct by Claude with `lane=automation`.
Run the same drill in the IDE panel while CC watches.

## Never do

- **Never import Claude credentials into OmniRoute** — no `cc/` or `claude/` provider, no Claude login, no
  `sk-ant-*` value in OmniRoute's database, logs or env. That intermediates the credential and impersonates
  the CLI; OmniRoute issue #4118 reports Max accounts banned about a minute after connecting.
- **Never enable `oc`, `kiro`, `agy` or Gemini OAuth** — not in a combo, not for a quick test. OpenCode free
  models may use what they collect to improve the model; the Kiro, Antigravity and Gemini logins breach their
  terms and draw bans (sources: [[brain/TOOL_SHED]] § 9).
- **Never run `omniroute config set claude`, `autostart`, `launch`, `run claude`, or the dashboard's Apply
  Config.** Each can overwrite `~/.claude/settings.json`.
- **Never stop the proxy as a kill switch.** Use `spillover passthrough`.
- Never put the proxy or OmniRoute under `fleet_watchdog` (ADR-0018 § 3), never paste a provider key into
  chat or `.env.agents`, never run `lane_key.py get` from an agent shell, and never commit an unsanitized
  429 capture.

## Related

[[docs/adr/0018-claude-spillover]] · [[scripts/spillover/CONTRACT]] · [[CONTEXT]] · [[brain/TOOL_SHED]] ·
[[docs/ENV_KEYS_TEMPLATE]] · [[docs/adr/0001-skill-dependency-classification]]
