"""
Remotion Video Render Script — Bravo V5.5

Renders Remotion compositions to video files.
All credentials loaded from .env.agents (never hardcoded).

Usage:
  python scripts/render_video.py quote --text "Quote text" --author "Conaugh McKenna"
  python scripts/render_video.py quote --text "Quote text" --author "CC" --output out/my_quote.mp4
  python scripts/render_video.py from-calendar <content_id>
  python scripts/render_video.py quote --text "Quote text" --json
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
REMOTION_DIR = REPO_ROOT / "remotion-content"
EXPORTS_DIR = REPO_ROOT / "media" / "exports"
ENV_PATH = REPO_ROOT / ".env.agents"


# ---------------------------------------------------------------------------
# Environment loading
# ---------------------------------------------------------------------------

def load_env() -> dict[str, str]:
    """Load .env.agents from project root. Returns key→value mapping."""
    if not ENV_PATH.exists():
        _fail(f".env.agents not found at {ENV_PATH}")
    env: dict[str, str] = {}
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    return env


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _out(data: dict, use_json: bool) -> None:
    if use_json:
        print(json.dumps(data, indent=2))
    else:
        status = data.get("status", "")
        if status == "ok":
            print(f"Rendered: {data.get('output_path')}")
            print(f"Duration:  {data.get('duration_frames')} frames @ {data.get('fps')} fps")
        else:
            print(f"ERROR: {data.get('error')}", file=sys.stderr)


def _fail(message: str, use_json: bool = False) -> None:
    data = {"status": "error", "error": message}
    if use_json:
        print(json.dumps(data, indent=2), file=sys.stderr)
    else:
        print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

def _get_supabase_client(env: dict[str, str]):
    """Create a Bravo Supabase client using service role key."""
    try:
        from supabase import create_client  # type: ignore[import-untyped]
    except ImportError:
        _fail("supabase-py not installed. Run: pip install supabase")

    url = env.get("BRAVO_SUPABASE_URL")
    key = env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        _fail("BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY missing in .env.agents")
    return create_client(url, key)


def fetch_content_calendar_entry(content_id: str, env: dict[str, str]) -> dict:
    """Fetch a single content_calendar row by id."""
    client = _get_supabase_client(env)
    result = client.table("content_calendar").select("*").eq("id", content_id).single().execute()
    if not result.data:
        _fail(f"No content_calendar entry found with id={content_id}")
    return result.data  # type: ignore[return-value]


def update_content_calendar_video_path(
    content_id: str, output_path: str, env: dict[str, str]
) -> None:
    """Store the rendered video path back on the content_calendar row."""
    client = _get_supabase_client(env)
    client.table("content_calendar").update({"video_path": output_path}).eq(
        "id", content_id
    ).execute()


# ---------------------------------------------------------------------------
# Render logic
# ---------------------------------------------------------------------------

def build_output_path(composition: str, label: str | None = None) -> Path:
    """Construct a timestamped output path inside media/exports/."""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = f"{label}_" if label else ""
    filename = f"{composition.lower()}_{slug}{timestamp}.mp4"
    return EXPORTS_DIR / filename


def render_composition(
    composition: str,
    props: dict,
    output_path: Path,
    use_json: bool,
) -> dict:
    """
    Call `npx remotion render` as a subprocess.
    Props are passed via --props as a JSON string.
    Returns a result dict.
    """
    props_json = json.dumps(props)
    cmd = [
        "npx",
        "remotion",
        "render",
        "src/index.ts",
        composition,
        str(output_path),
        "--props",
        props_json,
    ]

    if not use_json:
        print(f"Rendering {composition} → {output_path} ...")

    result = subprocess.run(
        cmd,
        cwd=str(REMOTION_DIR),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error_detail = result.stderr.strip() or result.stdout.strip()
        return {
            "status": "error",
            "error": f"remotion render failed (exit {result.returncode})",
            "detail": error_detail,
        }

    return {
        "status": "ok",
        "output_path": str(output_path),
        "composition": composition,
        "props": props,
        "duration_frames": 150,
        "fps": 30,
    }


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def cmd_quote(args: argparse.Namespace) -> None:
    use_json: bool = args.json

    output_path = Path(args.output) if args.output else build_output_path(
        "QuoteCard", label="quote"
    )

    props = {
        "quote": args.text,
        "author": args.author,
        "pillar": args.pillar,
    }

    result = render_composition("QuoteCard", props, output_path, use_json)
    _out(result, use_json)
    if result["status"] != "ok":
        sys.exit(1)


def cmd_from_calendar(args: argparse.Namespace) -> None:
    use_json: bool = args.json
    env = load_env()

    entry = fetch_content_calendar_entry(args.content_id, env)

    # Map content_calendar columns → QuoteCard props
    quote_text: str = entry.get("body") or entry.get("content") or entry.get("title") or ""
    if not quote_text:
        _fail(
            f"content_calendar entry {args.content_id} has no usable text "
            "(checked: body, content, title)",
            use_json,
        )

    author: str = entry.get("author") or "Conaugh McKenna"
    pillar: str = entry.get("pillar") or entry.get("content_type") or "quote_drop"

    output_path = build_output_path("QuoteCard", label=f"calendar_{args.content_id[:8]}")

    props = {
        "quote": quote_text,
        "author": author,
        "pillar": pillar,
    }

    result = render_composition("QuoteCard", props, output_path, use_json)

    if result["status"] == "ok":
        # Write video_path back to Supabase so late_publisher can pick it up
        update_content_calendar_video_path(args.content_id, str(output_path), env)
        result["content_id"] = args.content_id

    _out(result, use_json)
    if result["status"] != "ok":
        sys.exit(1)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render Remotion compositions to video files."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output results as JSON",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # --- quote sub-command ---
    p_quote = sub.add_parser("quote", help="Render a quote card from inline text")
    p_quote.add_argument("--text", required=True, help="Quote text")
    p_quote.add_argument(
        "--author", default="Conaugh McKenna", help="Author name (default: Conaugh McKenna)"
    )
    p_quote.add_argument(
        "--pillar", default="quote_drop", help="Content pillar tag (default: quote_drop)"
    )
    p_quote.add_argument(
        "--output", default=None, help="Output path (default: media/exports/quotecaRD_<ts>.mp4)"
    )

    # --- from-calendar sub-command ---
    p_cal = sub.add_parser(
        "from-calendar",
        help="Render a quote card from a content_calendar Supabase row",
    )
    p_cal.add_argument("content_id", help="UUID of the content_calendar row")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "quote":
        cmd_quote(args)
    elif args.command == "from-calendar":
        cmd_from_calendar(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
