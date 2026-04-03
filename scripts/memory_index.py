#!/usr/bin/env python3
"""
3-Layer Memory Index — Claude Code's Memory Architecture Pattern

Layer 1: INDEX (~150 chars per entry, always loaded) → memory/MEMORY_INDEX.md
Layer 2: TOPIC FILES (on-demand, loaded when relevant) → memory/*.md
Layer 3: ARCHIVES (grep-only, historical) → memory/ARCHIVES/*.md

The index is the only file loaded at boot. Everything else is read on-demand.
This minimizes token cost while keeping all knowledge accessible.

Usage:
  python scripts/memory_index.py build          Build/rebuild the index from all memory files
  python scripts/memory_index.py search <query> Search the index for relevant topics
  python scripts/memory_index.py stats          Show index statistics
  python scripts/memory_index.py --json         Machine-readable output
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEMORY_DIR = PROJECT_ROOT / "memory"
BRAIN_DIR = PROJECT_ROOT / "brain"
INDEX_FILE = MEMORY_DIR / "MEMORY_INDEX.md"

# Files to index (Layer 2 — topic files)
INDEXABLE_FILES = [
    ("ACTIVE_TASKS.md", "Current tasks, priorities, blocked items"),
    ("MISTAKES.md", "Past errors, root causes, prevention strategies"),
    ("PATTERNS.md", "Proven approaches, anti-patterns, validated workflows"),
    ("LONG_TERM.md", "High-confidence persistent facts (architecture, business, technical)"),
    ("DECISIONS.md", "Architectural and business decisions with rationale"),
    ("SELF_REFLECTIONS.md", "Failure analysis, lessons learned, reflexion entries"),
    ("SOP_LIBRARY.md", "Standard operating procedures with success rates"),
    ("SESSION_LOG.md", "Recent session activity (last 10 sessions)"),
]

# Brain files to index
BRAIN_FILES = [
    ("STATE.md", "Current operational state, confidence level, active systems"),
    ("AGENTS.md", "17 subagents, routing matrix, permissions, Codex integration"),
    ("CAPABILITIES.md", "180 skills, 30 workflows, 37 scripts, tool registry"),
    ("BRAIN_LOOP.md", "10-step reasoning protocol, multi-hypothesis, reflexion"),
    ("CEO_OPERATING_SYSTEM.md", "7 CEO domains, briefing protocol, revenue strategy"),
    ("OKRs.md", "Q2 2026 objectives and key results"),
    ("RISK_REGISTER.md", "Active business risks with mitigation plans"),
    ("APP_REGISTRY.md", "12 apps with local paths, GitHub repos, stacks"),
]


def extract_topics(filepath):
    """Extract topic headers and key facts from a memory file."""
    if not filepath.exists():
        return []

    content = filepath.read_text(encoding="utf-8")
    topics = []

    # Extract ### headers as topics
    for match in re.finditer(r"^###\s+(.+)$", content, re.MULTILINE):
        header = match.group(1).strip()
        # Get first 100 chars after the header as context
        start = match.end()
        snippet = content[start:start + 150].strip().split("\n")[0][:100]
        topics.append({
            "header": header,
            "snippet": snippet,
            "line": content[:start].count("\n") + 1,
        })

    # Extract table rows as facts (for LONG_TERM.md style)
    for match in re.finditer(r"^\|\s*(.+?)\s*\|\s*([\d.]+)\s*\|", content, re.MULTILINE):
        fact = match.group(1).strip()
        confidence = match.group(2).strip()
        if fact and not fact.startswith("---") and not fact.startswith("Fact"):
            topics.append({
                "header": fact[:80],
                "snippet": f"confidence={confidence}",
                "line": content[:match.start()].count("\n") + 1,
            })

    return topics


def build_index(output_json=False):
    """Build the 3-layer memory index."""
    index = {
        "generated": date.today().isoformat(),
        "layers": {
            "layer1_index": "memory/MEMORY_INDEX.md (always loaded, ~150 chars per pointer)",
            "layer2_topics": "memory/*.md (loaded on-demand when topic matches query)",
            "layer3_archives": "memory/ARCHIVES/*.md (grep-only, historical)",
        },
        "memory_files": {},
        "brain_files": {},
    }

    # Index memory files
    for fname, description in INDEXABLE_FILES:
        filepath = MEMORY_DIR / fname
        if not filepath.exists():
            continue
        lines = len(filepath.read_text(encoding="utf-8").splitlines())
        topics = extract_topics(filepath)
        index["memory_files"][fname] = {
            "description": description,
            "lines": lines,
            "topics": len(topics),
            "key_entries": [t["header"][:80] for t in topics[:5]],
        }

    # Index brain files
    for fname, description in BRAIN_FILES:
        filepath = BRAIN_DIR / fname
        if not filepath.exists():
            continue
        lines = len(filepath.read_text(encoding="utf-8").splitlines())
        index["brain_files"][fname] = {
            "description": description,
            "lines": lines,
        }

    # Index archives
    archive_files = list(MEMORY_DIR.glob("ARCHIVES/*.md"))
    index["archives"] = {
        "count": len(archive_files),
        "files": [f.name for f in sorted(archive_files)],
    }

    # Generate the index markdown
    md_lines = [
        "---",
        "tags: [memory, index]",
        "---",
        "# MEMORY INDEX -- 3-Layer Architecture",
        "",
        "> **Layer 1 (this file):** Pointers. Always loaded. ~150 chars each.",
        "> **Layer 2:** Topic files. Read on-demand: `Read memory/<file>.md`",
        "> **Layer 3:** Archives. Grep-only: `memory/ARCHIVES/*.md`",
        "",
        f"> Generated: {date.today()} | Files: {len(index['memory_files'])} memory + {len(index['brain_files'])} brain + {index['archives']['count']} archives",
        "",
        "## Memory Files (Layer 2 -- load when needed)",
        "",
    ]

    for fname, info in index["memory_files"].items():
        md_lines.append(f"- **{fname}** ({info['lines']}L) -- {info['description']}")
        if info["key_entries"]:
            for entry in info["key_entries"][:3]:
                md_lines.append(f"  - {entry[:100]}")

    md_lines.extend([
        "",
        "## Brain Files (Layer 2 -- load for complex tasks)",
        "",
    ])

    for fname, info in index["brain_files"].items():
        md_lines.append(f"- **{fname}** ({info['lines']}L) -- {info['description']}")

    md_lines.extend([
        "",
        "## Archives (Layer 3 -- grep only)",
        "",
    ])

    for af in index["archives"]["files"]:
        md_lines.append(f"- `ARCHIVES/{af}`")

    md_lines.append(f"\n*Index built: {date.today()}*")

    # Write the index
    INDEX_FILE.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    if output_json:
        print(json.dumps(index, indent=2))
    else:
        total_pointers = sum(
            len(info.get("key_entries", []))
            for info in index["memory_files"].values()
        ) + len(index["brain_files"]) + len(index["archives"]["files"])

        print(f"Memory Index Built -- {date.today()}")
        print("=" * 45)
        print(f"  Memory files indexed: {len(index['memory_files'])}")
        print(f"  Brain files indexed:  {len(index['brain_files'])}")
        print(f"  Archive files:        {index['archives']['count']}")
        print(f"  Total pointers:       {total_pointers}")
        print(f"  Index written to:     {INDEX_FILE}")

    return index


def search_index(query, output_json=False):
    """Search the index for relevant topics."""
    query_words = set(query.lower().split())
    results = []

    for fname, _ in INDEXABLE_FILES + [(f, d) for f, d in BRAIN_FILES]:
        filepath = MEMORY_DIR / fname if (MEMORY_DIR / fname).exists() else BRAIN_DIR / fname
        if not filepath.exists():
            continue

        topics = extract_topics(filepath)
        for topic in topics:
            title_words = set(topic["header"].lower().split())
            snippet_words = set(topic.get("snippet", "").lower().split())
            all_words = title_words | snippet_words

            overlap = query_words & all_words
            if overlap:
                score = len(overlap) / len(query_words)
                results.append({
                    "file": fname,
                    "topic": topic["header"],
                    "line": topic["line"],
                    "score": round(score, 2),
                    "snippet": topic.get("snippet", ""),
                })

    results.sort(key=lambda r: r["score"], reverse=True)

    if output_json:
        print(json.dumps(results[:10], indent=2))
    else:
        print(f"Search: '{query}' -- {len(results)} results")
        print("-" * 50)
        for r in results[:10]:
            print(f"  [{r['score']:.0%}] {r['file']}:{r['line']} -- {r['topic'][:70]}")

    return results[:10]


def show_stats(output_json=False):
    """Show index statistics."""
    total_memory = 0
    total_brain = 0

    stats = {"memory": {}, "brain": {}, "archives": 0}

    for fname, _ in INDEXABLE_FILES:
        fp = MEMORY_DIR / fname
        if fp.exists():
            lines = len(fp.read_text(encoding="utf-8").splitlines())
            stats["memory"][fname] = lines
            total_memory += lines

    for fname, _ in BRAIN_FILES:
        fp = BRAIN_DIR / fname
        if fp.exists():
            lines = len(fp.read_text(encoding="utf-8").splitlines())
            stats["brain"][fname] = lines
            total_brain += lines

    stats["archives"] = len(list(MEMORY_DIR.glob("ARCHIVES/*.md")))
    stats["total_lines"] = total_memory + total_brain
    stats["index_exists"] = INDEX_FILE.exists()

    if output_json:
        print(json.dumps(stats, indent=2))
    else:
        print(f"Memory Stats -- {date.today()}")
        print("=" * 45)
        print(f"  Memory files: {total_memory} lines across {len(stats['memory'])} files")
        print(f"  Brain files:  {total_brain} lines across {len(stats['brain'])} files")
        print(f"  Archives:     {stats['archives']} files")
        print(f"  Index:        {'exists' if stats['index_exists'] else 'NOT BUILT -- run: python scripts/memory_index.py build'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="3-Layer Memory Index")
    parser.add_argument("command", nargs="?", default="stats", choices=["build", "search", "stats"])
    parser.add_argument("query", nargs="*", help="Search query (for search command)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.command == "build":
        build_index(output_json=args.json)
    elif args.command == "search":
        query = " ".join(args.query) if args.query else ""
        if not query:
            print("Usage: python scripts/memory_index.py search <query>")
            sys.exit(1)
        search_index(query, output_json=args.json)
    else:
        show_stats(output_json=args.json)
