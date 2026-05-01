---
tags: [contributing, open-source, development]
---

# Contributing to Bravo

Bravo is an autonomous AI business operations system. The architecture is modular — you can add a new agent, skill, CLI tool, or workflow without touching the core.

## Before You Start

Read the system overview:

- `brain/SOUL.md` — identity and values
- `brain/CAPABILITIES.md` — full tool inventory
- `brain/ORCHESTRATION.md` — routing governance and delegation rules
- `CLAUDE.md` — the 9 rules that govern all agent behavior

Fork the repo, clone locally, and run the installer:

```bash
git clone https://github.com/CC90210/CEO-Agent.git
cd CEO-Agent
bash install/install.sh
bravo doctor
```

## What Can You Add?

### A new CLI tool (`scripts/your_tool.py`)

Follow the pattern in `scripts/cli_templates/backend_template.py`:

- Load credentials with `python-dotenv` from `.env.agents` — never hardcode
- Accept `--json` for machine-readable output
- Support `--help` for discovery
- Exit with code 0 on success, non-zero on failure
- Register in `brain/QUICK_REFERENCE.md` and `brain/CAPABILITIES.md`

### A new skill (`skills/your-skill/SKILL.md`)

Skills are knowledge files loaded on demand. Required frontmatter:

```yaml
---
name: your-skill
description: One sentence — what this skill enables
triggers:
  - keywords that load this skill automatically
---
```

Register in `brain/CAPABILITIES.md` skill table. If the skill mutates external state (sends, posts, publishes, pays, deploys), add `disable-model-invocation: true` to frontmatter.

### A new workflow (`.agents/workflows/your-command.md`)

Workflows are slash commands. They define a trigger (`/your-command`) and a step-by-step procedure. See `.agents/workflows/commit.md` for a reference example.

### A new agent (`.claude/agents/your-agent.md`)

Native Claude Code subagents. Use YAML frontmatter to declare name, description, and tools. Keep the `tools:` list as narrow as possible — only what the agent actually needs.

Register in `brain/AGENTS.md`.

## Code Standards

- TypeScript over JavaScript for all Next.js app code
- Python 3.10+ for all scripts
- No `any` in TypeScript without an explanatory comment
- No hardcoded secrets — credentials come from `.env.agents` at runtime
- No `console.log` in production code
- Error handling on every external call (network, DB, subprocess)
- Run `npm run build` before submitting — zero TypeScript errors required

## Commit Message Format

```
type(scope): short description

Longer explanation if needed. Focus on WHY, not WHAT.
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

Examples:
```
feat(scripts): add firecrawl competitor scraper with --json output
fix(email_engine): handle UID quarantine on IMAP reconnect
docs(skills): add frontmatter to missing skill files
```

## Pull Request Checklist

- [ ] `bravo doctor` passes (or failures are explained)
- [ ] New tool/skill registered in `brain/CAPABILITIES.md`
- [ ] No secrets in any committed file
- [ ] `npm run build` passes (zero TS errors) if touching app code
- [ ] `python -m pytest` passes if touching Python code with tests
- [ ] `brain/QUICK_REFERENCE.md` updated if adding a new CLI tool

## Security

Report security issues privately to `conaugh@oasisai.work`. Do not open a public issue for credential leaks, RLS bypasses, or injection vulnerabilities.

See `SECURITY.md` for the full policy.

## License

By contributing, you agree your code will be released under the MIT License.

## Obsidian Links

- [[CLAUDE]] | [[brain/CAPABILITIES]] | [[brain/ORCHESTRATION]] | [[SECURITY]]
