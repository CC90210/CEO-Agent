---
name: WHEN TO USE SKILLS
description: One-line trigger map per skill. The chat agent reads this once, knows which skill body to lazy-load when.
mutability: SEMI-MUTABLE
tags: [brain, agent-only, skills-index]
last_updated: 2026-05-06
---

# WHEN TO USE SKILLS

> The catalog has 150+ entries. Loading every `SKILL.md` body costs 100k+ tokens.
> This index is the cheap router: trigger phrase → skill name → when NOT to use.
> Read the skill's own `SKILL.md` body only after deciding it's the right one.

---

## Outbound + comms

| Trigger | Skill | Don't use when |
|---|---|---|
| send email, cold outreach, follow-up, reply | `outreach-send` | one-off "test send" — use `google_tool.py gmail send` directly |
| draft a long-form email sequence | `email-engine` | single message — `outreach-send` is lighter |
| Telegram / mobile notify | `notify` | scheduled posts — that's `late_tool` |
| social media post (single) | `social-publisher` | full content pipeline — delegate to Maven |

## Sales / CRM

| Trigger | Skill | Don't use when |
|---|---|---|
| add a lead, score a lead, run pipeline check | `lead-engine` (CLI direct) | qualifier scoring at ingest — `n8n-inbound-classifier` |
| client health check, churn alert | `client-success` | sales pipeline — that's `lead-engine` |
| pricing / proposal / SOW | `proposal-generation` | back-of-envelope — `deal-architecture` doc |
| competitive analysis, battlecard | `competitive-intelligence` | one-off lookup — `firecrawl_tool` is enough |
| objection handling on a call | `sales-methodology` (NEPQ) | written reply drafts — voice-rules in SOUL |

## Content (Maven domain — usually delegate)

| Trigger | Skill | Don't use when |
|---|---|---|
| make-this-a-post (full pipeline) | (delegate to Maven) | quick caption — `late_tool` direct |
| brand voice check | `brand-voice` (Maven) | one-line edit |

## Code / build

| Trigger | Skill | Don't use when |
|---|---|---|
| 5-whys debug, find root cause | `systematic-debugging` | typo / one-line fix |
| pre-ship review | `code-review` | post-ship — too late, log to `MISTAKES.md` |
| ship to prod | `ship` | local-only change |
| run tests | `test-driven-development` | exploratory — just run the script |
| browser automation | `browser-harness` (logged-in) or `browser-automation` (Playwright clean-room) | scraping for data — `firecrawl_tool` |
| anti-pattern check | `anti-drift` | normal code — only when self-improving |

## Memory / state

| Trigger | Skill | Don't use when |
|---|---|---|
| log a mistake | (write to `memory/MISTAKES.md` directly) | success — log to `PATTERNS.md` instead |
| stale memory, scan old | `memory-management` | one file — read it directly |
| context compaction needed | `context-optimization` | conversation is fine |

## Operations

| Trigger | Skill | Don't use when |
|---|---|---|
| daily plan / schedule | `daily-planner` | weekly — that's `weekly-review` |
| CEO briefing | `ceo-briefing` | metric lookup — `ceo_dashboard.py` direct |
| crisis response | `crisis-response` | normal hiccup |
| financial modeling | (delegate to Atlas) | quick MRR lookup — `revenue_engine.py` |
| email safety check | `email-safety` | normal send — `outreach-send` covers this |
| credentials / secrets | `security-protocol` | reading env names — that's automatic |

## Agent infrastructure

| Trigger | Skill | Don't use when |
|---|---|---|
| create new sub-agent | `agent-forge` | reuse existing — check `brain/AGENTS.md` first |
| agent permissions | `agent-permissions` | read-only intent — already allowlisted |
| agent runtime packaging | `agent-runtime-packaging` | one-off script |
| MCP setup | `mcp-operations` | use existing MCP — list in `brain/CAPABILITIES.md` |

## Google Workspace

| Trigger | Skill | Don't use when |
|---|---|---|
| create / read calendar event | `gws-calendar` (or `-insert` for write-only) | recurring meeting via templates |
| read / send Gmail | `gws-gmail-read` / `gws-gmail-send` | sequence — `email-engine` |
| Google Docs work | `gws-docs` (read) / `gws-docs-write` | template fill — `gws-templates` |
| Drive upload / share | `gws-drive` / `gws-drive-upload` | bulk — script directly |
| Forms create | `gws-forms` | survey analysis — `gws-forms-read` |

## Delegation skills

| Trigger | Skill | Don't use when |
|---|---|---|
| backend implementation, deep debug | `codex-delegation` | frontend, brand, simple fix (do inline) |
| Skool community engagement | `skool-automation` | one-off post — Playwright direct |
| ad creative production | (delegate to Maven) | — |

---

## How to use this file

1. Match the operator's intent against the trigger column above.
2. Note the skill name + the "don't use when" guard.
3. If you're going to invoke the skill, `read_file("skills/<skill-name>/SKILL.md")` for the body.
4. If multiple triggers match: prefer the more specific one. If still tied, prefer the skill closer to the operator's exact verbs.

If the trigger isn't here, the skill probably isn't meant to be picked from chat — it's a build-time artifact. Read `skills/INDEX.md` to confirm before guessing.

---

## How to add a skill to this index

When `skills/<new-name>/SKILL.md` lands and is meant to be invoked from chat:

1. Add a row to the right section. Trigger phrase, skill slug, "don't use when".
2. Bump `last_updated:`.
3. Don't grow this file past ~250 lines. If a section bloats, split into a domain-specific index file and link from here.
