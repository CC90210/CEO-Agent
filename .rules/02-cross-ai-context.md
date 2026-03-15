---
description: CRITICAL — How to maintain context across AI agents (Claude, Gemini, Antigravity)
---

# Cross-AI Context Protocol (NON-NEGOTIABLE)

CC uses THREE AI agents interchangeably: Claude Code CLI, Gemini CLI, and Antigravity IDE chat. Work done in ANY agent MUST be visible to ALL others.

## When CC asks "what did we do today?" or "what work was done?" or any question about recent activity:

**ALWAYS read these files FIRST before answering:**

1. `memory/SESSION_LOG.md` — Complete log of ALL work done across ALL agents
2. `memory/ACTIVE_TASKS.md` — Current task status and progress
3. `brain/STATE.md` — Current operational state, blockers, infrastructure status

These files are the **single source of truth** for cross-session context. Every AI agent updates them after every interaction (Rule 0). If you skip reading them, you will give CC incomplete or wrong answers.

## After EVERY interaction where state changed (Rule 0):

Update ALL THREE files immediately:
- `brain/STATE.md` — operational state
- `memory/ACTIVE_TASKS.md` — task progress
- `memory/SESSION_LOG.md` — append what was done

**Why:** If CC switches to Claude Code or Gemini on the very next prompt, they need perfect context. Zero-friction handoffs require up-to-the-second state sync.

## Additional context files to check when relevant:

- `memory/MISTAKES.md` — Known mistakes and prevention strategies
- `memory/PATTERNS.md` — Validated patterns and approaches
- `brain/CAPABILITIES.md` — What tools, skills, workflows exist
- `brain/APP_REGISTRY.md` — Local paths for all app codebases
- `brain/AGENTS.md` — 14 subagent definitions and delegation matrix

## NEVER do this:

- Answer questions about recent work from memory alone — ALWAYS read the files
- Assume nothing happened if you don't remember — another AI may have done the work
- Skip the state sync after making changes — this breaks handoffs to other agents
