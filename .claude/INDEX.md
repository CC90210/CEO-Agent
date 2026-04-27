---
tags: [claude-code, hub, index]
---

# .claude/ — Claude Code Local Configuration Hub

> Top-level index for `.claude/`. Links the local agent definitions, skill overrides, and Codex plugin so they're reachable from the graph.
>
> Parent: [[brain/INDEX]] · Sibling hubs: [[.agents/INDEX]] · [[.gemini/INDEX]]

## Native subagents (auto-discovered by Claude Code at spawn)
- [[.claude/agents/architect]] — system design, DB schema, API contracts (opus)
- [[.claude/agents/code-reviewer]] — two-pass structural + adversarial code review (sonnet)
- [[.claude/agents/content-writer]] — platform content in CC's authentic voice (opus)
- [[.claude/agents/debugger]] — root-cause-first debugging, 5 Whys, bisect (sonnet)
- [[.claude/agents/researcher]] — multi-source research, docs, competitive (sonnet)
- [[.claude/agents/security-reviewer]] — auth flaws, RLS gaps, OWASP top 10 (sonnet)
- [[.claude/agents/validator]] — read-only output validator for parallel-spawn results (haiku)

## Skill overrides (project-local — slash-command dispatch shims)
- [[.claude/skills/codex-setup]] — Codex companion bootstrap
- [[.claude/skills/grind]] — system-health cleanup workflow
- [[.claude/skills/playwright/SKILL]] — Playwright skill local override

### Workflow shims (mirror .agents/workflows/* for IDE discoverability)
- [[.claude/skills/commit]] · [[.claude/skills/ship]] · [[.claude/skills/review]] · [[.claude/skills/retro]]
- [[.claude/skills/prime]] · [[.claude/skills/status]] · [[.claude/skills/health]] · [[.claude/skills/debug]]
- [[.claude/skills/research]] · [[.claude/skills/post]] · [[.claude/skills/content]] · [[.claude/skills/execute]]
- [[.claude/skills/plan-feature]] · [[.claude/skills/create-prd]] · [[.claude/skills/evolve]] · [[.claude/skills/opencli]]

### Codex slash-command shims
- [[.claude/skills/codex-status]] · [[.claude/skills/codex-result]] · [[.claude/skills/codex-cancel]]
- [[.claude/skills/codex-review]] · [[.claude/skills/codex-adversarial-review]] · [[.claude/skills/codex-rescue]]

## Codex plugin (dual-AI delegation layer)
- [[.claude/plugins/codex/CHANGELOG]] — Codex plugin version history
- [[.claude/plugins/codex/agents/codex-rescue]] — second-AI rescue agent

### Codex commands (full registry)
- [[.claude/plugins/codex/commands/adversarial-review]] — Codex pre-ship review trigger
- [[.claude/plugins/codex/commands/rescue]] — escalate stuck task to Codex
- [[.claude/plugins/codex/commands/cancel]] — cancel an in-flight Codex task
- [[.claude/plugins/codex/commands/setup]] — Codex CLI install + token setup
- [[.claude/plugins/codex/commands/status]] — show in-flight Codex task status
- [[.claude/plugins/codex/commands/result]] — fetch a finished Codex task's result
- [[.claude/plugins/codex/commands/review]] — Codex code-review trigger

### Codex prompts (loaded by command shims)
- [[.claude/plugins/codex/prompts/stop-review-gate]] — pre-stop review prompt
- [[.claude/plugins/codex/prompts/adversarial-review]] — adversarial-review prompt body

### Codex skills (deep references for the runtime + result handling)
- [[.claude/plugins/codex/skills/codex-cli-runtime/SKILL]] — Codex CLI runtime details
- [[.claude/plugins/codex/skills/codex-result-handling/SKILL]] — result-fetching patterns
- [[.claude/plugins/codex/skills/gpt-5-4-prompting/SKILL]] — GPT-5.4 prompting reference

### Codex prompting reference (anti-patterns + recipes + blocks)
- [[.claude/plugins/codex/skills/gpt-5-4-prompting/references/codex-prompt-antipatterns]]
- [[.claude/plugins/codex/skills/gpt-5-4-prompting/references/codex-prompt-recipes]]
- [[.claude/plugins/codex/skills/gpt-5-4-prompting/references/prompt-blocks]]

## Why this directory is dot-prefixed
`.claude/` is Claude Code's project-local configuration directory. Files here are auto-loaded by the harness (agents at spawn, skills on demand, plugin commands as slash-triggers). Kept in the graph so cross-references stay discoverable.