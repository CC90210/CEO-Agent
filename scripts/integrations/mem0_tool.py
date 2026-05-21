"""
mem0ai Integration — Semantic Memory for Bravo V5.5
Persistent, auto-deduplicating semantic memory stored locally via Qdrant (embedded).
Uses fastembed (thenlper/gte-large, 1024-dim) for local embeddings — no OpenAI key needed.
Uses Claude Haiku as the LLM for memory extraction.
All credentials loaded from .env.agents (never hardcoded).

Vector store: local Qdrant at data/mem0_qdrant/ (persisted, no server required)
Upgrade path: set BRAVO_SUPABASE_DB_PASSWORD in .env.agents to migrate to Supabase pgvector.

Usage:
  python scripts/integrations/mem0_tool.py add "CC prefers direct communication, no filler"
  python scripts/integrations/mem0_tool.py search "what does CC prefer"
  python scripts/integrations/mem0_tool.py list [--limit 20]
  python scripts/integrations/mem0_tool.py get <memory_id>
  python scripts/integrations/mem0_tool.py delete <memory_id>
  python scripts/integrations/mem0_tool.py stats
  python scripts/integrations/mem0_tool.py history <memory_id>

Flags:
  --user-id   Override user_id (default: cc)
  --agent-id  Override agent_id (default: bravo)
  --json      Machine-readable JSON output (for agent consumption)
"""

import argparse
import json
import sys
import warnings
from pathlib import Path

# Suppress fastembed mean-pooling migration warning (benign — behaviour is correct)
warnings.filterwarnings("ignore", message=".*mean pooling.*", category=UserWarning)


# ── Config loading ────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _read_config_model(key: str, fallback: str) -> str:
    """Read a model name from .agents/config.toml."""
    config_path = _PROJECT_ROOT / ".agents" / "config.toml"
    if not config_path.exists():
        return fallback
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}") and "=" in line:
                    _, _, val = line.partition("=")
                    val = val.strip().strip('"').strip("'")
                    if val:
                        return val
    except OSError:
        pass
    return fallback


def load_env() -> dict[str, str]:
    """Load .env.agents from project root."""
    env_path = Path(__file__).resolve().parent.parent.parent / ".env.agents"
    if not env_path.exists():
        print(f"ERROR: {env_path} not found", file=sys.stderr)
        sys.exit(1)

    env_vars: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


# ── mem0 config builder ───────────────────────────────────────────────────────

def build_config(env_vars: dict[str, str]) -> dict:
    """
    Build the mem0 Memory config dict.

    Vector store: Qdrant embedded (local persistent path) — no external server.
    Embedder: fastembed thenlper/gte-large (1024-dim, runs via ONNX, no API key).
    LLM: Claude Haiku via Anthropic — used for memory fact extraction.

    Upgrade to Supabase pgvector: set BRAVO_SUPABASE_DB_PASSWORD in .env.agents.
    The script will auto-switch when that variable is present.
    """
    anthropic_key = env_vars.get("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        print("ERROR: ANTHROPIC_API_KEY must be set in .env.agents", file=sys.stderr)
        sys.exit(1)

    # Local Qdrant path — persisted inside the project data/ directory
    qdrant_path = str(Path(__file__).resolve().parent.parent.parent / "data" / "mem0_qdrant")
    Path(qdrant_path).mkdir(parents=True, exist_ok=True)

    # Optional: Supabase pgvector upgrade path
    db_password = env_vars.get("BRAVO_SUPABASE_DB_PASSWORD", "")
    supabase_url = env_vars.get("BRAVO_SUPABASE_URL", "")
    if db_password and supabase_url:
        project_id = supabase_url.replace("https://", "").split(".")[0]
        connection_string = (
            f"postgresql://postgres.{project_id}:{db_password}"
            f"@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
        )
        vector_store_config: dict = {
            "provider": "supabase",
            "config": {
                "connection_string": connection_string,
                "collection_name": "bravo_memories",
                "embedding_model_dims": 1024,
            },
        }
    else:
        vector_store_config = {
            "provider": "qdrant",
            "config": {
                "collection_name": "bravo_memories",
                "embedding_model_dims": 1024,
                "path": qdrant_path,
                "on_disk": True,
            },
        }

    return {
        "vector_store": vector_store_config,
        "llm": {
            "provider": "anthropic",
            "config": {
                "model": _read_config_model("extraction_model", "claude-haiku-4-5-20251001"),
                "api_key": anthropic_key,
            },
        },
        "embedder": {
            # fastembed runs locally via ONNX — no API key, ~120 MB model download on first use.
            # Model: thenlper/gte-large → 1024-dim dense embeddings.
            "provider": "fastembed",
            "config": {
                "model": "thenlper/gte-large",
            },
        },
    }


def get_memory(env_vars: dict[str, str]):
    """Initialise and return a mem0 Memory instance."""
    try:
        from mem0 import Memory
    except ImportError:
        print(
            "ERROR: mem0ai is not installed.\n"
            "Run: .venv/Scripts/python.exe -m pip install mem0ai fastembed vecs",
            file=sys.stderr,
        )
        sys.exit(1)

    config = build_config(env_vars)
    try:
        return Memory.from_config(config)
    except Exception as exc:
        print(f"ERROR: Failed to initialise mem0 Memory: {exc}", file=sys.stderr)
        sys.exit(1)


# ── Output helpers ────────────────────────────────────────────────────────────

def _pretty_print(data) -> None:
    if isinstance(data, list):
        if not data:
            print("No results.")
            return
        for i, item in enumerate(data, 1):
            if isinstance(item, dict):
                memory_text = item.get("memory", item.get("text", ""))
                memory_id = str(item.get("id", ""))
                score = item.get("score")
                score_str = f" (score: {score:.3f})" if score is not None else ""
                short_id = memory_id[:8] + "..." if len(memory_id) > 8 else memory_id
                print(f"{i:>3}. [{short_id}]{score_str}")
                print(f"     {memory_text}")
                meta = item.get("metadata") or item.get("categories")
                if meta:
                    print(f"     meta: {meta}")
            else:
                print(f"  {i}. {item}")
    elif isinstance(data, dict):
        for key, value in data.items():
            print(f"  {key}: {value}")
    else:
        print(data)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_add(m, args) -> None:
    result = m.add(args.text, user_id=args.user_id, agent_id=args.agent_id)

    memories = result.get("results", result) if isinstance(result, dict) else result

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return

    if isinstance(memories, list):
        added = [r for r in memories if isinstance(r, dict) and r.get("event") == "ADD"]
        updated = [r for r in memories if isinstance(r, dict) and r.get("event") == "UPDATE"]
        if added:
            print(f"Added {len(added)} memory/memories:")
            for r in added:
                mid = str(r.get("id", ""))[:8]
                print(f"  [{mid}...] {r.get('memory', '')}")
        if updated:
            print(f"Updated {len(updated)} existing (deduplication):")
            for r in updated:
                mid = str(r.get("id", ""))[:8]
                print(f"  [{mid}...] {r.get('memory', '')}")
        if not added and not updated:
            print(f"Memory processed: {memories}")
    else:
        print(f"Memory added: {memories}")


def cmd_search(m, args) -> None:
    results = m.search(
        args.query,
        user_id=args.user_id,
        agent_id=args.agent_id,
        limit=args.limit,
    )
    memories = results.get("results", results) if isinstance(results, dict) else results

    if args.json:
        print(json.dumps(memories, indent=2, default=str))
        return

    if not memories:
        print("No memories matched the query.")
        return

    print(f'Found {len(memories)} result(s) for: "{args.query}"\n')
    _pretty_print(memories)


def cmd_list(m, args) -> None:
    results = m.get_all(user_id=args.user_id, agent_id=args.agent_id, limit=args.limit)
    memories = results.get("results", results) if isinstance(results, dict) else results

    if args.json:
        print(json.dumps(memories, indent=2, default=str))
        return

    if not memories:
        print("No memories stored yet.")
        return

    print(f"Listing {len(memories)} memory/memories:\n")
    _pretty_print(memories)


def cmd_get(m, args) -> None:
    result = m.get(args.memory_id)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if result:
            _pretty_print(result)
        else:
            print(f"No memory found with id: {args.memory_id}")


def cmd_delete(m, args) -> None:
    m.delete(args.memory_id)
    if args.json:
        print(json.dumps({"deleted": args.memory_id}, indent=2))
    else:
        print(f"Deleted memory: {args.memory_id}")


def cmd_history(m, args) -> None:
    result = m.history(args.memory_id)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if not result:
            print(f"No history found for memory: {args.memory_id}")
            return
        print(f"History for [{str(args.memory_id)[:8]}...]:\n")
        for entry in result:
            event = entry.get("event", "?")
            prev = entry.get("previous_memory", "")
            curr = entry.get("new_memory", "")
            ts = entry.get("timestamp", "")
            print(f"  [{event}] {ts}")
            if prev:
                print(f"    before: {prev}")
            if curr:
                print(f"    after:  {curr}")


def cmd_stats(m, args) -> None:
    results = m.get_all(user_id=args.user_id, agent_id=args.agent_id, limit=10_000)
    memories = results.get("results", results) if isinstance(results, dict) else results
    count = len(memories) if isinstance(memories, list) else 0

    db_password = args._env_vars.get("BRAVO_SUPABASE_DB_PASSWORD", "")  # type: ignore[attr-defined]
    backend = "Supabase (pgvector via vecs)" if db_password else "Qdrant (local persistent)"

    data = {
        "total_memories": count,
        "user_id": args.user_id,
        "agent_id": args.agent_id,
        "collection": "bravo_memories",
        "backend": backend,
        "embedder": "fastembed / thenlper/gte-large (1024-dim)",
        "llm": "claude-haiku-4-5-20251001",
    }

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print("mem0 Memory Stats")
        print("-" * 40)
        for k, v in data.items():
            print(f"  {k:<25} {v}")


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="mem0ai semantic memory tool for Bravo V5.5",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    parser.add_argument("--user-id", default="cc", help="mem0 user_id (default: cc)")
    parser.add_argument("--agent-id", default="bravo", help="mem0 agent_id (default: bravo)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("add", help="Store a new memory").add_argument(
        "text", help="Memory text to store"
    )

    p_search = subparsers.add_parser("search", help="Semantic search over memories")
    p_search.add_argument("query", help="Natural language query")
    p_search.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")

    subparsers.add_parser("list", help="List stored memories").add_argument(
        "--limit", type=int, default=20, help="Max results (default: 20)"
    )

    subparsers.add_parser("get", help="Retrieve a single memory by ID").add_argument(
        "memory_id", help="Memory UUID"
    )

    subparsers.add_parser("delete", help="Delete a memory by ID").add_argument(
        "memory_id", help="Memory UUID"
    )

    subparsers.add_parser("history", help="View update history for a memory").add_argument(
        "memory_id", help="Memory UUID"
    )

    subparsers.add_parser("stats", help="Show memory store statistics")

    args = parser.parse_args()

    env_vars = load_env()

    # Attach env_vars to args so cmd_stats can read BRAVO_SUPABASE_DB_PASSWORD
    # without re-loading the file.
    args._env_vars = env_vars  # type: ignore[attr-defined]

    m = get_memory(env_vars)

    dispatch = {
        "add": cmd_add,
        "search": cmd_search,
        "list": cmd_list,
        "get": cmd_get,
        "delete": cmd_delete,
        "history": cmd_history,
        "stats": cmd_stats,
    }

    dispatch[args.command](m, args)


if __name__ == "__main__":
    main()
