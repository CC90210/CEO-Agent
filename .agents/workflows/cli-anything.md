---
description: Generate a CLI wrapper for any software, API, or service using the CLI-Anything methodology
---

// turbo-all

## Trigger
When CC says: "make a CLI for X", "wrap X as CLI", "CLI-anything X", or `/cli-anything <target>`

## Steps

1. **Identify Target**: What software/API/service needs a CLI wrapper?
2. **Load Skill**: Read `skills/cli-anything/SKILL.md` for the full 7-phase pipeline
3. **Phase 1 — Analyze**: Research the target (docs, API, source code). Use Playwright for web docs, Context7 for libraries.
4. **Phase 2 — Design**: Present CLI command structure to CC for approval. Include command groups, flags, and output formats.
5. **Wait for CC approval** before proceeding to implementation.
6. **Phase 3 — Implement**: Build the CLI using templates from `scripts/cli_templates/`. Backend MUST call real software via subprocess.
7. **Phase 4-5 — Test**: Write and run unit + E2E tests. Verify real output artifacts.
8. **Phase 6 — Package**: Create setup.py, install locally with `pip install -e .`
9. **Phase 7 — Integrate**: Update `brain/CAPABILITIES.md`, add usage examples, update AI entry points if needed.
10. **Log**: Append summary to `memory/SESSION_LOG.md`

## Rules
- NEVER install CLI packages inside Business-Empire-Agent. Use separate directories or global pip.
- NEVER reimplement core software logic — always subprocess to the real tool.
- ALWAYS support `--json` flag for agent-readable output.
- ALWAYS read credentials from `.env.agents` via `load_env_credentials()` — the wrapper loads them
  internally. Never read the file yourself; `secret_guard` blocks it by design.
- Present Phase 2 design to CC before building.

## Anti-Slop gates (V8.0 — added 2026-07-29)

The full matrix is stamped into every entry point (`PERSONAL.md` LOCKSTEP `anti_patterns`);
rationale in `brain/EXECUTION_RULES.md` § 19. The four rows that bite hardest on a CLI build:

| Gate | Applies here as |
|---|---|
| **#1 Probe, don't assume** | Before writing the auth layer, `python scripts/capability_probe.py check <service>`. AVAILABLE means the key exists — build against it. Never open with "you'll need to add credentials". |
| **#2 No silent swallowing** | A CLI that catches a subprocess failure and prints "done" is worse than one that crashes. Non-zero exit → non-zero exit, with the real stderr. |
| **#3 No mock data** | `--json` must emit what the tool actually returned. A sample payload shaped like the real one is the hardest defect in this document to detect later. |
| **#6 Empirical proof** | Phase 4-5 is not "wrote tests" — it is the test output pasted into the report, plus one real invocation against the live target. |

Read the target's actual API/schema before generating the consuming code (#7). A guessed flag
name produces a CLI that runs and does nothing.

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/CAPABILITIES]]
