"""ScrapeGraphAI API v2 CLI — primary public-site scraping provider.

Loads ``SCRAPE_GRAPH_AI_API`` (empire name) or ``SGAI_API_KEY`` (upstream
name) through the sanctioned secret loader. Secret values are never printed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests

CAPABILITY_META = {
    "category": "research.scraping",
    "lifecycle": "active",
    "risk": "read_only",
    "triggers": [
        "scrape a public website",
        "extract lead data from a website",
        "extract structured website information",
        "search the web and scrape results",
        "crawl a public website",
        "check scrapegraph credits",
    ],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": True, "confirm": False},
}

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from lib.secret_loader import load_env  # noqa: E402

DEFAULT_BASE_URL = "https://v2-api.scrapegraphai.com/api"
DEFAULT_TIMEOUT = 120
KEY_NAMES = ("SCRAPE_GRAPH_AI_API", "SGAI_API_KEY")


class ScrapeGraphError(RuntimeError):
    """ScrapeGraphAI could not return a usable response."""


def _config() -> tuple[str, str, int]:
    env = load_env()
    api_key = next(
        ((env.get(name) or "").strip() for name in KEY_NAMES if (env.get(name) or "").strip()),
        "",
    )
    if not api_key:
        raise ScrapeGraphError(
            "ScrapeGraphAI is not configured. Add SCRAPE_GRAPH_AI_API to .env.agents "
            "and verify with: python scripts/capability_probe.py check scrapegraphai"
        )
    base_url = (env.get("SGAI_API_URL") or DEFAULT_BASE_URL).rstrip("/")
    try:
        timeout = int(env.get("SGAI_TIMEOUT") or DEFAULT_TIMEOUT)
    except ValueError as exc:
        raise ScrapeGraphError("SGAI_TIMEOUT must be an integer number of seconds") from exc
    return api_key, base_url, timeout


def _request(method: str, path: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    api_key, base_url, timeout = _config()
    try:
        response = requests.request(
            method,
            f"{base_url}/{path.lstrip('/')}",
            headers={"SGAI-APIKEY": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise ScrapeGraphError(f"ScrapeGraphAI network failure: {exc}") from exc
    if not response.ok:
        detail = response.text[:400].replace("\n", " ")
        raise ScrapeGraphError(f"ScrapeGraphAI HTTP {response.status_code}: {detail}")
    try:
        data = response.json()
    except ValueError as exc:
        raise ScrapeGraphError("ScrapeGraphAI returned non-JSON content") from exc
    if not isinstance(data, dict):
        raise ScrapeGraphError("ScrapeGraphAI returned an unexpected response shape")
    return data


def scrape(url: str) -> dict[str, Any]:
    return _request("POST", "scrape", payload={"url": url, "formats": [{"type": "markdown"}]})


def extract(url: str, prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"url": url, "prompt": prompt}
    if schema is not None:
        payload["schema"] = schema
    return _request("POST", "extract", payload=payload)


def search(query: str, num_results: int = 5) -> dict[str, Any]:
    return _request("POST", "search", payload={"query": query, "numResults": num_results})


def crawl_start(url: str, max_pages: int = 10, max_depth: int = 2) -> dict[str, Any]:
    return _request(
        "POST",
        "crawl",
        payload={
            "url": url,
            "maxPages": max_pages,
            "maxDepth": max_depth,
            "formats": [{"type": "markdown"}],
        },
    )


def crawl_status(crawl_id: str) -> dict[str, Any]:
    return _request("GET", f"crawl/{crawl_id}")


def credits() -> dict[str, Any]:
    return _request("GET", "credits")


def _schema(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    path = Path(value)
    raw = path.read_text(encoding="utf-8") if path.is_file() else value
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ScrapeGraphError("Schema must be a JSON object")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_scrape = sub.add_parser("scrape")
    p_scrape.add_argument("url")
    p_scrape.add_argument("--json", action="store_true")

    p_extract = sub.add_parser("extract")
    p_extract.add_argument("url")
    p_extract.add_argument("--prompt", required=True)
    p_extract.add_argument("--schema")
    p_extract.add_argument("--json", action="store_true")

    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--num-results", type=int, default=5, choices=range(3, 21))
    p_search.add_argument("--json", action="store_true")

    p_crawl = sub.add_parser("crawl-start")
    p_crawl.add_argument("url")
    p_crawl.add_argument("--max-pages", type=int, default=10)
    p_crawl.add_argument("--max-depth", type=int, default=2)
    p_crawl.add_argument("--json", action="store_true")

    p_status = sub.add_parser("crawl-status")
    p_status.add_argument("crawl_id")
    p_status.add_argument("--json", action="store_true")

    p_credits = sub.add_parser("credits")
    p_credits.add_argument("--json", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "scrape":
            result = scrape(args.url)
        elif args.command == "extract":
            result = extract(args.url, args.prompt, _schema(args.schema))
        elif args.command == "search":
            result = search(args.query, args.num_results)
        elif args.command == "crawl-start":
            result = crawl_start(args.url, args.max_pages, args.max_depth)
        elif args.command == "crawl-status":
            result = crawl_status(args.crawl_id)
        else:
            result = credits()
    except (ScrapeGraphError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}) if args.json else f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **result}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
