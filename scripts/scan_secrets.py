#!/usr/bin/env python3
"""Secret scanner — hunt for leaked credentials before they hit GitHub.

Runs in two modes:

1. Working-tree scan (default)
   Walks every tracked file + every untracked-but-not-gitignored file and
   checks against a library of known secret shapes.

2. History scan (--history)
   Walks every commit in all branches/tags and flags any commit that
   introduced content matching a secret shape. Use this after you've
   already leaked something once — it tells you which commit to scrub.

Exit codes:
    0  = no secrets found
    1  = secrets found (details printed)
    2  = tool error (no scan performed)

Usage:
    python scripts/scan_secrets.py                    # quick tree scan
    python scripts/scan_secrets.py --history          # full git history
    python scripts/scan_secrets.py --json             # machine-readable
    python scripts/scan_secrets.py --path ../CMO-Agent # scan a sibling repo

Add-ons for future hardening (deliberately not done here to stay stdlib-only):
    - Pre-commit hook wiring (simple one-liner in .git/hooks/pre-commit)
    - Allowlist for known-safe test fixtures
    - Integration with GitGuardian or trufflehog for deeper scans
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterator

if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Secret shapes ─────────────────────────────────────────────────────────────
#
# Each rule: (display name, regex, minimum length to consider a match).
# Regex match is case-sensitive by default — that helps cut false positives.
# We explicitly avoid matching placeholder strings like "INSERT_YOUR_KEY".

SECRET_RULES: list[tuple[str, re.Pattern[str]]] = [
    # AI providers
    ("Anthropic API key",
     re.compile(r"\bsk-ant-(?:api03|oat01|admin01)-[A-Za-z0-9_\-]{60,}")),
    ("OpenAI API key",
     re.compile(r"\bsk-(?!ant-)(?!proj-)[A-Za-z0-9]{30,}")),
    ("OpenAI project key",
     re.compile(r"\bsk-proj-[A-Za-z0-9_\-]{40,}")),
    ("Google API key",
     re.compile(r"\bAIza[A-Za-z0-9_\-]{35}\b")),
    # Source control / infra
    ("GitHub personal access token",
     re.compile(r"\bghp_[A-Za-z0-9]{36,}")),
    ("GitHub OAuth token",
     re.compile(r"\bgho_[A-Za-z0-9]{36,}")),
    ("GitHub fine-grained PAT",
     re.compile(r"\bgithub_pat_[A-Za-z0-9_]{80,}")),
    # Cloud / platform
    ("Supabase service role (sbp_)",
     re.compile(r"\bsbp_[A-Za-z0-9]{40,}")),
    ("Stripe live secret key",
     re.compile(r"\bsk_live_[A-Za-z0-9]{24,}")),
    ("Stripe test secret key",
     re.compile(r"\bsk_test_[A-Za-z0-9]{24,}")),
    ("Stripe restricted key",
     re.compile(r"\brk_(?:live|test)_[A-Za-z0-9]{24,}")),
    ("AWS access key id",
     re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    # Chat / messaging
    ("Slack bot token",
     re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("Discord bot token (3-part)",
     re.compile(r"\b[MN][A-Za-z0-9]{23}\.[A-Za-z0-9_\-]{6}\.[A-Za-z0-9_\-]{27,}")),
    ("Telegram bot token",
     re.compile(r"\b\d{6,}:[A-Za-z0-9_\-]{30,}")),
    ("Twilio account SID",
     re.compile(r"\bAC[a-f0-9]{32}\b")),
    # Meta / Facebook (this incident's flavor)
    ("Facebook access token (EAA)",
     re.compile(r"\bEAA[A-Za-z0-9]{100,}")),
    ("Meta app_id|app_secret access token",
     re.compile(r"\b\d{14,20}\|[A-Za-z0-9]{20,40}\b")),
    # Generic catches
    ("Private key block",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----")),
    ("PGP private key block",
     re.compile(r"-----BEGIN PGP PRIVATE KEY BLOCK-----")),
    ("JWT",
     re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
]

# Filename substrings that ALWAYS warrant a flag (like `.long_lived_token.txt`
# — even if the contents happen to look innocent, a file named like this
# almost certainly holds a secret).
SUSPICIOUS_FILENAMES = [
    "long_lived_token",
    "_token.txt",
    "_token.json",
    "credentials.json",
    "service_account.json",
    "id_rsa",
    "id_ed25519",
]

# Known-safe filenames (avoid false positives from security tooling itself).
ALLOWLIST_FILES = {
    ".secrets.baseline",       # detect-secrets baseline — by design
    "scripts/scan_secrets.py", # this very scanner carries the regexes
}

# Placeholder strings that look secret-like but aren't.
PLACEHOLDERS = {
    "INSERT_YOUR_APP_SECRET",
    "INSERT_YOUR_APP_ID",
    "YOUR_API_KEY_HERE",
    "xxxxxxxxxxxx",
}

# Don't scan binary / large / irrelevant extensions.
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".mp3", ".mp4", ".mov",
    ".zip", ".tar", ".gz", ".7z", ".exe", ".dll", ".so", ".dylib", ".wasm",
    ".pyc", ".pyo", ".whl", ".egg", ".ttf", ".otf", ".woff", ".woff2",
    ".ico", ".icns", ".ldb", ".db-wal", ".sqlite-shm",
}

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".next", ".nuxt", ".cache", ".claude/worktrees",
}


def _git_cmd(args: list[str], cwd: Path) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=120,
        )
        return r.returncode, r.stdout or ""
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def _is_ignored(path: Path, repo_root: Path) -> bool:
    rc, _ = _git_cmd(["check-ignore", "-q", str(path)], cwd=repo_root)
    return rc == 0


def _iter_tree_files(repo_root: Path) -> Iterator[Path]:
    """Yield every file that git would include (tracked OR untracked-not-ignored).

    We ask git directly rather than walking the filesystem so gitignored
    content (.venv, node_modules, tmp/, browser caches) is skipped cleanly.
    A gitignored file cannot leak via git, so there's no reason to scan it —
    and Chromium caches in tmp/ produce endless false positives otherwise.
    """
    rc, stdout = _git_cmd(
        ["ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=repo_root)
    if rc != 0:
        return
    for rel in stdout.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        # Defense in depth: skip known cache/vendor dirs even if somehow not
        # gitignored (e.g. a new developer clone without .gitignore).
        if any(part in SKIP_DIRS for part in rel.replace("\\", "/").split("/")):
            continue
        p = (repo_root / rel).resolve()
        if p.suffix.lower() in SKIP_EXTENSIONS:
            continue
        try:
            if p.stat().st_size > 2 * 1024 * 1024:
                continue
        except OSError:
            continue
        yield p


def _scan_text(text: str) -> list[tuple[str, str]]:
    """Return list of (rule_name, matched_snippet) for any secret found."""
    hits = []
    for name, rgx in SECRET_RULES:
        for m in rgx.finditer(text):
            matched = m.group(0)
            # Skip obvious placeholders.
            if any(ph in matched for ph in PLACEHOLDERS):
                continue
            # Common Telegram documentation placeholder, not a live bot token.
            if name == "Telegram bot token" and matched.startswith("123456:"):
                continue
            # Redact the middle of the match — keep 8 chars at each end.
            redacted = (matched[:8] + "..." + matched[-8:]
                        if len(matched) > 20 else matched[:4] + "...")
            hits.append((name, redacted))
    return hits


def scan_tree(repo_root: Path) -> dict:
    findings: list[dict] = []
    files_scanned = 0
    for p in _iter_tree_files(repo_root):
        rel = p.relative_to(repo_root)
        rel_str = str(rel).replace("\\", "/")
        # Allowlist — security tooling itself can carry the regexes.
        if rel_str in ALLOWLIST_FILES:
            continue
        # Suspicious filename — flag even before reading
        for needle in SUSPICIOUS_FILENAMES:
            if needle in rel_str.lower():
                findings.append({"path": rel_str, "rule": "Suspicious filename",
                                 "match": needle})
                break
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        files_scanned += 1
        for rule_name, redacted in _scan_text(text):
            findings.append({"path": rel_str, "rule": rule_name,
                             "match": redacted})
    return {"mode": "tree", "repo": str(repo_root),
            "files_scanned": files_scanned, "findings": findings}


def scan_history(repo_root: Path) -> dict:
    """Grep every commit for secret-shaped content. Slower but catches
    leaked-once-then-deleted secrets — the exact case this tool was built for."""
    rc, commits_out = _git_cmd(
        ["log", "--all", "--full-history", "--pretty=format:%H"], cwd=repo_root)
    if rc != 0:
        return {"mode": "history", "error": "git log failed",
                "repo": str(repo_root)}
    commits = [c for c in commits_out.splitlines() if c.strip()]
    findings: list[dict] = []
    for commit in commits:
        rc, diff_out = _git_cmd(
            ["show", "--no-color", "--unified=0", commit], cwd=repo_root)
        if rc != 0:
            continue
        current_path = ""
        for line in diff_out.splitlines():
            if line.startswith("+++ b/"):
                current_path = line[6:].strip()
                continue
            if line.startswith("+++ /dev/null"):
                current_path = ""
                continue
            if current_path in ALLOWLIST_FILES:
                continue
            # Only scan added lines to reduce noise.
            if not line.startswith("+") or line.startswith("+++"):
                continue
            added = line[1:]
            for name, redacted in _scan_text(added):
                findings.append({"commit": commit[:8], "rule": name,
                                 "path": current_path or "?",
                                 "match": redacted})
    return {"mode": "history", "repo": str(repo_root),
            "commits_scanned": len(commits), "findings": findings}


def _format_findings(result: dict) -> int:
    findings = result.get("findings", [])
    mode = result.get("mode", "?")
    if not findings:
        scope = (f"{result.get('files_scanned', 0)} files"
                 if mode == "tree"
                 else f"{result.get('commits_scanned', 0)} commits")
        print(f"OK  clean - scanned {scope} in {result['repo']}")
        return 0
    print(f"FAIL  {len(findings)} finding(s) in {result['repo']}  ({mode})")
    print()
    for f in findings:
        if mode == "tree":
            print(f"    [{f['rule']}]  {f['path']}")
        else:
            print(f"    [{f['rule']}]  commit {f.get('commit', '?')}  {f.get('path', '?')}")
        print(f"        match: {f['match']}")
    print()
    print("Remediation:")
    print("  1. Revoke / rotate each exposed credential at its provider.")
    print("  2. Scrub git history with:  git filter-repo --path <file> --invert-paths")
    print("  3. Force-push:              git push origin --force --all")
    print("  4. Add the file pattern to .gitignore so it can't re-land.")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--history", action="store_true",
                    help="Scan all commits in all branches (slow, thorough)")
    ap.add_argument("--path", default=".",
                    help="Repo root to scan (default: cwd)")
    ap.add_argument("--json", action="store_true",
                    help="Machine-readable output")
    args = ap.parse_args()

    repo_root = Path(args.path).resolve()
    if not (repo_root / ".git").exists():
        print(f"Not a git repo: {repo_root}")
        return 2

    result = scan_history(repo_root) if args.history else scan_tree(repo_root)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if not result.get("findings") else 1
    return _format_findings(result)


if __name__ == "__main__":
    sys.exit(main())
