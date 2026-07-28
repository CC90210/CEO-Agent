---
name: manifest-ai-editor
description: AI-assisted editor for tenant manifests. Operator describes a desired change ("add a custom field 'preferred_lender' to application object") and the skill proposes a structured diff against object_metadata / field_metadata / views / tenant_manifests rows; every change is operator-approved before commit. Closes the V6.9 arc — the gap behind handoff doc #8 ("AI editor for manifests not wired").
tags: [skill, manifest, ai-editor, crm, v6.9, tenant]
triggers: ["edit manifest", "add custom field", "add view", "add workflow", "add object", "manifest editor", "customize tenant"]
owner: bravo
tier: T2
status: NEW
risk: medium
argument_hint: "Which manifest section? (object_metadata / field_metadata / views / workflows / brand / nav / agents)"
requires:
  state: [database/070_object_field_metadata.sql, database/071_tenant_views.sql, database/072_workflow_engine.sql]
  env: [ANTHROPIC_API_KEY, BRAVO_SUPABASE_URL, BRAVO_SUPABASE_SERVICE_ROLE_KEY]
last_updated: 2026-05-25
---

# manifest-ai-editor — AI-assisted manifest editing (V6.9.4)

## Overview

The dashboard's tenant manifests (`tenant_manifests` row + the V6.9 substrate of `object_metadata` / `field_metadata` / `views` / `workflows`) describe everything that makes one tenant's Command Center different from another's — brand, nav, data model, saved views, automations. Pre-V6.9.4, editing them meant hand-writing JSON or shipping a migration.

This skill is the operator-facing surface for AI-assisted editing. Operator describes intent in plain English; the skill proposes a structured diff; operator approves; the change persists through the existing `manifest_audit_log` (no silent writes).

**Closes:** AGENT_COMMAND_CENTER_HANDOFF.md gap #8 ("AI editor for manifests not wired").

## When to invoke

- Operator says "add a custom field" / "add a new entity type" / "add a saved view" / "add an automation".
- Operator says "customize the [X] tenant" / "edit the manifest for [slug]".
- The catch-all `/t/<slug>/settings/ai-editor` page (V6.9.4.x UI surface) invokes this skill as its primary backend.

## Substrate this skill stands on

| V6.9 layer | What this skill uses |
|---|---|
| V6.9.0 — `object_metadata` + `field_metadata` | Resolve target entity type + propose new fields with typed shape |
| V6.9.1 — `views` + `view_fields/filters/sorts` | Propose saved-view rows |
| V6.9.2 — `workflows` + step registry | Propose workflow definitions composed of registered step types |
| V6.9.3 — `ai-agent` step + field permissions | Internally uses `ai-agent` step to propose the diff; honors `field_permissions` on the operator-facing agent |

If any of those migrations is not applied to the live DB, this skill should fail loudly with a setup pointer:

> **Prerequisite:** Migrations 070 / 071 / 072 must be applied to Supabase before invoking. Run:
> `python scripts/apply_migration.py database/070_object_field_metadata.sql`
> `python scripts/apply_migration.py database/071_tenant_views.sql`
> `python scripts/apply_migration.py database/072_workflow_engine.sql`

## How the diff flow works

1. **Resolve intent.** Operator's natural-language request gets routed through the `ai-agent` workflow step with a system prompt that constrains output to a JSON diff shape: `{ table: 'object_metadata' | 'field_metadata' | 'views' | 'view_fields' | ..., op: 'insert' | 'update' | 'soft_delete', row: {...} }`.

2. **Validate against the live schema.** The schema-introspector (`~/APPS/oasis-command-center/lib/schema-introspector.ts`) confirms referenced entity slugs and field names exist (or are being created in the same diff). Unknown references return to the operator as `validation_failed: <field>` rather than silent insert of an orphan row.

3. **Render preview.** Operator sees a 3-section preview: *will create* / *will update* / *will retire*. Each row shown as a key:value list, not raw JSON, so non-technical operators can read it.

4. **Approve / reject / amend.** Approve → commit + audit-log entry with `actor_type='ai'` and the operator's user_id. Reject → discard. Amend → operator edits one field in the preview, skill re-validates.

5. **Audit trail.** Every committed diff lands in `manifest_audit_log` with the proposed diff + operator's user_id + timestamp. Operators can `/audit` to scroll history; system admins can revert from there.

## Anti-slop guardrails (mandatory)

- **No silent writes.** Every diff is operator-approved before commit. The skill must NEVER auto-apply, even when the model is very confident.
- **No prompt-only protection.** Field permissions (ADR-0004) are the wall. If the operator's role-gate forbids writing a field, the skill rejects the diff at the server boundary regardless of what the agent suggests.
- **No schema bypass.** All proposed `field_metadata` rows must use a valid `field_metadata_type` enum value (16 types per migration 070). Anything else fails validation.
- **No `tenant_records` reshuffle.** This skill edits the schema layer (metadata + views + workflows), not data rows. Operator-driven data changes route through `update_record` / `create_record` tool actions.

## V6.9.4.x UI surface (deferred from V6.9.4 core)

The chat UI at `/t/<slug>/settings/ai-editor` is V6.9.4.x — not in V6.9.4 substrate. Until it ships, this skill is invoked by Bravo directly through the existing chat surface (operator pastes their intent; Bravo runs the diff workflow; renders preview as a code block; operator says approve/reject).

When the UI lands, the skill's flow doesn't change — only the surface does.

## Related

- ADR-0003 (typed step registry): `docs/adr/0003-typed-workflow-step-registry.md`
- ADR-0004 (field permissions): `docs/adr/0004-field-level-permission-model.md`
- Migration 070: `database/070_object_field_metadata.sql`
- Migration 071: `database/071_tenant_views.sql`
- Migration 072: `database/072_workflow_engine.sql`
- Schema introspector: `~/APPS/oasis-command-center/lib/schema-introspector.ts`
- Plan: `~/.claude/plans/i-m-dropping-you-a-magical-cat.md`
