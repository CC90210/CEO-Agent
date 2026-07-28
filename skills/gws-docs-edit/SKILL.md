---
name: gws-docs-edit
description: "Edit an existing Google Doc in place — find/replace, replace a section between markers, append, or overwrite. Higher-level wrapper around the gws CLI's docs.documents.batchUpdate. Use when you previously created a Google Doc (or know its ID) and need to revise it without spinning up a new file."
triggers: ["gws docs edit", "edit google doc", "update google doc", "replace text in google doc", "replace section in google doc", "append to google doc", "overwrite google doc"]
tier: specialized
metadata:
  category: "productivity"
  requires:
    bins: ["gws", "python"]
  cliHelp: "python scripts/integrations/gws_docs_edit.py --help"
tags: [skill, gws-docs-edit]
last_updated: 2026-06-12
---

# gws-docs-edit — Edit Google Docs in place

> **PREREQUISITE:** `gws auth login` must have run at least once on this machine.
> See [[skills/gws-shared/SKILL.md]] for auth + global flags.

The Drive MCP that ships with the Claude session only supports **create + read**. When a Google Doc needs to be revised (proposal v2, meeting prep edit, etc.) creating a new doc each time creates file pollution. This skill closes that gap.

Wraps the gws CLI's `docs documents batchUpdate` with four high-level operations:

| Command | What it does |
|---------|--------------|
| `dump` | Print the doc body as plain text (useful for finding marker substrings before editing). |
| `replace-text` | Atomic find/replace via Docs API `replaceAllText`. Best for surgical changes like "$35K → $7.5K". |
| `replace-section` | Delete everything between a start marker and an optional end marker, insert new content in its place. Best for swapping a whole section of structured content. |
| `append` | Append plain text at end of body. |
| `overwrite` | Wipe doc body, write fresh content. Use when starting over is cleaner than diffing. |

The wrapper script lives at `scripts/integrations/gws_docs_edit.py`.

## Usage

```bash
# Print the doc text — locate the markers you need
python scripts/integrations/gws_docs_edit.py dump --doc <DOC_ID>

# Surgical find/replace (one offset to many — atomic)
python scripts/integrations/gws_docs_edit.py replace-text \
  --doc <DOC_ID> \
  --find "old text" \
  --replace "new text"

# Replace a whole section (start marker inclusive, end marker exclusive)
python scripts/integrations/gws_docs_edit.py replace-section \
  --doc <DOC_ID> \
  --start-marker "═══ 1. COST COVERAGE" \
  --end-marker "═══ 2. PLAID" \
  --content-file new-section.txt

# Append at end of body
python scripts/integrations/gws_docs_edit.py append \
  --doc <DOC_ID> \
  --text "Addendum: …"

# Or wipe and replace entirely
python scripts/integrations/gws_docs_edit.py overwrite \
  --doc <DOC_ID> \
  --content-file fresh.txt
```

## Argument shapes

| Flag | Required | Notes |
|------|----------|-------|
| `--doc` | ✓ | Google Doc ID (the long string in the URL after `/d/`). |
| `--find` / `--replace` | ✓ (replace-text) | Plain-text substring + replacement. Case-sensitive. |
| `--start-marker` | ✓ (replace-section) | Substring in the FIRST paragraph of the section to replace. Match is case-sensitive, first-occurrence wins. |
| `--end-marker` | optional (replace-section) | Substring in the first paragraph AFTER the section. Omit to replace through end of body. |
| `--text` / `--file` | one (append) | Plain text or a file path. |
| `--content` / `--content-file` | one (replace-section, overwrite) | Plain text or a file path. |

## How section replacement is computed

`replace-section` walks the doc body's structural-element list, finds the paragraph whose text contains the start marker, captures its `startIndex`, then walks forward to the paragraph containing the end marker and captures its `startIndex` as the end. If no end marker is given (or found), the end falls back to the body's last writable offset.

The resulting batchUpdate is:
1. `deleteContentRange({startIndex, endIndex})` to drop the old section
2. `insertText({location: {index: startIndex}, text: <new content>})` to write the replacement

Both fire as one atomic batch — partial failures roll back.

## Auth, env, and PATH gotchas

- **Auth:** Uses whatever account `gws auth login` is currently logged into. There is no per-call auth.
- **GWS_BIN env override:** If the wrapper can't find `gws` automatically, set `GWS_BIN=/path/to/gws` (or `gws.cmd` on Windows) and it'll honor that.
- **Windows + Unicode:** The wrapper forces UTF-8 on subprocess decode so em dashes / bullets / smart quotes don't blow up cp1252.

## Recommended pattern

For a multi-section doc (meeting prep, proposals, retros):

1. Author the first version with `mcp__claude_ai_Google_Drive__create_file` (one-shot).
2. Anchor each top-level section with a unique marker line you can target later — heavy box-drawing rules (`═══════════════════════════════════════════`) work great because they never appear in body content.
3. For any subsequent revision, use `replace-section` against those markers. The marker itself stays put; only the body between them changes.

This pattern keeps a single durable doc URL across revisions — no file pollution, no broken bookmarks/permissions, no "is v3 still the current one?" confusion.

## Security

- Per [[skills/gws-shared/SKILL.md]] write rules: **confirm with the operator before any write call**.
- `overwrite` is destructive — preview the new content with `dump` first if there's any doubt about preserving structure.
- Auth credentials live encrypted at `~/.config/gws/credentials.enc` (keyring-backed). The wrapper never sees them.

## See Also

- [[skills/gws-shared/SKILL.md]] — Auth, global flags, security
- [[skills/gws-docs/SKILL.md]] — Hub for all gws docs commands
- [[skills/gws-docs-write/SKILL.md]] — Lower-level append-only primitive
- `scripts/integrations/gws_docs_edit.py` — Implementation
