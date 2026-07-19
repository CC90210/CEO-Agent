---
adr: 1
title: "CONTEXT.md as this agent's canonical vocabulary"
status: accepted
date: {{TODAY}}
deciders: [{{AGENT_NAME}}, operator]
supersedes: null
superseded_by: null
---

# ADR-0001 — CONTEXT.md as this agent's canonical vocabulary

## Context

This agent is forked from the Business-Empire-Agent (Bravo) harness, which established the empire-wide pattern in its ADR-0002 (context-md-canonical-vocabulary): a single root glossary that every skill, script, and entry point references, so domain terms are defined once and never re-derived mid-session.

## Decision

`/CONTEXT.md` is the single source of truth for this agent's domain vocabulary. Rules inherited from the empire parent:

1. A new domain term enters CONTEXT.md before it enters code, skills, or docs.
2. One canonical definition per term — redefining a term elsewhere shadows the canonical entry and breaks retrieval.
3. Skills introducing ≥5 unique terms get a skill-local `LANGUAGE.md` instead of bloating the root glossary.
4. The glossary is per-agent: this file describes THIS agent's domain, never a copy of a sibling's.

## References

- Empire parent: Business-Empire-Agent `docs/adr/0002-context-md-canonical-vocabulary.md`
- Propagation contract: Business-Empire-Agent `brain/V68_AGENT_OS_PATTERNS.md`
