"""One YAML-frontmatter reader for every vault tool.

`obsidian_graph_doctor` (which reports gaps) and `frontmatter_doctor` (which
fills them) each grew their own regex and their own field parser. They then
disagreed: the reporter counted 34 gaps where the filler saw 0, because only one
of them understood the block-list form of `tags:`. Two parsers that must agree
are one parser.

Both list forms are valid YAML, valid Obsidian, and both are in use here:

    tags: [brain, genome]        # inline flow list
    tags:                        # block list — value is on the FOLLOWING lines
      - dashboard
      - pinned

`parse()` returns the same `{"tags": "dashboard, pinned"}` for either.
"""

from __future__ import annotations

import re

BLOCK_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---(\r?\n)", re.DOTALL)


def split(text: str) -> tuple[str | None, str, str]:
    """Return (frontmatter_block | None, body, eol).

    `eol` is the document's own line ending so callers can rewrite without
    silently converting CRLF to LF — that would break the repo's checksum gates.
    """
    eol = "\r\n" if "\r\n" in text[:2000] else "\n"
    m = BLOCK_RE.match(text)
    if not m:
        return None, text, eol
    return m.group(1), text[m.end():], eol


def parse(block: str | None) -> dict[str, str]:
    """Parse a frontmatter block into {key: value}, folding block lists into a
    comma-joined string. Returns {} for a missing block."""
    if not block:
        return {}
    fields: dict[str, str] = {}
    lines = block.splitlines()
    for i, line in enumerate(lines):
        if line[:1].isspace() or ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            # Normalize the inline flow list to the same shape as a block list,
            # so callers can treat `tags: [a, b]` and the `- a` form identically.
            val = ", ".join(p.strip() for p in val[1:-1].split(",") if p.strip())
        elif not val:
            items: list[str] = []
            for follow in lines[i + 1:]:
                if not follow[:1].isspace():
                    break
                stripped = follow.strip()
                if stripped.startswith("- "):
                    items.append(stripped[2:].strip())
            if items:
                val = ", ".join(items)
        fields[key.strip()] = val
    return fields


def has_field(block: str | None, key: str) -> bool:
    """True if `key` is declared at the top level of the block, value or not."""
    if not block:
        return False
    return any(
        line.split(":", 1)[0].strip() == key
        for line in block.splitlines()
        if ":" in line and not line[:1].isspace()
    )
