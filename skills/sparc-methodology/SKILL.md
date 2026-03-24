---
name: sparc-methodology
description: >
  SPARC development workflow: Specification, Pseudocode, Architecture, Refinement, Completion.
  A structured 5-phase approach for complex implementations that ensures thorough planning
  before any code is written. Use when: new feature implementation, complex integrations,
  architectural changes, system redesign, unclear requirements. Skip when: simple bug fixes,
  documentation updates, configuration changes, single-file edits.
tags: [development, planning, methodology]
---

# SPARC Methodology — Structured Development Phases

> **Purpose:** Complex implementations fail when coding starts before thinking finishes.
> SPARC enforces 5 sequential phases that guarantee you understand the problem before
> you write the solution.

## When to Use

**Always use SPARC for:**
- New feature implementation (MODERATE+ complexity)
- Architectural changes or system redesign
- Integration work (connecting new services/APIs)
- Unclear requirements that need decomposition
- Any task the routing skill classifies as COMPLEX or ARCHITECTURAL

**Skip SPARC for:**
- Simple bug fixes (use systematic-debugging skill instead)
- Documentation updates
- Configuration changes
- Well-defined single-file tasks
- Routine maintenance

## The Five Phases

### Phase 1: SPECIFICATION

**Goal:** Define exactly what needs to be built and what "done" looks like.

**Required outputs:**
1. **Requirements list** — Numbered list of specific, testable requirements
2. **Acceptance criteria** — For each requirement, define pass/fail conditions
3. **Edge cases** — What could go wrong? What are the boundary conditions?
4. **Non-requirements** — Explicitly state what is NOT in scope (prevents drift)

**Template:**
```markdown
## Specification: [Feature Name]

### Requirements
1. [Specific, testable requirement]
2. [Another requirement]

### Acceptance Criteria
- R1 passes when: [measurable condition]
- R2 passes when: [measurable condition]

### Edge Cases
- What happens when [boundary condition]?
- What if [failure scenario]?

### Out of Scope
- [Thing we're NOT building]
- [Thing that sounds related but isn't this task]
```

**Gate:** CC must approve the specification before proceeding.
Present it and ask: "Does this spec match what you need? Anything missing or out of scope?"

### Phase 2: PSEUDOCODE

**Goal:** Design the solution logic without implementation details.

**Required outputs:**
1. **Algorithm outline** — Step-by-step logic in plain English or pseudocode
2. **Data flow** — What data enters, transforms, and exits each component
3. **Error handling plan** — What errors can occur and how each is handled

**Template:**
```markdown
## Pseudocode: [Feature Name]

### Algorithm
1. Receive [input] from [source]
2. Validate: check [conditions]
3. Transform: [operation on data]
4. Store: write to [destination]
5. Return: [output format]

### Data Flow
[Source] → validate → transform → [Destination]
                ↓ (on error)
           [Error handler] → [Recovery or user message]

### Error Handling
| Error | Cause | Response |
|-------|-------|----------|
| [Error type] | [When it happens] | [What we do] |
```

**Gate:** Self-review — does the pseudocode cover all requirements from Phase 1?

### Phase 3: ARCHITECTURE

**Goal:** Map the solution to actual files, dependencies, and infrastructure.

**Required outputs:**
1. **File list with changes** — Every file to create/modify, with what changes
2. **Dependency map** — What depends on what (import chains, API calls, DB relations)
3. **Test strategy** — What tests to write, at which level (unit, integration, e2e)

**Template:**
```markdown
## Architecture: [Feature Name]

### File Changes
| Action | File | Changes |
|--------|------|---------|
| CREATE | `src/path/new-file.ts` | [Purpose of this file] |
| MODIFY | `src/path/existing.ts:45-60` | [What changes and why] |
| TEST | `tests/path/test-file.test.ts` | [What it tests] |

### Dependencies
- `new-file.ts` imports from `existing-module.ts`
- `new-file.ts` calls Supabase table `[table_name]`
- `api-route.ts` depends on `new-file.ts` for [purpose]

### Test Strategy
- Unit: [function-level tests for core logic]
- Integration: [tests that verify component interaction]
- E2E: [if applicable — browser-level verification]
```

**Gate:** CC must approve architecture for COMPLEX+ tasks.
Present: "Here's the architecture. [N] files, [M] new, [K] modified. Approve to proceed?"

### Phase 4: REFINEMENT

**Goal:** Implement the solution following TDD, then iterate based on test results.

**Process:**
1. Write failing tests first (see `skills/test-driven-development/SKILL.md`)
2. Implement minimal code to pass tests
3. Refactor while keeping tests green
4. Run code review (see `skills/code-review/SKILL.md`)
5. Fix any CRITICAL or HIGH issues from review

**Required outputs:**
1. **Code implementation** — All files from Phase 3 created/modified
2. **Test results** — All tests passing, with output
3. **Code review pass** — No CRITICAL/HIGH issues remaining

**Anti-drift check:** At the end of Phase 4, compare actual files touched against Phase 3's file list. Any unexpected files = scope creep.

### Phase 5: COMPLETION

**Goal:** Verify everything works end-to-end and ship.

**Checklist:**
- [ ] All tests pass (`npm test` or equivalent)
- [ ] Build succeeds (`npm run build`)
- [ ] Changelog entry written
- [ ] Documentation updated (if user-facing changes)
- [ ] SESSION_LOG.md updated
- [ ] ACTIVE_TASKS.md updated
- [ ] Commit with conventional format: `bravo: feat — [description]`

**Required outputs:**
1. All tests pass
2. Build succeeds
3. Changelog entry
4. Documentation updated (if applicable)

## SPARC + Task Routing Integration

The task routing skill determines WHEN to use SPARC:

| Routing Complexity | SPARC? | Phases Used |
|-------------------|--------|-------------|
| TRIVIAL | No | — |
| SIMPLE | No | — |
| MODERATE | Optional | Phases 1, 3-5 (skip pseudocode for familiar patterns) |
| COMPLEX | Required | All 5 phases |
| ARCHITECTURAL | Required | All 5 phases + CC approval at Phase 1 and 3 |

## SPARC + Existing Skills

SPARC doesn't replace existing skills — it orchestrates them:

- **Phase 1** (Specification): Uses `skills/writing-plans/SKILL.md` patterns
- **Phase 4** (Refinement): Uses `skills/test-driven-development/SKILL.md` for TDD
- **Phase 4** (Refinement): Uses `skills/code-review/SKILL.md` for quality gate
- **Phase 5** (Completion): Uses `skills/ship/SKILL.md` for deployment pipeline

## Config Reference

All SPARC settings are in `.agents/config.toml` [sparc] section:
- Phase sequence, required outputs, and approval gates are configurable
- Default: CC approval required at Specification and Architecture phases

## Obsidian Links
- [[skills/writing-plans/SKILL]] | [[skills/executing-plans/SKILL]]
- [[skills/test-driven-development/SKILL]] | [[skills/code-review/SKILL]]
- [[skills/task-routing/SKILL]] | [[brain/BRAIN_LOOP]]
