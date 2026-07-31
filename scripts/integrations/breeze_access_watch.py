#!/usr/bin/env python3
"""breeze_access_watch.py — INTERNAL access/change monitor for the Breeze handover.

Breeze Advance was granted pre-contract access (GitHub collaborator on the handover
account; Supabase + Vercel team membership). This watches for anything NEW since a
recorded baseline so a scrape, fork, role escalation, or foreign commit is caught
early instead of discovered later.

Checks (all READ-ONLY — this script never changes access):
  GitHub   forks · clone traffic · collaborators · non-OASIS commit authors
  Supabase organization members + their roles (cross-project exposure)
  Vercel   NOT covered — no API token wired here; check manually (see --help note)

Usage:
  python scripts/integrations/breeze_access_watch.py baseline   # record current state
  python scripts/integrations/breeze_access_watch.py check      # diff vs baseline
  python scripts/integrations/breeze_access_watch.py check --json

Baseline is stored at state/breeze_access_baseline.json.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASELINE = PROJECT_ROOT / "state" / "breeze_access_baseline.json"
REPO = "CC90210/breeze-portal"
SUPABASE_ORG = "oktipozhyojufxsytrse"
# Commit authors that are legitimately OASIS. Anything else is flagged.
KNOWN_AUTHORS = {"cc90210", "cc", "claude (vps)"}
GH_EXE = r"C:\Program Files\GitHub CLI\gh.exe"

sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def gh(path: str):
    """Call the GitHub API via the gh CLI (uses its stored auth)."""
    exe = GH_EXE if os.path.exists(GH_EXE) else "gh"
    try:
        r = subprocess.run([exe, "api", path], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return {"_err": (r.stderr or "").strip()[:200]}
        return json.loads(r.stdout or "null")
    except Exception as e:  # noqa: BLE001 — report, never crash the watch
        return {"_err": str(e)[:200]}


def supabase(path: str):
    """Call the Supabase Management API (token loaded internally, never printed)."""
    try:
        import supabase_tool as t

        token = t.load_env().get("SUPABASE_ACCESS_TOKEN")
        if not token:
            return {"_err": "no SUPABASE_ACCESS_TOKEN"}
        req = urllib.request.Request(
            f"https://api.supabase.com/v1{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        return {"_err": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"_err": str(e)[:200]}


def snapshot() -> dict:
    """Current observable access/change state across GitHub + Supabase."""
    forks = gh(f"repos/{REPO}/forks")
    collabs = gh(f"repos/{REPO}/collaborators")
    clones = gh(f"repos/{REPO}/traffic/clones")
    members = supabase(f"/organizations/{SUPABASE_ORG}/members")
    projects = supabase("/projects")

    # Commit authors across all refs — a non-OASIS author means someone else pushed.
    authors: list[str] = []
    repo_dir = Path.home() / "APPS" / "breeze-portal"
    if repo_dir.exists():
        try:
            r = subprocess.run(
                ["git", "-C", str(repo_dir), "log", "--all", "--format=%an"],
                capture_output=True, text=True, timeout=60,
            )
            authors = sorted({a.strip() for a in r.stdout.splitlines() if a.strip()})
        except Exception:
            authors = []

    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "github": {
            "forks": sorted(f.get("full_name", "?") for f in forks) if isinstance(forks, list) else forks,
            "collaborators": sorted(c.get("login", "?") for c in collabs) if isinstance(collabs, list) else collabs,
            "clone_count_14d": clones.get("count") if isinstance(clones, dict) else clones,
            "clone_uniques_14d": clones.get("uniques") if isinstance(clones, dict) else None,
            "commit_authors": authors,
        },
        "supabase": {
            "org_members": sorted(
                f"{m.get('email')}={m.get('role_name')}" for m in members
            ) if isinstance(members, list) else members,
            "projects": sorted(
                p.get("name", "?") for p in projects
            ) if isinstance(projects, list) else projects,
        },
    }


def diff(base: dict, now: dict) -> list[str]:
    """Human-readable list of what changed. Empty list = nothing new."""
    findings: list[str] = []

    def as_set(v):
        return set(v) if isinstance(v, list) else set()

    gb, gn = base.get("github", {}), now.get("github", {})
    for label, key in (("fork", "forks"), ("collaborator", "collaborators"), ("commit author", "commit_authors")):
        added = as_set(gn.get(key)) - as_set(gb.get(key))
        for a in sorted(added):
            findings.append(f"NEW {label}: {a}")
    removed_collab = as_set(gb.get("collaborators")) - as_set(gn.get("collaborators"))
    for r in sorted(removed_collab):
        findings.append(f"REMOVED collaborator: {r}")

    # Any commit author outside the known-OASIS set is flagged regardless of baseline.
    for a in as_set(gn.get("commit_authors")):
        if a.strip().lower() not in KNOWN_AUTHORS:
            findings.append(f"FOREIGN commit author present: {a}")

    b_cl, n_cl = gb.get("clone_count_14d"), gn.get("clone_count_14d")
    if isinstance(b_cl, int) and isinstance(n_cl, int) and n_cl > b_cl:
        findings.append(f"clone activity rose {b_cl} -> {n_cl} (14d window; uniques={gn.get('clone_uniques_14d')})")

    sb, sn = base.get("supabase", {}), now.get("supabase", {})
    added_m = as_set(sn.get("org_members")) - as_set(sb.get("org_members"))
    for m in sorted(added_m):
        findings.append(f"SUPABASE member/role CHANGED or ADDED: {m}")
    removed_m = as_set(sb.get("org_members")) - as_set(sn.get("org_members"))
    for m in sorted(removed_m):
        findings.append(f"SUPABASE member/role REMOVED: {m}")

    # Standing exposure warning: a non-owner in the shared org sees every project.
    members_now = sn.get("org_members")
    projects_now = sn.get("projects")
    if isinstance(members_now, list) and isinstance(projects_now, list) and len(projects_now) > 1:
        for m in members_now:
            if "konamak@icloud.com" not in m:
                findings.append(
                    f"EXPOSURE: {m} is in the shared org, which contains {len(projects_now)} projects "
                    f"({', '.join(projects_now)}) — Supabase access is org-wide, not per-project"
                )
    return findings


def main() -> int:
    p = argparse.ArgumentParser(description="Breeze handover access/change monitor (read-only)")
    p.add_argument("mode", choices=["baseline", "check"])
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    now = snapshot()

    if args.mode == "baseline":
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(now, indent=2), encoding="utf-8")
        print(f"[baseline] recorded -> {BASELINE}")
        print(json.dumps(now, indent=2) if args.json else "")
        return 0

    if not BASELINE.exists():
        print("[check] no baseline yet — run: breeze_access_watch.py baseline", file=sys.stderr)
        return 2
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    findings = diff(base, now)

    if args.json:
        print(json.dumps({"baseline_at": base.get("captured_at"), "checked_at": now["captured_at"],
                          "findings": findings, "current": now}, indent=2))
        return 0

    print(f"[check] baseline {base.get('captured_at')} -> now {now['captured_at']}")
    if not findings:
        print("  CLEAN — nothing new since baseline.")
    else:
        for f in findings:
            print(f"  !! {f}")
    print("\n  (Vercel is NOT monitored here — check Team -> Settings -> Members manually.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
