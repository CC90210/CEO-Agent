#!/usr/bin/env python3
"""check_bridge_manifest.py — drift guard for scripts/_bridge_manifest.json.

Builds the manifest in-memory and compares against the checked-in JSON.
Exit codes:
  0 — manifest is in sync with scripts/
  1 — drift detected (added/removed entries OR any stable entry policy changed)
  2 — manifest file missing

Wire as a pre-commit hook to prevent shipping a bridge that disagrees
with what the chat agent sees:

  # .git/hooks/pre-commit
  #!/bin/sh
  python scripts/check_bridge_manifest.py || exit 1

Or one-shot install via:
  python scripts/check_bridge_manifest.py --install-hook
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import build_bridge_manifest as bbm  # type: ignore


REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO_ROOT / ".git" / "hooks" / "pre-commit"
HOOK_BODY = """#!/bin/sh
# Auto-installed by scripts/check_bridge_manifest.py
# Refuses commits that drift the bridge manifest from scripts/.
python scripts/check_bridge_manifest.py
exit_code=$?
if [ $exit_code -ne 0 ]; then
    echo ""
    echo "[bridge-manifest] Commit blocked: scripts/_bridge_manifest.json is out of sync."
    echo "  Run: python scripts/build_bridge_manifest.py"
    echo "  Then: git add scripts/_bridge_manifest.json"
    exit 1
fi
"""


def _diff(live: dict, on_disk: dict) -> dict:
    """Return entry and policy drift between two manifests."""
    live_keys = {e["key"]: e for e in live.get("entries", [])}
    disk_keys = {e["key"]: e for e in on_disk.get("entries", [])}

    added = sorted(set(live_keys) - set(disk_keys))
    removed = sorted(set(disk_keys) - set(live_keys))
    mutating_changed = []
    policy_changed = []
    for k in set(live_keys) & set(disk_keys):
        if bool(live_keys[k].get("mutating")) != bool(disk_keys[k].get("mutating")):
            mutating_changed.append({
                "key": k,
                "from": disk_keys[k].get("mutating"),
                "to": live_keys[k].get("mutating"),
            })
        if live_keys[k] != disk_keys[k]:
            policy_changed.append(k)
    return {
        "added": added,
        "removed": removed,
        "mutating_changed": mutating_changed,
        "policy_changed": sorted(policy_changed),
        "version_changed": live.get("version") != on_disk.get("version"),
    }


def cmd_check(args: argparse.Namespace) -> int:
    manifest_path = bbm.MANIFEST_PATH
    if not manifest_path.is_file():
        print(f"[bridge-manifest] missing: {manifest_path}", file=sys.stderr)
        print("  Run: python scripts/build_bridge_manifest.py", file=sys.stderr)
        return 2
    on_disk = json.loads(manifest_path.read_text(encoding="utf-8"))
    live = bbm.build_manifest()
    diff = _diff(live, on_disk)
    if (
        not diff["added"]
        and not diff["removed"]
        and not diff["policy_changed"]
        and not diff["version_changed"]
    ):
        if args.verbose:
            print(f"[bridge-manifest] in sync — {len(live['entries'])} entries")
        return 0
    print("[bridge-manifest] DRIFT DETECTED:", file=sys.stderr)
    if diff["version_changed"]:
        print("  Manifest schema version changed", file=sys.stderr)
    if diff["added"]:
        print(f"  Added ({len(diff['added'])}):", file=sys.stderr)
        for k in diff["added"][:20]:
            print(f"    + {k}", file=sys.stderr)
        if len(diff["added"]) > 20:
            print(f"    ... and {len(diff['added']) - 20} more", file=sys.stderr)
    if diff["removed"]:
        print(f"  Removed ({len(diff['removed'])}):", file=sys.stderr)
        for k in diff["removed"][:20]:
            print(f"    - {k}", file=sys.stderr)
        if len(diff["removed"]) > 20:
            print(f"    ... and {len(diff['removed']) - 20} more", file=sys.stderr)
    if diff["mutating_changed"]:
        print(f"  Mutating-flag flipped ({len(diff['mutating_changed'])}):", file=sys.stderr)
        for c in diff["mutating_changed"][:10]:
            print(f"    ~ {c['key']}: {c['from']} -> {c['to']}", file=sys.stderr)
    other_policy = sorted(set(diff["policy_changed"]) - {c["key"] for c in diff["mutating_changed"]})
    if other_policy:
        print(f"  Entry policy changed ({len(other_policy)}):", file=sys.stderr)
        for key in other_policy[:20]:
            print(f"    ~ {key}", file=sys.stderr)
    print("\nRun: python scripts/build_bridge_manifest.py", file=sys.stderr)
    print("Then: git add scripts/_bridge_manifest.json", file=sys.stderr)
    return 1


def cmd_install_hook(_args: argparse.Namespace) -> int:
    if not (REPO_ROOT / ".git").is_dir():
        print("[bridge-manifest] not a git repo — cannot install pre-commit hook", file=sys.stderr)
        return 2
    HOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    HOOK_PATH.write_text(HOOK_BODY, encoding="utf-8")
    try:
        # POSIX: make executable. Windows ignores the bit.
        import os
        os.chmod(HOOK_PATH, 0o755)
    except Exception:
        pass
    print(f"[bridge-manifest] installed pre-commit hook at {HOOK_PATH}")
    print("  Bypass with: git commit --no-verify")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbose", "-v", action="store_true", help="print 'in sync' on success")
    ap.add_argument("--install-hook", action="store_true", help="install .git/hooks/pre-commit")
    args = ap.parse_args()
    if args.install_hook:
        return cmd_install_hook(args)
    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
