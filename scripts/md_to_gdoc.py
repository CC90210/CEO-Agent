#!/usr/bin/env python3
"""
md_to_gdoc — Export a markdown file to Google Docs with branded styling.

Thin wrapper around `scripts/google_tool.py docs create`:
  1. Strips YAML frontmatter
  2. Converts markdown -> HTML with inline CSS (tables, code, blockquotes, links)
  3. Calls google_tool.py to upload as a Google Doc
  4. Returns the Doc URL

Usage:
    python scripts/md_to_gdoc.py brain/TOOL_SHED.md
    python scripts/md_to_gdoc.py brain/TOOL_SHED.md --title "Tool Shed (public)"
    python scripts/md_to_gdoc.py brain/TOOL_SHED.md --folder <drive-folder-id>
    python scripts/md_to_gdoc.py brain/TOOL_SHED.md --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

try:
    import markdown
except ImportError:
    print("ERROR: pip install markdown", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
GOOGLE_TOOL = REPO_ROOT / "scripts" / "google_tool.py"

CSS = """
<style>
  body { font-family: -apple-system, Segoe UI, Arial, sans-serif; line-height: 1.55; color: #222; }
  h1 { color: #1a1a1a; border-bottom: 2px solid #333; padding-bottom: 6px; }
  h2 { color: #2c2c2c; margin-top: 26px; border-bottom: 1px solid #ccc; padding-bottom: 4px; }
  h3 { color: #3c3c3c; margin-top: 20px; }
  code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-family: Consolas, monospace; font-size: 0.92em; }
  pre { background: #f4f4f4; padding: 12px; border-radius: 5px; overflow-x: auto; font-size: 0.88em; }
  pre code { background: none; padding: 0; }
  table { border-collapse: collapse; margin: 12px 0; width: 100%; }
  th, td { border: 1px solid #ccc; padding: 8px 10px; text-align: left; vertical-align: top; }
  th { background: #f0f0f0; font-weight: 600; }
  blockquote { border-left: 4px solid #5a9; padding: 6px 14px; background: #f6fbf9; color: #333; margin: 12px 0; }
  a { color: #0969da; text-decoration: none; }
  a:hover { text-decoration: underline; }
  ul, ol { padding-left: 26px; }
  li { margin: 4px 0; }
  hr { border: none; border-top: 1px solid #ddd; margin: 24px 0; }
</style>
"""


def strip_frontmatter(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[end + 5:]
    return text


def md_to_html(md_path: Path) -> str:
    raw = md_path.read_text(encoding="utf-8")
    body = strip_frontmatter(raw)
    html_body = markdown.markdown(
        body,
        extensions=["extra", "tables", "fenced_code", "toc", "sane_lists"],
    )
    return f"<!DOCTYPE html><html><head><meta charset=\"utf-8\">{CSS}</head><body>{html_body}</body></html>"


def default_title(md_path: Path) -> str:
    # Prefer the first H1 in the file, falling back to a slugified filename.
    for line in md_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return md_path.stem.replace("_", " ").replace("-", " ").title()


def upload(html_path: Path, title: str, folder: str | None) -> dict:
    cmd = [sys.executable, str(GOOGLE_TOOL), "docs", "create",
           "--title", title, "--html", str(html_path), "--json"]
    if folder:
        cmd += ["--folder", folder]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, creationflags=WINDOWLESS_FLAGS)
    if result.returncode != 0:
        raise RuntimeError(f"google_tool failed: {result.stderr or result.stdout}")
    # google_tool.py --json emits a Drive file object; parse the last JSON object
    # off stdout (some tools prefix log lines).
    out = result.stdout.strip()
    brace = out.find("{")
    if brace == -1:
        raise RuntimeError(f"no JSON in output: {out}")
    return json.loads(out[brace:])


def main() -> int:
    p = argparse.ArgumentParser(description="Export a markdown file to Google Docs with styling")
    p.add_argument("file", help="Path to markdown file (relative to repo root or absolute)")
    p.add_argument("--title", help="Doc title (default: first H1 or filename)")
    p.add_argument("--folder", help="Google Drive folder ID")
    p.add_argument("--json", action="store_true", help="Emit JSON (id, name, url)")
    args = p.parse_args()

    md_path = Path(args.file)
    if not md_path.is_absolute():
        md_path = REPO_ROOT / md_path
    if not md_path.exists():
        print(f"ERROR: not found: {md_path}", file=sys.stderr)
        return 1

    title = args.title or default_title(md_path)

    # Stage HTML inside repo tmp/ (google_tool.py sandbox rejects paths outside repo root).
    tmp_dir = REPO_ROOT / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    html_path = tmp_dir / f"gdoc_{uuid.uuid4().hex[:8]}.html"
    html_path.write_text(md_to_html(md_path), encoding="utf-8")

    try:
        doc = upload(html_path, title, args.folder)
    finally:
        html_path.unlink(missing_ok=True)

    doc_id = doc.get("id", "")
    url = f"https://docs.google.com/document/d/{doc_id}/edit" if doc_id else ""

    if args.json:
        print(json.dumps({"id": doc_id, "name": doc.get("name"), "url": url}, indent=2))
    else:
        print(f"Created: {doc.get('name')}")
        print(f"URL:     {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
