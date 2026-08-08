---
description: "Approval queue for agent-proposed changes to core system files; tracks submissions, CC review status, and application history for entry points and BRAIN_LOOP"
tags: [memory, governance]
last_updated: 2026-05-21
freshness_threshold_days: 90
---

# BRAVO — Proposed Changes Queue

> Changes to semi-mutable files (entry points, BRAIN_LOOP.md, INTERACTION_PROTOCOL.md) require CC's approval.
> Agent writes proposals here. CC reviews and approves/rejects.
> [[brain/STATE]] | [[brain/INTERACTION_PROTOCOL]] | [[brain/CHANGELOG]]

## Format

- **File:** path to file
- **Section:** which section to change
- **Current:** what it says now
- **Proposed:** what it should say
- **Reason:** why this change improves the system
- **Evidence:** what observations support this
- **Risk:** what could go wrong
- **Rollback:** how to undo
- **Status:** PENDING | APPROVED | REJECTED | APPLIED

---

## Active Proposals

*None.*

---
tags: [governance, changes]
---

## Applied History

### #4 — `CLAUDE.md` · prompt_note · **WITHDRAWN**

- **File:** `CLAUDE.md`
- **Reason:** V7.6.0 verification: operator boundary
- **Evidence:** `python -c "print(open('CLAUDE.md',encoding='utf-8').read().count('RULE 5'))"`
- **Measured:** before `1` → after `(never applied)`
- **Rollback:** n/a — never applied (nothing to undo)
- **Status:** WITHDRAWN — withdrawn: V7.6.0 boundary verification only — not a real proposal
- **Created:** 2026-08-08 03:58:44 (session `local`)

### #3 — `memory/PATTERNS.md` · memory · **REVERTED**

- **File:** `memory/PATTERNS.md`
- **Reason:** V7.6.0 verification: accept path
- **Evidence:** `python -c "print(open('memory/PATTERNS.md',encoding='utf-8').read().count('validated 3+ uses'))"`
- **Measured:** before `0` → after `1`
- **Rollback:** n/a — never applied (nothing to undo)
- **Status:** REVERTED — reverted (byte-exact restore: True)
- **Created:** 2026-08-08 03:58:27 (session `local`)

### #2 — `memory/PATTERNS.md` · memory · **REJECTED**

- **File:** `memory/PATTERNS.md`
- **Reason:** V7.6.0 verification: reject path
- **Evidence:** `python scripts/harness_eval.py --json` (key: `score`)
- **Measured:** before `"9/10"` → after `"9/10"`
- **Rollback:** n/a — never applied (nothing to undo)
- **Status:** REJECTED — no measured effect — evidence unchanged ("9/10"); auto-reverted
- **Created:** 2026-08-08 03:57:54 (session `local`)

### #1 — `memory/PATTERNS.md` · memory · **REJECTED**

- **File:** `memory/PATTERNS.md`
- **Reason:** V7.6.0 verification: keyed evidence
- **Evidence:** `python scripts/harness_eval.py --json` (key: `score`)
- **Measured:** before `"9/10"` → after `(never applied)`
- **Rollback:** n/a — never applied (nothing to undo)
- **Status:** REJECTED — no-op edit — working tree unchanged after write
- **Created:** 2026-08-08 03:56:19 (session `local`)

## Obsidian Links
- [[brain/INTERACTION_PROTOCOL]] | [[brain/CHANGELOG]] | [[brain/STATE]]
- [[memory/DECISIONS]] | [[memory/SESSION_LOG]]
