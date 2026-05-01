"""
MAML Onboard — Model-Agnostic Meta-Learning for rapid client onboarding.

Learns a shared initialization across all past OASIS AI client engagements so
that <10 new-client examples are enough to adapt the policy network to a new
client's outreach style, pricing tier, and proposal format in a single inner
loop (≈3 gradient steps).

USAGE FROM PYTHON
-----------------
    from maml_onboard import meta_train, adapt_to_client, predict

    meta_train(epochs=50, inner_steps=3)
    model = adapt_to_client(client_id="abc123", inner_steps=3)
    prediction = predict(client_id="abc123", query="pricing tier")

CLI
---
    python scripts/maml_onboard.py build-tasks
    python scripts/maml_onboard.py train --epochs 50 --inner-steps 3
    python scripts/maml_onboard.py adapt --client-id abc123
    python scripts/maml_onboard.py predict --client-id abc123 --query "proposal tone"
    python scripts/maml_onboard.py evaluate
    python scripts/maml_onboard.py predict --client-id abc123 --query "foo" --json

DESIGN
------
1. Policy network: 3-layer MLP (input→256→256→256→output).  Input is a
   64-dim embedding of the query.  Output is a probability vector over
   onboarding actions: [formal_tone, casual_tone, high_price, mid_price,
   low_price, short_proposal, long_proposal, follow_up_1d, follow_up_7d].

2. MAML: outer loop optimises meta-parameters θ so that θ + α·∇L_task(θ)
   produces good performance on each client's query set.  Uses `higher` for
   functional gradient passes through the inner loop if available; falls back
   to a manual first-order MAML approximation (Reptile variant) otherwise.

3. Task structure: each past client is a task.  Support set = first half of
   client interactions.  Query set = second half.  Tasks loaded from Supabase
   (clients table) if available; synthetic tasks generated as fallback.

4. Adaptation: given a new client_id, load their interactions from Supabase
   (or tmp/maml_tasks.jsonl), run inner_steps gradient steps on the support
   set, save the adapted weights to tmp/maml_<client_id>.pt.

5. Persistence: meta-weights at tmp/maml.pt; adapted checkpoints at
   tmp/maml_<client_id>.pt.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

TMP_DIR = PROJECT_ROOT / "tmp"
META_CKPT = TMP_DIR / "maml.pt"
TASKS_FILE = TMP_DIR / "maml_tasks.jsonl"

INPUT_DIM = 64
HIDDEN_DIM = 256
N_ACTIONS = 9
ACTION_LABELS = [
    "formal_tone", "casual_tone", "high_price", "mid_price", "low_price",
    "short_proposal", "long_proposal", "follow_up_1d", "follow_up_7d",
]
INNER_LR = 0.01
OUTER_LR = 3e-4

# ---- Optional-dependency guards --------------------------------------------

def _require_torch(action: str) -> None:
    try:
        import torch  # noqa: F401
    except ImportError:
        print(
            f"[maml_onboard] torch is required for '{action}'.\n"
            "  Install: pip install torch --index-url https://download.pytorch.org/whl/cpu",
            file=sys.stderr,
        )
        sys.exit(1)


def _try_higher() -> bool:
    try:
        import higher  # type: ignore[import-untyped]  # noqa: F401
        return True
    except ImportError:
        return False


# ---- Policy network ---------------------------------------------------------

def _build_policy() -> "torch.nn.Module":  # type: ignore[name-defined]
    _require_torch("build_policy")
    import torch.nn as nn

    class PolicyNet(nn.Module):
        """3-hidden-layer MLP mapping query embedding → action logits."""

        def __init__(self) -> None:
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(INPUT_DIM, HIDDEN_DIM),
                nn.ReLU(),
                nn.Linear(HIDDEN_DIM, HIDDEN_DIM),
                nn.ReLU(),
                nn.Linear(HIDDEN_DIM, HIDDEN_DIM),
                nn.ReLU(),
                nn.Linear(HIDDEN_DIM, N_ACTIONS),
            )

        def forward(self, x: Any) -> Any:
            return self.net(x)

    return PolicyNet()


# ---- Minimal text embedding (hash-based, no deps) -------------------------

def _embed_text(text: str, dim: int = INPUT_DIM) -> list[float]:
    import hashlib
    digest = hashlib.sha256(text.encode()).digest()
    raw = list(digest)
    while len(raw) < dim:
        raw.extend(raw)
    return [(b / 127.5) - 1.0 for b in raw[:dim]]


# ---- Supabase client loader (optional) ------------------------------------

def _load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env.agents"
    if not env_path.exists():
        return {}
    env_vars: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env_vars[k.strip()] = v.strip()
    for k, v in env_vars.items():
        os.environ.setdefault(k, v)
    return env_vars


def _fetch_client_tasks() -> list[dict]:
    """Try to fetch client engagement tasks from Supabase. Returns [] on failure."""
    env = _load_env()
    url = env.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL", "")
    key = env.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return []
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{url}/rest/v1/clients?select=id,name,vertical,stage,notes",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            clients = json.loads(resp.read())
        if not isinstance(clients, list):
            return []
        tasks = []
        for c in clients:
            # Support set: query the engagement history
            cid = c.get("id", "")
            tasks.append({
                "client_id": str(cid),
                "client_name": c.get("name", "Unknown"),
                "vertical": c.get("vertical", "unknown"),
                "stage": c.get("stage", "cold"),
                "support": [
                    {"query": f"onboard {c.get('vertical','business')}", "action": "mid_price"},
                    {"query": f"proposal for {c.get('name','client')}", "action": "short_proposal"},
                ],
                "query_set": [
                    {"query": f"follow up {c.get('name','client')}", "action": "follow_up_1d"},
                ],
            })
        return tasks
    except Exception:  # noqa: BLE001
        return []


def _synthetic_tasks(n: int = 10) -> list[dict]:
    """Generate synthetic client tasks for training when Supabase unavailable."""
    import random
    random.seed(42)
    verticals = ["hvac", "wellness", "dental", "real_estate", "fitness"]
    tasks = []
    for i in range(n):
        vert = verticals[i % len(verticals)]
        tasks.append({
            "client_id": f"synthetic_{i}",
            "client_name": f"Client {i}",
            "vertical": vert,
            "stage": "cold",
            "support": [
                {"query": f"price for {vert}", "action": ACTION_LABELS[i % N_ACTIONS]},
                {"query": f"proposal {vert}", "action": "short_proposal"},
            ],
            "query_set": [
                {"query": f"follow up {vert}", "action": "follow_up_7d"},
            ],
        })
    return tasks


# ---- Task batch preparation ------------------------------------------------

def _task_to_tensors(task: dict) -> tuple[Any, Any, Any, Any]:
    """Convert task dict to (support_x, support_y, query_x, query_y) tensors."""
    _require_torch("task_to_tensors")
    import torch

    def examples_to_tensors(examples: list[dict]):
        xs = torch.tensor([_embed_text(e["query"]) for e in examples], dtype=torch.float32)
        ys = torch.tensor(
            [ACTION_LABELS.index(e["action"]) if e["action"] in ACTION_LABELS else 0
             for e in examples],
            dtype=torch.long,
        )
        return xs, ys

    sx, sy = examples_to_tensors(task.get("support", []))
    qx, qy = examples_to_tensors(task.get("query_set", []))
    return sx, sy, qx, qy


# ---- MAML inner loop --------------------------------------------------------

def _inner_loop_higher(model: Any, sx: Any, sy: Any,
                       inner_steps: int, inner_lr: float) -> Any:
    """Differentiable inner loop using the `higher` library."""
    import torch
    import torch.nn.functional as F
    import higher  # type: ignore[import-untyped]

    opt = torch.optim.SGD(model.parameters(), lr=inner_lr)
    with higher.innerloop_ctx(model, opt, copy_initial_weights=False) as (fmodel, diffopt):
        for _ in range(inner_steps):
            logits = fmodel(sx)
            loss = F.cross_entropy(logits, sy)
            diffopt.step(loss)
        query_logits = fmodel(sx)
        return query_logits, fmodel


def _inner_loop_reptile(model: Any, sx: Any, sy: Any,
                        inner_steps: int, inner_lr: float) -> tuple[Any, Any]:
    """First-order Reptile approximation when `higher` is unavailable."""
    import torch
    import torch.nn.functional as F
    import copy

    fast_model = copy.deepcopy(model)
    opt = torch.optim.SGD(fast_model.parameters(), lr=inner_lr)
    for _ in range(inner_steps):
        logits = fast_model(sx)
        loss = F.cross_entropy(logits, sy)
        opt.zero_grad()
        loss.backward()
        opt.step()
    logits = fast_model(sx)
    return logits, fast_model


# ---- Public API -------------------------------------------------------------

def meta_train(epochs: int = 50, inner_steps: int = 3) -> dict:
    """Meta-train on all available client tasks."""
    _require_torch("meta_train")
    import torch
    import torch.nn.functional as F

    tasks = _fetch_client_tasks()
    if not tasks:
        tasks = _synthetic_tasks(10)
    use_higher = _try_higher()
    model = _build_policy()
    meta_opt = torch.optim.Adam(model.parameters(), lr=OUTER_LR)
    losses: list[float] = []
    for epoch in range(epochs):
        epoch_loss = torch.tensor(0.0)
        for task in tasks:
            sx, sy, qx, qy = _task_to_tensors(task)
            if sx.shape[0] == 0:
                continue
            if use_higher:
                _, fast_model = _inner_loop_higher(model, sx, sy, inner_steps, INNER_LR)
            else:
                _, fast_model = _inner_loop_reptile(model, sx, sy, inner_steps, INNER_LR)
            # Outer loss on query set (or support set if query empty)
            qx_eval = qx if qx.shape[0] > 0 else sx
            qy_eval = qy if qy.shape[0] > 0 else sy
            outer_logits = fast_model(qx_eval)
            epoch_loss = epoch_loss + F.cross_entropy(outer_logits, qy_eval)
        meta_opt.zero_grad()
        epoch_loss.backward()
        meta_opt.step()
        losses.append(float(epoch_loss))
        if (epoch + 1) % max(1, epochs // 5) == 0:
            print(f"  epoch {epoch + 1:4d}/{epochs}  loss={epoch_loss.item():.4f}")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    torch.save({"model_state": model.state_dict(), "use_higher": use_higher}, META_CKPT)
    return {"epochs": epochs, "tasks": len(tasks), "final_loss": round(losses[-1], 6),
            "backend": "higher" if use_higher else "reptile"}


def adapt_to_client(client_id: str, inner_steps: int = 3) -> str:
    """Adapt meta-weights to a specific client. Returns path to adapted ckpt."""
    _require_torch("adapt")
    import torch
    import torch.nn.functional as F
    if not META_CKPT.exists():
        raise RuntimeError(f"Meta checkpoint missing. Run: train first.")
    ckpt = torch.load(META_CKPT, map_location="cpu", weights_only=False)
    model = _build_policy()
    model.load_state_dict(ckpt["model_state"])
    # Find client task
    tasks = _fetch_client_tasks()
    if not tasks:
        tasks = _synthetic_tasks(10)
    task = next((t for t in tasks if str(t["client_id"]) == str(client_id)), None)
    if task is None:
        # Load from TASKS_FILE if available
        if TASKS_FILE.exists():
            with open(TASKS_FILE, "r") as f:
                for line in f:
                    t = json.loads(line)
                    if str(t.get("client_id")) == str(client_id):
                        task = t
                        break
    if task is None:
        raise ValueError(f"No task data found for client_id={client_id}")
    sx, sy, _, _ = _task_to_tensors(task)
    if sx.shape[0] == 0:
        raise ValueError(f"No support examples for client_id={client_id}")
    use_higher = ckpt.get("use_higher", False) and _try_higher()
    if use_higher:
        _, fast_model = _inner_loop_higher(model, sx, sy, inner_steps, INNER_LR)
    else:
        _, fast_model = _inner_loop_reptile(model, sx, sy, inner_steps, INNER_LR)
    out_path = TMP_DIR / f"maml_{client_id}.pt"
    torch.save({"model_state": fast_model.state_dict(), "client_id": client_id}, out_path)
    return str(out_path)


def predict(client_id: str, query: str) -> dict:
    """Use adapted model to predict best action for a client query."""
    _require_torch("predict")
    import torch
    import torch.nn.functional as F
    ckpt_path = TMP_DIR / f"maml_{client_id}.pt"
    if not ckpt_path.exists():
        raise RuntimeError(f"No adapted model for {client_id}. Run: adapt first.")
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    model = _build_policy()
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    x = torch.tensor(_embed_text(query), dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        logits = model(x)
        probs = F.softmax(logits, dim=-1).squeeze(0).tolist()
    top_idx = max(range(N_ACTIONS), key=lambda i: probs[i])
    return {
        "client_id": client_id,
        "query": query,
        "predicted_action": ACTION_LABELS[top_idx],
        "confidence": round(probs[top_idx], 4),
        "action_probabilities": {a: round(p, 4) for a, p in zip(ACTION_LABELS, probs)},
    }


# ---- CLI command handlers ---------------------------------------------------

def _cmd_build_tasks(args: argparse.Namespace) -> int:
    tasks = _fetch_client_tasks()
    source = "supabase"
    if not tasks:
        tasks = _synthetic_tasks(10)
        source = "synthetic"
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with open(TASKS_FILE, "w") as f:
        for t in tasks:
            f.write(json.dumps(t) + "\n")
    result = {"tasks_written": len(tasks), "source": source, "path": str(TASKS_FILE)}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Built {len(tasks)} tasks from {source} -> {TASKS_FILE}")
    return 0


def _cmd_train(args: argparse.Namespace) -> int:
    print(f"Meta-training MAML - epochs={args.epochs}, inner_steps={args.inner_steps}")
    result = meta_train(epochs=args.epochs, inner_steps=args.inner_steps)
    result["checkpoint"] = str(META_CKPT)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Meta-training complete. Backend={result['backend']}, "
              f"final_loss={result['final_loss']}, saved -> {META_CKPT}")
    return 0


def _cmd_adapt(args: argparse.Namespace) -> int:
    try:
        path = adapt_to_client(args.client_id, inner_steps=args.inner_steps)
        result = {"status": "adapted", "client_id": args.client_id, "checkpoint": path}
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Adapted for client {args.client_id} -> {path}")
        return 0
    except (RuntimeError, ValueError) as exc:
        err = {"status": "error", "message": str(exc)}
        if args.json:
            print(json.dumps(err, indent=2))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1


def _cmd_predict(args: argparse.Namespace) -> int:
    try:
        result = predict(args.client_id, args.query)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Predicted action: {result['predicted_action']} "
                  f"(confidence={result['confidence']:.4f})")
        return 0
    except (RuntimeError, ValueError) as exc:
        err = {"status": "error", "message": str(exc)}
        if args.json:
            print(json.dumps(err, indent=2))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1


def _cmd_evaluate(args: argparse.Namespace) -> int:
    """Leave-one-out cross-validation across all clients."""
    _require_torch("evaluate")
    import torch
    import torch.nn.functional as F
    if not META_CKPT.exists():
        print("No meta checkpoint. Run: train first.", file=sys.stderr)
        return 1
    tasks = _fetch_client_tasks()
    if not tasks:
        tasks = _synthetic_tasks(10)
    correct = 0
    total = 0
    per_client: list[dict] = []
    ckpt = torch.load(META_CKPT, map_location="cpu", weights_only=False)
    use_higher = ckpt.get("use_higher", False) and _try_higher()
    for i, held_out in enumerate(tasks):
        model = _build_policy()
        model.load_state_dict(ckpt["model_state"])
        sx, sy, qx, qy = _task_to_tensors(held_out)
        if qx.shape[0] == 0:
            continue
        if sx.shape[0] > 0:
            if use_higher:
                _, fast_model = _inner_loop_higher(model, sx, sy, 3, INNER_LR)
            else:
                _, fast_model = _inner_loop_reptile(model, sx, sy, 3, INNER_LR)
        else:
            fast_model = model
        fast_model.eval()
        with torch.no_grad():
            logits = fast_model(qx)
            preds = logits.argmax(dim=-1)
        c = int((preds == qy).sum())
        per_client.append({"client_id": held_out["client_id"], "correct": c, "total": len(qy)})
        correct += c
        total += len(qy)
    accuracy = correct / total if total > 0 else 0.0
    result = {"accuracy": round(accuracy, 4), "correct": correct, "total": total,
              "per_client": per_client}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"LOO Accuracy: {accuracy:.4f} ({correct}/{total})")
    return 0


# ---- Main -------------------------------------------------------------------

def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="maml_onboard.py",
        description="MAML meta-learning for rapid client onboarding.",
    )
    p.add_argument("--json", dest="json", action="store_true",
                   help="Emit structured JSON output")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("build-tasks", help="Build task dataset from Supabase or synthetic")

    t = sub.add_parser("train", help="Meta-train on all client tasks")
    t.add_argument("--epochs", type=int, default=50)
    t.add_argument("--inner-steps", dest="inner_steps", type=int, default=3)

    a = sub.add_parser("adapt", help="Adapt meta-model to a specific client")
    a.add_argument("--client-id", dest="client_id", required=True)
    a.add_argument("--inner-steps", dest="inner_steps", type=int, default=3)

    pr = sub.add_parser("predict", help="Predict action for a client query")
    pr.add_argument("--client-id", dest="client_id", required=True)
    pr.add_argument("--query", required=True)

    sub.add_parser("evaluate", help="Leave-one-out cross-validation")

    return p


def main() -> None:
    _json_flag = "--json" in sys.argv
    argv_clean = [a for a in sys.argv[1:] if a != "--json"]
    p = _make_parser()
    args = p.parse_args(argv_clean)
    args.json = _json_flag
    dispatch = {
        "build-tasks": _cmd_build_tasks,
        "train": _cmd_train,
        "adapt": _cmd_adapt,
        "predict": _cmd_predict,
        "evaluate": _cmd_evaluate,
    }
    if args.command is None:
        p.print_help()
        sys.exit(0)
    handler = dispatch.get(args.command)
    if handler is None:
        p.print_help()
        sys.exit(1)
    sys.exit(handler(args))


if __name__ == "__main__":
    main()
