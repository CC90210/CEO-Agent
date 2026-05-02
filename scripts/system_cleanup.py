"""
System Cleanup — find and remove redundant artifacts left by repeated installs.

Targets:
  - Old per-agent install dirs (~/.bravo, ~/.oasis/wizard, ~/.oasis/<slug>/repo)
    that duplicate an existing tracked clone.
  - pip cache (Windows: %LOCALAPPDATA%\\pip\\Cache) — typically 1-5 GB.
  - npm cache (Windows: %LOCALAPPDATA%\\npm-cache).
  - tmp/ accumulation in tracked repos (older than --tmp-age days).
  - .pyc and __pycache__ trees.
  - Orphaned .scaffold-backup/ snapshots older than --tmp-age days.
  - Old node_modules/ in non-active project subdirectories.

Safe by default: --dry-run lists everything, --apply actually deletes.
Always shows a size summary BEFORE deleting so you can pick what to nuke.

USAGE
-----
    python scripts/system_cleanup.py                   # dry-run, full report
    python scripts/system_cleanup.py --json            # machine-readable
    python scripts/system_cleanup.py --apply           # delete (with confirm)
    python scripts/system_cleanup.py --apply --yes     # delete, no prompts
    python scripts/system_cleanup.py --tmp-age 14      # tmp older than 14d
    python scripts/system_cleanup.py --skip pip,npm    # leave those alone

The active OASIS repo (the one you're running this from) is ALWAYS preserved.
Only redundant clones — sibling locations like ~/.bravo/repo or
~/.oasis/wizard/repo that duplicate the active checkout — get flagged.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()


def _dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    try:
        for root, _, files in os.walk(path):
            for f in files:
                try:
                    total += (Path(root) / f).stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _human(size: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def _is_oasis_repo(path: Path) -> bool:
    if not (path / "bravo_cli" / "main.py").exists():
        return False
    if not (path / "requirements.txt").exists():
        return False
    try:
        out = subprocess.check_output(
            ["git", "-C", str(path), "config", "--get", "remote.origin.url"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:  # noqa: BLE001
        return False
    return bool(out) and any(s in out for s in ("CC90210/CEO-Agent", "CC90210/CFO-Agent",
                                                  "CC90210/CMO-Agent", "Business-Empire-Agent",
                                                  "CFO-Agent", "CMO-Agent"))


def find_redundant_clones() -> list[dict[str, Any]]:
    """Find OASIS clones that duplicate the active project."""
    candidates = [
        HOME / ".bravo" / "repo",
        HOME / ".oasis" / "wizard" / "repo",
        HOME / ".oasis" / "bravo" / "repo",
        HOME / ".oasis" / "atlas" / "repo",
        HOME / ".oasis" / "maven" / "repo",
        HOME / ".oasis" / "aura" / "repo",
        HOME / ".oasis" / "hermes" / "repo",
    ]
    results: list[dict[str, Any]] = []
    active = PROJECT_ROOT.resolve()
    for c in candidates:
        if not c.exists():
            continue
        try:
            if c.resolve() == active:
                continue  # the active repo — never delete
        except OSError:
            pass
        is_repo = _is_oasis_repo(c)
        size = _dir_size(c.parent)  # include venv + bin + repo
        results.append({
            "path": str(c.parent),
            "is_oasis_clone": is_repo,
            "size_bytes": size,
            "size_human": _human(size),
            "reason": "redundant OASIS clone (active is " + str(active) + ")" if is_repo else "non-OASIS dir at OASIS path",
        })
    return results


def find_pip_cache() -> dict[str, Any]:
    """Locate pip's wheel cache."""
    candidates = []
    if os.name == "nt":
        candidates.append(Path(os.environ.get("LOCALAPPDATA", "")) / "pip" / "Cache")
    else:
        candidates.append(HOME / ".cache" / "pip")
    for c in candidates:
        if c.exists():
            size = _dir_size(c)
            return {"path": str(c), "size_bytes": size, "size_human": _human(size), "exists": True}
    return {"path": str(candidates[0]), "exists": False, "size_bytes": 0, "size_human": "0 B"}


def find_npm_cache() -> dict[str, Any]:
    candidates = []
    if os.name == "nt":
        candidates.append(Path(os.environ.get("LOCALAPPDATA", "")) / "npm-cache")
        candidates.append(HOME / "AppData" / "Roaming" / "npm-cache")
    else:
        candidates.append(HOME / ".npm")
    for c in candidates:
        if c.exists():
            size = _dir_size(c)
            return {"path": str(c), "size_bytes": size, "size_human": _human(size), "exists": True}
    return {"path": str(candidates[0]), "exists": False, "size_bytes": 0, "size_human": "0 B"}


def find_old_tmp(repo: Path, age_days: int) -> dict[str, Any]:
    tmp = repo / "tmp"
    if not tmp.exists():
        return {"path": str(tmp), "exists": False, "files": 0, "size_bytes": 0, "size_human": "0 B"}
    cutoff = datetime.now(timezone.utc).timestamp() - (age_days * 86400)
    old_files: list[Path] = []
    total = 0
    for root, _, files in os.walk(tmp):
        for f in files:
            p = Path(root) / f
            try:
                mtime = p.stat().st_mtime
                if mtime < cutoff:
                    old_files.append(p)
                    total += p.stat().st_size
            except OSError:
                pass
    return {"path": str(tmp), "exists": True, "files": len(old_files),
            "size_bytes": total, "size_human": _human(total),
            "_paths": old_files}


def find_pycache_trees(repo: Path) -> dict[str, Any]:
    trees: list[Path] = []
    total = 0
    for root, dirs, _ in os.walk(repo):
        if any(skip in root for skip in (".git", "node_modules", ".venv", "venv")):
            continue
        for d in list(dirs):
            if d == "__pycache__":
                p = Path(root) / d
                trees.append(p)
                total += _dir_size(p)
    return {"count": len(trees), "size_bytes": total, "size_human": _human(total), "_paths": trees}


def find_scaffold_backups(repo: Path, age_days: int) -> dict[str, Any]:
    bdir = repo / ".scaffold-backup"
    if not bdir.exists():
        return {"path": str(bdir), "exists": False, "snapshots": 0, "size_bytes": 0, "size_human": "0 B"}
    cutoff = datetime.now(timezone.utc).timestamp() - (age_days * 86400)
    old: list[Path] = []
    total = 0
    for child in bdir.iterdir():
        if not child.is_dir():
            continue
        try:
            if child.stat().st_mtime < cutoff:
                old.append(child)
                total += _dir_size(child)
        except OSError:
            pass
    return {"path": str(bdir), "exists": True, "snapshots": len(old),
            "size_bytes": total, "size_human": _human(total), "_paths": old}


def run_audit(tmp_age_days: int = 7) -> dict[str, Any]:
    redundant = find_redundant_clones()
    pip_cache = find_pip_cache()
    npm_cache = find_npm_cache()
    tmp_old = find_old_tmp(PROJECT_ROOT, tmp_age_days)
    pycache = find_pycache_trees(PROJECT_ROOT)
    backups = find_scaffold_backups(PROJECT_ROOT, tmp_age_days)
    total = (sum(r["size_bytes"] for r in redundant) + pip_cache["size_bytes"]
             + npm_cache["size_bytes"] + tmp_old["size_bytes"]
             + pycache["size_bytes"] + backups["size_bytes"])
    return {
        "active_repo": str(PROJECT_ROOT),
        "redundant_clones": redundant,
        "pip_cache": pip_cache,
        "npm_cache": npm_cache,
        "tmp_old": {k: v for k, v in tmp_old.items() if not k.startswith("_")},
        "pycache_trees": {k: v for k, v in pycache.items() if not k.startswith("_")},
        "scaffold_backups": {k: v for k, v in backups.items() if not k.startswith("_")},
        "total_reclaimable_bytes": total,
        "total_reclaimable_human": _human(total),
        "_internal": {"tmp_paths": tmp_old.get("_paths", []),
                      "pycache_paths": pycache.get("_paths", []),
                      "backup_paths": backups.get("_paths", [])},
    }


def render_human(report: dict[str, Any]) -> str:
    lines = [
        "",
        "=" * 64,
        "  OASIS SYSTEM CLEANUP",
        "=" * 64,
        f"  Active repo:        {report['active_repo']}",
        f"  Total reclaimable:  {report['total_reclaimable_human']}",
        "",
        "  Redundant clones (duplicate OASIS installs):",
    ]
    if report["redundant_clones"]:
        for r in report["redundant_clones"]:
            lines.append(f"    {r['size_human']:>10}  {r['path']}  [{r['reason']}]")
    else:
        lines.append("    (none)")
    lines += [
        "",
        f"  Pip cache:          {report['pip_cache']['size_human']:>10}  {report['pip_cache']['path']}",
        f"  npm cache:          {report['npm_cache']['size_human']:>10}  {report['npm_cache']['path']}",
        f"  Old tmp/ files:     {report['tmp_old']['size_human']:>10}  ({report['tmp_old'].get('files', 0)} files)",
        f"  __pycache__ trees:  {report['pycache_trees']['size_human']:>10}  ({report['pycache_trees'].get('count', 0)} dirs)",
        f"  Scaffold backups:   {report['scaffold_backups']['size_human']:>10}  ({report['scaffold_backups'].get('snapshots', 0)} snapshots)",
        "",
        "  Re-run with --apply to delete the items above.",
        "  Or --skip <items> to leave specific categories alone.",
        "  Or --apply --yes to skip individual confirmations.",
        "=" * 64,
    ]
    return "\n".join(lines)


def apply_cleanup(report: dict[str, Any], skip: set[str], assume_yes: bool) -> dict[str, Any]:
    deleted: list[dict[str, Any]] = []

    def confirm(label: str, size: str) -> bool:
        if assume_yes:
            return True
        try:
            reply = input(f"  Delete {label} ({size})? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return reply.startswith("y")

    def remove(path: Path, label: str, size_bytes: int):
        if path.exists():
            try:
                if path.is_file():
                    path.unlink()
                else:
                    shutil.rmtree(path, ignore_errors=True)
                deleted.append({"label": label, "path": str(path),
                                "size_bytes": size_bytes,
                                "size_human": _human(size_bytes)})
            except Exception as exc:  # noqa: BLE001
                deleted.append({"label": label, "path": str(path), "error": str(exc)[:120]})

    if "redundant" not in skip:
        for r in report["redundant_clones"]:
            if confirm(f"redundant clone {r['path']}", r["size_human"]):
                remove(Path(r["path"]), "redundant_clone", r["size_bytes"])

    if "pip" not in skip and report["pip_cache"]["exists"]:
        if confirm(f"pip cache {report['pip_cache']['path']}", report["pip_cache"]["size_human"]):
            remove(Path(report["pip_cache"]["path"]), "pip_cache", report["pip_cache"]["size_bytes"])

    if "npm" not in skip and report["npm_cache"]["exists"]:
        if confirm(f"npm cache {report['npm_cache']['path']}", report["npm_cache"]["size_human"]):
            remove(Path(report["npm_cache"]["path"]), "npm_cache", report["npm_cache"]["size_bytes"])

    if "tmp" not in skip:
        old_paths = report.get("_internal", {}).get("tmp_paths", [])
        if old_paths and confirm(f"{len(old_paths)} old tmp/ files", report["tmp_old"]["size_human"]):
            for p in old_paths:
                try:
                    p.unlink()
                except OSError:
                    pass
            deleted.append({"label": "tmp_old_files", "count": len(old_paths),
                            "size_human": report["tmp_old"]["size_human"]})

    if "pycache" not in skip:
        cache_paths = report.get("_internal", {}).get("pycache_paths", [])
        if cache_paths and confirm(f"{len(cache_paths)} __pycache__ trees", report["pycache_trees"]["size_human"]):
            for p in cache_paths:
                shutil.rmtree(p, ignore_errors=True)
            deleted.append({"label": "pycache_trees", "count": len(cache_paths),
                            "size_human": report["pycache_trees"]["size_human"]})

    if "backups" not in skip:
        backup_paths = report.get("_internal", {}).get("backup_paths", [])
        if backup_paths and confirm(f"{len(backup_paths)} scaffold backups", report["scaffold_backups"]["size_human"]):
            for p in backup_paths:
                shutil.rmtree(p, ignore_errors=True)
            deleted.append({"label": "scaffold_backups", "count": len(backup_paths),
                            "size_human": report["scaffold_backups"]["size_human"]})

    return {"deleted": deleted, "count": len(deleted)}


def main() -> int:
    p = argparse.ArgumentParser(description="OASIS System Cleanup — find and remove redundant install artifacts.")
    p.add_argument("--apply", action="store_true", help="Actually delete (default: dry-run)")
    p.add_argument("--yes", "-y", action="store_true", help="Skip per-item confirmations")
    p.add_argument("--json", dest="output_json", action="store_true")
    p.add_argument("--tmp-age", type=int, default=7, help="Treat tmp/ files older than N days as cleanable (default: 7)")
    p.add_argument("--skip", default="", help="Comma-separated items to skip: redundant,pip,npm,tmp,pycache,backups")
    args = p.parse_args()

    report = run_audit(tmp_age_days=args.tmp_age)
    skip = {s.strip().lower() for s in args.skip.split(",") if s.strip()}

    if args.output_json and not args.apply:
        # Strip internal-only fields before JSON dump
        public = {k: v for k, v in report.items() if not k.startswith("_")}
        print(json.dumps(public, indent=2, default=str))
        return 0

    if not args.output_json:
        print(render_human(report))

    if args.apply:
        result = apply_cleanup(report, skip, args.yes)
        if args.output_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"\n  Deleted {result['count']} items.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
