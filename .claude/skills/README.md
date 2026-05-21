# .claude/skills/ — Claude Code Slash Command Wrappers

> **STRICT NOTE:** These are Claude Code slash command wrappers only. The actual execution logic and full skill definitions live in the root `/skills/` directory. Do not add core logic here.

## How It Works

- Files in `.claude/skills/` are thin wrappers that tell Claude Code about available slash commands (e.g., `/ship`, `/review`, `/commit`).
- The real implementation, templates, and reference docs live in `skills/<skill-name>/SKILL.md` at the repo root.
- When a skill is triggered, Claude Code loads the wrapper here, which then points to the full definition in `skills/`.

## Rules

1. **Do not add core logic to this directory.** All logic belongs in `skills/`.
2. **Do not edit wrapper files** unless you are adding or removing a slash command.
3. **If a skill's behavior needs changing**, edit the `skills/<name>/SKILL.md` file — not the wrapper here.
4. **Adding a new slash command:** create the wrapper in `.claude/skills/` AND the full skill definition in `skills/`.
