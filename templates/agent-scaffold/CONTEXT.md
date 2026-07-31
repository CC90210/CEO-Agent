---
name: CONTEXT
description: Canonical vocabulary for this agent. Every skill and entry point must use these terms with these meanings. New domain terms enter here first.
tags: [vocabulary, canonical, context]
last_updated: {{TODAY}}
---

# CONTEXT — Canonical Vocabulary

> Single source of truth for this agent's domain terminology. If you find yourself re-deriving what a term means mid-session, the term either belongs here or its existing entry needs tightening. Update this file; don't re-derive.
>
> This file is auto-injected on UserPromptSubmit when a glossary term appears in the prompt (if the hook is wired). Per-agent: do NOT copy another agent's glossary — write your domain's own (V6.8 propagation anti-pattern #1).

## People & agents

- **{{OPERATOR_NAME}}** — The operator. (Fill in on first operator turn.)
- **{{AGENT_NAME}}** — This agent. (Role, siblings, boundaries.)

## Brands

- (The operator's brands, one bullet each — name, what it is, ownership splits.)

## Domain vocabulary

- (The 10-30 terms this agent's work turns on. `- **Term** — definition` bullets, grouped into H2 sections as they accumulate. A skill introducing ≥5 unique terms gets its own `skills/<name>/LANGUAGE.md` instead — see ADR-0001.)

## State / substrate

- (Which files/DBs are source of truth for what.)

## North Star

- (The one metric or mission this agent optimizes for, and who owns it.)

## How to update this file

1. New term about to enter the codebase → add it here FIRST, then use it.
2. One canonical definition per term — never redefine elsewhere (shadowing breaks retrieval).
3. Keep entries to 1-3 lines; link to deeper docs rather than inlining them.
