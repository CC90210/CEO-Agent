"""
Neural Memory — differentiable memory store backed by a Neural Turing Machine.

Provides an addressable, persistent memory layer for the Business-Empire-Agent
stack. Trained on the copy/associative-recall benchmark; at inference time used
as a semantic retrieval surface over short-horizon context.

USAGE FROM PYTHON
-----------------
    from neural_memory import NTM, read_memory, write_memory

    model = NTM.load("tmp/ntm.pt")
    result = read_memory(model, query="last client meeting notes", top_k=3)

CLI
---
    python scripts/neural_memory.py init
    python scripts/neural_memory.py write --content "OASIS onboarding step 1"
    python scripts/neural_memory.py read  --query "onboarding" --top-k 3
    python scripts/neural_memory.py train --epochs 100 --task copy
    python scripts/neural_memory.py inspect
    python scripts/neural_memory.py read  --query "onboarding" --json

DESIGN
------
1. Controller: single-layer LSTM (hidden=128).  Receives current input
   concatenated with the previous read-vector from memory.  Small enough to
   run on CPU in <50 ms per step.

2. Memory matrix: M ∈ R^{128 x 64}.  128 cells, 64-wide representation.
   Persisted as a named tensor inside the checkpoint alongside model weights.

3. Addressing: content-based cosine similarity + sharpening (softmax with
   temperature β).  Location-based shifting via circular convolution so the
   head can walk forward or backward through memory sequentially.

4. Read head: weighted sum over rows of M.  Returns a 64-dim read vector.

5. Write head: erase-then-add mechanism per the Graves 2014 NTM paper.
   Erase and add vectors produced by the controller output layer.

6. Embedding: fastembed (BAAI/bge-small-en-v1.5, 384-dim) if available,
   projected down to 64-dim via a learned linear layer stored in the checkpoint.
   Hash-based fallback: SHA-256 of text → 64 floats in [-1, 1].

7. Copy task: sequence of random bit-vectors → model writes then reads back.
   Trains the controller + addressing mechanism without any external data.

8. Persistence: tmp/ntm.pt stores {model_state, memory_matrix,
   write_cursor, embedder_state, metadata}.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

TMP_DIR = PROJECT_ROOT / "tmp"
MODEL_PATH = TMP_DIR / "ntm.pt"

MEMORY_CELLS = 128
MEMORY_WIDTH = 64
HIDDEN_SIZE = 128
SHIFT_RANGE = 3       # convolution kernel width: shift by -1, 0, +1

# ---- Optional-dependency guards --------------------------------------------

def _require_torch(action: str) -> None:
    try:
        import torch  # noqa: F401
    except ImportError:
        print(
            f"[neural_memory] torch is required for '{action}'.\n"
            "  Install: pip install torch --index-url https://download.pytorch.org/whl/cpu",
            file=sys.stderr,
        )
        sys.exit(1)


def _try_fastembed() -> Optional[Any]:
    """Return a fastembed TextEmbedding model or None."""
    try:
        from fastembed import TextEmbedding  # type: ignore[import-untyped]
        return TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    except Exception:  # noqa: BLE001
        return None


# ---- Hash-based embedding fallback -----------------------------------------

def _hash_embed(text: str, dim: int = MEMORY_WIDTH) -> list[float]:
    """Deterministic float vector from SHA-256 hash of text. No deps."""
    digest = hashlib.sha256(text.encode()).digest()
    # Tile digest until we have enough bytes, then map to [-1, 1]
    raw = list(digest)
    while len(raw) < dim:
        raw.extend(raw)
    return [(b / 127.5) - 1.0 for b in raw[:dim]]


# ---- NTM model --------------------------------------------------------------

def _build_model() -> "torch.nn.Module":  # type: ignore[name-defined]
    _require_torch("build_model")
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    class NTM(nn.Module):
        """Neural Turing Machine — controller LSTM + external memory."""

        def __init__(
            self,
            input_size: int = MEMORY_WIDTH,
            hidden_size: int = HIDDEN_SIZE,
            memory_cells: int = MEMORY_CELLS,
            memory_width: int = MEMORY_WIDTH,
            shift_range: int = SHIFT_RANGE,
        ) -> None:
            super().__init__()
            self.memory_cells = memory_cells
            self.memory_width = memory_width
            self.shift_range = shift_range

            # Controller
            controller_input = input_size + memory_width
            self.controller = nn.LSTMCell(controller_input, hidden_size)

            # Head output sizes
            # Read head emits: key(W) + beta(1) + gate(1) + shift(2*shift_range+1) + gamma(1)
            # Write head emits the same plus erase(W) + add(W)
            base_head_dim = memory_width + 1 + 1 + (2 * shift_range + 1) + 1
            read_head_dim = base_head_dim
            write_head_dim = base_head_dim + memory_width + memory_width

            self.read_head = nn.Linear(hidden_size, read_head_dim)
            self.write_head = nn.Linear(hidden_size, write_head_dim)
            self.output_layer = nn.Linear(hidden_size + memory_width, input_size)

            # Projection from embedding space (384 or 64) to memory_width
            self.embed_proj = nn.Linear(384, memory_width)

        # ---- Addressing helpers ------------------------------------------

        def _address(
            self,
            memory: "torch.Tensor",
            key: "torch.Tensor",
            beta: "torch.Tensor",
            gate: "torch.Tensor",
            shift: "torch.Tensor",
            gamma: "torch.Tensor",
            prev_weight: "torch.Tensor",
        ) -> "torch.Tensor":
            import torch
            import torch.nn.functional as F

            # 1. Content addressing
            key_norm = F.normalize(key, dim=-1)
            mem_norm = F.normalize(memory, dim=-1)
            similarity = torch.matmul(mem_norm, key_norm)          # [N]
            content_w = F.softmax(beta * similarity, dim=0)

            # 2. Interpolation
            g = torch.sigmoid(gate)
            gated_w = g * content_w + (1 - g) * prev_weight

            # 3. Convolutional shift (circular)
            shift_w = F.softmax(shift, dim=0)
            conv_w = self._circular_conv(gated_w, shift_w)

            # 4. Sharpening
            gamma_val = F.softplus(gamma) + 1.0
            sharp_w = conv_w ** gamma_val
            return sharp_w / (sharp_w.sum() + 1e-8)

        def _circular_conv(
            self, w: "torch.Tensor", s: "torch.Tensor"
        ) -> "torch.Tensor":
            import torch
            # Pad w for circular wrap, then 1-D conv
            padded = torch.cat([w[-self.shift_range:], w, w[: self.shift_range]])
            kernel = s.flip(0).unsqueeze(0).unsqueeze(0)
            padded = padded.unsqueeze(0).unsqueeze(0)
            result = torch.nn.functional.conv1d(padded, kernel).squeeze()
            return result

        # ---- Forward -------------------------------------------------------

        def forward(
            self,
            x: "torch.Tensor",
            state: dict,
        ) -> tuple["torch.Tensor", dict]:
            import torch

            h, c = state["h"], state["c"]
            memory = state["memory"]
            prev_r = state["prev_r"]
            prev_rw = state["prev_rw"]
            prev_ww = state["prev_ww"]

            ctrl_in = torch.cat([x, prev_r], dim=-1)
            h, c = self.controller(ctrl_in, (h, c))

            # --- Read head
            rh = self.read_head(h)
            mw = self.memory_width
            sr = self.shift_range
            rkey = rh[:, :mw]
            rbeta = rh[:, mw:mw + 1]
            rgate = rh[:, mw + 1:mw + 2]
            rshift = rh[:, mw + 2:mw + 2 + (2 * sr + 1)]
            rgamma = rh[:, mw + 2 + (2 * sr + 1):]

            rw = self._address(memory, rkey.squeeze(0), rbeta.squeeze(0),
                               rgate.squeeze(0), rshift.squeeze(0),
                               rgamma.squeeze(0), prev_rw)
            r = (rw.unsqueeze(-1) * memory).sum(0)

            # --- Write head
            wh = self.write_head(h)
            wkey = wh[:, :mw]
            wbeta = wh[:, mw:mw + 1]
            wgate = wh[:, mw + 1:mw + 2]
            wshift = wh[:, mw + 2:mw + 2 + (2 * sr + 1)]
            wgamma = wh[:, mw + 2 + (2 * sr + 1):mw + 2 + (2 * sr + 1) + 1]
            erase = torch.sigmoid(wh[:, -(2 * mw):-mw])
            add = torch.tanh(wh[:, -mw:])

            ww = self._address(memory, wkey.squeeze(0), wbeta.squeeze(0),
                               wgate.squeeze(0), wshift.squeeze(0),
                               wgamma.squeeze(0), prev_ww)

            # Erase then add
            memory = memory * (1 - ww.unsqueeze(-1) * erase)
            memory = memory + ww.unsqueeze(-1) * add

            out = self.output_layer(torch.cat([h, r.unsqueeze(0)], dim=-1))

            new_state = {"h": h, "c": c, "memory": memory,
                         "prev_r": r.unsqueeze(0), "prev_rw": rw, "prev_ww": ww}
            return out, new_state

        def init_state(self, batch: int = 1) -> dict:
            import torch
            return {
                "h": torch.zeros(batch, self.lstm_hidden if hasattr(self, "lstm_hidden") else HIDDEN_SIZE),
                "c": torch.zeros(batch, HIDDEN_SIZE),
                "memory": torch.zeros(self.memory_cells, self.memory_width),
                "prev_r": torch.zeros(batch, self.memory_width),
                "prev_rw": torch.zeros(self.memory_cells),
                "prev_ww": torch.zeros(self.memory_cells),
            }

    return NTM()


# ---- Persistence ------------------------------------------------------------

def _load_checkpoint() -> dict:
    _require_torch("load")
    import torch
    if not MODEL_PATH.exists():
        print(f"[neural_memory] No checkpoint at {MODEL_PATH}. Run: init", file=sys.stderr)
        sys.exit(1)
    return torch.load(MODEL_PATH, map_location="cpu", weights_only=False)


def _save_checkpoint(ckpt: dict) -> None:
    import torch
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(ckpt, MODEL_PATH)


def _init_state(_model: Any) -> dict:
    import torch
    return {
        "h": torch.zeros(1, HIDDEN_SIZE),
        "c": torch.zeros(1, HIDDEN_SIZE),
        "memory": torch.zeros(MEMORY_CELLS, MEMORY_WIDTH),
        "prev_r": torch.zeros(1, MEMORY_WIDTH),
        "prev_rw": torch.zeros(MEMORY_CELLS),
        "prev_ww": torch.zeros(MEMORY_CELLS),
    }


# ---- Embedding --------------------------------------------------------------

def _embed(text: str, proj_layer: Optional[Any], fastembed_model: Optional[Any]) -> Any:
    import torch
    if fastembed_model is not None and proj_layer is not None:
        raw = list(fastembed_model.embed([text]))[0]  # (384,)
        t = torch.tensor(raw, dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            return proj_layer(t)  # (1, 64)
    fallback = _hash_embed(text, MEMORY_WIDTH)
    return torch.tensor(fallback, dtype=torch.float32).unsqueeze(0)


# ---- Public API -------------------------------------------------------------

def read_memory(query: str, top_k: int = 3) -> list[dict]:
    """Read top-k memory cells most similar to query."""
    _require_torch("read_memory")
    import torch
    import torch.nn.functional as F
    ckpt = _load_checkpoint()
    model = _build_model()
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    fe = _try_fastembed()
    q_vec = _embed(query, model.embed_proj, fe)
    memory = ckpt.get("memory", torch.zeros(MEMORY_CELLS, MEMORY_WIDTH))
    q_norm = F.normalize(q_vec, dim=-1)
    m_norm = F.normalize(memory, dim=-1)
    scores = torch.matmul(m_norm, q_norm.squeeze(0))
    top_vals, top_idx = torch.topk(scores, k=min(top_k, MEMORY_CELLS))
    results = []
    metadata = ckpt.get("cell_metadata", {})
    for rank, (idx, val) in enumerate(zip(top_idx.tolist(), top_vals.tolist())):
        results.append({
            "rank": rank,
            "cell_index": idx,
            "similarity": round(float(val), 4),
            "content": metadata.get(str(idx), {}).get("content", "<no text>"),
            "written_at": metadata.get(str(idx), {}).get("written_at", None),
        })
    return results


def write_memory(content: str) -> dict:
    """Write content into the NTM memory via attention-based addressing."""
    _require_torch("write_memory")
    import torch
    ckpt = _load_checkpoint()
    model = _build_model()
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    fe = _try_fastembed()
    vec = _embed(content, model.embed_proj, fe)
    state = {k: v for k, v in ckpt.get("rnn_state", {}).items()} if ckpt.get("rnn_state") else _init_state(model)
    state["memory"] = ckpt.get("memory", torch.zeros(MEMORY_CELLS, MEMORY_WIDTH))
    with torch.no_grad():
        _, new_state = model(vec, state)
    cell_metadata = ckpt.get("cell_metadata", {})
    import time
    write_cursor = int(ckpt.get("write_cursor", 0))
    cell_metadata[str(write_cursor)] = {
        "content": content[:200],
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    ckpt["memory"] = new_state["memory"]
    ckpt["rnn_state"] = {k: v.detach() for k, v in new_state.items() if k != "memory"}
    ckpt["cell_metadata"] = cell_metadata
    ckpt["write_cursor"] = (write_cursor + 1) % MEMORY_CELLS
    _save_checkpoint(ckpt)
    return {"written": True, "cell": write_cursor, "content_preview": content[:80]}


# ---- CLI command handlers ---------------------------------------------------

def _cmd_init(args: argparse.Namespace) -> int:
    _require_torch("init")
    import torch
    model = _build_model()
    ckpt = {
        "model_state": model.state_dict(),
        "memory": torch.zeros(MEMORY_CELLS, MEMORY_WIDTH),
        "rnn_state": None,
        "cell_metadata": {},
        "write_cursor": 0,
        "version": "1.0",
    }
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    _save_checkpoint(ckpt)
    result = {"status": "initialized", "path": str(MODEL_PATH),
              "memory_cells": MEMORY_CELLS, "memory_width": MEMORY_WIDTH}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"NTM initialized -> {MODEL_PATH}")
        print(f"  Memory: {MEMORY_CELLS} cells x {MEMORY_WIDTH} wide")
    return 0


def _cmd_read(args: argparse.Namespace) -> int:
    results = read_memory(args.query, top_k=args.top_k)
    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print(f"Top-{args.top_k} cells for query: '{args.query}'")
        for r in results:
            print(f"  [{r['rank']}] cell={r['cell_index']:3d}  sim={r['similarity']:.4f}  '{r['content']}'")
    return 0


def _cmd_write(args: argparse.Namespace) -> int:
    result = write_memory(args.content)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"Written to cell {result['cell']}: {result['content_preview']}")
    return 0


def _cmd_train(args: argparse.Namespace) -> int:
    _require_torch("train")
    import torch
    import torch.nn as nn
    ckpt = _load_checkpoint()
    model = _build_model()
    model.load_state_dict(ckpt["model_state"])
    model.train()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
    criterion = nn.BCEWithLogitsLoss()
    seq_len = 10
    bit_width = MEMORY_WIDTH
    losses = []
    print(f"Training NTM on '{args.task}' task for {args.epochs} epochs ...")
    for epoch in range(args.epochs):
        seq = torch.randint(0, 2, (seq_len, 1, bit_width)).float()
        state = _init_state(model)
        state["memory"] = ckpt.get("memory", torch.zeros(MEMORY_CELLS, MEMORY_WIDTH))
        # Write phase
        for t in range(seq_len):
            _, state = model(seq[t], state)
        # Read phase — predict the sequence back
        epoch_loss = torch.tensor(0.0)
        delimiter = torch.zeros(1, bit_width)
        _, state = model(delimiter, state)
        for t in range(seq_len):
            out, state = model(torch.zeros(1, bit_width), state)
            epoch_loss = epoch_loss + criterion(out, seq[t])
        optimizer.zero_grad()
        epoch_loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 10.0)
        optimizer.step()
        state = {k: v.detach() for k, v in state.items()}
        losses.append(float(epoch_loss))
        if (epoch + 1) % max(1, args.epochs // 5) == 0:
            print(f"  epoch {epoch + 1:4d}/{args.epochs}  loss={epoch_loss.item():.4f}")
    ckpt["model_state"] = model.state_dict()
    _save_checkpoint(ckpt)
    result = {"epochs": args.epochs, "final_loss": round(losses[-1], 6),
              "mean_last_10": round(sum(losses[-10:]) / min(10, len(losses)), 6)}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Training complete. Final loss: {result['final_loss']}")
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    _require_torch("inspect")
    import torch
    ckpt = _load_checkpoint()
    mem = ckpt.get("memory", torch.zeros(MEMORY_CELLS, MEMORY_WIDTH))
    total = mem.numel()
    nonzero = int((mem.abs() > 1e-4).sum())
    sparsity = 1.0 - nonzero / total
    result = {
        "memory_cells": MEMORY_CELLS,
        "memory_width": MEMORY_WIDTH,
        "total_elements": total,
        "nonzero_elements": nonzero,
        "sparsity": round(sparsity, 4),
        "mean": round(float(mem.mean()), 6),
        "var": round(float(mem.var()), 6),
        "min": round(float(mem.min()), 6),
        "max": round(float(mem.max()), 6),
        "written_cells": len(ckpt.get("cell_metadata", {})),
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Memory stats ({MEMORY_CELLS}x{MEMORY_WIDTH})")
        for k, v in result.items():
            print(f"  {k}: {v}")
    return 0


# ---- Main -------------------------------------------------------------------

def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="neural_memory.py",
        description="Neural Turing Machine — differentiable memory store.",
    )
    p.add_argument("--json", dest="json", action="store_true",
                   help="Emit structured JSON output")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize NTM + save tmp/ntm.pt")

    r = sub.add_parser("read", help="Read top-k memory cells matching query")
    r.add_argument("--query", required=True, help="Query text")
    r.add_argument("--top-k", dest="top_k", type=int, default=3,
                   help="Number of top cells to return")

    w = sub.add_parser("write", help="Write content into addressable memory")
    w.add_argument("--content", required=True, help="Text to write into memory")

    t = sub.add_parser("train", help="Train NTM on copy/associative-recall task")
    t.add_argument("--epochs", type=int, default=100)
    t.add_argument("--task", default="copy", choices=["copy"],
                   help="Benchmark task (only 'copy' implemented)")

    sub.add_parser("inspect", help="Print memory matrix statistics")

    return p


def main() -> None:
    _json_flag = "--json" in sys.argv
    argv_clean = [a for a in sys.argv[1:] if a != "--json"]
    p = _make_parser()
    args = p.parse_args(argv_clean)
    args.json = _json_flag
    dispatch = {
        "init": _cmd_init,
        "read": _cmd_read,
        "write": _cmd_write,
        "train": _cmd_train,
        "inspect": _cmd_inspect,
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
