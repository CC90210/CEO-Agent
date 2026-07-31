---
description: "Consolidated GWS workflow aliases indexed by operator role; agents reference this when user wants to act as a role to find matching workflows"
tags: [personas, role-aliases]
last_updated: 2026-05-07
freshness_threshold_days: 365
---

# PERSONAS — Role-Flavored Workflow Aliases

> Consolidated from the 9 `skills/persona-*/SKILL.md` files (archived 2026-05-07 per Architecture Certification finding C9).
>
> Each persona below is a thin alias over a stack of GWS workflows. They never added new capability beyond invoking `gws workflow +<name>` directly — they just bundled a stack with a role-flavored name. Keeping the role names here is useful when the operator says "act as my X" and we want a quick reminder of which GWS stack fits.
>
> If you need the literal old SKILL.md contents, the files are still in `skills/persona-*/SKILL.md` with `archived: 2026-05-07` in frontmatter; they're not loaded by the runtime catalog anymore. Don't add new personas here — extend the existing GWS workflows or write a real skill instead.

---

## Executive Assistant

**Use when:** operator says "act as my exec assistant" or wants a daily inbox/calendar pass.
**Stack:** `gws-gmail`, `gws-calendar`, `gws-drive`, `gws-chat`.
**Workflows:** `gws workflow +standup-report`, `+meeting-prep`, `+weekly-digest`.
**Tone:** professional, concise; prioritize direct reports + leadership.

---

## Sales Operations

**Use when:** "act as sales ops" — deal tracking, call prep, client comms.
**Stack:** `gws-gmail`, `gws-calendar`, `gws-sheets`, `gws-drive`.
**Workflows:** `gws workflow +meeting-prep`, `+email-to-task`, `+weekly-digest`.
**Notes:** log deal updates via `gws sheets +append`; share proposals via `gws drive +upload`.

---

## Project Manager

**Use when:** "act as PM" — task tracking, meeting coordination, doc sharing.
**Stack:** `gws-drive`, `gws-sheets`, `gws-calendar`, `gws-gmail`, `gws-chat`.
**Workflows:** `gws workflow +meeting-prep`, `+weekly-digest`, `+standup-report`.

---

## Customer Support

**Use when:** "act as support" — ticket triage, response drafting, escalation routing.
**Stack:** `gws-gmail`, `gws-sheets`, `gws-chat`, `gws-calendar`.
**Workflows:** `gws workflow +email-to-task`, `+weekly-digest`.
**Notes:** track tickets in a sheet; escalate via `gws chat +send` to the right room.

---

## HR Coordinator

**Use when:** "act as HR" — onboarding flows, announcements, employee comms.
**Stack:** `gws-gmail`, `gws-calendar`, `gws-drive`, `gws-chat`.
**Workflows:** `gws workflow +file-announce`, `+meeting-prep`, `+weekly-digest`.

---

## Event Coordinator

**Use when:** "act as event coord" — scheduling, invitations, run-of-show docs.
**Stack:** `gws-calendar`, `gws-gmail`, `gws-drive`, `gws-chat`, `gws-sheets`.
**Workflows:** `gws workflow +meeting-prep`, `+file-announce`.

---

## Researcher

**Use when:** "act as researcher" — reference management, notes, collaboration.
**Stack:** `gws-drive`, `gws-docs`, `gws-sheets`, `gws-gmail`.
**Workflows:** `gws workflow +weekly-digest`.
**Notes:** for actual research output, prefer the canonical `agents/researcher` agent or `firecrawl_tool.py`. This persona is for archival/reference org only.

---

## Team Lead

**Use when:** "act as team lead" — standups, task coordination, team comms.
**Stack:** `gws-calendar`, `gws-gmail`, `gws-chat`, `gws-drive`, `gws-sheets`.
**Workflows:** `gws workflow +standup-report`, `+weekly-digest`, `+meeting-prep`.

---

## IT Admin

**Use when:** "act as IT admin" — Workspace config + security monitoring.
**Stack:** `gws-gmail`, `gws-drive`, `gws-calendar`, plus `gws-admin-reports` for audit logs.
**Workflows:** `gws workflow +file-announce` (for change advisories).

---

## Why these are no longer skills

The Architecture Certification (2026-05-07, plan file `enter-plan-mode-run-cozy-plum.md`) flagged the 9 `persona-*/SKILL.md` files as 90% dead weight: each was a thin wrapper that invoked GWS workflows, adding role-flavored framing but no executable capability. They bloated `skills/INDEX.md`, `WHEN_TO_USE_SKILLS.md` decisions, and the capability graph without expanding what Bravo could do.

The actual GWS workflows (`gws workflow +standup-report`, `+meeting-prep`, etc.) live in `skills/gws-workflow-*/SKILL.md` and are still active. Use those directly. Reach for this file only when the operator names a role and we want a quick mapping to the right GWS stack.

## Obsidian Links
- [[skills/gws-workflow/SKILL]] | [[skills/gws-shared/SKILL]]
- [[brain/CAPABILITIES]] | [[skills/INDEX]]
