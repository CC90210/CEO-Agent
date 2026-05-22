"""
RLHF Outreach -- dataset builder, DPO training skeleton, and fast draft scorer.

USAGE FROM PYTHON
-----------------
    from rlhf_outreach import build_dataset, score_draft

    build_dataset()
    score = score_draft("Hi Jane -- quick idea for your intake workflow...")

CLI
---
    python scripts/rlhf_outreach.py build-dataset --json
    python scripts/rlhf_outreach.py train --algorithm dpo --epochs 3
    python scripts/rlhf_outreach.py score --draft "Hi Jane ..."
    python scripts/rlhf_outreach.py evaluate --json

DESIGN
------
1. Data source. Pull interaction context from `lead_interactions` and approval
   signals from `agent_decisions`.
2. Dataset shape. Persist `{state, action, reward}` JSONL rows for portability.
3. Heavy training optional. If TRL/PEFT/Transformers are missing, the script
   still builds the dataset and a lightweight lexical reward surrogate.
4. Fast scoring hook. `score_draft()` returns a 0..1 approval likelihood
   without requiring the LoRA adapter to be loaded inside `draft_critic.py`.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = PROJECT_ROOT / "tmp"
DATASET_PATH = TMP_DIR / "rlhf_dataset.jsonl"
META_PATH = TMP_DIR / "rlhf_policy_meta.json"
ADAPTER_DIR = TMP_DIR / "rlhf_outreach_adapter"
TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_'-]{1,30}")


def load_env() -> dict[str, str]:
    """V6.8.3: delegate to lib.secret_loader (was python-dotenv)."""
    env = dict(_load_env())
    for _k, _v in env.items():
        os.environ.setdefault(_k, str(_v))
    return {k: str(v) for k, v in env.items() if v is not None}


def _get_supabase():
    load_env()
    url = os.environ.get("BRAVO_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Missing Bravo Supabase credentials in environment")
    from supabase import create_client  # type: ignore
    return create_client(url, key)


def _trl_available() -> bool:
    try:
        import datasets  # noqa: F401
        import peft  # noqa: F401
        import transformers  # noqa: F401
        import trl  # noqa: F401
        return True
    except ImportError:
        return False


def _decision_signal(row: dict[str, Any]) -> Optional[float]:
    blob = json.dumps(row, default=str).lower()
    if any(token in blob for token in ("approved", "\"ship\"", "approve")):
        return 1.0
    if any(token in blob for token in ("rejected", "\"reject\"", "reject")):
        return -1.0
    if any(token in blob for token in ("edit", "revise", "rewrite")):
        return 0.35
    return None


def _state_text(ix: dict[str, Any], decision: dict[str, Any]) -> str:
    md = ix.get("metadata") or {}
    return "\n".join(
        [
            f"channel={ix.get('channel') or 'email'}",
            f"agent_source={ix.get('agent_source') or 'unknown'}",
            f"subject={ix.get('subject') or ''}",
            f"lead_id={ix.get('lead_id') or decision.get('target_lead_id') or 'unknown'}",
            f"decision_type={decision.get('decision_type') or ''}",
            f"reasoning={decision.get('reasoning') or ''}",
            f"stage={md.get('relationship_stage') or md.get('stage') or ''}",
        ]
    ).strip()


def _action_text(ix: dict[str, Any], decision: dict[str, Any]) -> str:
    md = ix.get("metadata") or {}
    parts = [
        str(md.get("draft_body") or md.get("body") or md.get("body_preview") or ix.get("content") or ""),
        str(md.get("draft_subject") or ix.get("subject") or ""),
        str((decision.get("execution_result") or {}).get("body_preview") or ""),
    ]
    return "\n".join(part for part in parts if part).strip()[:4000]


def build_dataset(limit: int = 500) -> dict[str, Any]:
    """Query Supabase and write tmp/rlhf_dataset.jsonl with state/action/reward."""
    db = _get_supabase()
    interactions = (db.table("lead_interactions").select("*").order("created_at", desc=True).limit(limit).execute().data or [])
    decisions = (db.table("agent_decisions").select("*").order("created_at", desc=True).limit(limit).execute().data or [])
    by_lead: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in interactions:
        if row.get("lead_id"):
            by_lead[str(row["lead_id"])].append(row)
    rows: list[dict[str, Any]] = []
    for decision in decisions:
        reward = _decision_signal(decision)
        lead_id = str(decision.get("target_lead_id") or "")
        if reward is None or not lead_id or lead_id not in by_lead:
            continue
        ix = by_lead[lead_id][0]
        action = _action_text(ix, decision)
        if not action:
            continue
        rows.append({"state": _state_text(ix, decision), "action": action, "reward": reward})
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with DATASET_PATH.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")
    return {"ok": True, "dataset_path": str(DATASET_PATH), "rows": len(rows)}


def _load_dataset() -> list[dict[str, Any]]:
    if not DATASET_PATH.exists():
        raise RuntimeError("Dataset missing. Run build-dataset first.")
    return [json.loads(line) for line in DATASET_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def _fit_surrogate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pos = Counter()
    neg = Counter()
    for row in rows:
        tokens = set(TOKEN_RE.findall((row.get("action") or "").lower()))
        target = pos if float(row.get("reward") or 0.0) > 0 else neg
        target.update(tokens)
    vocab = sorted(set(pos) | set(neg))
    weights = {}
    for token in vocab:
        weights[token] = math.log((pos[token] + 1.0) / (neg[token] + 1.0))
    meta = {"bias": 0.0, "weights": weights, "dataset_rows": len(rows)}
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def _pairwise_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    by_state: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"pos": [], "neg": []})
    for row in rows:
        bucket = "pos" if float(row["reward"]) > 0 else "neg"
        by_state[row["state"]][bucket].append(row["action"])
    negative_pool = [row["action"] for row in rows if float(row["reward"]) <= 0]
    pairs: list[dict[str, str]] = []
    for state, bucket in by_state.items():
        negatives = bucket["neg"] or negative_pool[:1]
        for chosen in bucket["pos"]:
            for rejected in negatives[:2]:
                if chosen != rejected:
                    pairs.append({"prompt": state, "chosen": chosen, "rejected": rejected})
    return pairs


def train_policy(algorithm: str = "dpo", epochs: int = 3, base_model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct") -> dict[str, Any]:
    """Train LoRA DPO when the TRL stack is installed; always fit a surrogate scorer."""
    rows = _load_dataset()
    meta = _fit_surrogate(rows)
    pairs = _pairwise_rows(rows)
    result = {"ok": True, "algorithm": algorithm, "epochs": epochs, "pairs": len(pairs), "surrogate_meta": str(META_PATH)}
    if algorithm.lower() != "dpo":
        result["ok"] = False
        result["error"] = "Only DPO is wired in this skeleton"
        return result
    if not _trl_available():
        result["adapter_trained"] = False
        result["note"] = "TRL/PEFT not installed; built surrogate scorer only."
        return result

    from datasets import Dataset  # type: ignore
    from peft import LoraConfig  # type: ignore
    from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
    from trl import DPOConfig, DPOTrainer  # type: ignore

    ds = Dataset.from_list(pairs[: max(1, min(len(pairs), 200))])
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(base_model)
    peft_cfg = LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05, task_type="CAUSAL_LM")
    train_args = DPOConfig(output_dir=str(ADAPTER_DIR), num_train_epochs=epochs, per_device_train_batch_size=1, learning_rate=5e-5, logging_steps=1)
    trainer = DPOTrainer(model=model, args=train_args, processing_class=tokenizer, train_dataset=ds, peft_config=peft_cfg)
    trainer.train()
    trainer.model.save_pretrained(str(ADAPTER_DIR))
    tokenizer.save_pretrained(str(ADAPTER_DIR))
    result["adapter_trained"] = True
    result["adapter_dir"] = str(ADAPTER_DIR)
    result["base_model"] = base_model
    result["surrogate_rows"] = meta["dataset_rows"]
    return result


def score_draft(text: str) -> float:
    """Return a 0..1 approval-likelihood score for a draft."""
    if not META_PATH.exists():
        return 0.5
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    score = float(meta.get("bias") or 0.0)
    weights = meta.get("weights") or {}
    for token in set(TOKEN_RE.findall(text.lower())):
        score += float(weights.get(token) or 0.0)
    return round(1.0 / (1.0 + math.exp(-score)), 4)


def evaluate_policy() -> dict[str, Any]:
    """Evaluate approval-rate prediction accuracy on an 80/20 held-out split."""
    rows = _load_dataset()
    random.Random(42).shuffle(rows)
    split = max(1, int(len(rows) * 0.8))
    train_rows, test_rows = rows[:split], rows[split:] or rows[:1]
    _fit_surrogate(train_rows)
    correct = 0
    for row in test_rows:
        predicted = score_draft(row["action"]) >= 0.5
        actual = float(row["reward"]) > 0
        correct += int(predicted == actual)
    return {"accuracy": round(correct / max(1, len(test_rows)), 4), "train_rows": len(train_rows), "test_rows": len(test_rows)}


def main() -> None:
    load_env()
    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument("--json", action="store_true", dest="output_json")

    parser = argparse.ArgumentParser(description="RLHF skeleton for outreach drafting.")
    sub = parser.add_subparsers(dest="command")
    p_build = sub.add_parser("build-dataset", parents=[json_parent], help="Build state/action/reward JSONL from Supabase")
    p_build.add_argument("--limit", type=int, default=500)
    p_train = sub.add_parser("train", parents=[json_parent], help="Train DPO LoRA skeleton")
    p_train.add_argument("--algorithm", default="dpo")
    p_train.add_argument("--epochs", type=int, default=3)
    p_score = sub.add_parser("score", parents=[json_parent], help="Score a candidate draft")
    p_score.add_argument("--draft", required=True)
    sub.add_parser("evaluate", parents=[json_parent], help="Evaluate held-out accuracy")

    args = parser.parse_args()
    if args.command == "build-dataset":
        result = build_dataset(args.limit)
    elif args.command == "train":
        result = train_policy(args.algorithm, args.epochs)
    elif args.command == "score":
        result = {"score": score_draft(args.draft)}
    elif args.command == "evaluate":
        result = evaluate_policy()
    else:
        parser.print_help()
        sys.exit(1)
    print(json.dumps(result, indent=2, default=str) if args.output_json or True else result)


if __name__ == "__main__":
    main()
