"""Generate a conventional-commits → CHANGELOG.md draft from `git log`.

Prints a markdown block for any commits SINCE the most recent version header
in CHANGELOG.md. Bucketed by conventional-commit type (`feat`, `fix`, `chore`,
`refactor`, `docs`, `test`, `perf`). Use the output as a starting point —
this script does NOT modify CHANGELOG.md directly.

Usage:
    python scripts/generate_changelog.py           # text block to stdout
    python scripts/generate_changelog.py --json    # parsed groups
    python scripts/generate_changelog.py --since v6.8.2  # explicit cut point
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"

# `feat(scope): message` / `fix: message` etc
_CONVENTIONAL_RE = re.compile(
    r"^(?P<type>feat|fix|chore|refactor|docs|test|perf|build|ci|style)"
    r"(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?:\s*(?P<msg>.+)$",
    re.IGNORECASE,
)

# `## [6.8.3] — ...` in CHANGELOG.md
_VERSION_HEADER_RE = re.compile(r"^## \[(?P<v>[0-9]+\.[0-9]+\.[0-9]+(?:[a-zA-Z0-9\.\-]*)?)\]")

# Bucket display order
_BUCKET_ORDER = [
    ("feat",     "Added"),
    ("fix",      "Fixed"),
    ("refactor", "Changed"),
    ("perf",     "Changed"),
    ("test",     "Tests"),
    ("docs",     "Docs"),
    ("chore",    "Chore"),
    ("build",    "Build"),
    ("ci",       "CI"),
    ("style",    "Style"),
]


def latest_version_in_changelog() -> str | None:
    if not CHANGELOG.exists():
        return None
    for line in CHANGELOG.read_text(encoding="utf-8").splitlines():
        m = _VERSION_HEADER_RE.match(line)
        if m:
            return m.group("v")
    return None


def git_commits_since(ref: str | None) -> list[str]:
    """Each commit as `<short_hash> <subject>`. Empty list if git fails."""
    cmd = ["git", "-C", str(PROJECT_ROOT), "log", "--pretty=format:%h %s"]
    if ref:
        cmd.append(f"{ref}..HEAD")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (subprocess.SubprocessError, OSError):
        return []
    if result.returncode != 0:
        return []
    return [ln for ln in result.stdout.splitlines() if ln.strip()]


def bucket_commits(commits: list[str]) -> dict[str, list[dict]]:
    """Group commits by conventional-commit type. Non-conventional → 'other'."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for line in commits:
        sha, _, subject = line.partition(" ")
        m = _CONVENTIONAL_RE.match(subject)
        if m:
            type_ = m.group("type").lower()
            groups[type_].append({
                "sha": sha,
                "scope": m.group("scope"),
                "breaking": bool(m.group("bang")),
                "message": m.group("msg").strip(),
            })
        else:
            groups["other"].append({"sha": sha, "message": subject.strip()})
    return groups


def render_text(groups: dict[str, list[dict]]) -> str:
    lines: list[str] = []
    seen_buckets: set[str] = set()
    for typ, label in _BUCKET_ORDER:
        if typ in groups and groups[typ] and label not in seen_buckets:
            lines.append(f"\n### {label}")
            for c in groups[typ]:
                scope = f"**{c['scope']}**: " if c.get("scope") else ""
                bang = "  ⚠️ BREAKING" if c.get("breaking") else ""
                lines.append(f"- {scope}{c['message']} ({c['sha']}){bang}")
            seen_buckets.add(label)
    if "other" in groups and groups["other"]:
        lines.append("\n### Other (non-conventional)")
        for c in groups["other"]:
            lines.append(f"- {c['message']} ({c['sha']})")
    return "\n".join(lines).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", help="git ref to diff from (default: latest CHANGELOG version tag)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    ref = args.since
    if not ref:
        latest = latest_version_in_changelog()
        if latest:
            ref = f"v{latest}"
            # Verify tag exists; otherwise fall back to no ref
            check = subprocess.run(
                ["git", "-C", str(PROJECT_ROOT), "rev-parse", "--verify", ref],
                capture_output=True, text=True, timeout=10,
            )
            if check.returncode != 0:
                ref = None  # tag doesn't exist; show full log

    commits = git_commits_since(ref)
    groups = bucket_commits(commits)

    if args.json:
        print(json.dumps({"since": ref, "commit_count": len(commits), "groups": groups}, indent=2))
    else:
        header_ref = ref or "(no prior version tag — full git log)"
        print(f"# Draft changelog block — commits since {header_ref}")
        print(f"# {len(commits)} commits parsed")
        print(render_text(groups))
    return 0


if __name__ == "__main__":
    sys.exit(main())
