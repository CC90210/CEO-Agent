---
tags: [data, market-research]
last_updated: 2026-04-27
---

# Market Research Archive

Store market research reports, industry analyses, and trend data here. All files must include `last_updated` in their frontmatter.

## Structure

- `/verticals/` — Research by industry vertical (HVAC, wellness, real estate, etc.)
- `/trends/` — AI/SaaS industry trends and technology shifts
- `/sizing/` — TAM/SAM/SOM calculations and methodology

## Freshness Policy

- Market data older than 90 days should be flagged for refresh
- Competitor data older than 30 days should be updated (see `data/competitors.json`)
- See `skills/knowledge-management/SKILL.md` for the full freshness scoring framework

## Naming Convention

Files should follow: `YYYY-MM-DD_[topic]_[scope].md`

Examples:
- `2026-03-28_hvac-automation-market_canada.md`
- `2026-03-28_saas-benchmarks_smb.md`
- `2026-03-28_proptech-funding_q1-2026.md`

## File Template

```markdown
---
topic: [topic name]
scope: [geography or segment]
last_updated: YYYY-MM-DD
source: [URL or description]
confidence: 0.0–1.0
tags: [data, market-research, vertical-name]
---

# [Title]

## Executive Summary
[Layer 4 — 1-2 sentence summary of the key insight]

## Key Findings
- [Finding with data point and source]
- [Finding with data point and source]

## Implications for OASIS AI / PropFlow / Nostalgic Requests
[Specific, actionable implication for each relevant brand]

## Sources
- [Source name, URL, date accessed]
```

## Obsidian Links
- [[skills/knowledge-management/SKILL]] | [[skills/market-research/SKILL]]
- `data/competitors.json` | [[brain/STATE]]
