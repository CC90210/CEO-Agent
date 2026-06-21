---
name: agent-teams
description: Spawn and coordinate Claude Code Agent Teams (experimental) — parallel subagents for complex multi-domain tasks
tags: [skill, orchestration, agent-teams]
triggers: ["agent teams", "use agent teams", "run agent teams"]
tier: standard
---

# Agent Teams — Parallel Subagent Coordination

> Enabled via `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in `~/.claude/settings.json`.
> Windows constraint: `teammateMode: "in-process"` only — no subprocess spawning.

## When to Use Agent Teams

Agent Teams are worth the coordination overhead only when:
- The task has clearly separable, non-dependent workstreams
- Each workstream would take > 10 minutes alone
- At least 2 different specializations are needed simultaneously

**Do NOT use for:**
- Simple fixes (< 3 files) — delegation overhead exceeds task effort
- Tasks where output of step A is input to step B (sequential, not parallel)
- Content creation — content-writer runs alone to preserve voice consistency
- Memory/state updates — always single-agent to prevent write conflicts

## Spawning a Teammate

Natural language trigger — no slash command needed. Just describe the parallel need:

> "Spawn a teammate using the security-reviewer agent to audit the auth flow while I implement the new endpoint."

> "Run the code-reviewer and debugger agents in parallel on this PR."

Claude Code will automatically spawn the teammate agent with the appropriate definition from `.claude/agents/`.

## Available Subagent Definitions (`.claude/agents/`)

| File | Agent | Model | Best For |
|------|-------|-------|----------|
| `security-reviewer.md` | security-reviewer | sonnet | Auth flaws, RLS gaps, credential exposure, OWASP checks |
| `researcher.md` | researcher | sonnet | Multi-source research, doc lookup, competitive analysis |
| `code-reviewer.md` | code-reviewer | sonnet | Two-pass structural + adversarial code review |
| `content-writer.md` | content-writer | opus | Platform content in CC's voice (X, LinkedIn, IG, TikTok) |
| `debugger.md` | debugger | sonnet | Root-cause debugging, 5 Whys, bisect regressions |
| `architect.md` | architect | opus | System design, DB schema, API contracts, ADRs |

## Communication Patterns

### Mailbox Pattern (preferred)
Bravo writes a scoped task to a temp file → teammate reads it → teammate writes output to a result file → Bravo reads result.

```
tmp/teammate-task-{agent}-{timestamp}.md   ← Bravo writes the task
tmp/teammate-result-{agent}-{timestamp}.md ← Teammate writes findings
```

### Shared Task List
For longer parallel runs, use `.agents/plans/active-{task}.md` as a shared task list both agents can read. Bravo owns writes; teammate reads only.

## Parallel Execution Patterns

### Pattern A: Review While Building
```
Bravo:    Implements the feature
Teammate: code-reviewer audits existing changes in parallel
Result:   Review ready when implementation is done — no waiting
```

### Pattern B: Security Sweep + Feature Ship
```
Bravo:    Ships the feature (test → changelog → PR)
Teammate: security-reviewer audits auth surface in parallel
Result:   Security sign-off attached to the PR
```

### Pattern C: Research + Architect
```
Bravo:    Researches competitive landscape (researcher agent)
Teammate: architect drafts system design while research runs
Result:   Design informed by findings, both complete simultaneously
```

### Pattern D: Debug + Implement Workaround
```
Bravo:    Implements short-term workaround to unblock CC
Teammate: debugger traces root cause in parallel
Result:   Fix applied now, root cause known for proper patch later
```

## Windows Limitations

- `teammateMode: "in-process"` — teammates share the same process, no subprocess isolation
- No worktree isolation on Windows (architect agent lists `isolation: worktree` but this is advisory — use with care on shared files)
- If two agents attempt to write the same file simultaneously, the last write wins — coordinate via separate output files

## Anti-Patterns

1. Spawning a teammate for a < 5-minute task — overhead exceeds benefit
2. Both agents writing to the same file — causes race conditions
3. Delegating memory writes (brain/, memory/) to a teammate — Bravo owns state
4. Running content-writer as a teammate — voice consistency requires single-agent execution
5. Ignoring teammate output — always read and present findings to CC

## Integration with Existing Routing

This skill extends `skills/task-routing/SKILL.md`. When task routing classifies a task as COMPLEX or ARCHITECTURAL, consider splitting across teammates:

| Routing Tier | Team Configuration |
|---|---|
| MODERATE | Optional: spawn code-reviewer in parallel |
| COMPLEX | Recommended: Bravo (frontend/orchestration) + teammate (backend/security) |
| ARCHITECTURAL | Recommended: architect teammate drafts spec, Bravo implements |

## Obsidian Links
- [[brain/AGENTS]] | [[brain/CAPABILITIES]] | [[skills/task-routing/SKILL.md]]
- [[skills/anti-drift/SKILL.md]] | [[skills/codex-delegation/SKILL.md]]
