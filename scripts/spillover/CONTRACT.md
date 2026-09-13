---
tags: [spillover, claude-code, omniroute, contract, failover]
last_updated: 2026-09-12
status: v1
---
# Claude Spillover — interface contract (v1)

The single source of truth for how the spillover pieces talk to each other. The design rationale lives in
[[docs/adr/0018-claude-spillover]]; operator usage lives in [[skills/claude-spillover/SKILL]].
If code and this file disagree, fix one of them in the same commit.

## 1. What it is
Claude Code sessions set `ANTHROPIC_BASE_URL=http://127.0.0.1:20131`, and no credential, so the
claude.ai Max login stays the active credential. The **spillover proxy** forwards everything
byte-for-byte to `https://api.anthropic.com`. When Anthropic returns an **account-wide subscription
usage-limit 429**, eligible requests go to **OmniRoute** (`127.0.0.1:20128`, combo `bravo-fallback`)
until the limit resets. OmniRoute never holds a Claude credential.

## 2. Ports and paths
| Thing | Value |
|---|---|
| Proxy listen | `127.0.0.1:20131` (never 0.0.0.0) |
| OmniRoute listen | `127.0.0.1:20128`, with `PORT`, `API_PORT` and `DASHBOARD_PORT` all 20128 |
| Runtime home (`HOME_DIR`) | Windows `%LOCALAPPDATA%\bravo-spillover`; Mac `~/Library/Application Support/bravo-spillover` |
| `HOME_DIR/app/` | Deployed `spillover_proxy.js`, `limit_detector.js`, `supervisor.js`, plus `VERSION` (git sha) |
| `HOME_DIR/bin/` | Deployed `lane_key.py`, `statusline.py`, `ensure_spillover.py`, `claude-direct.cmd` |
| `HOME_DIR/config.json` | Runtime config (schema §3). Hot-reloaded (mtime poll 2 s) |
| `HOME_DIR/state/` | `state.json`, `events.jsonl`, `captured/`, `fault.json`, `owned_settings.json`, `supervisor.pid`, `logs/` |
| `HOME_DIR/secrets/` | DPAPI blobs `omniroute_lane.key`, `storage_encryption.key`, `initial_password.key` (owner-only ACL) |
| `HOME_DIR/omniroute-src/` | OmniRoute checkout at the pinned sha, built |
| `HOME_DIR/omniroute-data/` | OmniRoute `DATA_DIR` (owner-only ACL) |
| Repo sources | `scripts/spillover/*.js`, `*.py`, `claude-direct.cmd`; `scripts/integrations/omniroute_tool.py`; `config/spillover.json` (committed defaults); `config/spillover/automation_pin.json` |

`omniroute_tool.py deploy` copies the repo sources into `HOME_DIR/app` and `HOME_DIR/bin`. It creates
`HOME_DIR/config.json` from `config/spillover.json` if it is missing, and merges new keys in without
overwriting local values. Everything that runs at runtime reads from `HOME_DIR`, never from the repo
checkout, so production does not depend on which branch the checkout is on.

## 3. `config.json` schema (repo defaults: `config/spillover.json`)
```json
{
  "version": 1,
  "min_claude_code": "2.1.268",
  "deny_claude_code": ["2.1.265", "2.1.266", "2.1.267"],
  "python_exe": "C:/Users/User/Business-Empire-Agent/.venv/Scripts/python.exe",
  "proxy": {
    "host": "127.0.0.1",
    "port": 20131,
    "mode": "observe",
    "anthropic_base": "https://api.anthropic.com",
    "omniroute_base": "http://127.0.0.1:20128",
    "spill_entrypoints": ["cli", "claude-vscode"],
    "probe_interval_sec": 600,
    "reset_clamp_min_sec": 60,
    "reset_clamp_max_sec": 691200,
    "fallback_first_content_timeout_ms": 90000,
    "fallback_retry_budget_ms": 60000,
    "fallback_persistent_outage_sec": 300,
    "fallback_health_fail_threshold": 3,
    "fallback_health_ttl_ok_ms": 15000,
    "fallback_health_ttl_fail_ms": 5000,
    "stream_silence_abort_ms": 180000,
    "ping_interval_ms": 15000,
    "max_replay_body_bytes": 33554432,
    "fallback_window_tokens": 200000,
    "allow_fault_injection": false,
    "alerts": { "telegram": true, "toast": true },
    "route_model_main": "bravo-fallback",
    "route_model_fast": "bravo-fallback-fast"
  },
  "omniroute": {
    "repo": "https://github.com/diegosouzapw/OmniRoute",
    "git_sha": "152d95108c9c3d557562311ffed63240a511eb31",
    "min_next": "16.3.3",
    "deny_versions": ["3.8.50"],
    "memory_mb": 1536,
    "forbidden_model_prefixes": ["cc/", "claude/", "oc/", "opencode/", "kr/", "kiro/", "agy/", "antigravity/", "gemini/", "gemini-cli/", "groq/", "glm-cn/", "qwen-web/", "deepseek-web/"]
  }
}
```
**`proxy.mode`:**
- `passthrough` is the kill switch. Everything is forwarded, nothing is spilled, and the state machine is frozen at `direct`.
- `observe` forwards everything and records detected limits and header telemetry, but never spills.
- `spill` enables the full behaviour.

## 4. Spill eligibility (all must hold)
1. `proxy.mode == "spill"` and state `mode == "spilling"`, or a limit was just detected on this request.
2. The request is `POST /v1/messages` (with or without the `?beta=true` query).
3. `authorization` is `Bearer sk-ant-oat…`, which is a claude.ai OAuth login. A request that carries `x-api-key` is **never** eligible.
4. The user-agent entrypoint (see `parseEntrypoint`) is in `proxy.spill_entrypoints`.
5. There is no `x-bravo-lane: automation` header and no `x-bravo-spill: deny` header (matching is case-insensitive).

## 5. Limit detector (`limit_detector.js`, a pure CommonJS module)
`classify({status, headers, bodyText, nowMs})` → `{kind, claim, reset_at, reset_source, reason}`

`headers` is a lowercase-keyed object, and `reset_at` is in epoch seconds.

**Kinds:**
- `subscription_limit` requires all of these:
  - `status === 429`
  - `headers['anthropic-ratelimit-unified-status'] === 'rejected'` (exact key; `…-overage-status` never counts)
  - `bodyText` JSON has `error.type === 'rate_limit_error'`
  - `anthropic-ratelimit-unified-representative-claim` is `five_hour` or `seven_day`
  - `anthropic-ratelimit-unified-fallback !== 'available'`
  - `anthropic-ratelimit-unified-overage-in-use` is not `true`
- `model_limit`: the same, but the claim is any other value (`seven_day_opus`, `seven_day_sonnet`, …). This is **never** spilled.
- `transient`: every other 429, and 529.
- `none`: anything else.

**`reset_at`** is taken from the first source that works:
1. `anthropic-ratelimit-unified-reset` (epoch seconds or RFC 3339), corrected by `(nowMs − Date header)` skew.
2. `retry-after` (seconds or HTTP-date).
3. `now + 1800`.

It is clamped to `[now + reset_clamp_min_sec, now + reset_clamp_max_sec]`.

**Other exports:**
- `parseEntrypoint(ua)`: for `claude-cli/<ver> (external, <entrypoint>[, …])` it returns `<entrypoint>`, otherwise `null`.
- `isOAuthBearer(authHeader)`.
- `claudeCodeVersion(ua)`.

## 6. State (`HOME_DIR/state/state.json`)
Writes are atomic: write to a tmp file, then rename, retrying on EPERM or EBUSY up to 10 times with backoff.
```json
{ "schema_version": 1, "mode": "direct|spilling", "config_mode": "passthrough|observe|spill",
  "limit": null,
  "fallback": { "healthy": true, "checked_at": null, "consecutive_failures": 0, "last_error": null, "outage_since": null },
  "last_probe_at": null,
  "counters": { "direct": 0, "fallback": 0, "limit_passthrough": 0, "overloaded_529": 0, "automation": 0, "errors": 0 },
  "last_route": null,
  "instance_id": "<uuid v4, stable per process start>", "pid": 0, "started_at": "ISO", "version": "<sha>" }
```
- `limit`, when set, is `{detected_at, reset_at (ISO), reset_source, claim, captured}`.
- `last_route` is `{at, route: "direct|fallback|limit-429|overloaded-529|local", status, lane: "interactive|automation|other"}`.

**`events.jsonl`** holds one JSON line per request with these fields:
`ts, req_id, method, path, lane, entrypoint, cc_version, route, status, upstream_status, ms, bytes_in, bytes_out, reason, route_model, unified:{status, claim, reset, fallback, overage_status}`

It never contains an authorization value, `x-api-key` or a body. At 5 MB it rotates to `events.jsonl.1`.

**`captured/429-<ts>.json`** is written by an allowlist. It keeps only:
- the status;
- header **names**;
- values for `anthropic-ratelimit-*`, `retry-after`, `date` and `content-type`;
- `error.type` and `error.message`.

In the message, ids (`req_…`, UUIDs, `org…`) are replaced with `<ID>`. Nothing else is written.

## 7. Health endpoint
`GET /__spillover/health` → `200 {"ok":true,"instance_id","pid","version","config_mode","mode","reset_at","fallback_healthy"}`

It answers only a loopback peer with a valid Host header. There are no other admin endpoints: every
control goes through `config.json` and `fault.json`.

## 8. Fault injection (`HOME_DIR/state/fault.json`)
`{"mode":"force_limit|force_reset|omniroute_down","expires_at":"ISO"}`

It is honoured only while `proxy.allow_fault_injection` is `true` and `expires_at` is at most one hour ahead.

| Mode | Effect |
|---|---|
| `force_limit` | The next eligible request is treated as if Anthropic returned a synthetic `subscription_limit` 429 (claim `five_hour`, reset = `expires_at`). Anthropic is not called. |
| `force_reset` | Clears `limit` and moves to `direct`. |
| `omniroute_down` | Fallback health reports false. |

`omniroute_tool.py spillover fault set` requires an interactive TTY confirmation and sends a Telegram alert.

## 9. Lane key and secrets
`lane_key.py` offers `generate <name> [--bytes N]`, `set <name>` (read with getpass), `exists <name>` (prints `true` or `false`) and `get <name>` (prints the value to stdout).
- **Storage:** DPAPI at user scope on Windows, the `security` keychain on the Mac. Stdlib only. `get` is blocked for agent Bash and PowerShell calls by `secret_guard`.
- **Callers:**
  - The proxy runs `python_exe bin/lane_key.py get omniroute_lane` windowless when it starts, and again after a fallback 401.
  - The supervisor fetches `storage_encryption` and `initial_password` the same way to build OmniRoute's env.
- **Handling:** values live only in process memory, are never logged, and are never written anywhere else.

## 10. Supervisor (`supervisor.js`)
- **Single instance.** It binds `proxy.port` itself (cluster primary, one worker running `spillover_proxy.js`). If the bind fails with `EADDRINUSE`, it checks `/__spillover/health`: if that shows our own instance it exits 0; otherwise it exits 3 and alerts.
- **Worker restarts.** It respawns the worker after 250 ms, backing off to 5 s after 5 crashes in a minute.
- **OmniRoute child.** It runs `node --use-system-ca <omniroute-src>/bin/omniroute.mjs serve --no-open --port 20128` with an allowlisted env and restarts it with backoff. Before spawning, it kills any stale process that owns :20128 and whose command line contains `HOME_DIR/omniroute-src`.
- **Environment.** Everything it launches gets an **allowlisted env**: `SystemRoot, SYSTEMROOT, PATH, TEMP, TMP, USERPROFILE, LOCALAPPDATA, APPDATA, HOME, COMPUTERNAME, NODE_EXTRA_CA_CERTS` (only if the file exists), plus the variables that component itself needs. No `ANTHROPIC_*`, `OPENAI_*` or `CLAUDE_*` variable is ever passed through.
- **Shutdown.** On shutdown it kills its children. On Windows the OmniRoute tree is killed with `taskkill /T /F`.

## 11. Test mode
A proxy or supervisor honours `--test --state-dir D --anthropic-base URL --omniroute-base URL --lane-key K --port N --now-offset S` only when `--test` is present **and** every URL host is `127.0.0.1` or `localhost`. In any other case these flags are rejected with exit 2. Environment overrides are never read.

## 12. Claude Code settings written by `omniroute_tool.py spillover enable-routing`
- **Env keys** in `~/.claude/settings.json`: `ANTHROPIC_BASE_URL=http://127.0.0.1:20131` and `ENABLE_TOOL_SEARCH=true`.
- **statusLine:** `bin/statusline.py`.
- **User SessionStart hook:** `pythonw bin/ensure_spillover.py`.
- **Owned keys** are recorded in `state/owned_settings.json` with a backup path.
- It **refuses** when any of these hold:
  - the proxy is unhealthy;
  - a running `claude.exe`, or the CLI, is in `deny_claude_code` or older than `min_claude_code`;
  - `~/.claude/settings.json` already holds `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY` or `apiKeyHelper`.
- **Rollback** (`omniroute_tool.py rollback`):
  1. Set `ANTHROPIC_BASE_URL=https://api.anthropic.com`.
  2. Instruct CC to restart open sessions.
  3. Stop the supervisor and remove the Startup VBS.
  4. Remove the owned keys and restore from backup.

## 13. Automation guards (independent of the proxy)
- `config/spillover/automation_pin.json` = `{"env":{"ANTHROPIC_BASE_URL":"https://api.anthropic.com"}}`. It is passed as `--settings <abs path>` by `run_claude_cli` and `run_claude_cli_on_document`.
- The spawn env extras add `ANTHROPIC_CUSTOM_HEADERS=X-Bravo-Lane: automation`.
- `build_claude_spawn_env` in all ports strips the inherited `lane_env_strip` vars **before** applying extras.
- Per-repo deny: the repo's `.claude/settings.local.json` env sets `ANTHROPIC_CUSTOM_HEADERS=X-Bravo-Spill: deny` (SunBiz-Agent).

## 14. Alert helper CLI (clarification 2026-09-12)
Usage: `<python_exe> <HOME_DIR>/bin/spillover_alert.py <kind> <message>`. Both arguments are
**positional**; there are no flags.
- **Callers** (proxy and supervisor) spawn it detached and windowless, and never await it.
- **Exit code:** it always exits 0, logging any delivery failure to `state/logs/alerts.log`.
- **Arguments:** never pass secrets in them.
- **`<kind>`** is free-form `[a-z_]+` and becomes part of the Telegram dedup key.
- **Kinds in use:** `entered_fallback`, `fallback_down`, `back_to_claude`, `session_too_large`,
  `supervisor_port_foreign`, `omniroute_secrets_missing`, `fault_injection`.

## 16. OmniRoute signing secrets (clarification 2026-09-12)
The OmniRoute runtime is the pinned source built in **backend-only** mode (`OMNIROUTE_BUILD_BACKEND_ONLY=1`,
Turbopack). That build stubs OmniRoute's instrumentation, so `ensureSecrets()` never generates its secrets.
The supervisor therefore passes all four from DPAPI blobs on every start:
- `STORAGE_ENCRYPTION_KEY` from `storage_encryption`
- `INITIAL_PASSWORD` from `initial_password`
- `JWT_SECRET` from `jwt_secret`
- `API_KEY_SECRET` from `api_key_secret`

All four must stay stable across restarts, or API keys, including the lane key, stop validating.
`omniroute_tool.py secrets init` generates any that are missing. If any secret is missing, the supervisor refuses to start OmniRoute.

## 15. OmniRoute runtime location (clarification 2026-09-12)
`config.json` key `omniroute.runtime_dir` names the OmniRoute install the supervisor runs and that
`doctor` / `install --verify` inspect. It may be absolute or relative to `HOME_DIR`, and it defaults
to `omniroute-src`, the pinned git build.
- **Must contain:** `bin/omniroute.mjs` and `dist/server.js`.
- **Bundled Next.js:** must be 16.3.3 or later.
- **npm install (e.g. `omniroute-npm/node_modules/omniroute`):** `omniroute.next_patched: true` records
  that its bundled Next.js runtime was upgraded to 16.3.3 or later in place. `doctor` still checks the
  real Next.js version on disk.
