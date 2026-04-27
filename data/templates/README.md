---
tags: [data, templates]
---

# Template Library

Reusable templates for proposals, emails, documents, content, and reports. Templates exist so the blank page problem never slows down execution.

## Categories

- `/proposals/` — Client proposal and SOW templates
- `/emails/` — Outreach, follow-up, and notification email templates
- `/documents/` — NDA, contract, project brief, and status report templates
- `/content/` — Social media post, blog, thread, and case study templates
- `/reports/` — Status report, QBR, and investor update templates

## Usage

Templates are referenced by skills and scripts. Specific usage points:

| Skill | Templates Used |
|-------|---------------|
| `skills/investor-communications/SKILL.md` | `/reports/investor-update.md`, `/reports/qbr.md` |
| `skills/knowledge-management/SKILL.md` | All categories |
| `skills/proposal-generation/SKILL.md` | `/proposals/retainer-proposal.md`, `/proposals/project-sow.md` |
| `../CMO-Agent/skills/email-marketing/SKILL.md` | `/emails/cold-outreach.md`, `/emails/follow-up.md` |
| `../CMO-Agent/skills/content-engine/SKILL.md` | `/content/linkedin-post.md`, `/content/x-thread.md` |

## Update Protocol

After using a template in a real engagement:
1. Note any sections that were always modified
2. Update the template to reflect the real-world version
3. Remove sections that were always deleted
4. Add sections that were always added manually

Templates that don't evolve become obsolete. Update after every 3rd use.

## Naming Convention

`[type]-[variant].md`

Examples:
- `retainer-proposal.md`
- `project-sow.md`
- `cold-outreach-hvac.md`
- `follow-up-day7.md`
- `linkedin-thought-leadership.md`

## Obsidian Links
- [[skills/knowledge-management/SKILL]] | [[skills/proposal-generation/SKILL]]
- [[../CMO-Agent/skills/email-marketing/SKILL]] | [[../CMO-Agent/skills/content-engine/SKILL]]
