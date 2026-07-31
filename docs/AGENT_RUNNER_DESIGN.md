---
tags: [docs]
last_updated: 2026-05-21
---

# AGENT RUNNER DESIGN

Date: 2026-05-05  
Scope: OASIS Agent Command Center chat widget backend on persistent Hetzner runner  
Status: Proposed build target for a 2-week implementation window

## Outcome

Replace the Telegram bridge plus Codex companion split-brain with one persistent backend service at `runner.oasisai.work`:

- Vercel dashboard stays UI-only.
- Browser talks directly to the runner for long-lived SSE.
- Runner verifies Supabase JWTs locally, resolves tenant/profile, and launches the selected agent/model against the correct Linux workspace.
- Every session is persisted to Supabase and streamed back in real time.
- File access is workspace-scoped and read-only by default.

## Architecture

```text
                             +----------------------------------+
                             |  Supabase                        |
                             |  tenants / user_profiles         |
                             |  agent_model_config              |
                             |  chat_sessions / chat_messages   |
                             |  audit_log / agent_events        |
                             +----------------+-----------------+
                                              ^
                                              | service role
                                              |
+---------------------------+    JWT + SSE    |    +--------------------------------------+
| apps/command-center       +-----------------+----> runner.oasisai.work                 |
| Next.js 15 on Vercel      |                      | Node/TypeScript daemon               |
| widget + auth + settings  |<--------------------+ POST /v1/chat                        |
+-------------+-------------+     event stream      GET  /v1/chat/:id/stream             |
              |                                        GET  /v1/files/tree|blob          |
              |                                        POST /v1/files/write-requests     |
              |                                        POST /v1/files/write-requests/... |
              |                                        +-----------------+---------------+
              |                                                          |
              |                                                          |
              |                                            wrapper spawn | session-scoped
              |                                                          v
              |                                +-------------------------+----------------------+
              |                                | provider wrappers / CLIs / API adapters        |
              |                                | Claude Code | Codex | Claude API | OpenAI     |
              |                                | Gemini      | future local models              |
              |                                +-------------------------+----------------------+
              |                                                          |
              |                                                          |
              |                                                workspace root per tenant/agent
              |                                                          v
              |                                +-------------------------+----------------------+
              |                                | /srv/agents/<tenant>/<agent>/...              |
              |                                | fs.watch fanout | read-only by default        |
              |                                | optional write approval + audit               |
              |                                +------------------------------------------------+
```

## 1. Service Architecture

### Decision

Use **lean Node/TypeScript**, not Python, for the runner.

### Why

- Same language family as the dashboard, easier shared types and shared auth assumptions.
- Native `http`, `fetch`, SSE, child-process handling, and UTF-8 stream decoding are all good enough.
- The runner is mostly orchestration, auth, streaming, and process control. It is not numerics-heavy or Python-first.

### Process model

Use **one long-lived runner service** on Hetzner plus **session-scoped child workers**.

- Do not run per-message Docker containers.
- Do not run one immortal subprocess per agent forever.
- Do not reuse a single `(tenant, agent)` CLI process across unrelated chats.

### Recommended runtime shape

- `systemd` or Docker Compose keeps the Node runner alive.
- Each `POST /v1/chat` creates a logical session row and spawns one worker process for that session.
- Workers stay warm for the lifetime of that chat session or operation, then exit.
- Idle session TTL target: 30-60 minutes before cleanup if future “resume turn” support is added.

### Session to subprocess mapping

Use **one subprocess per chat session**, not per turn and not per tenant-agent globally.

- Fresh per turn is too slow for Claude/Codex-style tooling and loses live working context.
- Reusing one global `(tenant, agent)` worker causes context bleed, approval bleed, and file edit ambiguity.
- Session-scoped reuse is the safe middle.

### cwd / workspace root

Do **not** trust the dashboard’s `AGENT_REGISTRY.location` strings as spawn-safe.

- `apps/command-center/lib/agents.ts` is a UI registry and still contains Windows labels.
- The runner must resolve Linux roots from server env:
  - `RUNNER_TENANT_ROOT_TEMPLATE=/srv/agents/{tenant}/{agent}`
  - or per-agent overrides like `RUNNER_WORKSPACE_BRAVO=/srv/agents/oasis-ai-cc/bravo`
- The client may choose `agentKey`. It may never choose arbitrary `cwd`.

### Implementation scaffold

Added:

- `apps/agent-runner/package.json`
- `apps/agent-runner/tsconfig.json`
- `apps/agent-runner/src/server.ts`
- `apps/agent-runner/src/sessions.ts`
- `apps/agent-runner/src/spawner.ts`
- `apps/agent-runner/src/auth.ts`
- `apps/agent-runner/src/files.ts`
- `apps/agent-runner/src/sse.ts`

### File-by-file scaffold

| File | Responsibility |
|---|---|
| `package.json` | Isolated runner package with only Node/SSE/auth/process-control deps. |
| `src/server.ts` | HTTP entrypoint, routing, JWT-gated endpoints, file routes, write-approval routes. |
| `src/sessions.ts` | In-memory live session store plus durable writes to `chat_sessions`, `chat_messages`, `audit_log`. |
| `src/spawner.ts` | Session launch, config lookup, libsodium key decrypt, wrapper process spawn, structured stream parsing. |
| `src/auth.ts` | Supabase JWT verification via JWKS, tenant/profile resolution, CORS allowlist. |
| `src/files.ts` | Safe workspace root resolution, path traversal prevention, `.gitignore` and dotfile filtering, `fs.watch` fanout. |
| `src/sse.ts` | SSE headers, replay-from-`Last-Event-ID`, heartbeat, subscriber cleanup. |

## 2. Streaming Protocol

### Contract

- `POST /v1/chat`
  - Auth: `Authorization: Bearer <Supabase access token>`
  - Body: `{ agentKey, provider, model, prompt, operationMode, writeMode }`
  - Returns: `{ sessionId, streamUrl, status }`

- `GET /v1/chat/:id/stream`
  - SSE stream for live deltas, tool events, status, approvals, and heartbeats.
  - Supports `Last-Event-ID` replay.

### Event shape

Runner-internal standard event types:

- `assistant.delta`
- `assistant.final`
- `tool.started`
- `tool.completed`
- `usage.updated`
- `approval.requested`
- `approval.granted`
- `workspace.changed`
- `runner.log`
- `runner.stderr`
- `runner.failed`
- `runner.cancelled`

### Chunking strategy

The service should not stream raw byte chunks blindly.

- Use `StringDecoder("utf8")` so multibyte UTF-8 is not split mid-character.
- Prefer a **wrapper NDJSON contract** over raw CLI stdout:
  - wrapper emits one JSON event per line
  - runner parses line by line
  - ANSI never leaks unless a wrapper explicitly includes it inside JSON
- If a wrapper emits plain text unexpectedly, treat it as `assistant.delta`.

### Heartbeat and reconnect

- Send SSE heartbeat every 15 seconds.
- Keep last ~500 live events in memory for replay.
- Persist meaningful checkpoints to `chat_messages`.
- On reconnect:
  - if `Last-Event-ID` exists and is still in memory, replay missing frames
  - otherwise send persisted session state and continue live

### Mid-conversation tool-call injection

Do not make the browser infer tool events from text.

- Wrapper/adapter emits `tool.started` and `tool.completed`.
- Runner writes them as `chat_messages.role='runner'`, `message_kind='event'`.
- UI renders them as structured sub-events in the same stream.

## 3. Multi-Tenant Auth and Key Management

### Auth

Use **Supabase access tokens verified locally on the runner**.

- Verify JWTs against Supabase JWKS with `jose`.
- Resolve `user_profiles.auth_user_id -> profile_id -> tenant_id`.
- Never trust tenant IDs coming from the browser body.

### Key table

Migration added `agent_model_config` with:

- tenant, agent, provider, model
- auth mode
- credential origin
- secretbox ciphertext + nonce
- wrapper command/args
- budgets and concurrency

### Encryption decision

Use **libsodium app-layer secretbox**, not pgcrypto, for provider keys.

Why:

- DB compromise alone should not reveal tenant API keys.
- Service-role SQL should not be able to decrypt secrets by itself.
- Key rotation belongs to runner ops, not SQL functions.

Use pgcrypto only if you explicitly want convenience over separation. That is the wrong tradeoff here.

### Subscription-first policy

Allowed:

- CC internal tenant: `credential_origin='platform_subscription'` or `platform_api_key`
- client tenants: `credential_origin='tenant_key'` only

Enforcement:

- `tenants.custom_fields.managed_auth_allowed=true` is set for `oasis-ai-cc`
- trigger on `agent_model_config` blocks platform-managed auth for other tenants

### ToS rule

Clients must bring their own keys. CC’s Claude subscription is never shared.

That rule must be enforced in:

- schema trigger
- runner auth resolution
- settings UI copy
- onboarding docs

## 4. File-Tree Access

### Read-only by default

File browsing should be safe even when chat is enabled.

- root is always resolved server-side
- no client-supplied absolute paths
- deny `.git`, `.claude`, `.codex`, `.env*`, `node_modules`, build output
- respect `.gitignore`
- hide most dotfiles except allowlist
- max depth default: 4
- max readable file size default: 256 KB

### Live updates

Use `fs.watch` fanout on visible directories and push `workspace.changed` events over the same SSE stream.

Tradeoff:

- `fs.watch` on Linux is light and available, but recursive behavior is not universal.
- For the 2-week build, directory fanout is enough.
- If event drop/noise shows up, replace the watcher layer with `chokidar` without changing the API.

### Opt-in write flow

Do not let file-tree UI write directly.

Flow:

1. Widget posts `POST /v1/files/write-requests`
2. Runner appends `approval.requested`
3. User approves in-widget
4. Runner emits `approval.granted`
5. only then may the active worker apply the patch
6. every request/approval/apply is written to `audit_log`

### Sandboxing

Read-only browsing is not enough. The worker sandbox must also enforce it.

Recommended runtime hardening:

- launch workers under a dedicated Unix user
- wrap CLI workers with `bubblewrap` or `firejail`
- mount workspace root read-only unless `writeMode='approved'`
- mount only the provider auth material the worker actually needs

## 5. Replacing Codex Companion

### Existing pattern

Today:

- `task`
- `review`
- `adversarial-review`
- `status`
- `result`
- `.claude/jobs/` as local queue/state

### Replacement

Move the **control plane** to Postgres and keep filesystem artifacts local-only.

- `chat_sessions.operation_mode` covers `chat`, `task`, `review`, `adversarial_review`
- `chat_sessions.status` replaces queue status
- `chat_messages` replaces result tape
- `audit_log` replaces “what happened” guessing
- local wrapper logs can still exist under `/tmp` or a spool dir, but they are not the source of truth

### Keep file queue or move to Postgres?

Move control state to Postgres.

Do not keep `.claude/jobs/` as primary state because it is:

- single-machine
- not tenant-aware
- opaque to the widget
- brittle across restarts

Okay to keep local spool files for:

- raw wrapper logs
- large diffs
- transient resume handles

## 6. Long-Running Tasks and Vercel Timeout

### Network path

Browser should talk to the runner **directly** for chat and streaming.

- Vercel stays out of the hot path for 5-10 minute runs.
- `apps/command-center` only renders UI and manages auth/session bootstrap.
- Runner domain: `https://runner.oasisai.work`

### Why this matters

- avoids Vercel function timeout ceilings
- avoids proxy buffering issues
- makes SSE reconnect logic local to the runner
- keeps operational concerns in one place

### Auth shape

- Browser fetches Supabase access token from its session.
- Browser sends that token directly to the runner.
- Runner verifies it locally via JWKS.
- No cookies, no shared server session, no Vercel proxy dependency.

## 7. Failure Modes

### Subprocess crash mid-stream

Behavior:

- persist partial output already received
- emit `runner.failed`
- set `chat_sessions.status='failed'`
- keep `provider_session_id` when available for future resume work

Recommended retry UX:

- “retry from last user turn”
- “resume provider session” only when the provider wrapper supports it

### Per-tenant token budget enforcement

Use `agent_model_config` budgets as hard gates.

- preflight reject if budget exhausted
- update estimated usage from wrapper/API events
- store estimated values even when provider does not return official usage

### Concurrent session limits and queueing

- enforce tenant concurrency from `agent_model_config.concurrency_limit`
- return `202 queued` instead of hard failing when reasonable
- reject with `429` if tenant or global queue is saturated

For the 2-week build, one Hetzner runner plus queueing is enough. Do not overbuild autoscaling before demand.

### Unauthorized file edit sandboxing

Three layers:

1. UI-level approval flow
2. runner write-mode checks
3. OS-level sandbox mount mode

If layer 3 is missing, the system is not actually safe.

## Migration Summary

Added: `database/020_agent_runner.sql`

Tables:

- `agent_model_config`
- `chat_sessions`
- `chat_messages`
- `audit_log`

Key choices:

- service-role writes, tenant read policies
- libsodium ciphertext fields instead of pgcrypto decrypt RPCs
- explicit managed-auth enforcement for CC tenant only

## Implementation Checklist

| Item | Risk |
|---|---:|
| Provision Hetzner runner host, domain, systemd/Compose, env loading | 1 |
| Add runner package install/build/deploy path | 1 |
| Wire direct browser-to-runner auth with Supabase JWT verify | 2 |
| Build session persistence and SSE replay | 2 |
| Build provider wrapper contract and first wrappers for Claude Code + Codex | 3 |
| Build direct API adapters for Claude API / OpenAI / Gemini | 2 |
| Add settings UI for `agent_model_config` management | 2 |
| Add budget accounting + reject paths | 2 |
| Add file tree browse/read/watch | 2 |
| Add write approval UX + audit plumbing | 3 |
| Add worker sandboxing with read-only vs approved write mounts | 3 |
| Add runner-to-`agent_events` publish for session lifecycle | 2 |
| Add observability: health, logs, queue depth, failure alerts | 2 |

Risk scale:

- `1` straightforward
- `2` moderate integration risk
- `3` likely source of rework if not handled up front

## Things Bravo's Plan Got Wrong

1. One persistent `(tenant,agent)` subprocess is the wrong reuse boundary. It leaks context and approvals across chats. Use session-scoped workers.
2. `AGENT_REGISTRY.location` is a UI label, not a trusted Linux spawn path. The runner needs its own workspace map.
3. Sharing CC’s subscription with client tenants is a policy and billing trap. Enforce BYOK in schema and runtime.
4. `.claude/jobs/` cannot be the system of record on a multi-tenant runner. It belongs behind the runner, not in front of it.
5. `fs.watch` is not magically recursive or perfectly reliable on Linux. Design the watcher layer as swappable from day one.
6. Per-client Postgres schemas are not needed for this 2-week build. Existing `tenant_id` + RLS is enough unless a regulated client forces a harder boundary.
7. “Docker per session” would burn time without buying real product value. Build one stable daemon first; isolate workers with OS sandboxing.
8. Streaming plain stdout directly to the browser is not robust enough. Wrap providers in structured NDJSON events so tool calls, approvals, and usage are first-class.

## Recommended Build Order

Week 1:

1. deploy runner host and package
2. land migration
3. land JWT auth + chat session persistence
4. land SSE stream and minimal file tree read
5. land Claude Code + Codex wrappers

Week 2:

1. land API providers
2. land budgets and queueing
3. land write approval flow
4. land sandboxing
5. land widget integration and operational alerts

If you want zero rework, do not postpone:

- managed-auth enforcement
- session-scoped worker model
- structured wrapper protocol
- OS-level sandbox mode split

## Related

- [[docs/INDEX]]
- [[docs/AI_WORKSTATION_ROADMAP]]
