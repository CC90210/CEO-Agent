"""
Bravo V6.0 — Memory Chunker

Splits Markdown files into retrieval-sized chunks for the RAG index
(migration 014). Preserves provenance (nearest heading) and extracts
Obsidian wiki-links for graph-expansion retrieval.

USAGE
-----
    from memory_chunker import chunk_file, chunk_text

    chunks = chunk_file("brain/STATE.md")
    # -> list[Chunk] each with: content, heading, wiki_links, tags, hash

CLI::
    python scripts/memory_chunker.py brain/STATE.md
    python scripts/memory_chunker.py --stats brain/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator, Optional

MAX_TOKENS_PER_CHUNK = 800    # ~3200 chars — leaves headroom under pgvector context
MIN_CHUNK_CHARS = 80
OVERLAP_CHARS = 200           # last N chars of previous chunk prepended to next

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
_TAG_RE = re.compile(r"(?:^|\s)#([a-zA-Z0-9_\-/]+)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class Chunk:
    source_file: str
    chunk_index: int
    source_heading: Optional[str]
    content: str
    content_hash: str
    wiki_links: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    token_estimate: int = 0
    metadata: dict = field(default_factory=dict)


def _estimate_tokens(s: str) -> int:
    # Cheap approximation: 4 chars ≈ 1 token for English markdown.
    return max(1, len(s) // 4)


def _extract_wiki_links(s: str) -> list[str]:
    return [m.group(1).strip() for m in _WIKILINK_RE.finditer(s)]


def _extract_tags(s: str) -> list[str]:
    return sorted({m.group(1).strip() for m in _TAG_RE.finditer(s)})


def _parse_frontmatter(s: str) -> tuple[dict, str]:
    """Extract YAML-ish frontmatter + return (meta, body_without_frontmatter)."""
    m = _FRONTMATTER_RE.match(s)
    if not m:
        return {}, s
    raw = m.group(1)
    meta: dict = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip().strip('"').strip("'")
    body = s[m.end():]
    return meta, body


def _heading_for_position(text: str, position: int) -> Optional[str]:
    """Find the nearest H2/H3 heading at or before `position`."""
    last: Optional[str] = None
    for m in _HEADING_RE.finditer(text[:position]):
        level = len(m.group(1))
        if 2 <= level <= 3:
            last = m.group(2).strip()
    return last


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def chunk_text(
    source_file: str,
    text: str,
    *,
    max_tokens: int = MAX_TOKENS_PER_CHUNK,
    overlap_chars: int = OVERLAP_CHARS,
    extra_tags: Optional[list[str]] = None,
) -> list[Chunk]:
    """
    Chunk a markdown string. Strategy:
      1. Split on H2/H3 boundaries (primary).
      2. If a section exceeds max_tokens, sub-split by paragraph, preserving
         overlap between sub-chunks.
      3. Merge tiny sub-chunks (<MIN_CHUNK_CHARS) into the neighbor.

    Each chunk carries its nearest heading for provenance.
    """
    meta, body = _parse_frontmatter(text)
    top_tags = _extract_tags(body)
    for k in ("tags", "keywords"):
        v = meta.get(k)
        if v:
            top_tags += [t.strip().strip("[]") for t in v.split(",") if t.strip()]
    if extra_tags:
        top_tags += extra_tags
    top_tags = sorted({t for t in top_tags if t})

    # Primary split: H2/H3 boundaries.
    boundaries = [m.start() for m in _HEADING_RE.finditer(body) if 2 <= len(m.group(1)) <= 3]
    if not boundaries or boundaries[0] != 0:
        boundaries = [0] + boundaries
    boundaries.append(len(body))
    raw_sections: list[tuple[int, int]] = list(zip(boundaries, boundaries[1:]))

    chunks: list[Chunk] = []
    idx = 0
    for (a, b) in raw_sections:
        section = body[a:b].strip()
        if len(section) < MIN_CHUNK_CHARS:
            continue
        heading = _heading_for_position(body, a)
        if _estimate_tokens(section) <= max_tokens:
            chunks.append(_make_chunk(source_file, idx, heading, section, top_tags))
            idx += 1
            continue
        # Sub-split by paragraph.
        paras = [p for p in re.split(r"\n\s*\n", section) if p.strip()]
        buf = ""
        for p in paras:
            candidate = (buf + "\n\n" + p).strip() if buf else p
            if _estimate_tokens(candidate) > max_tokens and buf:
                chunks.append(_make_chunk(source_file, idx, heading, buf, top_tags))
                idx += 1
                tail = buf[-overlap_chars:] if overlap_chars > 0 else ""
                buf = (tail + "\n\n" + p).strip() if tail else p
            else:
                buf = candidate
        if buf and len(buf) >= MIN_CHUNK_CHARS:
            chunks.append(_make_chunk(source_file, idx, heading, buf, top_tags))
            idx += 1

    return chunks


def _make_chunk(source_file: str, idx: int, heading: Optional[str],
                content: str, base_tags: list[str]) -> Chunk:
    wl = _extract_wiki_links(content)
    tags = sorted({*base_tags, *_extract_tags(content)})
    return Chunk(
        source_file=source_file,
        chunk_index=idx,
        source_heading=heading,
        content=content,
        content_hash=_sha256(content),
        wiki_links=wl,
        tags=tags,
        token_estimate=_estimate_tokens(content),
    )


def chunk_file(path: str | Path, *, project_root: Optional[Path] = None,
               extra_tags: Optional[list[str]] = None) -> list[Chunk]:
    path = Path(path)
    project_root = project_root or Path.cwd()
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = str(path.resolve().relative_to(project_root.resolve())).replace("\\", "/")
    return chunk_text(rel, text, extra_tags=extra_tags)


def iter_markdown(root: Path, include: list[str], exclude: list[str]) -> Iterator[Path]:
    for sub in include:
        for p in root.joinpath(sub).rglob("*.md"):
            rel = str(p.relative_to(root)).replace("\\", "/")
            if any(rel.startswith(x) for x in exclude):
                continue
            yield p


def _cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="File or directory to chunk")
    ap.add_argument("--root", default=".", help="Project root (default cwd)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--stats", action="store_true", help="Print summary instead of chunks")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    target = Path(args.target)
    if not target.is_absolute():
        target = (root / target).resolve()

    all_chunks: list[Chunk] = []
    if target.is_file():
        all_chunks.extend(chunk_file(target, project_root=root))
    elif target.is_dir():
        for p in target.rglob("*.md"):
            all_chunks.extend(chunk_file(p, project_root=root))
    else:
        print(f"not a file or directory: {target}", file=sys.stderr)
        return 2

    if args.stats:
        total_tokens = sum(c.token_estimate for c in all_chunks)
        files = sorted({c.source_file for c in all_chunks})
        print(json.dumps({
            "files": len(files),
            "chunks": len(all_chunks),
            "estimated_tokens": total_tokens,
            "avg_chunk_tokens": total_tokens // max(1, len(all_chunks)),
            "example_files": files[:10],
        }, indent=2))
        return 0

    if args.json:
        print(json.dumps([asdict(c) for c in all_chunks], indent=2))
    else:
        for c in all_chunks:
            print(f"\n=== {c.source_file}#{c.chunk_index} [{c.source_heading}] "
                  f"tokens~{c.token_estimate} tags={c.tags} ===")
            print(c.content[:400] + ("..." if len(c.content) > 400 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
