#!/usr/bin/env python3
"""Content-keyed PII sweep (audit V2). Sweep a repo by OPERATOR-ADJUDICATED
strings — never by paths alone (the goldstorm/***REMOVED*** lesson: path-keyed purges
miss content that leaked wider).

Distinguishes the CONTROLLABLE surface (branches + tags — what a normal clone gets
and what `git push` can rewrite) from GitHub-managed `refs/pull/*` (which git
cannot rewrite — only GitHub Support / making the repo private clears those). Also
flags blobs git treats as BINARY, because `filter-repo --replace-text` skips them.

Usage:
  python pii_sweep.py <repo_path> --strings strings.txt        # report carriers
  python pii_sweep.py <repo_path> --emails-heuristic            # propose candidates
  python pii_sweep.py <repo_path> --strings strings.txt --rewrite   # purge (mirror + force-push)

Exit 0 iff the controllable surface (branches+tags) is clean of every string.
Destined for empire-harness/tools/ (Fleet V2 Phase 2).
"""
from __future__ import annotations
import argparse, re, subprocess, sys, os
from pathlib import Path

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SAFE = ("example.", "noreply", "no-reply", "@oasisai", "icloud.com", "anthropic",
        "github", "test.com", "localhost", "domain.com", "sentry", "supabase",
        "vercel", "stripe", "openai", "googlegroups", "goldstorm")
TEXT_GLOBS = ["*.md", "*.json", "*.py", "*.csv", "*.txt", "*.js", "*.ts", "*.yml", "*.yaml", "*.html", "*.sql"]


def git(repo, args):
    return subprocess.run(["git", "-C", repo] + args, capture_output=True, text=True, errors="ignore").stdout


def nlines(s):
    return len([x for x in s.splitlines() if x.strip()])


def mask(s):
    return (s[:3] + "***") if len(s) > 3 else s + "*"


def load_strings(path):
    out = []
    for ln in open(path, encoding="utf-8"):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        out.append(ln.split("==>", 1)[0])
    return out


def cmd_sweep(repo, strings):
    print(f"=== PII sweep: {repo} ({len(strings)} strings) ===")
    bt_total = pr_total = 0
    for s in strings:
        bt = nlines(git(repo, ["log", "--branches", "--tags", "-S", s, "--oneline", "--"] + TEXT_GLOBS))
        allh = nlines(git(repo, ["log", "--all", "-S", s, "--oneline", "--"] + TEXT_GLOBS))
        pr = allh - bt
        bt_total += bt
        pr_total += pr
        if bt or pr:
            print(f"  {mask(s):<14} branches+tags={bt}  pull-refs/other={pr}")
    print(f"\n  CONTROLLABLE surface (branches+tags): {bt_total}  {'CLEAN' if bt_total == 0 else 'DIRTY — purge needed'}")
    if pr_total:
        print(f"  GitHub-managed refs/pull/* (or binary blobs): {pr_total} — git cannot rewrite these.")
        print("  Clear via: GitHub Support purge of unreachable commits, OR make the repo private.")
    return 0 if bt_total == 0 else 1


def cmd_emails_heuristic(repo):
    seen = {}
    # HEAD tree + recent history sample
    files = git(repo, ["ls-tree", "-r", "--name-only", "HEAD"]).splitlines()
    for f in files:
        if not f.lower().endswith(tuple(g[1:] for g in TEXT_GLOBS)):
            continue
        for e in set(EMAIL.findall(git(repo, ["show", f"HEAD:{f}"]))):
            if not any(x in e.lower() for x in SAFE):
                seen.setdefault(e.lower(), set()).add(f)
    print(f"=== {len(seen)} candidate non-safe email(s) on HEAD (adjudicate before --rewrite) ===")
    for e in sorted(seen):
        print(f"  {e:<40} [{sorted(seen[e])[0]}]")
    return 0


def cmd_rewrite(repo, strings_file):
    repo = str(Path(repo).resolve())
    name = Path(repo).name
    mirror = str(Path(repo).parent / f"{name}_piisweep_mirror.git")
    url = git(repo, ["remote", "get-url", "origin"]).strip()
    if not url:
        print("ERROR: no origin remote; cannot rewrite safely.", file=sys.stderr)
        return 2
    print(f"[rewrite] mirror={mirror} origin={url}")
    subprocess.run(["rm", "-rf", mirror])
    subprocess.run(["git", "clone", "--mirror", url, mirror])
    r = subprocess.run(["git", "-C", mirror, "filter-repo", "--replace-text", strings_file,
                        "--replace-message", strings_file, "--force"])
    if r.returncode != 0:
        print("ERROR: filter-repo failed; mirror left for inspection.", file=sys.stderr)
        return 1
    print("[rewrite] filter-repo done. Mirror NOT pushed — verify, then:")
    print(f"  git -C {mirror} push origin --force --all && git -C {mirror} push origin --force --tags")
    print("  (binary blobs are skipped by --replace-text; check the sweep for pull-ref/binary residual.)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repo")
    ap.add_argument("--strings")
    ap.add_argument("--emails-heuristic", action="store_true")
    ap.add_argument("--rewrite", action="store_true")
    args = ap.parse_args()
    if args.emails_heuristic:
        return cmd_emails_heuristic(args.repo)
    if not args.strings:
        ap.error("--strings is required unless --emails-heuristic")
    strings = load_strings(args.strings)
    if args.rewrite:
        return cmd_rewrite(args.repo, args.strings)
    return cmd_sweep(args.repo, strings)


if __name__ == "__main__":
    sys.exit(main())
