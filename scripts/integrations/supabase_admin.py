#!/usr/bin/env python3
"""supabase_admin.py — Supabase Management API helpers from Python.

LESSON LEARNED 2026-04-30: Cloudflare in front of api.supabase.com rejects
requests with the default Python-urllib User-Agent ('Python-urllib/3.x') with
HTTP 403 + Cloudflare error code 1010. The fix: send a real browser-like
User-Agent. Wasted ~2 hours of "your token must be expired" diagnostics
before noticing 1010 is a Cloudflare bot-protection code, not a Supabase
auth-rejection code.

This module wraps the Management API with the right headers so every script
that touches it gets the fix for free.

Usage:
    from supabase_admin import api_get, api_patch
    cfg = api_get('/v1/projects/{ref}/config/auth')
    api_patch('/v1/projects/{ref}/config/auth',
              {'external_google_enabled': True, ...})
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Project root is THREE levels up from this file:
#   scripts/integrations/supabase_admin.py → scripts/integrations → scripts → <repo root>
# The file moved into scripts/integrations/ during a 2026-05-20 reorg
# without updating the parent count, which left .env.agents unloadable
# and forced every caller to re-implement env loading inline.
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# V6.8.3: migrated from python-dotenv to lib.secret_loader.
# The repo was originally named Business-Empire-Agent and got renamed
# to CEO-Agent during the 2026-05-21 split (Bravo/CEO-Agent +
# Maven/CMO-Agent + Atlas/CFO-Agent). Match either name; otherwise
# fall back to the file's grandparent (this file lives at
# <repo>/scripts/integrations/supabase_admin.py).
_REPO = Path(__file__).resolve()
_RECOGNIZED_REPO_NAMES = {'Business-Empire-Agent', 'CEO-Agent'}
while _REPO.name not in _RECOGNIZED_REPO_NAMES and _REPO.parent != _REPO:
    _REPO = _REPO.parent
if _REPO.parent == _REPO:
    _REPO = Path(__file__).resolve().parent.parent.parent
import sys as _sys
_sys.path.insert(0, str(_REPO / 'scripts'))
from lib.secret_loader import load_env as _load_env  # noqa: E402

_env = _load_env()
import os as _os
for _k, _v in _env.items():
    _os.environ.setdefault(_k, str(_v))

API_BASE = "https://api.supabase.com"

# Real-browser UA so Cloudflare doesn't 403 us with code 1010
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _headers() -> dict:
    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("SUPABASE_ACCESS_TOKEN missing in .env.agents")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": DEFAULT_UA,
    }


def _request(method: str, path: str, body: dict | None = None, timeout: int = 30) -> dict:
    url = path if path.startswith("http") else f"{API_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Supabase API {method} {path} -> {e.code}: {body_text}") from e


def api_get(path: str) -> dict:
    return _request("GET", path)


def api_post(path: str, body: dict) -> dict:
    return _request("POST", path, body)


def api_patch(path: str, body: dict) -> dict:
    return _request("PATCH", path, body)


def api_delete(path: str) -> dict:
    return _request("DELETE", path)


# ============================================================================
# CLI for ad-hoc operations
# ============================================================================
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Supabase Management API helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_get = sub.add_parser("get", help="GET a path")
    p_get.add_argument("path")

    p_patch = sub.add_parser("patch", help="PATCH a path with JSON body")
    p_patch.add_argument("path")
    p_patch.add_argument("--body", required=True, help="JSON string")

    p_oauth = sub.add_parser("enable-google-oauth", help="Enable Google provider on a project")
    p_oauth.add_argument("--project-ref", required=True)
    p_oauth.add_argument("--client-id", required=True)
    p_oauth.add_argument("--client-secret", required=True)

    args = p.parse_args()

    if args.cmd == "get":
        print(json.dumps(api_get(args.path), indent=2, default=str))
    elif args.cmd == "patch":
        print(json.dumps(api_patch(args.path, json.loads(args.body)), indent=2, default=str))
    elif args.cmd == "enable-google-oauth":
        out = api_patch(
            f"/v1/projects/{args.project_ref}/config/auth",
            {
                "external_google_enabled": True,
                "external_google_client_id": args.client_id,
                "external_google_secret": args.client_secret,
            },
        )
        print(f"google_enabled = {out.get('external_google_enabled')}")
        print(f"client_id      = {(out.get('external_google_client_id') or '')[:40]}...")
