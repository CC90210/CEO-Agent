"""
Model Router -- unified provider registry, routing, and call surface.

USAGE FROM PYTHON
-----------------
    from model_router import list_providers, resolve, call

    providers = list_providers()
    route = resolve(agent="bravo", task_type="coding")
    result = call(
        messages=[{"role": "user", "content": "Reply with OK."}],
        agent="codex",
    )

CLI
---
    python scripts/model_router.py list-providers --json
    python scripts/model_router.py test --provider claude --model claude-sonnet-4-6
    python scripts/model_router.py switch --agent bravo --provider openai --model gpt-5.4
    python scripts/model_router.py show-config
    python scripts/model_router.py route --agent atlas --task-type analysis --json

DESIGN
------
1. Single registry. Providers are exposed only when their auth env is present.
2. YAML config. `brain/MODEL_CONFIG.md` stores per-agent preferences and
   explicit fallbacks in human-editable YAML.
3. Unified call interface. Anthropic, OpenAI-compatible APIs, and local
   Ollama all normalize to the same `{text, tokens, cost}` return shape.
4. Fail closed. Missing keys, unknown models, or provider call failures
   return structured errors rather than half-working implicit fallbacks.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "brain" / "MODEL_CONFIG.md"

PROVIDER_SPECS: dict[str, dict[str, Any]] = {
    "claude": {
        "env_var": "ANTHROPIC_API_KEY",
        "models": ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"],
        "pricing": {
            "claude-opus-4-7": (15.0, 75.0),
            "claude-sonnet-4-6": (3.0, 15.0),
            "claude-haiku-4-5": (1.0, 5.0),
        },
    },
    "openai": {
        "env_var": "OPENAI_API_KEY",
        "models": ["gpt-5.4", "gpt-5.4-mini"],
        "pricing": {"gpt-5.4": (5.0, 15.0), "gpt-5.4-mini": (0.6, 2.4)},
    },
    "openrouter": {
        "env_var": "OPENROUTER_API_KEY",
        "models": [
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o",
            "deepseek/deepseek-r1",
            "nous/hermes-3",
        ],
        "pricing": {},
    },
    "groq": {
        "env_var": "GROQ_API_KEY",
        "models": ["llama-3.3-70b", "mixtral-8x7b"],
        "pricing": {},
    },
    "deepseek": {
        "env_var": "DEEPSEEK_API_KEY",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "pricing": {},
    },
    "local": {
        "env_var": "LOCAL_LLM_ENDPOINT",
        "models": ["ollama/*"],
        "pricing": {},
    },
}

TASK_TYPE_PREFERENCES: dict[str, list[tuple[str, str]]] = {
    "coding": [
        ("openai", "gpt-5.4"),
        ("claude", "claude-sonnet-4-6"),
        ("deepseek", "deepseek-reasoner"),
        ("groq", "llama-3.3-70b"),
    ],
    "analysis": [
        ("claude", "claude-opus-4-7"),
        ("openai", "gpt-5.4"),
        ("deepseek", "deepseek-reasoner"),
    ],
    "fast": [
        ("claude", "claude-haiku-4-5"),
        ("openai", "gpt-5.4-mini"),
        ("groq", "mixtral-8x7b"),
        ("local", "ollama/*"),
    ],
    "cheap": [
        ("local", "ollama/*"),
        ("groq", "mixtral-8x7b"),
        ("openrouter", "nous/hermes-3"),
        ("claude", "claude-haiku-4-5"),
    ],
}


def load_env() -> dict[str, str]:
    """Load `.env.agents` via python-dotenv and return the visible env slice."""
    env_file = PROJECT_ROOT / ".env.agents"
    try:
        from dotenv import dotenv_values, load_dotenv  # type: ignore
    except ImportError:
        return {}
    load_dotenv(env_file)
    raw = dotenv_values(env_file)
    return {k: str(v) for k, v in raw.items() if v is not None}


def _default_config() -> dict[str, Any]:
    fallback = [{"provider": "claude", "model": "claude-haiku-4-5"}]
    return {
        "version": 1,
        "defaults": {"provider": "claude", "model": "claude-sonnet-4-6", "fallbacks": fallback},
        "agents": {
            name: {"provider": "claude", "model": "claude-sonnet-4-6", "fallbacks": fallback}
            for name in ("bravo", "atlas", "maven", "aura")
        },
        "task_types": {},
    }


def _read_config() -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pyyaml is required for MODEL_CONFIG.md") from exc
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(yaml.safe_dump(_default_config(), sort_keys=False), encoding="utf-8")
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RuntimeError("brain/MODEL_CONFIG.md must contain a YAML mapping")
    return data


def _write_config(data: dict[str, Any]) -> None:
    import yaml  # type: ignore
    CONFIG_PATH.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _local_models(timeout: int = 4) -> list[str]:
    endpoint = os.environ.get("LOCAL_LLM_ENDPOINT", "").rstrip("/")
    if not endpoint:
        return []
    req = urllib.request.Request(f"{endpoint}/api/tags")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = [f"ollama/{m.get('name')}" for m in data.get("models") or [] if m.get("name")]
        return names or ["ollama/*"]
    except Exception:
        return ["ollama/*"]


def list_providers(include_unavailable: bool = True) -> list[dict[str, Any]]:
    """Return all registered providers with availability flag.

    `available` is True when the provider's auth env var is present (and, for
    `local`, when the Ollama endpoint responds). When `include_unavailable` is
    False, only providers with credentials present are returned.
    """
    load_env()
    rows: list[dict[str, Any]] = []
    for provider, spec in PROVIDER_SPECS.items():
        env_present = bool(os.environ.get(spec["env_var"]))
        if provider == "local":
            local_models = _local_models()
            available = env_present and bool(local_models) and local_models != ["ollama/*"]
            models = local_models or list(spec["models"])
        else:
            available = env_present
            models = list(spec["models"])
        if not available and not include_unavailable:
            continue
        rows.append({
            "provider": provider,
            "env_var": spec["env_var"],
            "models": models,
            "available": available,
        })
    return rows


def _provider_defaults(provider: str, model: str) -> list[dict[str, str]]:
    models = _local_models() if provider == "local" else list(PROVIDER_SPECS[provider]["models"])
    choices = [m for m in models if m != model]
    return [{"provider": provider, "model": m} for m in choices[:2]]


def _candidate_sequence(agent: str, task_type: Optional[str]) -> list[dict[str, str]]:
    cfg = _read_config()
    base = dict(cfg.get("defaults") or {})
    base.update((cfg.get("agents") or {}).get(agent) or {})
    if task_type:
        base.update((cfg.get("task_types") or {}).get(task_type) or {})
    seq: list[dict[str, str]] = []
    if base.get("provider") and base.get("model"):
        seq.append({"provider": base["provider"], "model": base["model"]})
    seq.extend(base.get("fallbacks") or [])
    if task_type:
        seq.extend({"provider": p, "model": m} for p, m in TASK_TYPE_PREFERENCES.get(task_type, []))
    for provider, spec in PROVIDER_SPECS.items():
        first_model = _local_models()[0] if provider == "local" and _local_models() else spec["models"][0]
        seq.append({"provider": provider, "model": first_model})
    dedup: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in seq:
        key = (str(row.get("provider")), str(row.get("model")))
        if key not in seen:
            seen.add(key)
            dedup.append({"provider": key[0], "model": key[1]})
    return dedup


def _available_models() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in list_providers():
        out[row["provider"]] = list(row["models"])
    return out


def resolve(agent: str, task_type: str | None = None) -> dict[str, Any]:
    """Resolve the preferred model for an agent + task type."""
    load_env()
    available = _available_models()
    chosen: Optional[dict[str, str]] = None
    fallbacks: list[dict[str, str]] = []
    for candidate in _candidate_sequence(agent, task_type):
        provider = candidate["provider"]
        model = candidate["model"]
        models = available.get(provider) or []
        if model == "ollama/*" and models:
            model = models[0]
        if provider in available and (model in models or model == "ollama/*"):
            row = {"provider": provider, "model": model}
            if chosen is None:
                chosen = row
            else:
                fallbacks.append(row)
    if chosen is None:
        cfg = _read_config()
        base = (cfg.get("agents") or {}).get(agent) or cfg.get("defaults") or {}
        chosen = {"provider": base.get("provider", "claude"), "model": base.get("model", "claude-sonnet-4-6")}
        fallbacks = list(base.get("fallbacks") or [])
    return {
        "agent": agent,
        "task_type": task_type,
        "provider": chosen["provider"],
        "model": chosen["model"],
        "fallbacks": fallbacks[:4],
    }


def _usage_to_cost(provider: str, model: str, tokens_in: int, tokens_out: int) -> float:
    price = PROVIDER_SPECS.get(provider, {}).get("pricing", {}).get(model)
    if not price:
        return 0.0
    per_in, per_out = price
    return round(((tokens_in / 1_000_000.0) * per_in) + ((tokens_out / 1_000_000.0) * per_out), 6)


def _messages_to_text(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, str]]]:
    system_parts: list[str] = []
    chat: list[dict[str, str]] = []
    for msg in messages:
        role = str(msg.get("role") or "user")
        content = str(msg.get("content") or "")
        if role == "system":
            system_parts.append(content)
        else:
            chat.append({"role": role, "content": content})
    return "\n\n".join(system_parts), chat or [{"role": "user", "content": "Reply with OK."}]


def _openai_like(provider: str, model: str, api_key: str, base_url: Optional[str], messages: list[dict[str, Any]], max_tokens: int) -> dict[str, Any]:
    from openai import OpenAI  # type: ignore

    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    system_prompt, chat = _messages_to_text(messages)
    try:
        resp = client.responses.create(model=model, input=[{"role": m["role"], "content": m["content"]} for m in chat], instructions=system_prompt or None, max_output_tokens=max_tokens)
        text = (getattr(resp, "output_text", None) or "").strip()
        usage = getattr(resp, "usage", None)
        tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
        return {"text": text, "tokens_in": tokens_in, "tokens_out": tokens_out}
    except Exception:
        if system_prompt:
            chat = [{"role": "system", "content": system_prompt}] + chat
        resp = client.chat.completions.create(model=model, messages=chat, max_tokens=max_tokens)
        text = (resp.choices[0].message.content or "").strip()
        usage = getattr(resp, "usage", None)
        tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
        return {"text": text, "tokens_in": tokens_in, "tokens_out": tokens_out}


def call(messages: list[dict], agent: str | None = None, model: str | None = None, max_tokens: int = 1024) -> dict[str, Any]:
    """Unified call interface across Anthropic, OpenAI-compatible, and Ollama."""
    load_env()
    route = resolve(agent or "bravo") if model is None else None
    provider = route["provider"] if route else next((p for p, s in PROVIDER_SPECS.items() if model in s["models"]), "local" if str(model).startswith("ollama/") else "")
    chosen_model = model or route["model"]
    start = time.perf_counter()
    if provider == "claude":
        import anthropic  # type: ignore

        system_prompt, chat = _messages_to_text(messages)
        kwargs: dict[str, Any] = {
            "model": chosen_model,
            "max_tokens": max_tokens,
            "messages": chat,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        resp = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]).messages.create(**kwargs)
        text = "".join(block.text for block in resp.content if hasattr(block, "text")).strip()
        tokens_in = int(getattr(resp.usage, "input_tokens", 0) or 0)
        tokens_out = int(getattr(resp.usage, "output_tokens", 0) or 0)
    elif provider == "openai":
        payload = _openai_like(provider, chosen_model, os.environ["OPENAI_API_KEY"], None, messages, max_tokens)
        text, tokens_in, tokens_out = payload["text"], payload["tokens_in"], payload["tokens_out"]
    elif provider == "openrouter":
        payload = _openai_like(provider, chosen_model, os.environ["OPENROUTER_API_KEY"], "https://openrouter.ai/api/v1", messages, max_tokens)
        text, tokens_in, tokens_out = payload["text"], payload["tokens_in"], payload["tokens_out"]
    elif provider == "groq":
        api_model = {"llama-3.3-70b": "llama-3.3-70b-versatile", "mixtral-8x7b": "mixtral-8x7b-32768"}.get(chosen_model, chosen_model)
        payload = _openai_like(provider, api_model, os.environ["GROQ_API_KEY"], "https://api.groq.com/openai/v1", messages, max_tokens)
        text, tokens_in, tokens_out = payload["text"], payload["tokens_in"], payload["tokens_out"]
    elif provider == "deepseek":
        payload = _openai_like(provider, chosen_model, os.environ["DEEPSEEK_API_KEY"], "https://api.deepseek.com/v1", messages, max_tokens)
        text, tokens_in, tokens_out = payload["text"], payload["tokens_in"], payload["tokens_out"]
    elif provider == "local":
        endpoint = os.environ["LOCAL_LLM_ENDPOINT"].rstrip("/")
        _, chat = _messages_to_text(messages)
        ollama_model = chosen_model.split("/", 1)[1] if chosen_model.startswith("ollama/") else chosen_model
        body = json.dumps({"model": ollama_model, "messages": chat, "stream": False, "options": {"num_predict": max_tokens}}).encode("utf-8")
        req = urllib.request.Request(f"{endpoint}/api/chat", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = str(((data.get("message") or {}).get("content")) or "").strip()
        tokens_in = int(data.get("prompt_eval_count") or 0)
        tokens_out = int(data.get("eval_count") or 0)
    else:
        raise RuntimeError(f"Unknown provider for model '{chosen_model}'")
    latency_ms = round((time.perf_counter() - start) * 1000.0, 2)
    return {
        "text": text,
        "provider": provider,
        "model": chosen_model,
        "latency_ms": latency_ms,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": _usage_to_cost(provider, chosen_model, tokens_in, tokens_out),
    }


def test_connection(provider: str, model: str, timeout: int = 10) -> dict[str, Any]:
    """Run a one-shot completion test against the selected provider."""
    start = time.perf_counter()
    try:
        result = call(
            messages=[{"role": "user", "content": "Reply with OK."}],
            agent=None,
            model=model,
            max_tokens=32,
        )
        return {"ok": bool(result.get("text")), "provider": provider, "model": model, "latency_ms": round((time.perf_counter() - start) * 1000.0, 2)}
    except Exception as exc:
        if isinstance(exc, urllib.error.URLError):
            error = str(exc.reason)
        else:
            error = str(exc)
        return {"ok": False, "provider": provider, "model": model, "latency_ms": round((time.perf_counter() - start) * 1000.0, 2), "error": error[:300]}


def _print(obj: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, indent=2, default=str))
    elif isinstance(obj, dict) and any(k in obj for k in ("provider", "model", "fallbacks")):
        print(json.dumps(obj, indent=2, default=str))
    else:
        print(obj)


def main() -> None:
    load_env()
    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument("--json", action="store_true", dest="output_json")

    parser = argparse.ArgumentParser(description="Provider registry + per-agent model router.")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list-providers", parents=[json_parent], help="List providers with keys present")

    p_test = sub.add_parser("test", parents=[json_parent], help="Run one-shot completion test")
    p_test.add_argument("--provider", required=True, choices=sorted(PROVIDER_SPECS))
    p_test.add_argument("--model", required=True)
    p_test.add_argument("--timeout", type=int, default=10)

    p_switch = sub.add_parser("switch", parents=[json_parent], help="Persist per-agent model override")
    p_switch.add_argument("--agent", required=True)
    p_switch.add_argument("--provider", required=True, choices=sorted(PROVIDER_SPECS))
    p_switch.add_argument("--model", required=True)

    sub.add_parser("show-config", parents=[json_parent], help="Show MODEL_CONFIG.md")

    p_route = sub.add_parser("route", parents=[json_parent], help="Resolve provider/model/fallbacks")
    p_route.add_argument("--agent", required=True)
    p_route.add_argument("--task-type", default=None)

    p_call = sub.add_parser("call", parents=[json_parent], help="Send a real prompt and return the model's reply")
    p_call.add_argument("--agent", default="bravo")
    p_call.add_argument("--model", default=None, help="Override resolved model")
    p_call.add_argument("--system", default=None, help="System prompt (optional)")
    p_call.add_argument("--message", required=True, help="User message")
    p_call.add_argument("--max-tokens", type=int, default=512)

    args = parser.parse_args()
    if args.command == "list-providers":
        _print(list_providers(), args.output_json or True)
    elif args.command == "test":
        _print(test_connection(args.provider, args.model, args.timeout), args.output_json or True)
    elif args.command == "switch":
        cfg = _read_config()
        cfg.setdefault("agents", {})
        cfg["agents"][args.agent] = {
            "provider": args.provider,
            "model": args.model,
            "fallbacks": _provider_defaults(args.provider, args.model),
        }
        _write_config(cfg)
        _print(cfg["agents"][args.agent], args.output_json or True)
    elif args.command == "show-config":
        _print(_read_config(), args.output_json or True)
    elif args.command == "route":
        _print(resolve(args.agent, args.task_type), args.output_json or True)
    elif args.command == "call":
        msgs: list[dict] = []
        if args.system:
            msgs.append({"role": "system", "content": args.system})
        msgs.append({"role": "user", "content": args.message})
        _print(call(messages=msgs, agent=args.agent, model=args.model, max_tokens=args.max_tokens), args.output_json or True)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
