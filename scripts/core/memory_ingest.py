"""
Bravo V6.0 — Memory Ingest

Walks the project tree, chunks every markdown file, computes embeddings, and
upserts rows into `memory_chunks` (migration 014). Idempotent: unchanged
chunks (same content_hash) are skipped.

WHAT IT INDEXES
---------------
Defaults: brain/, memory/, knowledge/, APPS_CONTEXT/, skills/, agents/, docs/,
          .agents/workflows/

Excluded: memory/ARCHIVES/, .claude/, tmp/, node_modules/, .git/, __pycache__/

EMBEDDINGS
----------
Three providers supported (first available wins):
  1. OPENAI_API_KEY → text-embedding-3-small (1536-dim, matches migration 014)
  2. Local Ollama w/ nomic-embed-text (truncated/padded to 1536)
  3. Deterministic hash-stub (development fallback — do NOT use in prod)

CLI
---
    python scripts/core/memory_ingest.py --dry-run
    python scripts/core/memory_ingest.py --force-reembed
    python scripts/core/memory_ingest.py --only brain/STATE.md
    python scripts/core/memory_ingest.py --delete-missing   # prune removed files
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from memory_chunker import Chunk, chunk_file  # noqa: E402

DEFAULT_INCLUDE = [
    "brain",
    "memory",
    "knowledge",
    "APPS_CONTEXT",
    "skills",
    "agents",
    "docs",
    ".agents/workflows",
]
DEFAULT_EXCLUDE = [
    "memory/ARCHIVES",
    ".claude",
    "tmp",
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
]

EMBED_DIM = 1536


# ---- Env / DB (same pattern as event_bus.py) --------------------------------

def _load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env.agents"
    if not env_path.exists():
        return {}
    env: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _get_supabase(env: Optional[dict[str, str]] = None):
    env = env or _load_env()
    url = env.get("BRAVO_SUPABASE_URL") or env.get("SUPABASE_URL")
    key = env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("BRAVO_SUPABASE_URL/KEY missing in .env.agents")
    from supabase import create_client  # type: ignore
    return create_client(url, key)


# ---- Embedding providers ----------------------------------------------------

def _openai_embed(texts: list[str], env: dict[str, str]) -> Optional[list[list[float]]]:
    api_key = env.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        print("[memory_ingest] openai SDK not installed; skipping OpenAI provider",
              file=sys.stderr)
        return None
    client = OpenAI(api_key=api_key)
    out: list[list[float]] = []
    for i in range(0, len(texts), 64):
        batch = texts[i:i + 64]
        resp = client.embeddings.create(model="text-embedding-3-small", input=batch)
        out.extend([d.embedding for d in resp.data])
    return out


def _ollama_embed(texts: list[str], env: dict[str, str]) -> Optional[list[list[float]]]:
    host = env.get("OLLAMA_HOST") or "http://localhost:11434"
    try:
        import urllib.request
    except Exception:
        return None
    out: list[list[float]] = []
    try:
        for t in texts:
            body = json.dumps({"model": "nomic-embed-text", "prompt": t}).encode()
            req = urllib.request.Request(
                f"{host}/api/embeddings",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
                emb = data.get("embedding") or []
                out.append(_resize(emb, EMBED_DIM))
        return out
    except Exception as exc:
        print(f"[memory_ingest] Ollama unreachable ({exc}); skipping", file=sys.stderr)
        return None


def _hash_embed(texts: list[str]) -> list[list[float]]:
    """Deterministic fallback. Good enough for unit tests + local ingest smoke
    tests. NEVER rely on this in production — neighbor distances are meaningless."""
    import hashlib
    import struct
    out: list[list[float]] = []
    for t in texts:
        h = hashlib.sha256(t.encode("utf-8")).digest()
        # Repeat the 32-byte digest to fill EMBED_DIM floats, then normalize.
        floats: list[float] = []
        for i in range(EMBED_DIM):
            b = h[(i * 4) % (len(h) - 3): (i * 4) % (len(h) - 3) + 4]
            (v,) = struct.unpack("f", b)
            floats.append(v)
        # L2 normalize
        norm = sum(x * x for x in floats) ** 0.5 or 1.0
        out.append([x / norm for x in floats])
    return out


def _resize(v: list[float], dim: int) -> list[float]:
    if len(v) == dim:
        return v
    if len(v) > dim:
        return v[:dim]
    return v + [0.0] * (dim - len(v))


def embed_batch(texts: list[str], env: Optional[dict[str, str]] = None) -> list[list[float]]:
    env = env or _load_env()
    for provider in (_openai_embed, _ollama_embed):
        result = provider(texts, env)
        if result is not None and len(result) == len(texts):
            return result
    print("[memory_ingest] falling back to deterministic hash embeddings "
          "— DO NOT use this in production retrieval", file=sys.stderr)
    return _hash_embed(texts)


# ---- Ingest loop ------------------------------------------------------------

def _iter_markdown_files(root: Path, include: list[str], exclude: list[str]) -> Iterable[Path]:
    seen: set[Path] = set()
    for sub in include:
        sub_path = root / sub
        if not sub_path.exists():
            continue
        for p in sub_path.rglob("*.md"):
            rel = str(p.relative_to(root)).replace("\\", "/")
            if any(rel.startswith(x) for x in exclude):
                continue
            if p not in seen:
                seen.add(p)
                yield p


def _existing_hashes(client, file: str) -> dict[int, str]:
    res = (client.table("memory_chunks")
           .select("chunk_index, content_hash")
           .eq("source_file", file)
           .execute())
    return {r["chunk_index"]: r["content_hash"] for r in (res.data or [])}


def _upsert_chunk(client, c: Chunk, embedding: list[float]) -> None:
    row = {
        "source_file": c.source_file,
        "source_heading": c.source_heading,
        "chunk_index": c.chunk_index,
        "content": c.content,
        "content_hash": c.content_hash,
        "embedding": embedding,
        "tags": c.tags,
        "wiki_links": c.wiki_links,
        "token_estimate": c.token_estimate,
        "metadata": c.metadata,
    }
    # Upsert on (source_file, chunk_index) — migration 014 has the unique idx.
    client.table("memory_chunks").upsert(row, on_conflict="source_file,chunk_index").execute()


def _delete_file_chunks(client, file: str) -> int:
    res = client.table("memory_chunks").delete().eq("source_file", file).execute()
    return len(res.data or [])


def _delete_missing(client, seen_files: set[str]) -> int:
    if not seen_files:
        return 0
    res = client.table("memory_chunks").select("source_file").execute()
    db_files = {r["source_file"] for r in (res.data or [])}
    missing = db_files - seen_files
    count = 0
    for f in missing:
        count += _delete_file_chunks(client, f)
    return count


def ingest(
    *,
    root: Path = PROJECT_ROOT,
    include: list[str] = DEFAULT_INCLUDE,
    exclude: list[str] = DEFAULT_EXCLUDE,
    only: Optional[str] = None,
    force: bool = False,
    dry_run: bool = False,
    delete_missing: bool = False,
) -> dict[str, int]:
    """Full or targeted ingest. Returns stats."""
    env = _load_env()
    client = None if dry_run else _get_supabase(env)

    if only:
        files: list[Path] = [root / only]
        if not files[0].exists():
            raise FileNotFoundError(only)
    else:
        files = list(_iter_markdown_files(root, include, exclude))

    seen_files: set[str] = set()
    stats = {"files": 0, "chunks_total": 0, "chunks_upserted": 0,
             "chunks_skipped": 0, "files_deleted_from_index": 0}

    for p in files:
        stats["files"] += 1
        chunks = chunk_file(p, project_root=root)
        if not chunks:
            continue
        file_key = chunks[0].source_file
        seen_files.add(file_key)
        stats["chunks_total"] += len(chunks)

        if dry_run:
            continue

        existing = {} if force else _existing_hashes(client, file_key)
        to_embed: list[Chunk] = [c for c in chunks
                                 if existing.get(c.chunk_index) != c.content_hash]
        stats["chunks_skipped"] += len(chunks) - len(to_embed)

        if not to_embed:
            continue

        embeddings = embed_batch([c.content for c in to_embed], env=env)
        for c, e in zip(to_embed, embeddings):
            _upsert_chunk(client, c, _resize(e, EMBED_DIM))
            stats["chunks_upserted"] += 1

    if delete_missing and not dry_run and not only:
        stats["files_deleted_from_index"] = _delete_missing(client, seen_files)

    return stats


# ---- CLI --------------------------------------------------------------------

def _cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(PROJECT_ROOT))
    ap.add_argument("--include", nargs="+", default=DEFAULT_INCLUDE)
    ap.add_argument("--exclude", nargs="+", default=DEFAULT_EXCLUDE)
    ap.add_argument("--only", help="Ingest a single file path relative to root")
    ap.add_argument("--force-reembed", action="store_true",
                    help="Re-embed even if content_hash matches")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--delete-missing", action="store_true",
                    help="Prune rows whose source_file no longer exists")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    stats = ingest(
        root=Path(args.root),
        include=args.include,
        exclude=args.exclude,
        only=args.only,
        force=args.force_reembed,
        dry_run=args.dry_run,
        delete_missing=args.delete_missing,
    )
    stats["elapsed_seconds"] = round(time.time() - t0, 2)

    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        print("=" * 54)
        print(" MEMORY INGEST ")
        print("=" * 54)
        for k, v in stats.items():
            print(f"  {k:32s} {v}")
        print("=" * 54)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
