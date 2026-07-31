#!/usr/bin/env python3
"""custom_llm_client.py — Client library for self-hosted Bravo Custom LLM API server.

Reads CUSTOM_LLM_BASE_URL and CUSTOM_LLM_API_KEY from .env.agents (or environment variables)
and provides standard OpenAI-compatible completion & chat methods for Business-Empire-Agent tools.

Usage:
  python scripts/lib/custom_llm_client.py --health
  python scripts/lib/custom_llm_client.py --prompt "What is the status of our system?"
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# Load env variables from .env.agents
env_file = PROJECT_ROOT / ".env.agents"
if env_file.is_file():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))

try:
    import urllib.request
    import json
except ImportError:
    pass

class CustomLLMClient:
    """Client wrapper for self-hosted OpenAI-compatible LLM endpoint."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self.base_url = (base_url or os.environ.get("CUSTOM_LLM_BASE_URL", "http://localhost:4000/v1")).rstrip("/")
        # No literal default: a hardcoded fallback key is a shared secret in a
        # public repo, and it silently "works" so nobody notices it is the one
        # everyone has. Fail loudly instead — the caller must supply the key.
        self.api_key = api_key or os.environ.get("CUSTOM_LLM_API_KEY", "")
        if not self.api_key:
            raise RuntimeError(
                "CUSTOM_LLM_API_KEY is not set. Export it (or pass api_key=) before "
                "calling the custom LLM proxy — there is no default key by design."
            )
        self.model_name = model_name or os.environ.get("CUSTOM_LLM_MODEL", "bravo-custom-llm")

    def health_check(self) -> bool:
        """Verify server endpoint health."""
        url = f"{self.base_url}/models"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.api_key}"})
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status == 200
        except Exception as e:
            sys.stderr.write(f"[custom_llm_client] Health check failed: {e}\n")
            return False

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Optional[str]:
        """Send chat completion request to the custom LLM endpoint."""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                return res_data["choices"][0]["message"]["content"]
        except Exception as e:
            sys.stderr.write(f"[custom_llm_client] Request failed: {e}\n")
            return None


def main():
    parser = argparse.ArgumentParser(description="Custom LLM API Client CLI.")
    parser.add_argument("--health", action="store_true", help="Check endpoint health.")
    parser.add_argument("--prompt", type=str, help="Send test prompt to custom LLM.")
    args = parser.parse_args()

    client = CustomLLMClient()

    if args.health:
        ok = client.health_check()
        print(f"[*] Custom LLM Endpoint ({client.base_url}): {'HEALTHY [OK]' if ok else 'UNREACHABLE [FAILED]'}")
        return

    if args.prompt:
        print(f"[*] Sending prompt to {client.model_name}...")
        messages = [
            {"role": "system", "content": "You are Bravo, CC's right hand. Plain-English response."},
            {"role": "user", "content": args.prompt},
        ]
        res = client.chat_completion(messages)
        if res:
            print("\nResponse:")
            print(res)
        else:
            print("[!] Failed to receive response from custom LLM endpoint.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
