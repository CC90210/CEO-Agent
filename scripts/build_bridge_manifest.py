#!/usr/bin/env python3
"""build_bridge_manifest.py — walk scripts/, generate the chat-bridge manifest.

The bridge chat server (bravo_cli/bridge_chat_server.py) used to hold a
hardcoded SCRIPT_ALLOWLIST of 16 entries. Every new script meant editing
that file. This builder generates `scripts/_bridge_manifest.json`
automatically by scanning every Python script in `scripts/`, parsing its
docstring + argparse setup, and emitting a JSON manifest the bridge reads
at boot.

Preferred contract: a literal ``CAPABILITY_META`` dictionary in each reviewed
operator-facing script. Its ``bridge`` policy controls visibility, confirmation,
per-subcommand overrides, fixed safe arguments, and denied legacy arguments
without importing the script.

Legacy opt-in / opt-out header comments remain supported during migration:
  # bridge_visible: true   — explicitly include (default for scripts with
                              an argparse parser + a docstring)
  # bridge_visible: false  — exclude even if otherwise eligible
  # bridge_mutating: true  — force the mutating flag (requires confirm:true)
  # bridge_mutating: false — force read-only (no confirm needed)

Fail-closed rules when neither metadata nor a header is present:
  - bridge_visible:  true if file has argparse AND a triple-quoted docstring
  - bridge_mutating: true for every entry until its behavior is explicitly reviewed

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


# Additional script roots scanned and registered with a non-default root
# key. The bridge maps each `root` value to an absolute path at runtime
# (BRAVO_AGENT_ROOT for "bravo", SUNBIZ_AGENT_ROOT for "sunbiz"). Keeps
# the manifest portable across machines and platforms. Probe logic is
# centralised in lib/agent_roots.py.
sys.path.insert(0, str(SCRIPTS_DIR))
from lib.agent_roots import resolve_sunbiz_root  # noqa: E402
from lib.capability_metadata import (  # noqa: E402
    capability_meta_declared,
    capability_meta_from_tree,
    validate_capability_meta,
)

EXTRA_ROOTS: list[tuple[str, Path]] = []
_sunbiz_root = resolve_sunbiz_root()
if _sunbiz_root is not None:
    EXTRA_ROOTS.append(("sunbiz", _sunbiz_root / "scripts"))

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
NESTED_SKIP_PARTS = frozenset({"_archive", "__pycache__", "tests"})

VISIBILITY_HEADER_RE = re.compile(r"^#\s*bridge_visible\s*:\s*(true|false)\s*$", re.MULTILINE)
MUTATING_HEADER_RE = re.compile(r"^#\s*bridge_mutating\s*:\s*(true|false)\s*$", re.MULTILINE)


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


def _script_candidates(scripts_dir: Path) -> list[Path]:
    """Return bridge candidates, with nested discovery explicitly opt-in.

    Existing top-level CLIs retain their legacy migration behavior. Nested
    modules are internal by default and become operator-facing only when they
    declare the static ``CAPABILITY_META`` contract.
    """
    candidates: list[Path] = []
    if not scripts_dir.is_dir():
        return candidates
    for path in sorted(scripts_dir.rglob("*.py")):
        rel = path.relative_to(scripts_dir)
        if any(part in NESTED_SKIP_PARTS for part in rel.parts[:-1]):
            continue
        if len(rel.parts) == 1:
            candidates.append(path)
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, SyntaxError, ValueError):
            continue
        if capability_meta_declared(tree):
            candidates.append(path)
    return candidates


def build_one(path: Path, root_key: str = "bravo", root_dir: Path | None = None) -> list[dict]:
    """Return zero or more manifest entries for a single script.
    One entry per (script, subcommand) pair when subcommands exist; one
    flat entry otherwise.

    root_key/root_dir: the script root this path belongs to. "bravo" is
    the default (CEO-Agent); the bridge resolves other roots to their
    absolute path at runtime (e.g. "sunbiz" → SUNBIZ_AGENT_ROOT). The
    stored `path` is relative to that root so the manifest stays
    portable across machines.
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

    try:
        meta = capability_meta_from_tree(tree)
    except ValueError:
        return []  # malformed governance metadata is never bridge-exposed
    if meta is not None and validate_capability_meta(meta):
        return []

    flags = _read_header_flags(text) if meta is None else {}
    bridge = (meta or {}).get("bridge", {})
    visible = bridge.get("visible") if meta is not None else flags.get("bridge_visible")
    if visible is False:
        return []
    has_ap = _has_argparse(tree)
    summary = _extract_docstring_summary(tree)
    if visible is None and not (has_ap and summary):
        return []

    stem = path.stem
    rel_base = root_dir.parent if root_dir is not None else REPO_ROOT
    rel_path = str(path.relative_to(rel_base)).replace("\\", "/")
    subcmds = _find_subcommands(tree)
    forced_mutating = flags.get("bridge_mutating")

    def policy_for(subcmd: str | None) -> dict:
        if meta is None:
            return {}
        policy = dict(bridge)
        policy.pop("subcommands", None)
        if subcmd is not None:
            policy.update(bridge.get("subcommands", {}).get(subcmd, {}))
        return policy

    def subcommand_visible(subcmd: str) -> bool:
        if meta is None:
            return True
        declared = bridge.get("subcommands", {})
        if declared and subcmd not in declared:
            return False
        return policy_for(subcmd).get("visible", bridge.get("visible", False)) is True

    def manifest_policy(subcmd: str | None) -> dict:
        if meta is None:
            # Legacy tools remain available, but ambiguity requires confirmation.
            mutating = forced_mutating if forced_mutating is not None else True
            return {"mutating": bool(mutating)}
        policy = policy_for(subcmd)
        deny_args = list(dict.fromkeys([
            *bridge.get("deny_args", []),
            *policy.get("deny_args", []),
        ]))
        fields = {
            "mutating": bool(policy.get("confirm", bridge.get("confirm", True))),
            "category": meta["category"],
            "lifecycle": meta["lifecycle"],
            "risk": meta["risk"],
            "project": meta["project"],
        }
        if deny_args:
            fields["deny_args"] = deny_args
        confirm_args = list(dict.fromkeys([
            *bridge.get("confirm_args", []),
            *policy.get("confirm_args", []),
        ]))
        if confirm_args:
            fields["confirm_args"] = confirm_args
        fixed_args = policy.get("fixed_args", bridge.get("fixed_args", []))
        if fixed_args:
            fields["fixed_args"] = fixed_args
        return fields

    if subcmds:
        return [
            {
                "key": policy_for(sub).get("key", f"{stem}_{sub.replace('-', '_')}"),
                "path": rel_path,
                "root": root_key,
                "subcmd": sub,
                **manifest_policy(sub),
                "help": f"{summary} — subcommand: {sub}".strip(" —"),
            }
            for sub in subcmds
            if sub not in {"-h", "--help"} and subcommand_visible(sub)
        ]
    return [
        {
            "key": stem,
            "path": rel_path,
            "root": root_key,
            "subcmd": None,
            **manifest_policy(None),
            "help": summary,
        }
    ]


def build_manifest() -> dict:
    entries: list[dict] = []
    skipped_oversize: list[tuple[str, int]] = []
    # Default CEO-Agent root scan
    for path in _script_candidates(SCRIPTS_DIR):
        es = build_one(path, root_key="bravo")
        if len(es) > MAX_ENTRIES_PER_SCRIPT:
            skipped_oversize.append((path.name, len(es)))
            continue
        entries.extend(es)
    # Additional roots (e.g., SunBiz-Agent) — each registered with its
    # own root key so the bridge runtime knows where to resolve it.
    for root_key, scripts_dir in EXTRA_ROOTS:
        for path in _script_candidates(scripts_dir):
            es = build_one(path, root_key=root_key, root_dir=scripts_dir)
            if len(es) > MAX_ENTRIES_PER_SCRIPT:
                skipped_oversize.append((f"{root_key}/{path.name}", len(es)))
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
        "version": 2,
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
