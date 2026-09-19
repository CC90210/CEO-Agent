#!/usr/bin/env python
"""Create oasis-store's Cloudflare resources (R2 bucket + KV namespace) and stamp the KV id.

    python scripts/integrations/oasis_store_cf_bootstrap.py

Reuses wrangler_tool's token injection (_wrangler_env) so the Cloudflare token
never leaves the child process. Idempotent: an existing bucket/namespace is
detected and reused. Writes the KV namespace id into the app's wrangler.jsonc.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

import wrangler_tool as wt  # noqa: E402
from lib.app_registry import app_dir  # noqa: E402

SLUG = "oasis-store"
BUCKET = "oasis-store-media"
KV_TITLE = "STORE_KV"


def _registry() -> dict:
    return json.loads((PROJECT_ROOT / "config" / "cloudflare" / "apps.json").read_text(encoding="utf-8"))


def _wrangler(args: list[str], cwd: Path, env: dict) -> str:
    proc = subprocess.run([wt._npx(), "wrangler", *args], cwd=str(cwd), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=False)
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise SystemExit(f"wrangler {' '.join(args)} failed ({proc.returncode}):\n{out[-1200:]}")
    return out


def main() -> int:
    registry = _registry()
    cwd = app_dir(SLUG)
    env = wt._wrangler_env(registry)

    # R2
    buckets = _wrangler(["r2", "bucket", "list"], cwd, env)
    if BUCKET in buckets:
        print(f"r2: {BUCKET} exists")
    else:
        _wrangler(["r2", "bucket", "create", BUCKET], cwd, env)
        print(f"r2: created {BUCKET}")

    # KV
    listing = _wrangler(["kv", "namespace", "list"], cwd, env)
    kv_id = None
    try:
        start = listing.index("[")
        for ns in json.loads(listing[start:]):
            if ns.get("title") == KV_TITLE:
                kv_id = ns.get("id")
    except (ValueError, json.JSONDecodeError):
        pass
    if kv_id:
        print(f"kv: {KV_TITLE} exists ({kv_id})")
    else:
        out = _wrangler(["kv", "namespace", "create", "STORE_KV"], cwd, env)
        m = re.search(r'"?id"?\s*[:=]\s*"?([0-9a-f]{32})"?', out)
        if not m:
            raise SystemExit(f"could not parse KV id from:\n{out[-800:]}")
        kv_id = m.group(1)
        print(f"kv: created {KV_TITLE} ({kv_id})")

    cfg = cwd / "wrangler.jsonc"
    text = cfg.read_text(encoding="utf-8")
    new = re.sub(r'"id":\s*"[^"]*"(\s*\})', f'"id": "{kv_id}"\\1', text, count=1)
    if new != text:
        cfg.write_text(new, encoding="utf-8")
        print(f"wrangler.jsonc: STORE_KV id set")
    else:
        print("wrangler.jsonc: unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
