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
- ALWAYS read credentials from `.env.agents` via `load_env_credentials()`.
- Present Phase 2 design to CC before building.
