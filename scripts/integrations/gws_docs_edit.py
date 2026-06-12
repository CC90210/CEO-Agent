#!/usr/bin/env python3
"""
Google Docs in-place editor.

Wraps the existing `gws` CLI to expose higher-level editing operations
that Drive MCP doesn't cover:

  - dump            Get the plain-text content of a doc (useful for
                    locating markers before editing).
  - replace-text    Atomic find/replace via Docs API replaceAllText.
  - append          Append plain text at end of body.
  - replace-section Delete the range between two markers (start
                    inclusive, end exclusive) and insert new content.
                    Falls back to end-of-body if no end marker given.
  - overwrite       Wipe doc body entirely, write fresh content.

Auth: relies on `gws auth login` (OAuth2) — same auth path the rest of
the empire gws skills use. No new credentials needed.

Empire integration:
  - Lives alongside other integration wrappers in scripts/integrations/.
  - Companion skill at skills/gws-docs-edit/SKILL.md.
  - Composes with existing gws-shared / gws-docs / gws-docs-write
    skill chain.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


# ───────────────────────────────────────────────────────────────────
# gws CLI shim
# ───────────────────────────────────────────────────────────────────

def _resolve_gws() -> list[str]:
    """Locate the gws CLI binary.

    On Windows the npm-installed gws ships as a sh script + .cmd shim.
    Python subprocess won't pick the .cmd up from `which gws`, so we
    look explicitly and fall back to the shim form `cmd /c gws`.
    """
    # Honor explicit env override
    env_path = os.environ.get("GWS_BIN")
    if env_path and Path(env_path).exists():
        return [env_path]
    # Try common npm-global locations on Windows
    candidates = [
        Path(os.environ.get("APPDATA", "")) / "npm" / "gws.cmd",
        Path(os.environ.get("APPDATA", "")) / "npm" / "gws",
        Path.home() / "AppData" / "Roaming" / "npm" / "gws.cmd",
    ]
    for c in candidates:
        if c.exists():
            return [str(c)]
    # Fall back to PATH lookup
    found = shutil.which("gws") or shutil.which("gws.cmd")
    if found:
        return [found]
    raise RuntimeError(
        "gws CLI not found. Set GWS_BIN or install with "
        "`npm install -g @googleworkspace/cli`."
    )


_GWS = _resolve_gws()


def gws(*args: str) -> dict:
    """Invoke `gws ... --format json`, parse JSON, return the body.

    Strips the `Using keyring backend: ...` prefix line that the gws
    CLI writes to stdout before the JSON body on Windows.
    """
    cmd = [*_GWS, *args, "--format", "json"]
    # Force UTF-8 — Windows defaults subprocess decoding to cp1252 which
    # blows up on em dashes / bullets / smart quotes common in real docs.
    # creationflags + startupinfo: gws is a .cmd shim on Windows; without
    # both flags the bridge sees a console pop on every doc edit.
    from lib.subprocess_helpers import WINDOWLESS_FLAGS, windowless_startupinfo
    proc = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        creationflags=WINDOWLESS_FLAGS, startupinfo=windowless_startupinfo(),
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"gws {' '.join(args[:3])} failed (exit {proc.returncode}):\n"
            f"stderr: {proc.stderr.strip()}\n"
            f"stdout: {proc.stdout.strip()[:500]}"
        )
    out = proc.stdout
    # Strip the keyring prefix line if present
    while out.startswith(("Using keyring backend", "keyring:")):
        out = out.split("\n", 1)[1] if "\n" in out else ""
    out = out.strip()
    if not out:
        return {}
    return json.loads(out)


def get_doc(doc_id: str) -> dict:
    return gws(
        "docs", "documents", "get",
        "--params", json.dumps({"documentId": doc_id}),
    )


def batch_update(doc_id: str, requests: list[dict]) -> dict:
    return gws(
        "docs", "documents", "batchUpdate",
        "--params", json.dumps({"documentId": doc_id}),
        "--json", json.dumps({"requests": requests}),
    )


# ───────────────────────────────────────────────────────────────────
# Doc traversal helpers
# ───────────────────────────────────────────────────────────────────

def paragraph_text(elem: dict) -> str:
    """Concatenate the text of all runs in a paragraph structural element."""
    para = elem.get("paragraph")
    if not para:
        return ""
    return "".join(
        r.get("textRun", {}).get("content", "")
        for r in para.get("elements", [])
    )


def dump_text(doc: dict) -> str:
    parts = [paragraph_text(e) for e in doc.get("body", {}).get("content", [])]
    return "".join(parts)


def find_section_range(
    doc: dict, start_marker: str, end_marker: str | None
) -> tuple[int, int]:
    """Return (startIndex, endIndex) for the body slice to replace.

    `startIndex` is the start of the paragraph containing start_marker.
    `endIndex` is the start of the paragraph containing end_marker, OR
    if end_marker is None or not found, the end of the body (minus 1
    to avoid the final structural newline).
    """
    content = doc.get("body", {}).get("content", [])
    start_idx: int | None = None
    end_idx: int | None = None
    for elem in content:
        text = paragraph_text(elem)
        if start_idx is None and start_marker in text:
            start_idx = elem["startIndex"]
            continue
        if start_idx is not None and end_marker and end_marker in text:
            end_idx = elem["startIndex"]
            break
    if start_idx is None:
        raise RuntimeError(f"start_marker not found: {start_marker!r}")
    if end_idx is None:
        last = content[-1]
        end_idx = last.get("endIndex", start_idx + 1) - 1
    return start_idx, end_idx


def body_end_index(doc: dict) -> int:
    """Last writable index of the doc body (one before the trailing newline)."""
    last = doc["body"]["content"][-1]
    return last.get("endIndex", 1) - 1


# ───────────────────────────────────────────────────────────────────
# Commands
# ───────────────────────────────────────────────────────────────────

def cmd_dump(args) -> None:
    print(dump_text(get_doc(args.doc)))


def cmd_replace_text(args) -> None:
    res = batch_update(args.doc, [{
        "replaceAllText": {
            "containsText": {"text": args.find, "matchCase": True},
            "replaceText": args.replace,
        }
    }])
    n = (
        res.get("replies", [{}])[0]
        .get("replaceAllText", {})
        .get("occurrencesChanged", 0)
    )
    print(f"Replaced {n} occurrence(s).")


def _resolve_text(args) -> str:
    if getattr(args, "text", None):
        return args.text
    if getattr(args, "file", None):
        return Path(args.file).read_text(encoding="utf-8")
    if getattr(args, "content", None):
        return args.content
    if getattr(args, "content_file", None):
        return Path(args.content_file).read_text(encoding="utf-8")
    raise RuntimeError("no content source given")


def cmd_append(args) -> None:
    text = _resolve_text(args)
    doc = get_doc(args.doc)
    end = body_end_index(doc)
    batch_update(args.doc, [
        {"insertText": {"location": {"index": end}, "text": text}}
    ])
    print(f"Appended {len(text)} chars at offset {end}.")


def cmd_replace_section(args) -> None:
    new_content = _resolve_text(args)
    doc = get_doc(args.doc)
    start, end = find_section_range(doc, args.start_marker, args.end_marker)
    requests: list[dict] = []
    if end > start:
        requests.append({"deleteContentRange": {
            "range": {"startIndex": start, "endIndex": end}
        }})
    requests.append({"insertText": {
        "location": {"index": start}, "text": new_content
    }})
    batch_update(args.doc, requests)
    print(
        f"Replaced section between offsets {start}-{end} with "
        f"{len(new_content)} chars."
    )


def cmd_overwrite(args) -> None:
    new_content = _resolve_text(args)
    doc = get_doc(args.doc)
    end = body_end_index(doc)
    requests: list[dict] = []
    if end > 1:
        requests.append({"deleteContentRange": {
            "range": {"startIndex": 1, "endIndex": end}
        }})
    requests.append({"insertText": {
        "location": {"index": 1}, "text": new_content
    }})
    batch_update(args.doc, requests)
    print(f"Overwrote body ({end - 1} chars deleted, "
          f"{len(new_content)} chars inserted).")


# ───────────────────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        prog="gws_docs_edit",
        description="Edit existing Google Docs via the gws CLI.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pd = sub.add_parser("dump", help="Print doc body as plain text")
    pd.add_argument("--doc", required=True, help="Google Doc ID")
    pd.set_defaults(func=cmd_dump)

    pr = sub.add_parser(
        "replace-text",
        help="Atomic find/replace (calls Docs replaceAllText)",
    )
    pr.add_argument("--doc", required=True)
    pr.add_argument("--find", required=True)
    pr.add_argument("--replace", required=True)
    pr.set_defaults(func=cmd_replace_text)

    pa = sub.add_parser("append", help="Append text at end of body")
    pa.add_argument("--doc", required=True)
    g = pa.add_mutually_exclusive_group(required=True)
    g.add_argument("--text")
    g.add_argument("--file")
    pa.set_defaults(func=cmd_append)

    ps = sub.add_parser(
        "replace-section",
        help="Replace body between start marker and end marker "
             "(or end-of-body if no end marker)",
    )
    ps.add_argument("--doc", required=True)
    ps.add_argument(
        "--start-marker", required=True,
        help="Substring in the first paragraph of the section",
    )
    ps.add_argument(
        "--end-marker",
        help="Substring in the first paragraph AFTER the section "
             "(exclusive). Omit to replace through end of body.",
    )
    g2 = ps.add_mutually_exclusive_group(required=True)
    g2.add_argument("--content")
    g2.add_argument("--content-file")
    ps.set_defaults(func=cmd_replace_section)

    po = sub.add_parser(
        "overwrite",
        help="Wipe body, write fresh content",
    )
    po.add_argument("--doc", required=True)
    g3 = po.add_mutually_exclusive_group(required=True)
    g3.add_argument("--content")
    g3.add_argument("--content-file")
    po.set_defaults(func=cmd_overwrite)

    args = p.parse_args()
    try:
        args.func(args)
    except Exception as e:  # noqa: BLE001
        print(f"[gws_docs_edit] error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
