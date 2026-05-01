"""
GNN Skill Router -- graph-based next-skill prediction over the Obsidian vault.

USAGE FROM PYTHON
-----------------
    from gnn_skill_router import export_graph, predict_skills

    export_graph()
    top_skills = predict_skills("Need a safe outbound email review loop")

CLI
---
    python scripts/gnn_skill_router.py export-graph --json
    python scripts/gnn_skill_router.py train --epochs 50 --lr 0.001
    python scripts/gnn_skill_router.py predict --task "debug Supabase webhooks"
    python scripts/gnn_skill_router.py evaluate --json

DESIGN
------
1. Graph source. Prefer existing vault structure from `memory_index.py`;
   otherwise scan `brain/`, `memory/`, and `skills/` markdown files directly.
2. Nodes. Brain notes, memory notes, and skill playbooks all become nodes;
   only skill nodes are returned at inference time.
3. Self-supervision. Train on masked skill neighbors: given a source node,
   rank the linked skill node among all skills.
4. Graceful degradation. Missing `torch`, `torch_geometric`, or `fastembed`
   never breaks `--help`; the command path prints install guidance and exits 0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = PROJECT_ROOT / "tmp"
GRAPH_PATH = TMP_DIR / "skill_graph.pt"
MODEL_PATH = TMP_DIR / "gnn_skill_router.pt"
WIKI_LINK = re.compile(r"\[\[([^\]]+)\]\]")


def load_env() -> dict[str, str]:
    env_file = PROJECT_ROOT / ".env.agents"
    try:
        from dotenv import dotenv_values, load_dotenv  # type: ignore
    except ImportError:
        return {}
    load_dotenv(env_file)
    raw = dotenv_values(env_file)
    return {k: str(v) for k, v in raw.items() if v is not None}


def _require_graph_stack(action: str):
    try:
        import torch  # type: ignore
        import torch.nn.functional as F  # type: ignore
        from torch import nn  # type: ignore
        from torch_geometric.nn import GCNConv  # type: ignore
    except ImportError:
        print(
            f"[gnn_skill_router] '{action}' needs torch + torch_geometric.\n"
            "Install:\n"
            "  pip install torch --index-url https://download.pytorch.org/whl/cpu\n"
            "  pip install torch-geometric",
        )
        sys.exit(0)
    return torch, nn, F, GCNConv


def _try_fastembed():
    try:
        from fastembed import TextEmbedding  # type: ignore[import-untyped]
        return TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    except Exception:
        return None


def _markdown_files() -> list[Path]:
    files: set[Path] = set()
    try:
        import memory_index  # type: ignore

        for name, _ in getattr(memory_index, "INDEXABLE_FILES", []):
            files.add(Path(memory_index.MEMORY_DIR) / name)
        for name, _ in getattr(memory_index, "BRAIN_FILES", []):
            files.add(Path(memory_index.BRAIN_DIR) / name)
    except Exception:
        pass
    files.update(PROJECT_ROOT.glob("brain/**/*.md"))
    files.update(PROJECT_ROOT.glob("memory/**/*.md"))
    files.update(PROJECT_ROOT.glob("skills/**/SKILL.md"))
    return sorted(fp for fp in files if fp.exists())


def _aliases(path: Path) -> list[str]:
    rel = path.relative_to(PROJECT_ROOT).as_posix()
    stem = rel[:-3] if rel.endswith(".md") else rel
    out = {stem, path.stem, rel}
    if rel.startswith("skills/") and rel.endswith("/SKILL.md"):
        out.add(rel[:-3])
    return sorted(out)


def _embed(texts: list[str]) -> list[list[float]]:
    model = _try_fastembed()
    if model is not None:
        return [list(vec) for vec in model.embed(texts)]
    out: list[list[float]] = []
    for text in texts:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        raw = list(digest) * 24
        out.append([(b / 127.5) - 1.0 for b in raw[:384]])
    return out


def _build_graph_dict() -> dict[str, Any]:
    docs = _markdown_files()
    nodes: list[dict[str, Any]] = []
    alias_map: dict[str, int] = {}
    for idx, path in enumerate(docs):
        text = path.read_text(encoding="utf-8", errors="ignore")
        title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), path.stem)
        node = {
            "path": path.relative_to(PROJECT_ROOT).as_posix(),
            "title": title,
            "text": text[:4000],
            "is_skill": "/SKILL.md" in path.as_posix(),
        }
        nodes.append(node)
        for alias in _aliases(path):
            alias_map.setdefault(alias.lower(), idx)
    edges: set[tuple[int, int]] = set()
    for idx, node in enumerate(nodes):
        for match in WIKI_LINK.findall(node["text"]):
            target = match.split("|", 1)[0].split("#", 1)[0].strip().lower()
            target_idx = alias_map.get(target)
            if target_idx is not None and target_idx != idx:
                edges.add((idx, target_idx))
                edges.add((target_idx, idx))
    if not edges:
        for i in range(max(0, len(nodes) - 1)):
            edges.add((i, i + 1))
            edges.add((i + 1, i))
    texts = [f"{n['title']}\n{n['text'][:1500]}" for n in nodes]
    return {"nodes": nodes, "edges": sorted(edges), "features": _embed(texts)}


def export_graph() -> dict[str, Any]:
    """Build and persist the graph payload to tmp/skill_graph.pt."""
    load_env()
    torch, _, _, _ = _require_graph_stack("export-graph")
    graph = _build_graph_dict()
    x = torch.tensor(graph["features"], dtype=torch.float32)
    edge_index = torch.tensor(graph["edges"], dtype=torch.long).t().contiguous()
    skill_mask = torch.tensor([n["is_skill"] for n in graph["nodes"]], dtype=torch.bool)
    payload = {"x": x, "edge_index": edge_index, "skill_mask": skill_mask, "nodes": graph["nodes"]}
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(payload, GRAPH_PATH)
    return {"ok": True, "graph_path": str(GRAPH_PATH), "nodes": len(graph["nodes"]), "edges": len(graph["edges"])}


def _load_graph():
    torch, nn, F, GCNConv = _require_graph_stack("graph-load")
    if not GRAPH_PATH.exists():
        export_graph()
    return torch, nn, F, GCNConv, torch.load(GRAPH_PATH, map_location="cpu")


def _skill_pairs(data: dict[str, Any]) -> tuple[list[int], list[int], list[int]]:
    skill_nodes = [i for i, flag in enumerate(data["skill_mask"].tolist()) if flag]
    skill_set = set(skill_nodes)
    skill_to_idx = {node: i for i, node in enumerate(skill_nodes)}
    sources: list[int] = []
    targets: list[int] = []
    for src, dst in data["edge_index"].t().tolist():
        if dst in skill_set:
            sources.append(src)
            targets.append(skill_to_idx[dst])
    return sources, targets, skill_nodes


def train_model(epochs: int = 50, lr: float = 0.001) -> dict[str, Any]:
    """Train the 2-layer GCN on masked-neighbor skill prediction."""
    load_env()
    torch, nn, F, GCNConv, data = _load_graph()

    class SkillGNN(nn.Module):
        def __init__(self, input_dim: int, hidden: int = 128) -> None:
            super().__init__()
            self.query_proj = nn.Linear(input_dim, hidden)
            self.conv1 = GCNConv(hidden, hidden)
            self.conv2 = GCNConv(hidden, hidden)

        def forward(self, x, edge_index):
            h = F.relu(self.query_proj(x))
            h = F.relu(self.conv1(h, edge_index))
            h = self.conv2(h, edge_index)
            return F.normalize(h, dim=-1)

        def encode_query(self, q):
            return F.normalize(self.query_proj(q), dim=-1)

    sources, targets, skill_nodes = _skill_pairs(data)
    if not sources:
        raise RuntimeError("No skill-linked edges found in the vault graph")
    pairs = list(zip(sources, targets))
    random.Random(42).shuffle(pairs)
    model = SkillGNN(data["x"].shape[1])
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    for _ in range(max(1, epochs)):
        model.train()
        z = model(data["x"], data["edge_index"])
        src = torch.tensor([p[0] for p in pairs], dtype=torch.long)
        tgt = torch.tensor([p[1] for p in pairs], dtype=torch.long)
        scores = z[src] @ z[torch.tensor(skill_nodes, dtype=torch.long)].T
        loss = F.cross_entropy(scores, tgt)
        opt.zero_grad()
        loss.backward()
        opt.step()
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "input_dim": int(data["x"].shape[1]), "nodes": data["nodes"]}, MODEL_PATH)
    return {"ok": True, "model_path": str(MODEL_PATH), "epochs": epochs, "lr": lr, "pairs": len(pairs)}


def predict_skills(task: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Embed a task string and return the top-k skill matches."""
    load_env()
    torch, nn, F, GCNConv, data = _load_graph()

    class SkillGNN(nn.Module):
        def __init__(self, input_dim: int, hidden: int = 128) -> None:
            super().__init__()
            self.query_proj = nn.Linear(input_dim, hidden)
            self.conv1 = GCNConv(hidden, hidden)
            self.conv2 = GCNConv(hidden, hidden)

        def forward(self, x, edge_index):
            h = F.relu(self.query_proj(x))
            h = F.relu(self.conv1(h, edge_index))
            h = self.conv2(h, edge_index)
            return F.normalize(h, dim=-1)

        def encode_query(self, q):
            return F.normalize(self.query_proj(q), dim=-1)

    model = SkillGNN(data["x"].shape[1])
    trained = False
    if MODEL_PATH.exists():
        state = torch.load(MODEL_PATH, map_location="cpu")
        model.load_state_dict(state["state_dict"])
        trained = True
    skill_nodes = [i for i, flag in enumerate(data["skill_mask"].tolist()) if flag]
    q = torch.tensor(_embed([task])[0], dtype=torch.float32).unsqueeze(0)
    if trained:
        z = model(data["x"], data["edge_index"])
        qz = model.encode_query(q).squeeze(0)
        scores = (z[torch.tensor(skill_nodes)] @ qz).tolist()
    else:
        scores = (data["x"][torch.tensor(skill_nodes)] @ q.squeeze(0)).tolist()
    ranked = sorted(zip(skill_nodes, scores), key=lambda item: item[1], reverse=True)[:top_k]
    return [{"skill": data["nodes"][idx]["title"], "path": data["nodes"][idx]["path"], "score": round(float(score), 4), "trained": trained} for idx, score in ranked]


def evaluate_model() -> dict[str, Any]:
    """80/20 split evaluation for top-1 and top-5 masked-neighbor accuracy."""
    load_env()
    torch, nn, F, GCNConv, data = _load_graph()

    class SkillGNN(nn.Module):
        def __init__(self, input_dim: int, hidden: int = 128) -> None:
            super().__init__()
            self.query_proj = nn.Linear(input_dim, hidden)
            self.conv1 = GCNConv(hidden, hidden)
            self.conv2 = GCNConv(hidden, hidden)

        def forward(self, x, edge_index):
            h = F.relu(self.query_proj(x))
            h = F.relu(self.conv1(h, edge_index))
            h = self.conv2(h, edge_index)
            return F.normalize(h, dim=-1)

    sources, targets, skill_nodes = _skill_pairs(data)
    pairs = list(zip(sources, targets))
    random.Random(42).shuffle(pairs)
    split = max(1, int(len(pairs) * 0.8))
    train_pairs, test_pairs = pairs[:split], pairs[split:] or pairs[:1]
    model = SkillGNN(data["x"].shape[1])
    if MODEL_PATH.exists():
        model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu")["state_dict"])
    else:
        opt = torch.optim.Adam(model.parameters(), lr=0.001)
        for _ in range(20):
            z = model(data["x"], data["edge_index"])
            src = torch.tensor([p[0] for p in train_pairs], dtype=torch.long)
            tgt = torch.tensor([p[1] for p in train_pairs], dtype=torch.long)
            scores = z[src] @ z[torch.tensor(skill_nodes, dtype=torch.long)].T
            loss = F.cross_entropy(scores, tgt)
            opt.zero_grad()
            loss.backward()
            opt.step()
    model.eval()
    z = model(data["x"], data["edge_index"])
    top1 = 0
    top5 = 0
    skill_tensor = torch.tensor(skill_nodes, dtype=torch.long)
    for src_idx, target_idx in test_pairs:
        scores = z[src_idx] @ z[skill_tensor].T
        ranked = torch.argsort(scores, descending=True).tolist()[:5]
        top1 += int(ranked[0] == target_idx)
        top5 += int(target_idx in ranked)
    total = max(1, len(test_pairs))
    return {"top1_accuracy": round(top1 / total, 4), "top5_accuracy": round(top5 / total, 4), "train_pairs": len(train_pairs), "test_pairs": len(test_pairs)}


def main() -> None:
    load_env()
    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument("--json", action="store_true", dest="output_json")

    parser = argparse.ArgumentParser(description="Graph neural router for Obsidian skills.")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("export-graph", parents=[json_parent], help="Build tmp/skill_graph.pt")
    p_train = sub.add_parser("train", parents=[json_parent], help="Train masked-neighbor predictor")
    p_train.add_argument("--epochs", type=int, default=50)
    p_train.add_argument("--lr", type=float, default=0.001)
    p_predict = sub.add_parser("predict", parents=[json_parent], help="Predict top-5 skills for a task")
    p_predict.add_argument("--task", required=True)
    sub.add_parser("evaluate", parents=[json_parent], help="Report top-1/top-5 accuracy")

    args = parser.parse_args()
    if args.command == "export-graph":
        result = export_graph()
    elif args.command == "train":
        result = train_model(args.epochs, args.lr)
    elif args.command == "predict":
        result = predict_skills(args.task)
    elif args.command == "evaluate":
        result = evaluate_model()
    else:
        parser.print_help()
        sys.exit(1)
    print(json.dumps(result, indent=2, default=str) if args.output_json or True else result)


if __name__ == "__main__":
    main()
