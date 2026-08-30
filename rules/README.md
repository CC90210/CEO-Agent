---
tags: [rules]
last_updated: 2026-08-25
---

# `rules/` — Compliance Datalog (Not Agent Rules)

This directory holds **Datalog compliance rules** (`.dl` files) used by the
neuro-symbolic compliance gate inside `scripts/integrations/send_gateway.py`.
It is **not** the same thing as `.rules/`, which holds the markdown
instruction set for AI agents (identity, routing, capabilities, etc.).

**Heuristic:**
- Agent instructions / behavior contracts → `.rules/`
- Programmatic rule definitions in Datalog → `rules/`
- Engineering notes / one-off coding rules → `docs/` (there is no third `rules/` location — the former `docs/rules/` fragment was removed 2026-08-25)

If a future Datalog file needs to live here, name it descriptively and add a
one-line note in this README about what it gates.

## Current contents

| File | Purpose |
|---|---|
| `compliance.dl` | Datalog rules consumed by the V6.0 compliance gate (CASL + GDPR + send-rate guards). |

## Cross-reference
- [[.rules/INDEX]] — IDE workspace rules for AI agents (different purpose).
