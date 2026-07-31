#!/usr/bin/env python3
"""Stamp canonical `tags:` + `last_updated:` frontmatter on vault knowledge notes.

Why `last_updated` comes from git, not from today:
  RULE 0's staleness gate, `scripts/core/memory_aging.py`, and
  `scripts/check_brain_freshness.py` all treat `last_updated:` as ground truth
  for "is this note still current?". Blanket-stamping today's date on a note
  last genuinely touched in May would tell every future agent the note is fresh
  when it is not — defeating the exact rule that exists to stop agents trusting
  stale context. So the date is derived from the file's last commit
  (`git log -1 --date=short`), falling back to filesystem mtime for untracked
  files. Truthful, and it keeps the freshness gate meaningful.

Existing `tags:` / `last_updated:` values are NEVER overwritten — this only
fills gaps.

Usage:
  python scripts/frontmatter_doctor.py --report
  python scripts/frontmatter_doctor.py --scope brain --scope memory --dry-run
  python scripts/frontmatter_doctor.py --scope brain --scope memory --apply
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from lib import frontmatter as fm  # noqa: E402
from lib.vault_scope import (  # noqa: E402
    ARTIFACT_PREFIXES,
    is_ignored,
    is_protected,
    load_ignore_filters,
)

# Trees that are not this vault's knowledge. ARTIFACT_PREFIXES comes from
# lib.vault_scope so the graph doctor and this tool share ONE per-repo list —
# maintaining two drifted once already (CMO's `vendor/` was excluded from the
# graph but still stamped here). Only genuinely tool-specific paths belong below.
EXCLUDE_PREFIXES = ARTIFACT_PREFIXES + (
    "node_modules/",
    "templates/agent-scaffold/",  # copied into NEW agent repos; keep self-contained
    "browser/evidence/",
    "output/",
    "tmp/",
)

# path prefix -> canonical tags. Longest prefix wins.
TAG_MAP: list[tuple[str, list[str]]] = [
    ("docs/adr/", ["docs", "adr", "decision"]),
    ("docs/sop/", ["docs", "sop", "runbook"]),
    ("docs/deploy/", ["docs", "deploy"]),
    ("docs/audits/", ["docs", "audit"]),
    ("docs/compliance/", ["docs", "compliance"]),
    ("docs/", ["docs"]),
    ("brain/_canonical/", ["brain", "genome", "lockstep"]),
    ("brain/_archive/", ["brain", "archive"]),
    ("brain/", ["brain"]),
    ("memory/ARCHIVES/", ["memory", "archive"]),
    ("memory/daily/", ["memory", "daily"]),
    ("memory/outreach_archive/", ["memory", "archive", "outreach"]),
    ("memory/", ["memory"]),
    ("skills/_archive/", ["skill", "archive"]),
    ("skills/", ["skill"]),
    ("agents/", ["agent"]),
    ("plans/", ["plans"]),
    ("prompts/", ["prompts"]),
    ("browser/", ["browser", "automation"]),
    ("scripts/", ["scripts"]),
    ("_templates/", ["template"]),
    ("rules/", ["rules"]),
    ("infra/", ["infra"]),
    ("install/", ["install"]),
    ("deploy/", ["deploy"]),
    ("knowledge/", ["knowledge"]),
    ("courses/", ["courses"]),
    ("media/", ["media"]),
    ("data/", ["data"]),
    ("state/", ["state"]),
    ("APPS_CONTEXT/", ["apps-context"]),
    ("apps/", ["apps"]),
    (".github/", ["github", "ci"]),
    ("runtime/", ["runtime"]),
    ("database/", ["database", "migrations"]),
    # Sibling-repo directories. Prefixes that don't exist here are inert, and
    # carrying them means Maven/Atlas inherit a working taxonomy instead of
    # tagging half their vault `[root]` the first time they run --apply.
    ("ad-engine/", ["ad-engine", "ads"]),            # Maven
    ("campaigns/", ["campaigns"]),                    # Maven
    ("content-studio/", ["content-studio", "content"]),  # Maven
    ("scratch/", ["scratch", "transient"]),           # Maven
    ("research/quant/", ["research", "quant"]),       # Atlas
    ("research/", ["research"]),                      # Atlas
    ("archive/", ["archive"]),                        # Atlas (retired trading)
]


def git_last_modified() -> dict[str, str]:
    """{repo_relative_path: YYYY-MM-DD} from one `git log` pass.

    One walk of history beats 400+ `git log -1 <file>` subprocess spawns.
    """
    try:
        out = subprocess.run(
            ["git", "log", "--name-only", "--format=%x00%ad", "--date=short", "--", "*.md"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}

    dates: dict[str, str] = {}
    current = ""
    for line in out.splitlines():
        if line.startswith("\x00"):
            current = line[1:].strip()
        elif line.strip() and current:
            dates.setdefault(line.strip(), current)  # first hit = newest commit
    return dates


def tags_for(rel: str) -> list[str]:
    """Canonical tags derived from the note's location in the vault."""
    best: list[str] = []
    best_len = -1
    for prefix, tags in TAG_MAP:
        if rel.startswith(prefix) and len(prefix) > best_len:
            best, best_len = tags, len(prefix)
    if not best:
        best = ["root"]
    tags = list(best)
    # A skill's own name is its most useful retrieval tag.
    if rel.startswith("skills/") and rel.endswith("/SKILL.md"):
        name = rel.split("/")[1]
        if name not in tags:
            tags.append(name)
    return tags


# Frontmatter parsing lives in lib/frontmatter so this tool and
# obsidian_graph_doctor can never disagree about what "has tags" means.
parse_fm = fm.split
has_key = fm.has_field


def collect(scopes: list[str]) -> list[Path]:
    """In-vault notes needing a frontmatter decision.

    Vault membership is decided by the SAME rule the graph doctor uses —
    `.obsidian/app.json` userIgnoreFilters. Without that, an unscoped `--report`
    counts `.claude/`, `.agents/`, and `.gemini/` files that Obsidian never
    indexes, and reports gaps in a vault that is actually clean.
    """
    filters = load_ignore_filters()
    notes: list[Path] = []
    for md in REPO_ROOT.rglob("*.md"):
        rel = md.relative_to(REPO_ROOT).as_posix()
        if rel.startswith(EXCLUDE_PREFIXES) or "/.git/" in "/" + rel:
            continue
        if any(part in {".git", "node_modules", "__pycache__", ".venv"} for part in rel.split("/")):
            continue
        if is_ignored(rel, filters):
            continue
        # Generated docs are re-emitted, and vendored LOCKSTEP blocks are
        # hash-pinned — stamping either breaks a test with no local re-sync path.
        if is_protected(rel):
            continue
        if scopes and not any(rel.startswith(s.rstrip("/") + "/") or rel == s for s in scopes):
            continue
        notes.append(md)
    return sorted(notes)


def plan(scopes: list[str]) -> list[tuple[Path, list[str], str, list[str]]]:
    """[(path, tags_to_add, date_to_add, what_was_missing), ...]"""
    git_dates = git_last_modified()
    out: list[tuple[Path, list[str], str, list[str]]] = []
    for md in collect(scopes):
        rel = md.relative_to(REPO_ROOT).as_posix()
        with open(md, "r", encoding="utf-8", errors="replace", newline="") as fh:
            text = fh.read()
        fm, _body, _eol = parse_fm(text)
        missing: list[str] = []
        if fm is None:
            missing = ["frontmatter", "tags", "last_updated"]
        else:
            if not has_key(fm, "tags"):
                missing.append("tags")
            if not (has_key(fm, "last_updated") or has_key(fm, "updated")):
                missing.append("last_updated")
        if not missing:
            continue
        stamp = git_dates.get(rel)
        if not stamp:
            stamp = datetime.fromtimestamp(md.stat().st_mtime).strftime("%Y-%m-%d")
        add_tags = tags_for(rel) if "tags" in missing else []
        add_date = stamp if "last_updated" in missing else ""
        out.append((md, add_tags, add_date, missing))
    return out


def apply(items: list[tuple[Path, list[str], str, list[str]]]) -> int:
    changed = 0
    for md, add_tags, add_date, missing in items:
        with open(md, "r", encoding="utf-8", errors="replace", newline="") as fh:
            text = fh.read()
        fm, body, eol = parse_fm(text)
        new_lines: list[str] = []
        if add_tags:
            new_lines.append(f"tags: [{', '.join(add_tags)}]")
        if add_date:
            new_lines.append(f"last_updated: {add_date}")
        if not new_lines:
            continue
        if fm is None:
            block = eol.join(["---", *new_lines, "---", ""]) + eol
            text = block + text
        else:
            merged = fm.split("\n")
            merged = [ln.rstrip("\r") for ln in merged]
            merged.extend(new_lines)
            text = (
                "---" + eol + eol.join(merged) + eol + "---" + eol + body
            )
        with open(md, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        changed += 1
    return changed


FALLBACK_TAGS = "[root]"


def retag_fallback(scopes: list[str], dry_run: bool) -> list[tuple[str, list[str]]]:
    """Re-derive tags for notes stamped with the `[root]` fallback.

    `plan()` never overwrites an existing `tags:`, which is the right default —
    but it means a note stamped before TAG_MAP knew about its directory keeps a
    meaningless `[root]` forever. Extending the map fixes nothing on its own.

    Only touches notes whose CURRENT tag is exactly the fallback AND whose path
    now maps to something better. A note genuinely at the repo root still
    resolves to `[root]` and is left alone.
    """
    done: list[tuple[str, list[str]]] = []
    for md in collect(scopes):
        rel = md.relative_to(REPO_ROOT).as_posix()
        with open(md, "r", encoding="utf-8", errors="replace", newline="") as fh:
            text = fh.read()
        block, _body, eol = fm.split(text)
        if not block or f"tags: {FALLBACK_TAGS}" not in block:
            continue
        better = tags_for(rel)
        if better == ["root"]:
            continue  # genuinely a repo-root note
        new_block = block.replace(
            f"tags: {FALLBACK_TAGS}", f"tags: [{', '.join(better)}]", 1
        )
        if not dry_run:
            with open(md, "w", encoding="utf-8", newline="") as fh:
                fh.write(text.replace(block, new_block, 1))
        done.append((rel, better))
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scope", action="append", default=[],
                    help="limit to a directory (repeatable); default = whole vault")
    ap.add_argument("--report", action="store_true", help="summary counts only")
    ap.add_argument("--dry-run", action="store_true", help="list every planned change")
    ap.add_argument("--apply", action="store_true", help="write the changes")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--retag-fallback", action="store_true",
                    help="re-derive tags for notes stamped [root] before TAG_MAP knew their dir")
    args = ap.parse_args()

    if args.retag_fallback:
        done = retag_fallback(args.scope, args.dry_run and not args.apply)
        verb = "Would retag" if (args.dry_run and not args.apply) else "Retagged"
        print(f"{verb} {len(done)} note(s) stamped with the [root] fallback\n")
        for rel, tags in done[: args.limit]:
            print(f"  {rel}\n      -> tags: [{', '.join(tags)}]")
        if len(done) > args.limit:
            print(f"  ... and {len(done) - args.limit} more")
        if not done:
            print("  none — every note either has a real tag or genuinely lives at the repo root")
        return 0

    items = plan(args.scope)
    if not items:
        print("All notes in scope already carry tags + last_updated.")
        return 0

    by_dir: dict[str, int] = defaultdict(int)
    for md, _t, _d, _m in items:
        by_dir[md.relative_to(REPO_ROOT).as_posix().split("/")[0]] += 1

    print(f"FRONTMATTER DOCTOR — {len(items)} note(s) need stamping"
          f"{' in scope ' + ', '.join(args.scope) if args.scope else ''}\n")
    for d, n in sorted(by_dir.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>4}  {d}/")
    print()

    if args.report:
        return 0

    if args.dry_run or not args.apply:
        for md, tags, stamp, missing in items[: args.limit]:
            rel = md.relative_to(REPO_ROOT).as_posix()
            bits = []
            if tags:
                bits.append(f"tags: [{', '.join(tags)}]")
            if stamp:
                bits.append(f"last_updated: {stamp}")
            print(f"  {rel}\n      + {'  |  '.join(bits)}   (was missing: {', '.join(missing)})")
        if len(items) > args.limit:
            print(f"  ... and {len(items) - args.limit} more")
        print("\n(dry run — nothing written; pass --apply to write)")
        return 0

    n = apply(items)
    print(f"Stamped {n} note(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
