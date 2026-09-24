from __future__ import annotations

import importlib.util
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "scripts" / "integrations" / "wrangler_tool.py"
SPEC = importlib.util.spec_from_file_location("wrangler_tool_system_ca_test", MODULE_PATH)
assert SPEC and SPEC.loader
wrangler_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wrangler_tool)


def test_wrangler_env_uses_windows_system_ca(monkeypatch):
    monkeypatch.setattr(wrangler_tool, "_secrets", lambda: {"CF": "token"})
    monkeypatch.setattr(wrangler_tool, "_cf_token", lambda loaded: loaded["CF"])
    monkeypatch.setattr(wrangler_tool, "_account_id", lambda registry, loaded: "acct")
    monkeypatch.setenv("NODE_OPTIONS", "--max-old-space-size=4096")

    child = wrangler_tool._wrangler_env({})

    assert child["NODE_OPTIONS"] == "--max-old-space-size=4096 --use-system-ca"


def test_wrangler_env_does_not_duplicate_system_ca(monkeypatch):
    monkeypatch.setattr(wrangler_tool, "_secrets", lambda: {"CF": "token"})
    monkeypatch.setattr(wrangler_tool, "_cf_token", lambda loaded: loaded["CF"])
    monkeypatch.setattr(wrangler_tool, "_account_id", lambda registry, loaded: "acct")
    monkeypatch.setenv("NODE_OPTIONS", "--use-system-ca")

    child = wrangler_tool._wrangler_env({})

    assert child["NODE_OPTIONS"] == "--use-system-ca"
