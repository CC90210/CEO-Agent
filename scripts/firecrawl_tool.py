"""
Firecrawl CLI Tool -- Web Scraping & Structured Extraction
Fallback to the Firecrawl MCP server. Reads FIRECRAWL_API_KEY from .env.agents.
All credentials loaded from .env.agents (never hardcoded).

Usage (from any agent via terminal):
  python scripts/firecrawl_tool.py scrape <url>              # Scrape page -> clean markdown
  python scripts/firecrawl_tool.py crawl <url> [--limit 10]  # Crawl site (max pages)
  python scripts/firecrawl_tool.py search <query>            # Search and scrape results
  python scripts/firecrawl_tool.py extract <url> --schema {} # Extract structured data
  python scripts/firecrawl_tool.py map <url>                 # Get site map / all URLs

Flags:
  --json    Output raw JSON for agent consumption
  --limit   Max pages to crawl (crawl command, default: 10)
  --schema  JSON schema string for structured extraction (extract command)
"""

import argparse
import json
import sys
from pathlib import Path

# Fix Windows console encoding for unicode/emoji content
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ANSI color codes -- suppressed when piping or when --json is used
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_CYAN   = "\033[36m"
_RED    = "\033[31m"
_DIM    = "\033[2m"


def _c(code: str, text: str, json_mode: bool) -> str:
    """Wrap text in ANSI code only for terminal output."""
    if json_mode or not sys.stdout.isatty():
        return text
    return f"{code}{text}{_RESET}"


def load_env() -> dict:
    """Load .env.agents from project root."""
    env_path = Path(__file__).resolve().parent.parent / ".env.agents"
    if not env_path.exists():
        print(f"ERROR: {env_path} not found", file=sys.stderr)
        sys.exit(1)

    env_vars: dict = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


def get_app(env_vars: dict):
    """Initialise FirecrawlApp with the API key from .env.agents."""
    try:
        from firecrawl import FirecrawlApp
    except ImportError:
        print(
            "ERROR: 'firecrawl-py' not installed. Run: pip install firecrawl-py",
            file=sys.stderr,
        )
        sys.exit(1)

    api_key = env_vars.get("FIRECRAWL_API_KEY")
    if not api_key:
        print(
            "ERROR: FIRECRAWL_API_KEY not found in .env.agents.\n"
            "  Add: FIRECRAWL_API_KEY=fc-xxx",
            file=sys.stderr,
        )
        sys.exit(1)

    return FirecrawlApp(api_key=api_key)


# -- Commands ----------------------------------------------


def _to_dict(obj):
    """Convert firecrawl response objects to plain dicts."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    return obj


def cmd_scrape(app, args) -> None:
    """Scrape a single page and return clean markdown."""
    jm = args.output_json
    result = _to_dict(app.scrape(args.url, formats=["markdown"]))

    if jm:
        print(json.dumps(result, indent=2, default=str))
        return

    markdown = result.get("markdown", "")
    metadata = result.get("metadata", {})
    title = metadata.get("title", args.url)
    desc = metadata.get("description", "")

    print(_c(_BOLD + _CYAN, f"Scraped: {title}", jm))
    if desc:
        print(_c(_DIM, desc, jm))
    print(_c(_DIM, f"URL: {args.url}", jm))
    print()
    print(markdown)
    print()
    print(_c(_DIM, f"--- {len(markdown)} characters ---", jm))


def cmd_crawl(app, args) -> None:
    """Crawl a site up to --limit pages and return markdown for each."""
    jm = args.output_json
    raw = app.crawl(args.url, limit=args.limit)
    result = _to_dict(raw)

    if jm:
        print(json.dumps(result, indent=2, default=str))
        return

    pages = result.get("data", result.get("results", []))
    print(_c(_BOLD + _CYAN, f"Crawl complete: {args.url}", jm))
    print(_c(_DIM, f"Pages crawled: {len(pages)} (limit: {args.limit})", jm))
    print()

    for i, page in enumerate(pages, 1):
        meta = page.get("metadata", {})
        url = meta.get("url", meta.get("sourceURL", "?"))
        title = meta.get("title", url)
        md = page.get("markdown", "")
        print(_c(_BOLD, f"[{i}] {title}", jm))
        print(_c(_DIM, f"    {url}", jm))
        # Show first 300 chars of each page as preview
        preview = md[:300].replace("\n", " ").strip()
        if preview:
            print(f"    {preview}{'...' if len(md) > 300 else ''}")
        print()

    print(_c(_DIM, f"--- {len(pages)} page(s) crawled ---", jm))


def cmd_search(app, args) -> None:
    """Search and scrape results."""
    jm = args.output_json
    raw = app.search(args.query)
    result = _to_dict(raw)

    if jm:
        print(json.dumps(result, indent=2, default=str))
        return

    data = result.get("data", result.get("results", []))
    print(_c(_BOLD + _CYAN, f'Search: "{args.query}"', jm))
    print(_c(_DIM, f"Results: {len(data)}", jm))
    print()

    for i, item in enumerate(data, 1):
        title = item.get("title", "No title")
        url = item.get("url", "")
        desc = item.get("description", "")
        md = item.get("markdown", "")
        print(_c(_BOLD, f"[{i}] {title}", jm))
        print(_c(_DIM, f"    {url}", jm))
        if desc:
            print(f"    {desc[:200]}")
        if md and not desc:
            preview = md[:200].replace("\n", " ").strip()
            print(f"    {preview}{'...' if len(md) > 200 else ''}")
        print()

    print(_c(_DIM, f"--- {len(data)} result(s) ---", jm))


def cmd_extract(app, args) -> None:
    """Extract structured data from a page using a JSON schema."""
    jm = args.output_json

    schema = None
    if args.schema:
        try:
            schema = json.loads(args.schema)
        except json.JSONDecodeError as exc:
            print(f"ERROR: Invalid JSON schema -- {exc}", file=sys.stderr)
            sys.exit(1)

    raw = app.extract([args.url], schema=schema)
    result = _to_dict(raw)

    if jm:
        print(json.dumps(result, indent=2, default=str))
        return

    extracted = result.get("extract", result)
    print(_c(_BOLD + _CYAN, f"Extracted: {args.url}", jm))
    print()
    print(json.dumps(extracted, indent=2, default=str))
    print()
    print(_c(_DIM, "--- extraction complete ---", jm))


def cmd_map(app, args) -> None:
    """Get site map -- all crawlable URLs for a domain."""
    jm = args.output_json
    raw = app.map(args.url)
    result = _to_dict(raw)

    if jm:
        print(json.dumps(result, indent=2, default=str))
        return

    links = result.get("links", result.get("urls", []))
    print(_c(_BOLD + _CYAN, f"Site Map: {args.url}", jm))
    print(_c(_DIM, f"URLs found: {len(links)}", jm))
    print()

    for url in links:
        print(f"  {url}")

    print()
    print(_c(_DIM, f"--- {len(links)} URL(s) ---", jm))


# -- Entry Point -------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Firecrawl CLI Tool -- Web scraping and structured extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s scrape https://example.com
  %(prog)s scrape https://example.com --json
  %(prog)s crawl https://example.com --limit 20
  %(prog)s search "AI automation agencies Ontario"
  %(prog)s extract https://example.com --schema '{"type":"object","properties":{"price":{"type":"string"}}}'
  %(prog)s map https://example.com

Credentials: FIRECRAWL_API_KEY in .env.agents (get key at firecrawl.dev)
Skill: skills/web-scraping/SKILL.md -- Firecrawl vs Playwright decision guide
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # scrape
    p_scrape = subparsers.add_parser("scrape", help="Scrape a single page -> markdown")
    p_scrape.add_argument("url", help="URL to scrape")
    p_scrape.add_argument(
        "--json", dest="output_json", action="store_true", help="Output raw JSON"
    )

    # crawl
    p_crawl = subparsers.add_parser("crawl", help="Crawl a site (follows links)")
    p_crawl.add_argument("url", help="Starting URL")
    p_crawl.add_argument(
        "--limit", "-l", type=int, default=10, help="Max pages to crawl (default: 10)"
    )
    p_crawl.add_argument(
        "--json", dest="output_json", action="store_true", help="Output raw JSON"
    )

    # search
    p_search = subparsers.add_parser("search", help="Search and scrape results")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument(
        "--json", dest="output_json", action="store_true", help="Output raw JSON"
    )

    # extract
    p_extract = subparsers.add_parser(
        "extract", help="Extract structured data with JSON schema"
    )
    p_extract.add_argument("url", help="URL to extract from")
    p_extract.add_argument(
        "--schema",
        default="",
        help='JSON schema string, e.g. \'{"type":"object","properties":{"price":{"type":"string"}}}\'',
    )
    p_extract.add_argument(
        "--json", dest="output_json", action="store_true", help="Output raw JSON"
    )

    # map
    p_map = subparsers.add_parser("map", help="Get site map / all URLs for a domain")
    p_map.add_argument("url", help="Domain URL to map")
    p_map.add_argument(
        "--json", dest="output_json", action="store_true", help="Output raw JSON"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    env_vars = load_env()
    app = get_app(env_vars)

    commands = {
        "scrape": cmd_scrape,
        "crawl": cmd_crawl,
        "search": cmd_search,
        "extract": cmd_extract,
        "map": cmd_map,
    }

    try:
        commands[args.command](app, args)
    except Exception as exc:
        jm = getattr(args, "output_json", False)
        if jm:
            print(json.dumps({"error": str(exc)}, indent=2))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
