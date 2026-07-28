---
name: personas-archive
description: Archived persona-* skills (customer-support, event-coordinator, exec-assistant, hr-coordinator, it-admin, project-manager, researcher, sales-ops, team-lead). Superseded 2026-05-07 by memory/PERSONAS.md, physically archived 2026-05-16 in V6.7 cleanup.
status: archived
archived_at: 2026-05-16
superseded_by: memory/PERSONAS.md
tags: [skill, archive]
last_updated: 2026-05-16
---

# Personas Archive

These 9 persona-* skills were marked `archived: 2026-05-07` in their own frontmatter with `superseded_by: memory/PERSONAS.md`, but had not been physically moved off the active skills tree until V6.7 cleanup on 2026-05-16. The capability graph was indexing them as live, which polluted trigger-resolution for unrelated queries.

**For persona-style work**, read `memory/PERSONAS.md`.

Originals preserved here (read-only) in case any of them encode a workflow chain that wasn't fully captured in PERSONAS.md and needs to be recovered. If you find a useful pattern that should be re-promoted, copy it into the appropriate active skill (`gws-workflow`, `client-success`, etc.) — do NOT un-archive in place.

| Archived skill | Original purpose |
|---|---|
| persona-customer-support | Triage support inbox, log tickets, escalate |
| persona-event-coordinator | Plan events, scheduling, invitations |
| persona-exec-assistant | Manage executive schedule + inbox |
| persona-hr-coordinator | Onboarding, announcements, employee comms |
| persona-it-admin | Workspace admin, security monitoring |
| persona-project-manager | Track tasks, schedule meetings, share docs |
| persona-researcher | Manage references, notes, collaboration |
| persona-sales-ops | Track deals, schedule calls, client comms |
| persona-team-lead | Run standups, coordinate tasks, comms |

All 9 were thin wrappers over `gws-*` skills (gws-gmail, gws-sheets, gws-chat, gws-calendar, gws-workflow). The functional content is preserved in those underlying skills + the persona patterns documented in `memory/PERSONAS.md`.
