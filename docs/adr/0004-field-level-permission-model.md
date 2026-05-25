---
adr: 0004
title: Field-level permission model (V6.9.3)
status: accepted
date: 2026-05-25
deciders: [bravo, cc]
supersedes: null
superseded_by: null
---

# ADR-0004 — Field-level permission model

## Context

Today's permission model in the Agent Command Center has three layers:

1. **Row-level (RLS):** every `tenant_records` row carries `tenant_id`; Supabase RLS scopes reads/writes via `current_tenant_id()`.
2. **Tool-level (`tool_palette`):** `manifest.agents[].tool_palette` is an allowlist of cloud tools the agent can call (`list_records`, `send_email`, ...). Defined per-agent in `lib/manifest/schema.ts:ManifestAgentBinding`.
3. **Role-level (`role-gates.ts`):** `read_only` operators can't fire `create_record`/`update_record`/`delete_record`/`send_email`/`send_sms`/`bash`/`run_script`/`write_file`. Other roles are unrestricted.

What's missing: **per-field** read/write enforcement. An agent that has `list_records` on the `lead` entity gets every column — including PII columns like `ssn_last4`, internal notes, lender ID lists. The 2026-05-17 security audit flagged: *"prompt-based role enforcement is advisory; lib/role-gates.ts is the wall."* The wall has no field-level brick today.

Pattern observed at [twentyhq/twenty](https://github.com/twentyhq/twenty) (AGPLv3 — patterns only): field permissions are declared at the app/manifest layer (not just the DB layer), so front-end components and server functions get the same enforcement.

## Decision

Extend `manifest.agents[].field_permissions` with a list of per-(entity_type, mode) field allowlists. Enforced server-side in `lib/role-gates.ts`.

### Schema extension

```ts
// lib/manifest/schema.ts:ManifestAgentBinding
field_permissions?: Array<{
  entity_type: string;
  fields: string[];
  mode: "read" | "write";
}>;
```

### Enforcement helpers (lib/role-gates.ts)

```ts
resolveAllowedFields(permissions, entity_type, mode): string[] | null
applyFieldReadFilter(data, allowed): Partial<data>
findDisallowedWriteFields(data, allowed): string[]   // empty = ok
```

### Three-state semantics

| field_permissions value | Behavior on entity_type X |
|---|---|
| `undefined` / missing | No filter; agent gets full read+write on every field (preserves V5 behavior; safe default) |
| `[]` (empty array) | Agent has zero field access on X (metadata-only) |
| `[{ entity_type: 'X', fields: [a,b], mode: 'read' }]` | Read returns only `{a,b}`; writes to X are rejected (no write entry) |
| `[{ ..., mode:'write' }]` covers `{a,b}` | Read inherits write (write is a superset); writes outside `{a,b}` rejected |
| Agent has entries for entity_type Y but NOT X | Default-deny on X (`[]` semantics; preventing the gap where adding *any* palette accidentally widens *every* entity) |

### Enforcement boundary

The wall lives in **API route handlers** that read/write `tenant_records`. Before returning a row to the agent, the handler:
1. Loads `permissions = manifest.agents[agentSlug].field_permissions`
2. `allowed = resolveAllowedFields(permissions, entityType, 'read')`
3. `data = applyFieldReadFilter(record.data, allowed)`

Before persisting an inbound write:
1. `allowed = resolveAllowedFields(permissions, entityType, 'write')`
2. `disallowed = findDisallowedWriteFields(body, allowed)`
3. If `disallowed.length > 0` → reject with `403 field_permission_denied: <list>`

### Anti-slop guardrails

- Enforcement is server-side. The agent's chat prompt may also be told "don't read field X" but that is **advisory only** — the wall is the API.
- Default = full access. Operators opt into narrowing; we don't ship a tenant with surprise denied lists.
- No prompt-based bypass. The model can ask, the API still says no.
- No leak via error messages — the disallowed list returns in the error response so the operator can fix the palette, but never the *values* of disallowed fields.

## Consequences

- Operators can now restrict agents to specific PII-safe field subsets per entity (e.g. Helios sales gets `name + phone + business_name`, not `ssn_last4 + bank_account`).
- Existing agents without `field_permissions` are unchanged (default-allow preserves behavior).
- API routes touching `tenant_records.data` get a single 4-line addition (resolve → filter on response, resolve → validate on write).
- The AI manifest editor (V6.9.4) will surface field_permissions as a per-agent editable list with an explicit "I want to restrict this" affordance — avoids accidental zero-access lockouts.

## Related

- Implementation: `~/APPS/oasis-command-center/lib/role-gates.ts` (resolveAllowedFields + applyFieldReadFilter + findDisallowedWriteFields)
- Schema extension: `~/APPS/oasis-command-center/lib/manifest/schema.ts:ManifestAgentBinding.field_permissions`
- Original audit: `memory/feedback_security_must_be_server_side.md` (2026-05-17)
- Original audit: `memory/feedback_role_enum_needs_matrix.md` (2026-05-17 "Role enum needs enforced matrix")
- Plan: `~/.claude/plans/i-m-dropping-you-a-magical-cat.md`
- Source (patterns only): https://github.com/twentyhq/twenty
