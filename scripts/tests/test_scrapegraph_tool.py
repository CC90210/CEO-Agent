from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def tool():
    return _load("scrapegraph_tool_test", ROOT / "integrations" / "scrapegraph_tool.py")


class _Response:
    ok = True
    status_code = 200
    text = ""

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def test_scrape_uses_empire_key_alias_without_exposing_it(tool, monkeypatch):
    secret = "sgai-secret-value"
    monkeypatch.setattr(tool, "load_env", lambda: {"SCRAPE_GRAPH_AI_API": secret})
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return _Response({"results": {"markdown": {"data": ["# Example"]}}})

    monkeypatch.setattr(tool.requests, "request", fake_request)
    result = tool.scrape("https://example.com")

    assert result["results"]["markdown"]["data"] == ["# Example"]
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/api/scrape")
    assert captured["headers"]["SGAI-APIKEY"] == secret
    assert secret not in captured["url"]
    assert secret not in str(captured["json"])


def test_extract_forwards_prompt_and_schema(tool, monkeypatch):
    monkeypatch.setattr(tool, "load_env", lambda: {"SGAI_API_KEY": "sgai-test"})
    captured = {}
    monkeypatch.setattr(
        tool.requests,
        "request",
        lambda method, url, **kwargs: captured.update(kwargs) or _Response({"json": {"name": "ACME"}}),
    )
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    assert tool.extract("https://example.com", "Extract company", schema)["json"]["name"] == "ACME"
    assert captured["json"] == {
        "url": "https://example.com",
        "prompt": "Extract company",
        "schema": schema,
    }


def test_missing_key_fails_loudly(tool, monkeypatch):
    monkeypatch.setattr(tool, "load_env", lambda: {})
    with pytest.raises(tool.ScrapeGraphError, match="SCRAPE_GRAPH_AI_API"):
        tool.scrape("https://example.com")


def test_http_error_includes_status_not_secret(tool, monkeypatch):
    monkeypatch.setattr(tool, "load_env", lambda: {"SCRAPE_GRAPH_AI_API": "do-not-print"})
    response = _Response({})
    response.ok = False
    response.status_code = 402
    response.text = "credits exhausted"
    monkeypatch.setattr(tool.requests, "request", lambda *args, **kwargs: response)
    with pytest.raises(tool.ScrapeGraphError, match="HTTP 402: credits exhausted") as exc:
        tool.scrape("https://example.com")
    assert "do-not-print" not in str(exc.value)
