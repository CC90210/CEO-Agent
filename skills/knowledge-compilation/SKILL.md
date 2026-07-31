---
name: knowledge-compilation
description: Use this skill to ingest raw documents into the compiled wiki, query the knowledge base for sourced answers, or lint the wiki for broken links and stale facts. Implements Karpathy-style LLM knowledge compilation — no RAG, deterministic retrieval via structured wiki pages.
triggers: [ingest, query knowledge, lint knowledge, compile knowledge, knowledge base, wiki, raw document, karpathy]
tier: specialized
dependencies: [knowledge-management, memory-management]
tags: [skill, knowledge, compilation, wiki, ingest]
last_updated: 2026-05-21
---

# Knowledge Compilation Skill

The Business-Empire-Agent knowledge base uses a Karpathy-style architecture: raw source documents
are compiled by an LLM into structured, cross-linked markdown wiki pages. There are no embeddings,
no vector stores, no fuzzy retrieval. An LLM navigates the wiki deterministically by reading
`knowledge/index.md` and then reading only the relevant pages.

**Architecture reference:** [[knowledge/SCHEMA]] — read this before any operation.

## When to Use This Skill

| Trigger | Operation |
|---------|-----------|
| CC shares a document, article, research, or notes | `/ingest` |
| CC asks a factual question about OASIS AI, revenue, tech stack, or clients | `/query-knowledge` |
| After a batch of ingests, or weekly maintenance | `/lint-knowledge` |
| CC says "add this to the knowledge base" or "remember this" | `/ingest` |
| CC asks "what do we know about X?" | `/query-knowledge` |

## Operation 1: Ingest (`/ingest`)

**Trigger:** CC provides a document, text block, URL content, or raw file path.

### Protocol

**Step 1 — Receive the source.**
Accept the raw material in any form:
- A file in `knowledge/raw/` (check if it already exists)
- Text pasted directly into the conversation
- A URL (use Playwright to retrieve the content first, then treat it as raw text)
- Notes CC dictates verbally

If the source is a file, save it to `knowledge/raw/YYYY-MM-DD-[slug].md` before processing.
If it is inline text, save it to `knowledge/raw/YYYY-MM-DD-[slug].md` first anyway — the raw
layer is always preserved.

**Step 2 — Extract entities and facts.**
Read the source in full. Identify:
- Key facts (people, prices, dates, metrics, decisions)
- Relationships between entities
- Opinions or positions (tag these as such — they are not facts)
- Action items or next steps (these go to `memory/ACTIVE_TASKS.md`, not the wiki)

**Step 3 — Classify each fact into a wiki page.**
Read `knowledge/index.md`. For each fact:
- Does an existing page cover this topic? → update that page
- Is this a new topic without a home? → create a new wiki page
- Does this contradict something already in the wiki? → note the conflict explicitly

**Step 4 — Update or create wiki pages.**
For each affected page:
- If updating: add or modify only the relevant section. Do not rewrite the whole page.
- If creating: use the wiki page template from `knowledge/SCHEMA.md`
- Update the `last_updated` field in the frontmatter
- Add the new source to the `sources:` frontmatter list
- Ensure at least 2 ``wiki-links`` are present

**Step 5 — Update index and log.**
- Add any new pages to the table in `knowledge/index.md`
- Add relevant keywords to the topic index in `knowledge/index.md`
- Append an ingest entry to `knowledge/log.md` using the standard format

**Step 6 — Report to CC.**
State concisely:
- What was ingested
- Which pages were created or updated
- Any conflicts found with existing knowledge
- Any follow-up questions or gaps identified

### Ingest Quality Rules

- Never copy-paste from the source. Compile and restate in your own words.
- Distinguish facts from opinions. Tag speculative content with `(inferred)` or `(CC's view)`.
- If a fact has an expiry (a price, a metric), tag it with `last_verified: YYYY-MM-DD`.
- Set confidence based on source quality: CC's first-hand account = 0.9+. Third-party article = 0.7.
- If the source contradicts the wiki, surface the conflict explicitly. Do not silently overwrite.

---

## Operation 2: Query (`/query-knowledge`)

**Trigger:** CC asks a factual question that may be answered by the compiled wiki.

### Protocol

**Step 1 — Read `knowledge/index.md`.**
Scan the table and topic index. Identify which wiki pages are relevant to the question.

**Step 2 — Read only the relevant pages.**
Do not read all wiki pages. Read only those identified in Step 1.
If the question spans multiple topics, read all relevant pages — but still only those pages.

**Step 3 — Synthesize an answer.**
Construct a direct answer from what the wiki contains. Include:
- The answer (1–5 sentences)
- Which wiki page(s) the information came from
- The confidence score of the relevant page(s)
- The `last_updated` date, if the answer involves metrics that change over time

**Step 4 — Handle gaps explicitly.**
If the wiki does not contain the answer:
- Say "this is not yet compiled in the knowledge base"
- Identify what raw sources would need to be ingested to answer it
- Offer to do the research and ingest it

**Never guess or hallucinate.** The value of the knowledge base is sourced, deterministic
answers. An honest "not compiled yet" is better than a confident wrong answer.

### Query Examples

| Question | Pages to Read |
|----------|--------------|
| "What's our current MRR?" | `wiki/revenue-model` |
| "What's OASIS AI's ICP?" | `wiki/ai-automation-agency` |
| "What stack does PropFlow use?" | `wiki/tech-stack` |
| "How do we handle at-risk clients?" | `wiki/client-playbook` |
| "What's the primary retainer rev share deal?" | `wiki/revenue-model` |

---

## Operation 3: Lint (`/lint-knowledge`)

**Trigger:** Weekly maintenance, or after any batch of ingests.

### Protocol

**Step 1 — Catalog check.**
Read `knowledge/index.md`. For each page listed:
- Verify the file exists at `knowledge/wiki/[slug].md`
- Flag any listed pages that don't exist on disk

**Step 2 — Link integrity.**
Read every file in `knowledge/wiki/`. For each `` ``wiki-link`` `` found:
- Verify the linked file exists (check both `knowledge/wiki/` and `knowledge/SCHEMA.md`, `knowledge/index.md`)
- Flag any broken links (target file does not exist)

**Step 3 — Frontmatter completeness.**
For each wiki page, verify:
- `tags:` field is present and contains `knowledge` and `wiki`
- `sources:` field is present and non-empty
- `last_updated:` field is present
- `confidence:` field is present (0.0–1.0)
- At least 2 ``wiki-links`` in the document body

**Step 4 — Orphan detection.**
Check `knowledge/log.md`. For each ingest entry:
- Is the ingested source reflected in at least one wiki page?
- Is the source listed in that page's `sources:` frontmatter?
- Flag any ingested sources not traceable to a wiki page

**Step 5 — Staleness check.**
For each wiki page, check `last_updated`:
- If older than 90 days: flag as potentially stale
- If `confidence` < 0.5: flag for re-ingest

**Step 6 — Output lint report.**
Produce a structured report:

```
## Lint Report — YYYY-MM-DD

### Broken Links
- [file] → `link` (target not found)

### Missing Frontmatter
- [file] missing: [field names]

### Orphaned Sources
- log.md entry YYYY-MM-DD references source not found in any wiki page

### Stale Pages (last_updated > 90 days)
- [file] — last updated YYYY-MM-DD

### Low Confidence Pages (< 0.5)
- [file] — confidence: 0.X

### Summary
- Pages checked: N
- Broken links: N
- Frontmatter issues: N
- Orphaned sources: N
- Stale pages: N
```

Append the lint report to `knowledge/log.md` as a lint entry.

---

## File Naming Conventions

| File type | Pattern | Example |
|-----------|---------|---------|
| Raw source | `raw/YYYY-MM-DD-[slug].md` | `raw/2026-04-06-client-call-notes.md` |
| Wiki page | `wiki/[slug].md` | `wiki/client-playbook.md` |
| Slug format | lowercase, hyphenated, no dates | `ai-automation-agency` |

## Integration with Other Skills

- After ingesting a document with action items → route those to `memory/ACTIVE_TASKS.md`
- After ingesting competitor data → also update `data/competitors.json` via `scripts/competitive_intel.py`
- After ingesting client feedback → also update client health score via `scripts/client_health.py`
- Lint runs as part of `/knowledge-maintenance` workflow → see `/knowledge-maintenance`

## Obsidian Links
- [[knowledge/SCHEMA]] | [[knowledge/index]] | [[knowledge/log]]
- [[knowledge/wiki/ai-automation-agency]] | [[knowledge/wiki/revenue-model]]
- [[knowledge/wiki/tech-stack]] | [[knowledge/wiki/client-playbook]]
- [[skills/knowledge-management/SKILL.md]] | [[skills/memory-management/SKILL.md]]
- `/ingest` | `/query-knowledge`
- [[brain/CAPABILITIES]] | [[brain/STATE]]
