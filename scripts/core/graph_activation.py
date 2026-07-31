"""graph_activation.py — spreading activation over the Obsidian wiki-link graph.

The retrieval upgrade (2026-07-10, CC directive): memory_retriever's hybrid
search (FTS5 + vectors) finds notes that MATCH a query. This module makes
retrieval ASSOCIATIVE — the way activation spreads through a neural network:

    query → matching notes light up (seeds)
          → activation flows along [[wiki-links]] to neighbors (damped)
          → related-but-unmatched notes surface; matched notes that are
            also well-connected rank higher
          → recency modulates everything (old un-touched notes dim)

This is why the vault is wiki-linked: the links ARE the associations. Until
now only humans followed them; now the agent's recall does too.

Design:
  - Adjacency built from `[[target]]` / `[[target|alias]]` across the same
    source scopes the retriever indexes. Forward links propagate at DAMP_FWD,
    backlinks at DAMP_BACK (weaker — being cited is a hint, not a claim).
  - Activation for a neighbor = sum over seeds of seed_weight * damp, then
    modulated by recency decay e^(-age_days/HALF_LIFE), floored — a stale
    note can surface, but it must earn it.
  - Cache at state/graph_adjacency.json, rebuilt when stale (>6h) or --rebuild.

CLI:
  python scripts/core/graph_activation.py build            # (re)build adjacency
  python scripts/core/graph_activation.py status
  python scripts/core/graph_activation.py neighbors <rel/path.md>
  python scripts/core/graph_activation.py query "<text>"   # end-to-end demo

Integration: memory_retriever.query() calls boost_hits() behind the
EMPIRE_GRAPH_BOOST env gate (default on), with hard try/except fallback —
graph failures can never degrade baseline retrieval.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = PROJECT_ROOT / "state" / "graph_adjacency.json"
CACHE_MAX_AGE_SEC = 6 * 3600

# Activation parameters — tuned for "surface 1-3 associative extras", not
# "flood the context". Damping halves per hop; one hop only (2-hop spreads
# too thin and costs too much context).
DAMP_FWD = 0.50    # seed --[[links to]]--> neighbor
DAMP_BACK = 0.35   # neighbor --[[links to]]--> seed (backlink)
RECENCY_HALF_LIFE_DAYS = 180.0
RECENCY_FLOOR = 0.35
MAX_ASSOCIATIVE_EXTRAS = 3   # cap on new (non-matching) notes injected
GRAPH_WEIGHT = 0.6           # graph term weight vs base retrieval score

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _walk_sources():
    """Same source universe the retriever indexes — reuse its walker so the
    graph and the index can never disagree about scope. The retriever yields
    (kind, path); we derive the PROJECT_ROOT-relative path (the retriever's
    `source` field uses the same form, so hit['source'] keys match ours)."""
    sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "core"))
    from memory_retriever import _walk_sources as walk  # type: ignore
    for _kind, path in walk():
        yield str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"), path


def _resolve_targets(raw_targets: set[str], files: dict[str, Path]) -> dict[str, str]:
    """Map raw [[target]] strings to indexed rel-paths. Vault-style resolution:
    exact rel (± .md), then unique basename match. Unresolvable → dropped."""
    by_base: dict[str, list[str]] = {}
    for rel in files:
        base = Path(rel).stem.lower()
        by_base.setdefault(base, []).append(rel)
    out: dict[str, str] = {}
    for t in raw_targets:
        norm = t.strip().replace("\\", "/")
        for cand in (norm, norm + ".md"):
            if cand in files:
                out[t] = cand
                break
        else:
            hits = by_base.get(Path(norm).stem.lower(), [])
            if len(hits) == 1:
                out[t] = hits[0]
    return out


def build(force: bool = False) -> dict:
    """(Re)build the adjacency cache. Returns the graph dict."""
    if not force and CACHE_PATH.exists():
        age = time.time() - CACHE_PATH.stat().st_mtime
        if age < CACHE_MAX_AGE_SEC:
            try:
                return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass

    files: dict[str, Path] = {}
    raw_links: dict[str, set[str]] = {}
    all_targets: set[str] = set()
    for rel, path in _walk_sources():
        rel = rel.replace("\\", "/")
        files[rel] = path
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        targets = set(WIKILINK_RE.findall(text))
        if targets:
            raw_links[rel] = targets
            all_targets |= targets

    resolved = _resolve_targets(all_targets, files)
    fwd: dict[str, list[str]] = {}
    back: dict[str, list[str]] = {}
    for src, targets in raw_links.items():
        for t in targets:
            dst = resolved.get(t)
            if not dst or dst == src:
                continue
            fwd.setdefault(src, []).append(dst)
            back.setdefault(dst, []).append(src)
    # de-dup
    fwd = {k: sorted(set(v)) for k, v in fwd.items()}
    back = {k: sorted(set(v)) for k, v in back.items()}

    mtimes = {}
    for rel, path in files.items():
        try:
            mtimes[rel] = path.stat().st_mtime
        except OSError:
            mtimes[rel] = 0.0

    graph = {
        "built_at": time.time(),
        "nodes": len(files),
        "edge_count": sum(len(v) for v in fwd.values()),
        "fwd": fwd,
        "back": back,
        "mtimes": mtimes,
    }
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(graph), encoding="utf-8")
    return graph


def _recency(graph: dict, rel: str) -> float:
    mt = graph.get("mtimes", {}).get(rel)
    if not mt:
        return RECENCY_FLOOR
    age_days = max(0.0, (time.time() - mt) / 86400.0)
    return max(RECENCY_FLOOR, math.exp(-age_days / RECENCY_HALF_LIFE_DAYS))


def _first_heading_or_desc(path: Path) -> str:
    """Cheap snippet for an associative extra: frontmatter description if
    present, else the first heading/line of body."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return ""
    m = re.search(r"(?m)^description:\s*(.+)$", text)
    if m:
        return m.group(1).strip().strip('"')[:220]
    body = re.sub(r"(?s)^---.*?---\s*", "", text)
    for line in body.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:220]
    return ""


def boost_hits(hits: list[dict], limit: int = 5) -> list[dict]:
    """Spread activation from retrieval hits through the wiki-link graph.

    In-place-safe: returns a new ranked list. Matched notes gain a graph term
    (connectedness matters); up to MAX_ASSOCIATIVE_EXTRAS unmatched neighbors
    are appended as associative results tagged kind='associative'."""
    if not hits:
        return hits
    graph = build(force=False)
    fwd, back = graph.get("fwd", {}), graph.get("back", {})

    # Normalize seed weights to [0,1] by rank (scores across modes aren't comparable).
    seeds: dict[str, float] = {}
    for rank, h in enumerate(hits):
        rel = str(h.get("source", "")).replace("\\", "/")
        if rel:
            seeds[rel] = max(seeds.get(rel, 0.0), 1.0 / (1 + rank))

    activation: dict[str, float] = {}
    for rel, w in seeds.items():
        for nb in fwd.get(rel, []):
            activation[nb] = activation.get(nb, 0.0) + w * DAMP_FWD
        for nb in back.get(rel, []):
            activation[nb] = activation.get(nb, 0.0) + w * DAMP_BACK

    # Graph term for matched hits (their own activation from OTHER seeds).
    out = []
    for rank, h in enumerate(hits):
        h = dict(h)
        rel = str(h.get("source", "")).replace("\\", "/")
        g = activation.get(rel, 0.0) * _recency(graph, rel)
        base = 1.0 / (1 + rank)
        h["graph_score"] = round(g, 4)
        h["assoc_score"] = round(base + GRAPH_WEIGHT * g, 4)
        out.append(h)

    # Associative extras — activated neighbors that did NOT match the query.
    extras = []
    # V7 fix (Codex P3): rank on the DECAYED score, not raw activation. The old
    # loop sorted by raw activation and `break`-ed on the decayed threshold, so
    # one stale high-backlink note could hide fresher neighbors with better
    # final scores behind the break.
    decayed = sorted(
        ((rel, act * _recency(graph, rel)) for rel, act in activation.items()
         if rel not in seeds),
        key=lambda kv: (-kv[1], kv[0]),
    )
    for rel, score in decayed:
        if score < 0.15:  # not activated enough to spend context on
            break
        path = PROJECT_ROOT / rel
        snippet = _first_heading_or_desc(path)
        if not snippet:
            continue
        extras.append({
            "source": rel, "line_start": 1, "kind": "associative",
            "snippet": snippet,
            # V7.3.3+2 (Codex finding): extras must carry the standard hit
            # fields — the retriever's human-output path prints hit['ref'] /
            # hit['heading'] and crashed on any associative extra without them.
            "ref": f"{rel}:1",
            "heading": "",
            "line_range": "1-1",
            "chunk_idx": -1,
            "graph_score": round(score, 4),
            "assoc_score": round(GRAPH_WEIGHT * score, 4),
            "why": f"linked from {sum(1 for s in seeds if rel in fwd.get(s, []) or rel in back.get(s, []))} matched note(s)",
        })
        if len(extras) >= MAX_ASSOCIATIVE_EXTRAS:
            break

    merged = sorted(out, key=lambda h: -h["assoc_score"]) + extras
    return merged[: limit + len(extras)]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Spreading activation over the vault's wiki-link graph")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build").add_argument("--force", action="store_true")
    sub.add_parser("status")
    nb = sub.add_parser("neighbors"); nb.add_argument("rel")
    q = sub.add_parser("query"); q.add_argument("text"); q.add_argument("--limit", type=int, default=5)
    args = p.parse_args(argv)

    if args.cmd == "build":
        g = build(force=getattr(args, "force", False))
        print(json.dumps({"nodes": g["nodes"], "edges": g["edge_count"],
                          "cache": str(CACHE_PATH)}, indent=2))
        return 0
    if args.cmd == "status":
        if not CACHE_PATH.exists():
            print(json.dumps({"built": False}))
            return 1
        g = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        print(json.dumps({"built": True, "nodes": g["nodes"], "edges": g["edge_count"],
                          "age_min": round((time.time() - g["built_at"]) / 60, 1)}, indent=2))
        return 0
    if args.cmd == "neighbors":
        g = build()
        rel = args.rel.replace("\\", "/")
        print(json.dumps({"fwd": g["fwd"].get(rel, []), "back": g["back"].get(rel, [])}, indent=2))
        return 0
    if args.cmd == "query":
        sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "core"))
        import memory_retriever  # type: ignore
        base = memory_retriever.query(args.text, limit=args.limit)
        boosted = boost_hits(base, limit=args.limit)
        for h in boosted:
            tag = "ASSOC" if h.get("kind") == "associative" else "match"
            print(f"[{tag}] ({h.get('assoc_score', h.get('score', 0))}) {h['source']}:{h.get('line_start', 1)}")
            print(f"        {str(h.get('snippet', ''))[:140]}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
