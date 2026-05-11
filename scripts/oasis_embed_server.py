"""OASIS Town V6 Apex Phase 3 — embedding + retrieval bridge for the agent sim.

A tiny FastAPI daemon that exposes Bravo's existing FTS5 + LanceDB retrieval
engine (scripts/memory_retriever.py) to the OASIS Town Convex backend over
loopback. Bound to 127.0.0.1 only — no external surface, no auth needed.

Endpoints:
  GET  /health           → liveness probe; returns model name + index size
  POST /embed            → batch-embed texts using fastembed MiniLM-L6-v2
                           body: {"texts": ["str", ...]}
                           returns: {"embeddings": [[f32; 384], ...]}
  POST /query            → semantic+lexical hybrid retrieval (RRF k=60)
                           body: {"question": "...", "limit": 5, "kind": "memory"|"skill"|"brain"|null}
                           returns: {"hits": [{snippet, source, score, line_start, line_end, kind}]}

Why a separate daemon (vs Convex's HTTP action calling memory_retriever directly):
  Convex Cloud runs in a serverless context — even anonymous-local-convex doesn't
  have Python in-process. We need a long-lived Python service that holds the
  fastembed ONNX model in memory + the SQLite + LanceDB handles. ~50ms first
  call (model load), <10ms steady-state per /embed call.

Run:
  python scripts/oasis_embed_server.py             # default 127.0.0.1:8767
  python scripts/oasis_embed_server.py --port 8800

PM2 (production):
  pm2 start scripts/oasis_embed_server.py --name oasis-embed --interpreter python
  pm2 save
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Import here so a missing-dep error is clear if fastapi/uvicorn aren't installed.
try:
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except ImportError as e:
    sys.stderr.write(f"[oasis_embed_server] missing dep: {e}\n")
    sys.stderr.write("  Run: pip install fastapi uvicorn pydantic\n")
    sys.exit(1)

# Lazy import — memory_retriever loads fastembed which downloads the model on
# first run. We do this here (module load) so the daemon's first request is
# fast, not the 30-second cold-start.
import memory_retriever as mr  # noqa: E402


app = FastAPI(
    title="OASIS Embed Server",
    description="Local-only retrieval bridge for OASIS Town's agent memory layer.",
    version="0.1.0",
)


class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, description="Texts to embed in one batch")


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    dim: int
    count: int


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    limit: int = Field(default=5, ge=1, le=25)
    kind: Optional[str] = Field(default=None, description="memory|skill|brain|archive")
    mode: str = Field(default="hybrid", description="hybrid|lexical|semantic")


class QueryHit(BaseModel):
    source: str
    heading: str
    snippet: str
    score: float
    line_start: int
    line_end: int
    kind: str


class QueryResponse(BaseModel):
    hits: list[QueryHit]
    question: str
    mode: str


@app.get("/health")
def health() -> dict:
    """Liveness probe. Reports the model name + index file stats so the
    Convex side knows what it's pointed at."""
    index_path = PROJECT_ROOT / "state" / "memory_index.db"
    lance_path = PROJECT_ROOT / "state" / "memory_index.lance"
    return {
        "ok": True,
        "service": "oasis-embed",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2 (fastembed ONNX)",
        "embedding_dim": 384,
        "index_db_exists": index_path.exists(),
        "index_db_size_kb": (index_path.stat().st_size // 1024) if index_path.exists() else 0,
        "lance_table_exists": lance_path.exists(),
    }


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest) -> EmbedResponse:
    """Batch-embed texts using the same fastembed model the retriever uses.

    Returns 384-dim float vectors. Reuses memory_retriever._embed_texts so
    there's exactly one fastembed instance in the process — no duplicate
    model loads.
    """
    try:
        vectors = mr._embed_texts(req.texts)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"embed failed: {exc}") from exc
    if not vectors or not vectors[0]:
        raise HTTPException(status_code=500, detail="empty embeddings returned")
    return EmbedResponse(
        embeddings=vectors,
        dim=len(vectors[0]),
        count=len(vectors),
    )


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    """Hybrid (FTS5 + LanceDB) retrieval over Bravo's indexed memory.

    Passes through to memory_retriever.query directly. Returns ranked snippets
    with file:line references — the same payload `python scripts/memory_retriever.py
    query "..."` returns at the CLI.
    """
    try:
        hits = mr.query(req.question, limit=req.limit, kind=req.kind, mode=req.mode)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"query failed: {exc}") from exc

    out: list[QueryHit] = []
    for h in hits:
        out.append(
            QueryHit(
                source=h.get("source") or "",
                heading=h.get("heading") or "",
                snippet=h.get("snippet") or h.get("body") or "",
                score=float(h.get("score") or h.get("lex_score") or h.get("sem_score") or 0.0),
                line_start=int(h.get("line_start") or 0),
                line_end=int(h.get("line_end") or 0),
                kind=h.get("kind") or "",
            )
        )
    return QueryResponse(hits=out, question=req.question, mode=req.mode)


def main() -> int:
    p = argparse.ArgumentParser(description="OASIS Town embedding + retrieval bridge")
    p.add_argument("--host", default="127.0.0.1", help="loopback by design — do NOT bind 0.0.0.0")
    p.add_argument("--port", type=int, default=8767)
    p.add_argument("--reload", action="store_true", help="dev mode")
    args = p.parse_args()

    if args.host != "127.0.0.1":
        sys.stderr.write(
            "[oasis_embed_server] WARNING: binding to non-loopback host. "
            "This service has no auth — only expose to localhost.\n"
        )

    print(
        f"[oasis_embed_server] starting on http://{args.host}:{args.port}\n"
        f"  endpoints: GET /health · POST /embed · POST /query\n"
        f"  index db:  {PROJECT_ROOT / 'state' / 'memory_index.db'}\n",
        flush=True,
    )
    uvicorn.run(
        "scripts.oasis_embed_server:app" if args.reload else app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
