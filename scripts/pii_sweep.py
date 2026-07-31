#!/usr/bin/env python3
"""Content-keyed PII sweep (audit V2/V3). Sweep a repo by OPERATOR-ADJUDICATED
strings — never by paths alone (the path-keyed-purge lesson: path-keyed purges
miss content that leaked wider into prose, changelogs, and tooling).

STANDING LAW (V3): redaction tooling and redaction paperwork must NEVER contain
or emit the strings they redact. Adjudicated strings live ONLY in a gitignored
local file (default: state/pii_adjudication.txt); this tool reports carriers as
`string #N` (an index), never the value or even a masked prefix. The companion
self-test (scripts/tests/test_pii_sweep_self.py) asserts output ∩ input = ∅ and
that no adjudicated string appears in this source file.

Distinguishes the CONTROLLABLE surface (branches + tags — what a normal clone gets
and what `git push` can rewrite) from GitHub-managed `refs/pull/*` (which git
cannot rewrite — only GitHub Support / making the repo private clears those). Also
flags blobs git treats as BINARY, because `filter-repo --replace-text` skips them.

Usage:
  python pii_sweep.py <repo_path>                               # uses default adjudication file
  python pii_sweep.py <repo_path> --strings <local_file>        # report carriers (string #N)
  python pii_sweep.py <repo_path> --emails-heuristic            # propose candidates (operator-facing)
  python pii_sweep.py <repo_path> --rewrite                     # purge (mirror + filter-repo)

Exit 0 iff the controllable surface (branches+tags) is clean of every string.
Mirrored into empire-harness/tools/ (kept in lockstep via the version bump).
"""
from __future__ import annotations
import argparse, re, subprocess, sys, tempfile, os
from pathlib import Path

CAPABILITY_META = {
    "category": "security.privacy",
    "lifecycle": "active",
    "risk": "destructive",
    "triggers": ["scan repository for pii", "audit pii history", "check redaction carriers"],
    "owner": "bravo",
    "project": "empire",
    "bridge": {
        "visible": True,
        "confirm": False,
        "fixed_args": ["."],
        "deny_args": ["--rewrite", "--strings"],
    },
}

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Generic infrastructure / own-domain tokens excluded from the email heuristic.
# These are NOT redacted strings — they are exclusions — so the standing law does
# not apply to them. Operator-specific test handles may also be listed in the
# adjudication file under a leading "safe:" prefix.
SAFE = ("example.", "noreply", "no-reply", "@oasisai", "icloud.com", "anthropic",
        "github", "test.com", "localhost", "domain.com", "sentry", "supabase",
        "vercel", "stripe", "openai", "googlegroups", "goldstorm")
TEXT_GLOBS = ["*.md", "*.json", "*.py", "*.csv", "*.txt", "*.js", "*.ts", "*.yml", "*.yaml", "*.html", "*.sql"]

DEFAULT_STRINGS = "state/pii_adjudication.txt"  # gitignored; local-only


def git(repo, args):
    # Windows console-suppression — pii_sweep is interactive but also
    # called from PR-time hooks; either way no console flicker desired.
    from lib.subprocess_helpers import WINDOWLESS_FLAGS, windowless_startupinfo
    return subprocess.run(
        ["git", "-C", repo] + args, capture_output=True, text=True, errors="ignore",
        creationflags=WINDOWLESS_FLAGS, startupinfo=windowless_startupinfo(),
    ).stdout


def nlines(s):
    return len([x for x in s.splitlines() if x.strip()])


def load_strings(path):
    """Read adjudicated redact-strings from a local file. Lines beginning with
    '#' are comments; lines beginning with 'safe:' are exclusions (returned
    separately); an optional '==>' replacement is stripped for matching."""
    redact, safe = [], []
    for ln in open(path, encoding="utf-8"):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        if ln.lower().startswith("safe:"):
            safe.append(ln.split(":", 1)[1].strip())
            continue
        redact.append(ln.split("==>", 1)[0].strip())
    return redact, safe


def cmd_sweep(repo, strings):
    print(f"=== PII sweep: {repo} ({len(strings)} adjudicated strings) ===")
    bt_total = pr_total = 0
    for i, s in enumerate(strings, 1):
        bt = nlines(git(repo, ["log", "--branches", "--tags", "-S", s, "--oneline", "--"] + TEXT_GLOBS))
        allh = nlines(git(repo, ["log", "--all", "-S", s, "--oneline", "--"] + TEXT_GLOBS))
        pr = allh - bt
        bt_total += bt
        pr_total += pr
        if bt or pr:
            print(f"  string #{i:<3} branches+tags={bt}  pull-refs/other={pr}")
    print(f"\n  CONTROLLABLE surface (branches+tags): {bt_total}  {'CLEAN' if bt_total == 0 else 'DIRTY — purge needed'}")
    if pr_total:
        print(f"  GitHub-managed refs/pull/* (or binary blobs): {pr_total} — git cannot rewrite these.")
        print("  Clear via: GitHub Support purge of unreachable commits, OR make the repo private.")
    return 0 if bt_total == 0 else 1


def cmd_emails_heuristic(repo, extra_safe=()):
    safe = tuple(s.lower() for s in SAFE) + tuple(s.lower() for s in extra_safe)
    seen = {}
    files = git(repo, ["ls-tree", "-r", "--name-only", "HEAD"]).splitlines()
    for f in files:
        if not f.lower().endswith(tuple(g[1:] for g in TEXT_GLOBS)):
            continue
        for e in set(EMAIL.findall(git(repo, ["show", f"HEAD:{f}"]))):
            if not any(x in e.lower() for x in safe):
                seen.setdefault(e.lower(), set()).add(f)
    print(f"=== {len(seen)} candidate non-safe email(s) on HEAD (adjudicate before --rewrite) ===")
    for e in sorted(seen):
        print(f"  {e:<40} [{sorted(seen[e])[0]}]")
    return 0


def cmd_rewrite(repo, strings):
    repo = str(Path(repo).resolve())
    name = Path(repo).name
    mirror = str(Path(repo).parent / f"{name}_piisweep_mirror.git")
    url = git(repo, ["remote", "get-url", "origin"]).strip()
    if not url:
        print("ERROR: no origin remote; cannot rewrite safely.", file=sys.stderr)
        return 2
    # Materialize a filter-repo --replace-text file from the adjudicated strings.
    # (filter-repo treats a bare line as `literal==>***REMOVED***`.)
    fd, repl = tempfile.mkstemp(prefix="piisweep_repl_", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for s in strings:
            fh.write(s + "\n")
    print(f"[rewrite] mirror={mirror} origin={url}  ({len(strings)} strings)")
    # Local import — pii_sweep is sometimes invoked in environments
    # without lib/ on sys.path; the git() helper already imported above.
    from lib.subprocess_helpers import WINDOWLESS_FLAGS, windowless_startupinfo
    subprocess.run(
        ["rm", "-rf", mirror],
        creationflags=WINDOWLESS_FLAGS, startupinfo=windowless_startupinfo(),
    )
    subprocess.run(
        ["git", "clone", "--mirror", url, mirror],
        creationflags=WINDOWLESS_FLAGS, startupinfo=windowless_startupinfo(),
    )
    r = subprocess.run(
        ["git", "-C", mirror, "filter-repo", "--replace-text", repl,
         "--replace-message", repl, "--force"],
        creationflags=WINDOWLESS_FLAGS, startupinfo=windowless_startupinfo(),
    )
    os.unlink(repl)
    if r.returncode != 0:
        print("ERROR: filter-repo failed; mirror left for inspection.", file=sys.stderr)
        return 1
    print("[rewrite] filter-repo done. Mirror NOT pushed — verify, then:")
    print(f"  git -C {mirror} push origin --force --all && git -C {mirror} push origin --force --tags")
    print("  (binary blobs are skipped by --replace-text; check the sweep for pull-ref/binary residual.)")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Content-keyed PII sweep — see module docstring.")
    ap.add_argument("repo")
    ap.add_argument("--strings", default=DEFAULT_STRINGS,
                    help=f"local adjudication file (default: {DEFAULT_STRINGS}, gitignored)")
    ap.add_argument("--emails-heuristic", action="store_true")
    ap.add_argument("--rewrite", action="store_true")
    args = ap.parse_args()

    redact, safe = ([], [])
    if Path(args.strings).exists():
        redact, safe = load_strings(args.strings)
    if args.emails_heuristic:
        return cmd_emails_heuristic(args.repo, extra_safe=safe)
    if not redact:
        ap.error(f"no adjudicated strings found in {args.strings} (create it locally; it is gitignored)")
    if args.rewrite:
        return cmd_rewrite(args.repo, redact)
    return cmd_sweep(args.repo, redact)


if __name__ == "__main__":
    sys.exit(main())
