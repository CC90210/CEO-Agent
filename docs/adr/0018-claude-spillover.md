---
adr: 18
title: "Claude Spillover: a base-URL-only pass-through proxy that fails over to OmniRoute at the subscription usage limit"
status: accepted
date: 2026-09-12
deciders: [cc, bravo]
supersedes: null
superseded_by: null
tags: [docs, adr, decision, spillover, claude-code, omniroute, failover]
last_updated: 2026-09-12
---

# ADR-0018 — Claude Spillover: a base-URL-only pass-through proxy that fails over to OmniRoute at the subscription usage limit

**Status:** Accepted 2026-09-12 by CC · **Deciders:** CC, Bravo
**Interface contract:** [[scripts/spillover/CONTRACT]] · **Operator skill:** [[skills/claude-spillover/SKILL]] · **Vocabulary:** [[CONTEXT]] § Spillover

> Numbered 0018, the next free number after [[docs/adr/0017-cross-agent-claim-leases]]. 0013 and 0014 stay
> reserved for the 0003/0004 renumber described in [[docs/adr/INDEX]].

## Context

Claude Code is the main agent harness: the Antigravity IDE extension and the CLI, on Windows 11 and a Mac,
logged in to a Claude Max subscription. When that subscription hits its usage limit, every session stops
until the reset. CC wants the same conversation to carry on automatically, with no manual step, in every
future session. CC found OmniRoute ([github.com/diegosouzapw/OmniRoute](https://github.com/diegosouzapw/OmniRoute),
MIT), a local AI router with fallback chains.

A 9-agent research sweep and a 4-agent design and red-team pass checked the facts against source code and
official docs. These facts decided the shape:

- **OmniRoute's own Claude provider is unusable.** It cannot pass Claude Code's login through. It always
  sends upstream with a copy of the login stored in its own database, and disguises that traffic as the
  official Claude CLI — it intermediates the credential and impersonates the client. Anthropic's
  [legal page](https://code.claude.com/docs/en/legal-and-compliance) bars tools from collecting, storing or
  intermediating Claude.ai credentials, and OmniRoute issue
  [#4118](https://github.com/diegosouzapw/OmniRoute/issues/4118) reports Max accounts banned about a minute
  after connecting.
- **Claude Code picks one credential per session,** and its built-in model fallback ignores usage limits.
  The only documented way to keep the subscription while sending traffic through a local process is
  base-URL-only mode: set `ANTHROPIC_BASE_URL`, set no credential.
- **The published OmniRoute build is unsafe.** npm 3.8.50 bundles Next.js 16.3.1, which carries a Windows
  unauthenticated RCE (CVE-2026-75604), and it listens on every network interface with no API key. The
  fixes live only on the unreleased branch `release/v3.8.51`; its tip, commit `152d9510` (2026-09-12),
  bundles Next.js 16.3.3.
- **OmniRoute's minimal build profile doesn't build here.** At `152d9510`, `OMNIROUTE_BUILD_PROFILE=minimal`
  fails under webpack with `Module not found: Can't resolve './src/lib/cloudSync.stub.ts'`. The stub files
  exist, but the minimal aliases in `next.config.mjs` are project-root-relative: Turbopack resolves them and
  webpack doesn't. Webpack is required on this 15 GB machine, because the default Turbopack build ran out of
  memory.
- **Claude Code 2.1.265–2.1.267 fail every turn behind any custom base URL.** 2.1.268 is the floor.
- **The repo is public** (CC90210/CEO-Agent). No secret and no unsanitized capture may be committed.

## Decision

### 1. Our own base-URL-only pass-through proxy; OmniRoute on the fallback leg only

Claude Code sessions set `ANTHROPIC_BASE_URL=http://127.0.0.1:20131` and no credential, so the Max login
stays the active credential. The **spillover proxy** (zero-dependency Node) forwards every path, header and
body byte unchanged to `https://api.anthropic.com` — about 99% of traffic. Only an account-wide
**subscription usage-limit 429** (the exact header set is pinned in [[scripts/spillover/CONTRACT]] §5)
moves it to SPILLING, where eligible requests go to OmniRoute (`127.0.0.1:20128`, combo `bravo-fallback`)
until the limit resets. Model-scoped limits and transient 429s and 529s pass through untouched, so Claude
Code's own handling applies.

Why a pass-through of our own, in base-URL-only mode:

- It is the one documented mode that keeps the subscription login. The proxy sees the credential in flight
  and never stores, logs or rewrites it. OmniRoute never holds a Claude credential at all; a code assertion
  plus a test keep any `sk-ant-*` value off the fallback leg.
- Byte-for-byte forwarding keeps Claude Code's own behaviour intact on the path that carries almost all
  traffic — tools, subagents, MCP tool search, `--resume`, streaming, thinking-signature recovery — because
  nothing on the direct leg is reinterpreted. Error bodies are never modified.
- The failover decision needs Anthropic's rate-limit headers, which only something on the request path can
  see. Claude Code's built-in fallback can't make it.

### 2. Spill eligibility is narrow

A request may spill only if it carries a claude.ai OAuth bearer, its user-agent entrypoint is `cli` or
`claude-vscode`, and it has neither `X-Bravo-Lane: automation` nor `X-Bravo-Spill: deny`. `x-api-key`
requests never spill. Daemon automations are also pinned direct to Anthropic by
`--settings config/spillover/automation_pin.json`, independent of the proxy. SunBiz-Agent, which holds
merchant PII, carries `X-Bravo-Spill: deny` by default.

### 3. Deployed outside the repo, supervised outside `fleet_watchdog`

- **Deployed to `%LOCALAPPDATA%\bravo-spillover\`** (Mac: `~/Library/Application Support/bravo-spillover`)
  by `omniroute_tool.py deploy` and stamped with the git SHA. Everything at runtime reads from there, never
  from the checkout. **Why — branch coupling:** the canonical checkout is on `fix/smtp-third-door` with
  uncommitted work; running from it would make every Claude session depend on whichever branch happens to be
  checked out.
- **Its own supervisor.** One Node `supervisor.js` holds the proxy listener, respawns the proxy worker, and
  runs OmniRoute as a separate child. A Startup-folder VBS starts it at logon, and a user SessionStart
  ensure-hook starts it windowless (one instance per port) if it's down.
- **Not under `fleet_watchdog`** — a deliberate deviation from how the rest of the fleet is supervised:
  - the watchdog's **stop is sticky**: a stopped proxy stays stopped, and every session pointed at it breaks;
  - it can be **stopped from the dashboard**: one click would kill every Claude session at once;
  - its pass holds a **lock for about 14 s**, while a proxy that every open session is waiting on has to
    come back in under a second (the supervisor respawns the worker after 250 ms).
- **The kill switch is `omniroute_tool.py spillover passthrough`**: a hot-reloaded config change that keeps
  forwarding and never reroutes. The proxy is never stopped as a kill switch.

### 4. Provider allow / deny list

Enforced as `omniroute.forbidden_model_prefixes` in `config/spillover.json` and checked by
`omniroute_tool.py doctor`. Every row's source URL is in [[brain/TOOL_SHED]] § 9.

| Provider (OmniRoute prefix) | Verdict | Reason |
|---|---|---|
| Codex via ChatGPT OAuth (`cx/`) | **allowed, first** | CC's existing ChatGPT plan (GPT-5.6). OmniRoute gets its own OAuth grant, never an import of `~/.codex/auth.json`. It presents itself as the official Codex CLI — the pattern rejected for Claude — accepted for this one account as R2 because it puts the ChatGPT account at risk, not the Claude login the harness runs on. ChatGPT training must be off before any fallback traffic. |
| Cerebras free key | **allowed after smoke** | Its privacy policy says it does not retain inference inputs and outputs. Joins the combo only after the tool-use smoke gate. |
| Cloudflare Workers AI (`cf/`) | **allowed after smoke, third** | CC's existing Cloudflare account. Cloudflare's data-usage page says customer content isn't used to train models without consent. It needs a token with Workers AI permission, then the same gate. |
| Z.AI free key | **dropped** | CC removed it from the chain on 2026-09-13. The PRC endpoint (`glm-cn/`) stays denied. |
| Claude login (`cc/`, `claude/`) | **denied** | Stores and intermediates the login and impersonates the CLI, which Anthropic's legal page bars; issue #4118 reports bans. |
| OpenCode Free (`oc/`, `opencode/`) | **denied** | OpenCode's Zen free models state that "collected data may be used to improve the model". Its pre-wired provider and the `auto` combo are disabled at setup. |
| Gemini CLI OAuth (`gemini/`, `gemini-cli/`) | **denied** | Gemini CLI's terms call using its OAuth with third-party software a violation that may mean suspension or termination; Google said proxy bans also block Gemini CLI and Code Assist, with a second violation permanent; OmniRoute users report bans; and Gemini CLI stopped serving individual free, Pro and Ultra accounts on 2026-06-18, so CC's login couldn't serve anyway. |
| Antigravity OAuth (`agy/`, `antigravity/`) | **denied** | Antigravity's terms call third-party access with its OAuth a breach that can suspend Antigravity and Gemini CLI; OmniRoute's catalog rates it "avoid", and it lowercases tool names with no released fix. Antigravity stays CC's IDE; only proxying its login is denied. |
| Kiro (`kr/`, `kiro/`) | **denied** | OmniRoute's catalog rates it "avoid"; suspensions are reported; free-tier content may be used for service improvement, and free inputs are stored up to 60 days. |
| Groq (`groq/`) | **denied** | Every Groq model tried failed inside Claude Code through OmniRoute (issue #12134), each with a different error — for example a 4096-token context against Claude Code's ~20.5K-token baseline of system prompt plus tool schemas. |
| `glm-cn/` | **denied** | PRC endpoint (`open.bigmodel.cn`). |
| `qwen-web/`, `deepseek-web/`, and any keyless or training provider | **denied** | Keyless and training providers are excluded by rule. |

### 5. Client-facing automations hold for review

When anything other than Claude answers, email auto-replies (`email_brain.py`), the draft critic
(`draft_critic.py`) and the Instagram DM closer (`ig_conversation_brain.py`) **hold instead of sending**.
They call `model_fallback.run_smart_cli_ex(require_claude=True)`; a non-Claude result takes the existing
degraded/hold path — no auto-send, no DM, a Telegram note to CC. `require_claude=True` also skips the
OpenCode tier, so client content stops going to OpenCode free models. Automations never spill (Decision 2);
the hold covers the other way a non-Claude model can answer them, the existing model-fallback chain.

### 6. OmniRoute is built backend-only, with Turbopack

OmniRoute is built from the pinned source with `OMNIROUTE_BUILD_BACKEND_ONLY=1`, OmniRoute's supported
headless mode:
- **What it keeps:** every `route.ts` API handler.
- **What it drops:** the dashboard UI files. They're swapped for stubs during the build and restored afterwards, which leaves the source tree clean.

Build settings: Turbopack (the default bundler), `OMNIROUTE_BUILD_MEMORY_MB=4096`,
`NEXT_TELEMETRY_DISABLED=1`, and dependencies from `npm ci --ignore-scripts`.

This came out of five build attempts on this 15 GB machine at `152d9510`:
- **Full Turbopack build:** it exhausted system memory. Commit charge reached ~36 of 61 GB with 35 MB of RAM free, and small Node workers died with "Zone Allocation failed".
- **Full builds under both bundlers:** they pulled Node-only modules (`child_process`, `fs`, `net`, `tls`, via playwright-core, ioredis and detect-libc) into the dashboard's browser bundle. Turbopack reported 168 "Module not found" errors, and webpack failed the same way.
- **`minimal`:** it also fails under webpack (see Context).

The backend-only build succeeded in 7.7 minutes. In a local trial it booted in 8 s, listened on 127.0.0.1 only, and returned 401 both on unauthenticated `/v1/*` and on the Codex device-flow route.

What backend-only changes:
- **No dashboard UI.** Codex connects through OmniRoute's device-code flow, and API-key providers through the management API (`omniroute_tool.py omniroute connect codex` and `connect-key`). `connect-key` reads the key either from a hidden prompt or, with `--from-env-agents`, from `.env.agents` through the audited secret loader. Combos and the lane key are created through the same API.
- **OmniRoute's startup still runs** (corrected 2026-09-13). An earlier draft said the instrumentation was stubbed.
  - Backend-only stubs only the dashboard pages. The instrumentation entrypoint is stubbed only for the separate contributor profile (`scripts/build/build-next-isolated.mjs:294-304`).
  - So `registerNodejs()` runs `ensureSecrets()` (`instrumentation-node.ts:358`). Unless `OMNIROUTE_DISABLE_BACKGROUND_SERVICES` is set, it also starts the background services; they are left on.
  - The first live start proved it: OmniRoute's embedded-service WebSocket proxy took 127.0.0.1:20131 from the spillover proxy. It now runs on 20133, and the live dashboard socket is off (CONTRACT §10).
  - **Secrets:** the supervisor passes `STORAGE_ENCRYPTION_KEY`, `INITIAL_PASSWORD`, `JWT_SECRET` and `API_KEY_SECRET` from DPAPI blobs on every start (CONTRACT §16). With them set, `ensureSecrets()` neither generates nor persists its own, so they stay stable; if they changed, the lane key would stop validating.
  - **Token refresh and log retention don't depend on the background schedulers.** The pinned source shows:
    - Codex OAuth tokens refresh at request time: `open-sse/executors/base.ts:735` checks `needsRefresh()` before each call, and `CodexExecutor` extends `BaseExecutor` (`codex.ts:801`).
    - Call-log rotation is triggered on write: `callLogs.ts:638` and `:694` call `scheduleCallLogRotation()`, which runs the day-based delete, the row trim and the file cleanup (`callLogRotation.ts:333-359`).
  - **No switch turns call-log persistence off.** `deploy` therefore writes privacy-minimal caps into `omniroute.log_env`: 1-day retention, 200 rows, 2 KB text, a 16 KB body limit, no app log file and no debug file.
  - **Still owed:** both behaviours must be confirmed in the live smoke test before spilling is switched on.

## Consequences

**Accepted risks, named plainly:**

- **R1 — Anthropic terms.** Claude Code's own login passes through a local process in Anthropic's documented
  base-URL-only mode; it is never stored or logged. Anthropic still doesn't *support* non-Claude models
  behind gateways. The sanctioned paid alternative is `/usage-credits`.
- **R2 — OpenAI terms.** OmniRoute's `cx/` presents itself to OpenAI as the official Codex CLI on CC's
  ChatGPT account, and OpenAI reportedly flags subscription-to-API proxying. Worst case the ChatGPT account
  is actioned, which would hit Codex delegation. Mitigations: one personal account, training off. The
  terms-clean swap is a paid OpenAI API key.
- **R3 — Lost features.** Remote Control and server-managed settings are off in every session.
- **R4 — Single point of failure.** One proxy serves every interactive session. Mitigations: supervisor
  self-heal, the SessionStart ensure-hook, `claude-direct`, and one-command rollback.
- **R5 — Fallback quality.** Below Opus 5. Sessions bigger than the fallback window can't spill — they get a
  "new chat" alert instead. Each return to Claude may cost one invisible retry.
- **R6 — OmniRoute itself.** An unreleased branch with open OOM, VACUUM-freeze and JWT issues. Loopback-only
  binding, a scoped key and required login reduce the exposure but don't remove it. Its news and version
  calls to GitHub and npm can't be switched off.
- **R7 — The Mac.** Uncovered until a session is opened there, which runs the same installer plus a launchd
  agent.

**Backend-only build (part of R6).** Four privileged modules that `minimal` would stub out lose their
dashboard UI, but their API routes are still compiled in: the MITM certificate installer, the Zed keychain
import, Cloud Sync, and the 9router installer. Those routes stay behind four protections:
- OmniRoute's `LOCAL_ONLY` route guard
- required login
- the loopback-only bind
- `doctor` checks that assert unauthenticated and rebinding callers are refused

That reduces the exposure but doesn't remove it. Decision 6 lists what the backend-only build changes and
what must be verified before spilling. Re-evaluate the build once upstream fixes the full-build
module leak and the `minimal` alias paths, or npm ships a patched release.

**Other costs:** one more always-on local service; a Claude Code version floor (2.1.268, with
2.1.265–2.1.267 denied) that `spillover enable-routing` enforces; a pinned OmniRoute sha to re-check when
npm 3.8.51+ ships; provider terms to re-check quarterly.

**Rollback** is one command, `omniroute_tool.py rollback`: change `ANTHROPIC_BASE_URL` back to
`https://api.anthropic.com` (a changed value reaches open sessions; a removed one doesn't), tell CC to
restart open sessions, stop the supervisor and remove its VBS, then remove the owned keys and hooks and
restore from backup. `claude-direct` reaches Claude with no proxy and no Python; `uninstall --purge`
removes OmniRoute and its data.

**Not decided here:** swapping `cx/` for a paid OpenAI API key (the R2 exit), buying `/usage-credits` (the
R1 alternative), and the Mac install (R7).

## Compliance

```bash
python scripts/integrations/omniroute_tool.py doctor --json   # every hardening check passes
python -m pytest scripts/tests/test_spillover_*.py -q          # detector, proxy, supervisor
python scripts/harness_eval.py --json                         # spillover row ok
python scripts/machine_parity.py --check                      # [OK] claude-spillover
python scripts/audit_mcp_secrets.py --json                    # leak_count 0; OmniRoute-key canary detected
```

## Related

[[scripts/spillover/CONTRACT]] · [[skills/claude-spillover/SKILL]] · [[CONTEXT]] · [[brain/TOOL_SHED]] ·
[[docs/adr/0001-skill-dependency-classification]] · [[docs/adr/0010-external-resource-catalog]] ·
[[docs/adr/INDEX]]
