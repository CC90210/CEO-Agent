---
adr: 0009
title: Tenant-safe bridge-tool catalog for non-admin operators
status: proposed
date: 2026-06-09
deciders: CC, Bravo
supersedes: —
superseded_by: —
related: ADR-0006 (multi-employee tenant bridge access), Codex round-8 audit 2026-06-09
tags: [docs, adr, decision]
last_updated: 2026-06-09
---

# ADR-0009 — Tenant-safe bridge-tool catalog for non-admin operators

## Context

`/api/bridge/exec-tool` is the dashboard route that lets the chat path
execute bridge tools (`read_file`, `bash`, `send_email`, etc) on the
operator's machine. Auth is gated by `bridgeExecToolAllowedForRole()`
in `lib/role-gates.ts`.

Codex audit 2026-06-09 round-7 [high] caught that `read_file` and
`load_skill` were in the non-admin allowlist — those tools read under
all registered agent repo roots (Bravo, Atlas, Maven, Aura, Hermes), so
a non-admin SunBiz employee (read_only / loan_officer / processor)
could harvest CC's empire code. Round-7 removed them.

Codex round-8 [medium] followed up that `list_scripts` and `list_skills`
were ALSO leaks — the bridge implementations don't return names only.
`list_scripts` extracts the first-line docstring from each script (so a
non-admin sees authored content about WHAT each script does, which
brand it serves, what the operator's setup is).  `list_skills`  returns
`SKILL.md` frontmatter: `description`, `triggers`, `tags`. That's
operator-repo authored content, not pure enumeration. Round-8 removed
both.

After round-8, the non-admin allowlist is: `cli_status` only — a daemon
health probe that returns uptime + last-error string, no operator data.

## Decision

The conservative round-8 stance ships now: non-admin SunBiz users can
NOT enumerate the operator's scripts or skills via the bridge. They
can chat with Solara/Helios via the cloud + bridge paths and use the
agent's manifest-declared capabilities, but cannot ask "list every
script available" or "list every skill available" and get an answer
through the bridge.

A proper long-term fix (deferred to this ADR's "accepted" state):
serve a **tenant-safe static catalog** from the dashboard side, NOT
from the operator's repo:

  - `GET /api/bridge/tenant-catalog` returns a curated catalog scoped
    to the calling user's tenant + role.
  - Catalog content comes from the tenant manifest (CC explicitly
    authors which scripts / skills / capabilities are advertised to
    non-admin users on this tenant).
  - The route NEVER reaches into the operator repo. The catalog is
    DB-resident.
  - Non-admin allowlist GAINS this new route, not the legacy
    `list_scripts` / `list_skills` exec-tool calls.

The tenant manifest schema needs:

  ```
  tenants.custom_fields.bridge_tool_catalog = {
    scripts: [
      { name, public_description, target_audience: "admin"|"operator"|"customer" },
      ...
    ],
    skills: [
      { name, public_description, public_triggers: [...] },
      ...
    ],
  }
  ```

`public_description` and `public_triggers` are explicitly-authored
sanitized strings — never derived from operator-repo content.

## Why this is a separate ADR-tracked change instead of "just fix it now"

1. **Requires per-tenant catalog authorship.** Today there is no
   curated public catalog — only the raw repo content. Building this
   needs CC to decide what non-admin SunBiz users SHOULD see in a
   "what can Solara do?" surface. That's a product/business decision,
   not a code one.

2. **Requires manifest schema migration.** Adding a `bridge_tool_catalog`
   field to `tenants.custom_fields` is non-breaking but needs migration
   tooling + a default empty value for existing tenants.

3. **Round-8's conservative move (allowlist = cli_status only) is
   already safe.** Non-admin users lose script/skill discovery; they
   keep cloud + bridge chat access via Solara/Helios via Solara's
   manifest-declared capabilities. That's a usability degradation but
   not a feature break.

## Consequences

**Accepted today:**

- Non-admin SunBiz users can no longer call `list_scripts` or
  `list_skills` through the bridge exec-tool route. Owner/admin retain
  full access for operator workflows.

**Deferred (ADR-0009 acceptance triggers):**

- `bridge_tool_catalog` schema addition to `tenant_manifests`.
- `GET /api/bridge/tenant-catalog` route that returns the curated list.
- ChatWidget surface that reads from the catalog for the
  "what can this agent do?" question.

**Acceptance triggers:**

1. A non-admin SunBiz user reports they need to know what Solara can
   do and cannot get the answer through chat.
2. Adon's tenant or a new client agent onboards and needs the catalog
   for their non-admin operators.
3. CC explicitly authorizes a catalog manifest for SunBiz.

Until one of those triggers fires, the round-8 conservative posture
stays.

## Obsidian Links
- [[docs/adr/INDEX]]
- [[CONTEXT]]
