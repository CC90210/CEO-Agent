---
tags: [knowledge, schema, navigation]
last_updated: 2026-04-06
---

# KNOWLEDGE SCHEMA — Navigation Guide for LLMs

> This file tells any LLM how to navigate and contribute to the knowledge base.
> Read this first before any ingest, query, or lint operation.
> [[knowledge/index]] | [[knowledge/log]] | [[brain/CAPABILITIES]]

## Architecture (Karpathy-Style Compilation)

This knowledge base bypasses RAG. Instead of embedding chunks and doing fuzzy retrieval,
documents are compiled by an LLM into structured, cross-linked wiki pages that any LLM
can navigate deterministically — like a wiki, not a vector database.

```
knowledge/
├── SCHEMA.md        ← you are here — LLM navigation guide
├── index.md         ← catalog of all wiki pages (start here for queries)
├── log.md           ← chronological ingest history
├── raw/             ← immutable source documents (never modify)
│   └── *.md / *.txt / *.pdf summaries
└── wiki/            ← LLM-compiled structured pages (queryable)
    ├── ai-automation-agency.md
    ├── revenue-model.md
    ├── tech-stack.md
    ├── client-playbook.md
│   ├── frontier-models.md
    └── [additional pages as knowledge grows]
```

## Three Operations

### 1. Ingest (`/ingest`)
Convert a raw document into wiki knowledge.

**Input:** A file in `knowledge/raw/` (or inline text passed to the skill)
**Process:**
1. Read the raw source in full
2. Identify the core entities, facts, and relationships it contains
3. For each fact: determine which wiki page it belongs in (check `index.md`)
4. If the page exists: add/update the relevant section, preserving existing content
5. If the page does not exist: create it using the wiki page template below
6. Update `index.md` with any new pages created
7. Append an entry to `log.md`

**Never delete raw source documents. They are the ground truth.**

### 2. Query (`/query-knowledge`)
Search the compiled wiki for relevant information.

**Input:** A natural language question from CC
**Process:**
1. Read `index.md` to identify which wiki pages are relevant to the query
2. Read those specific pages — do not read all wiki pages
3. Extract the relevant facts and synthesize an answer
4. If the answer requires data not in the wiki: say so explicitly, recommend an ingest

**Do not hallucinate.** If the knowledge is not in the wiki, say "not compiled yet" rather
than guessing. The value of this system is deterministic, sourced answers.

### 3. Lint (`/lint-knowledge`)
Check the knowledge base for consistency and completeness.

**Input:** None (runs against the whole wiki)
**Process:**
1. Read `index.md` — verify every listed page exists on disk
2. Read every wiki page — extract all ``wiki-links``
3. Verify each linked page exists in `index.md` and on disk
4. Check every page for a `last_updated` frontmatter field — flag if missing
5. Check every page for at least 2 ``wiki-links`` — flag if fewer
6. Cross-check `log.md` — are all ingested sources reflected in at least one wiki page?
7. Output a lint report with: broken links, stale pages, orphaned sources, missing cross-refs

## Wiki Page Template

All wiki pages in `knowledge/wiki/` follow this structure:

```markdown
---
tags: [knowledge, wiki, <topic-tag>]
sources: [<raw/filename.md>, ...]
last_updated: YYYY-MM-DD
confidence: 0.9
---

# [Page Title]

> One-sentence summary of what this page covers.
> `[[knowledge/index]]` | ```related wiki pages```

## [Section 1]

[Compiled facts, structured prose, not copy-paste from source]

## [Section 2]

...

## Sources
- `raw/<filename>` — [what it contributed]
- Compiled from: brain/STATE.md, brain/USER.md, etc.

## Obsidian Links
- `[[knowledge/index]]` | ```related wiki pages``` | ```the relevant brain file```
```

## Confidence Scoring

Every wiki page has a `confidence` score (0.0 – 1.0) in its frontmatter:

| Score | Meaning |
|-------|---------|
| 0.9 – 1.0 | Verified, current, multiple sources agree |
| 0.7 – 0.89 | Reliable, single source, recently checked |
| 0.5 – 0.69 | Reasonable inference, needs verification |
| Below 0.5 | Stale or contradicted — flag for re-ingest |

Confidence decays by 0.05 per 30 days without a re-ingest.

## Cross-Linking Rules

1. Every wiki page links to `[[knowledge/index]]`
2. Every wiki page links to at least 2 other wiki pages or brain files
3. Use `` ```knowledge/wiki/page-name``` `` format for wiki-to-wiki links
4. Use `` ``brain/FILE`` `` format for links to brain files
5. The index links to every wiki page

## What Goes in `raw/`

Raw documents are source material — unchanged, permanent. They can be:
- Markdown notes from CC (client calls, strategy sessions, ideas)
- Text summaries of PDFs, research papers, articles
- Exported data files (JSON, CSV) with a companion `.md` summary
- Competitor research notes
- Market data snapshots

**Naming convention:** `raw/YYYY-MM-DD-[topic-slug].md`

## Obsidian Links
- [[knowledge/index]] | [[knowledge/log]]
- [[skills/knowledge-compilation/SKILL]] | [[brain/CAPABILITIES]]
