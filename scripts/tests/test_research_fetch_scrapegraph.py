from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def fetcher():
    scripts = str(ROOT)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location("research_fetch_test", ROOT / "research_fetch.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _result(ok=True, text="x" * 200, error=None):
    return {
        "ok": ok,
        "status": 200 if ok else 402,
        "text": text,
        "title": "Example",
        "final_url": "https://example.com",
        "error": error,
    }


def test_scrapegraph_is_default_primary(fetcher, monkeypatch):
    monkeypatch.setattr(fetcher, "_reputation_lookup", lambda domain: None)
    monkeypatch.setattr(fetcher, "_call_scrapegraph", lambda url: _result())
    monkeypatch.setattr(fetcher, "_reputation_record", lambda *args: None)
    monkeypatch.setattr(fetcher, "_call_firecrawl", lambda url: pytest.fail("fallback should not run"))

    result = fetcher.fetch("https://example.com")

    assert result["ok"] is True
    assert result["tier_used"] == "scrapegraph"
    assert result["tiers_tried"] == ["scrapegraph"]


def test_firecrawl_is_fallback_after_scrapegraph_credit_failure(fetcher, monkeypatch):
    monkeypatch.setattr(fetcher, "_reputation_lookup", lambda domain: None)
    monkeypatch.setattr(fetcher, "_call_scrapegraph", lambda url: _result(False, "", "HTTP 402: credits exhausted"))
    monkeypatch.setattr(fetcher, "_call_firecrawl", lambda url: _result())
    monkeypatch.setattr(fetcher, "_reputation_record", lambda *args: None)

    result = fetcher.fetch("https://example.com")

    assert result["tier_used"] == "firecrawl"
    assert result["tiers_tried"] == ["scrapegraph", "firecrawl"]
    assert "credits exhausted" in result["errors"]["scrapegraph"]


def test_cloak_remains_separate_escalation_after_public_providers(fetcher, monkeypatch):
    monkeypatch.setattr(fetcher, "_reputation_lookup", lambda domain: None)
    monkeypatch.setattr(fetcher, "_call_scrapegraph", lambda url: _result(False, "", "blocked"))
    monkeypatch.setattr(fetcher, "_call_firecrawl", lambda url: _result(False, "", "blocked"))
    monkeypatch.setattr(fetcher, "_call_cloak", lambda url, timeout: _result())
    monkeypatch.setattr(fetcher, "_reputation_record", lambda *args: None)

    result = fetcher.fetch("https://protected.example.com")

    assert result["tier_used"] == "cloak"
    assert result["tiers_tried"] == ["scrapegraph", "firecrawl", "cloak"]


def test_force_tier_supports_scrapegraph(fetcher, monkeypatch):
    monkeypatch.setattr(fetcher, "_reputation_lookup", lambda domain: None)
    monkeypatch.setattr(fetcher, "_call_scrapegraph", lambda url: _result())
    monkeypatch.setattr(fetcher, "_reputation_record", lambda *args: None)
    result = fetcher.fetch("https://example.com", force_tier="scrapegraph")
    assert result["tiers_tried"] == ["scrapegraph"]
