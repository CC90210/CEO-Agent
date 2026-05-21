---
name: agent-runtime-packaging
description: "Build and maintain product-grade agent infrastructure: onboarding diagnostics, runtime home, packaging, skill lifecycle, tool manifests, and agent scaffolds."
triggers: ["agent runtime packaging", "use agent runtime packaging", "run agent runtime packaging"]
---

# Agent Runtime Packaging

Use this skill when turning Bravo, Atlas, Maven, Aura, Hermes, or a client agent from a repo into an installable, diagnosable, repeatable product.

The goal is Hermes-grade infrastructure under Bravo-grade business intelligence.

## Core Principle

Business intelligence sits on top of infrastructure. The infrastructure should make the agent easy to install, inspect, operate, repair, extend, and package for another business.

## Required Layers

Every productized agent should have:

1. Entry point docs: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `ANTIGRAVITY.md`.
2. Brain and memory: `brain/`, `memory/`, state, active tasks, session log.
3. CLI layer: setup, doctor, status, tools, skills, browser, sessions, gateway.
4. Runtime home: `~/.bravo`, `~/.atlas`, `~/.maven`, `~/.aura`, or client-specific equivalent.
5. Config template: no secrets, clear env requirements, safe defaults.
6. Skill lifecycle: create, register, validate, audit, promote, deprecate.
7. Tool manifest: discoverable scripts and commands.
8. Browser intelligence: Browser Harness plus domain skills and approval gates.
9. Safety gates: outbound chokepoint, finance approval, production approval, destructive-action approval.
10. Diagnostics: read-only doctor command that explains what is missing.

## Current Bravo Files

- Onboarding doctor: `scripts/onboarding_diagnostics.py`
- Browser doctor: `scripts/browser/browser_harness_doctor.py`
- Runtime notes: `runtime/README.md`
- Install notes: `install/README.md`
- Config example: `config/bravo-config.example.toml`
- Browser skill: `skills/browser-harness/SKILL.md`
- Browser domain memory: `browser/domain-skills/`

## Build Order

When packaging a new agent:

1. Create the brain/memory/entry-point skeleton.
2. Add config template and env scaffold.
3. Add a doctor command before adding automation.
4. Add tool manifest and skill registry.
5. Add Browser Harness domain-skill folder.
6. Add install scripts.
7. Add session store/search.
8. Add gateway adapters only after the basic doctor is green.

## Skill Lifecycle

Skills should move through these states:

- `draft`: local only, not trusted yet.
- `registered`: discoverable in docs and registry.
- `validated`: used successfully and passes structural checks.
- `promoted`: included in the default agent pack.
- `deprecated`: replaced or unsafe, retained only for history.

Every skill needs:

- YAML frontmatter with `name` and `description`.
- A clear trigger.
- Safety constraints.
- Verification steps.
- References to scripts, docs, or templates it uses.

## Diagnostics Standard

Doctor commands must be read-only and should print:

- required tools
- missing credentials without revealing values
- required directories/files
- service reachability if safe
- current attach/runtime state
- exact next action

Doctor commands should not:

- mutate `.env.agents`
- run database migrations
- send messages
- start paid services
- delete or overwrite files
- hide partial failure behind a green status

## Safety

Never let packaging work bypass Bravo's business safety:

- Outbound stays behind `scripts/integrations/send_gateway.py`.
- Browser writes require approval.
- Finance actions require approval.
- Production setting changes require approval.
- Destructive actions require approval.

## Related
- [[skills/INDEX.md]]
- [[brain/CAPABILITIES]]
