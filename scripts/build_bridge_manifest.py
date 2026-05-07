#!/usr/bin/env python3
"""build_bridge_manifest.py — walk scripts/, generate the chat-bridge manifest.

The bridge chat server (bravo_cli/bridge_chat_server.py) used to hold a
hardcoded SCRIPT_ALLOWLIST of 16 entries. Every new script meant editing
that file. This builder generates `scripts/_bridge_manifest.json`
automatically by scanning every Python script in `scripts/`, parsing its
docstring + argparse setup, and emitting a JSON manifest the bridge reads
at boot.

Opt-in / opt-out via header comments at the top of each script:
  # bridge_visible: true   — explicitly include (default for scripts with
                              an argparse parser + a docstring)
  # bridge_visible: false  — exclude even if otherwise eligible
  # bridge_mutating: true  — force the mutating flag (requires confirm:true)
  # bridge_mutating: false — force read-only (no confirm needed)

Auto-detection rules when no header is present:
  - bridge_visible:  true if file has argparse AND a triple-quoted docstring
  - bridge_mutating: true if any subcommand name matches the mutating regex
                     (send|insert|update|delete|post|create|run|execute|
                      apply|migrate|publish|approve|revoke|reset)

Run via:
  python scripts/build_bridge_manifest.py            # write the JSON
  python scripts/build_bridge_manifest.py --dry-run  # print to stdout
  python scripts/build_bridge_manifest.py --diff     # compare vs existing
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
MANIFEST_PATH = SCRIPTS_DIR / "_bridge_manifest.json"

# Files we never expose: meta-tooling, internal helpers, this builder itself.
BLOCKLIST = {
    "build_bridge_manifest.py",       # this file
    "check_bridge_manifest.py",       # drift-guard, sibling tool
    "test_build_bridge_manifest.py",  # tests, not a chat tool
    "build_capability_graph.py",      # internal infra
    "capability_query.py",
    "register.py",
    "register_skill.py",
    "scaffold.py",
    "personalize.py",
    "memory_aging.py",
    "memory_index.py",
    "context_manager.py",
    "self_audit.py",
    "system_cleanup.py",
    "auto_dream.py",
    "state_sync.py",
    # OS-level leaf tools — too granular for chat, and most aren't
    # safe to invoke remotely. Operator runs these directly.
    "windows_control.py",
    "macos_control.py",
    "computer_control.py",
    "music_control.py",
    # Internal helpers
    "scheduler.py",               # process-loop, not invocable
    "telegram_bot_handler.py",    # daemon
    "browser_harness_doctor.py",  # diagnostic, not chat-grade
    "n8n_inbound_doctor.py",      # diagnostic, run via run_script with explicit key
}

# Cap on per-script entry count. Scripts with more subcommands than this
# are leaf-control surfaces (volume_up / volume_down / ...) where every
# subcommand is a tiny atomic action. Surface those via direct CLI, not
# the chat agent. 20 is generous — n8n_tool has 12, lead_engine has 11.
MAX_ENTRIES_PER_SCRIPT = 25

MUTATING_VERBS_RE = re.compile(
    r"(?:^|_|-)(send|insert|update|delete|post|create|run|execute|apply|"
    r"migrate|publish|approve|revoke|reset|drop|truncate|rotate|book|cancel|"
    r"open|close|enqueue|complete|fire|trigger|refresh|sync|push|deploy|"
    r"add|remove|disable|enable|set|seed|grant)(?:_|$|-)",
    re.IGNORECASE,
)

VISIBILITY_HEADER_RE = re.compile(r"^#\s*bridge_visible\s*:\s*(true|false)\s*$", re.MULTILINE)
MUTATING_HEADER_RE = re.compile(r"^#\s*bridge_mutating\s*:\s*(true|false)\s*$", re.MULTILINE)


def _slug(filename: str) -> str:
    """scripts/lead_engine.py + subcommand 'list' -> 'lead_engine_list'."""
    return Path(filename).stem


def _read_header_flags(text: str) -> dict:
    """Parse opt-in/opt-out header comments."""
    out: dict = {}
    m = VISIBILITY_HEADER_RE.search(text[:2000])
    if m:
        out["bridge_visible"] = m.group(1).lower() == "true"
    m = MUTATING_HEADER_RE.search(text[:2000])
    if m:
        out["bridge_mutating"] = m.group(1).lower() == "true"
    return out


def _extract_docstring_summary(tree: ast.AST) -> str:
    """First non-empty line of the module docstring."""
    if not isinstance(tree, ast.Module):
        return ""
    doc = ast.get_docstring(tree)
    if not doc:
        return ""
    for line in doc.splitlines():
        line = line.strip()
        if line:
            return line[:200]
    return ""


def _find_subcommands(tree: ast.AST) -> list[str]:
    """Return subparser names by scanning for `sub.add_parser('name', ...)`
    or `sub.add_parser("name")`. Misses dynamic registration; that's fine —
    most of our scripts use the static pattern.
    """
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "add_parser" and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    names.append(first.value)
    # Dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _has_argparse(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "ArgumentParser":
                return True
            if isinstance(node.func, ast.Name) and node.func.id == "ArgumentParser":
                return True
    return False


def _is_mutating(script_stem: str, subcmd: str | None) -> bool:
    target = subcmd if subcmd else script_stem
    return bool(MUTATING_VERBS_RE.search(target))


def build_one(path: Path) -> list[dict]:
    """Return zero or more manifest entries for a single script.
    One entry per (script, subcommand) pair when subcommands exist; one
    flat entry otherwise.
    """
    if path.name in BLOCKLIST or path.name.startswith("_"):
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    flags = _read_header_flags(text)
    if flags.get("bridge_visible") is False:
        return []
    has_ap = _has_argparse(tree)
    summary = _extract_docstring_summary(tree)
    if flags.get("bridge_visible") is None and not (has_ap and summary):
        return []

    stem = path.stem
    rel_path = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    subcmds = _find_subcommands(tree)
    forced_mutating = flags.get("bridge_mutating")

    if subcmds:
        return [
            {
                "key": f"{stem}_{sub.replace('-', '_')}",
                "path": rel_path,
                "subcmd": sub,
                "mutating": forced_mutating if forced_mutating is not None else _is_mutating(stem, sub),
                "help": f"{summary} — subcommand: {sub}".strip(" —"),
            }
            for sub in subcmds
            if sub not in {"-h", "--help"}
        ]
    return [
        {
            "key": stem,
            "path": rel_path,
            "subcmd": None,
            "mutating": forced_mutating if forced_mutating is not None else _is_mutating(stem, None),
            "help": summary,
        }
    ]


def build_manifest() -> dict:
    entries: list[dict] = []
    skipped_oversize: list[tuple[str, int]] = []
    for path in sorted(SCRIPTS_DIR.glob("*.py")):
        es = build_one(path)
        if len(es) > MAX_ENTRIES_PER_SCRIPT:
            skipped_oversize.append((path.name, len(es)))
            continue
        entries.extend(es)
    if skipped_oversize:
        print(
            f"[build_bridge_manifest] Skipped {len(skipped_oversize)} oversize scripts "
            f"(>{MAX_ENTRIES_PER_SCRIPT} subcommands):",
            file=sys.stderr,
        )
        for name, count in skipped_oversize:
            print(f"  - {name} ({count} entries)", file=sys.stderr)

    # Stable order, no dupes
    seen: set[str] = set()
    deduped: list[dict] = []
    for e in entries:
        if e["key"] in seen:
            continue
        seen.add(e["key"])
        deduped.append(e)

    return {
        "version": 1,
        "generated_at_iso": _utc_now(),
        "script_count": len({e["path"] for e in deduped}),
        "entry_count": len(deduped),
        "entries": deduped,
    }


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="print JSON to stdout, don't write")
    ap.add_argument("--diff", action="store_true", help="compare new manifest vs existing")
    args = ap.parse_args()

    manifest = build_manifest()

    if args.dry_run:
        print(json.dumps(manifest, indent=2))
        return 0

    if args.diff and MANIFEST_PATH.exists():
        old = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        old_keys = {e["key"] for e in old.get("entries", [])}
        new_keys = {e["key"] for e in manifest["entries"]}
        added = sorted(new_keys - old_keys)
        removed = sorted(old_keys - new_keys)
        print(f"Existing entries:  {len(old.get('entries', []))}")
        print(f"Generated entries: {len(manifest['entries'])}")
        if added:
            print(f"\nAdded ({len(added)}):")
            for k in added:
                print(f"  + {k}")
        if removed:
            print(f"\nRemoved ({len(removed)}):")
            for k in removed:
                print(f"  - {k}")
        if not added and not removed:
            print("\nNo entry-level diff (descriptions/mutating flags may have changed).")
        return 0

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH}")
    print(f"  scripts: {manifest['script_count']}")
    print(f"  entries: {manifest['entry_count']}")
    mutating_count = sum(1 for e in manifest["entries"] if e["mutating"])
    print(f"  read-only: {manifest['entry_count'] - mutating_count}")
    print(f"  mutating:  {mutating_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
