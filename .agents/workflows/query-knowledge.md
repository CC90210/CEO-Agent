---
name: Query Knowledge
trigger: /query-knowledge
schedule: on-demand
agent: bravo
dependencies: [knowledge-compilation, knowledge-management]
tags: [workflow, knowledge, query]
---

# Query Knowledge Workflow — Sourced Answers from the Wiki

Retrieve deterministic, sourced answers from the compiled knowledge wiki.
Full protocol: [[skills/knowledge-compilation/SKILL]]

## When to Run

- CC asks a factual question about OASIS AI, revenue, clients, or the tech stack
- CC says "what do we know about X?"
- Any question where the answer should come from compiled, verified knowledge
  rather than from the agent's training data or from reading raw brain files

## Why This Approach

The knowledge wiki is compiled and curated. It has confidence scores, source attribution,
and freshness dates. Answers from the wiki are more reliable than answers from training
data or ad-hoc brain file reads because they are explicitly sourced and auditable.

## Steps

### Step 1 — Read the index

Read `knowledge/index.md`. Scan:
- The pages table (what exists and what it covers)
- The topic index (which keywords map to which pages)

Identify which 1–3 pages are most relevant to the query.

### Step 2 — Read only the relevant pages

Read the identified pages from `knowledge/wiki/`. Do not read all pages.
If the query spans multiple topics: read all relevant pages, still limited to those identified.

### Step 3 — Synthesize the answer

Construct a direct answer that includes:
- The answer itself (1–5 sentences, plain language)
- The source page(s): `knowledge/wiki/[page]`
- The confidence score of the relevant page(s)
- The `last_updated` date when the answer involves time-sensitive data (MRR, metrics)

### Step 4 — Handle gaps

If the wiki does not contain enough information to answer the query:
1. Say explicitly: "This is not yet compiled in the knowledge base."
2. Identify what information is missing
3. Recommend which raw sources to ingest (e.g., "Ingesting the Q1 revenue report would answer this")
4. If Bravo can research and ingest on the spot: offer to do so

**Never hallucinate or guess.** Honest gaps are better than confident wrong answers.

### Step 5 — Flag stale information

If answering from a page with:
- `confidence` < 0.7 → mention this: "Note: this data has confidence 0.6 — worth verifying"
- `last_updated` > 60 days ago → mention: "Last compiled on YYYY-MM-DD — may need a refresh"

## Examples

| CC Asks | Pages to Read | Expected Answer Type |
|---------|--------------|---------------------|
| "What's our net MRR right now?" | `wiki/revenue-model` | Specific number + breakdown |
| "What's OASIS AI's ideal client?" | `wiki/ai-automation-agency` | ICP description |
| "How does the primary retainer rev share work?" | `wiki/revenue-model` | Deal structure |
| "What tools does Bravo use for social?" | `wiki/tech-stack` | Zernio + late_tool.py |
| "How do I handle an at-risk client?" | `wiki/client-playbook` | Health score + retention actions |

## Output

A direct, sourced answer. Not a file dump. Not a wall of context. The answer + where it came from.

## Obsidian Links
- [[skills/knowledge-compilation/SKILL]] | [[knowledge/SCHEMA]] | [[knowledge/index]]
- [[.agents/workflows/ingest]] | [[.agents/workflows/knowledge-maintenance]]
- [[.agents/workflows/INDEX]]
