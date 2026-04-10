---
name: Ingest
trigger: /ingest
schedule: on-demand
agent: bravo
dependencies: [knowledge-compilation, knowledge-management]
tags: [workflow, knowledge, ingest]
---

# Ingest Workflow — Raw Document to Compiled Wiki

Compile a raw source document into the structured knowledge wiki.
Full protocol: [[skills/knowledge-compilation/SKILL]]

## When to Run

- CC shares notes from a client call, strategy session, or research session
- CC says "add this to the knowledge base" or "remember this fact"
- A raw document is dropped into `knowledge/raw/`
- After any significant new information is discussed in session

## Steps

### Step 1 — Receive and save the raw source

If CC provided inline text:
1. Determine a slug: lowercase, hyphenated, descriptive (e.g., `primary_retainer-may-call-notes`)
2. Save to `knowledge/raw/YYYY-MM-DD-[slug].md` with the raw content verbatim
3. Confirm: "Saved to `knowledge/raw/[filename]`"

If CC provided a file path or URL:
1. Read the file (or use Playwright to retrieve URL content)
2. Save a clean copy to `knowledge/raw/YYYY-MM-DD-[slug].md`
3. Confirm the save before proceeding

### Step 2 — Read the navigation schema

Read `knowledge/SCHEMA.md` to understand the page template and confidence rules.
Read `knowledge/index.md` to see which wiki pages already exist.

### Step 3 — Extract key facts

From the raw source, extract:
- Concrete facts (metrics, prices, names, dates)
- Relationships (who owns what, how things connect)
- Decisions made (log to `memory/DECISIONS.md` as well)
- Action items (route to `memory/ACTIVE_TASKS.md`, not the wiki)
- Opinions or preferences from CC (tag as `(CC's view)` in the wiki)

### Step 4 — Map facts to wiki pages

For each fact:
- Identify which existing wiki page it belongs in (use the topic index in `knowledge/index.md`)
- If no page exists for this topic: plan to create one

### Step 5 — Update or create wiki pages

For each wiki page being modified:
1. Read the current page first
2. Add or update only the relevant section — no unnecessary rewrites
3. Update `last_updated` in frontmatter to today
4. Add the new source to the `sources:` list in frontmatter
5. Verify at least 2 `wiki-links` remain present

For each new wiki page:
1. Use the template from `knowledge/SCHEMA.md`
2. Set confidence based on source quality (CC first-hand = 0.9+, article = 0.7)
3. Add to `knowledge/index.md` table and topic index

### Step 6 — Update index and log

In `knowledge/index.md`:
- Add any new pages to the table (with confidence and last_updated)
- Add any new keywords to the topic index

In `knowledge/log.md`:
- Append a new ingest entry (source, pages affected, agent, notes)

### Step 7 — Report to CC

State:
- File saved: `knowledge/raw/[filename]`
- Pages updated: [list]
- Pages created: [list, if any]
- Conflicts found: [if any — describe the conflict]
- Action items routed to ACTIVE_TASKS: [if any]

## Output

A compiled wiki with the new knowledge integrated. The raw source is preserved unchanged.
The index is updated. The log shows the ingest history.

## Obsidian Links
- [[skills/knowledge-compilation/SKILL]] | [[knowledge/SCHEMA]] | [[knowledge/index]]
- [[knowledge/log]] | [[.agents/workflows/query-knowledge]] | [[.agents/workflows/knowledge-maintenance]]
- [[.agents/workflows/INDEX]]
