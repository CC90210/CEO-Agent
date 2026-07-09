# `apps/agent-runner/` — Design-Stage Scaffold

Status: **scaffold only, not deployed.**

Captured during the 2026-05-05 backend-runner design session. Source files
implement the skeleton for a direct `runner.oasisai.work` Node/TypeScript
runner that backs the Command Center chat widget — session-scoped workers,
SSE streaming, Supabase JWT verification on-runner, libsodium app-layer key
encryption, BYOK enforcement for non-CC tenants, read-only file tree with
approval-gated writes.

**Why it's still here:** The design (`docs/AGENT_RUNNER_DESIGN.md`) is
documented and the scaffold compiles. Production traffic has not been
routed to it yet, but the artifact is intentional and waiting for the next
infra push.

**Operator note:** the repo contains a tracked
`database/020_chat_widget_and_pairings.sql` that overlaps migration
numbering and scope with the scaffold's intended schema. Choose one
migration lineage before applying anything to Supabase.

## Files

| File | Purpose |
|---|---|
| `src/server.ts` | Fastify/Express bootstrap |
| `src/sessions.ts` | Per-tenant session lifecycle |
| `src/spawner.ts` | Child-process / worker spawn |
| `src/auth.ts` | Supabase JWT verification |
| `src/files.ts` | Read-only file tree adapter |
| `src/sse.ts` | Server-sent-event streaming |

## Cross-references
- [[docs/AGENT_RUNNER_DESIGN]] — full design rationale
- [[brain/STATE]] — "Agent Runner Backend (2026-05-05)" section
