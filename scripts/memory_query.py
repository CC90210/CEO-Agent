"""
Bravo V6.0 — Memory Query (retrieval)

Queries the `memory_chunks` table via the `search_memory_chunks` RPC
(migration 014). Used by the agent harness to assemble context on-demand
instead of loading whole markdown files at boot.

USAGE
-----
From Python::
    from memory_query import retrieve, format_context

    chunks = retrieve(
        task="Alejandro retainer status",
        k=8,
        always_tags=["critical-links"],
    )
    context_block = format_context(chunks)
    # drop context_block into the next prompt

CLI::
    python scripts/memory_query.py --task "alejandro retainer" --k 6
    python scripts/memory_query.py --task "booking link" --format markdown
    python scripts/memory_query.py --task "send gateway" --always-file brain/STATE.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from memory_ingest import _get_supabase, _load_env, embed_batch  # noqa: E402


def retrieve(
    task: str,
    *,
    k: int = 8,
    always_tags: Optional[list[str]] = None,
    exclude_files: Optional[list[str]] = None,
    db: Any = None,
    env: Optional[dict[str, str]] = None,
) -> list[dict[str, Any]]:
    """Return top-k chunks ranked by hybrid score."""
    env = env or _load_env()
    client = db or _get_supabase(env)
    embedding = embed_batch([task], env=env)[0]
    rpc = client.rpc(
        "search_memory_chunks",
        {
            "p_embedding": embedding,
            "p_query_text": task,
            "p_k": k,
            "p_always_tags": always_tags or [],
            "p_exclude_files": exclude_files or [],
        },
    ).execute()
    return rpc.data or []


def format_context(
    chunks: list[dict[str, Any]],
    *,
    max_tokens: int = 3000,
    always_include_files: Optional[list[str]] = None,
    project_root: Path = PROJECT_ROOT,
) -> str:
    """Render retrieved chunks as a markdown context block, budgeted.
    Appends always_include_files verbatim at the end (up to budget)."""
    lines: list[str] = ["# Retrieved context (V6.0 RAG)\n"]
    budget = max_tokens
    for ch in chunks:
        source = ch.get("source_file")
        heading = ch.get("source_heading") or "(no heading)"
        content = ch.get("content") or ""
        score = ch.get("total_score", 0)
        est_tokens = max(1, len(content) // 4)
        if est_tokens > budget:
            break
        budget -= est_tokens
        lines.append(f"\n### from {source} § {heading}  _(score {score:.3f})_\n")
        lines.append(content)
        lines.append("")

    for f in always_include_files or []:
        path = project_root / f
        if not path.exists():
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        est_tokens = max(1, len(body) // 4)
        if est_tokens > budget:
            body = body[: budget * 4]
        lines.append(f"\n### always-included: {f}\n")
        lines.append(body)
        budget = max(0, budget - est_tokens)
        if budget <= 0:
            break
    return "\n".join(lines)


def _cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, help="The query / task description")
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--always-tags", nargs="+", default=["critical-links"])
    ap.add_argument("--exclude-files", nargs="+", default=[])
    ap.add_argument("--always-file", nargs="+", default=[])
    ap.add_argument("--max-tokens", type=int, default=3000)
    ap.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = ap.parse_args()

    chunks = retrieve(
        task=args.task,
        k=args.k,
        always_tags=args.always_tags,
        exclude_files=args.exclude_files,
    )

    if args.format == "json":
        print(json.dumps(chunks, indent=2, default=str))
        return 0

    block = format_context(
        chunks,
        max_tokens=args.max_tokens,
        always_include_files=args.always_file,
    )
    print(block)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
