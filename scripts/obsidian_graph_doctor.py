#!/usr/bin/env python3
"""Obsidian vault graph doctor — broken links, orphan nodes, frontmatter hygiene.

Why this exists (and why it supersedes the naive scanner):
  Obsidian resolves `[[Foo]]` by *basename* anywhere in the vault, not by
  repo-root-relative path. It also excludes any path matching
  `.obsidian/app.json -> userIgnoreFilters` from the vault entirely. A scanner
  that ignores both facts reports resolvable links as broken (false positives)
  AND treats links into ignored dirs (e.g. `.claude/`) as fine (false negatives).

Definitions used here (matching Obsidian's own graph view):
  broken link  — a `[[target]]` that resolves to no in-vault note.
  orphan       — an in-vault note with zero inbound AND zero outbound links.
  weak node    — an in-vault note with links in only one direction (<2 total).

Usage:
  python scripts/obsidian_graph_doctor.py                 # full report
  python scripts/obsidian_graph_doctor.py --json          # machine-readable
  python scripts/obsidian_graph_doctor.py --broken-only
  python scripts/obsidian_graph_doctor.py --orphans-only
  python scripts/obsidian_graph_doctor.py --frontmatter   # tags/last_updated audit
  python scripts/obsidian_graph_doctor.py --strict        # exit 1 if broken links exist
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from lib import frontmatter as fm  # noqa: E402
from lib.vault_scope import (  # noqa: E402
    ARTIFACT_PREFIXES,
    HARD_IGNORES,
    is_ignored,
    is_protected,
    load_ignore_filters,
)

WIKILINK_RE = re.compile(r"\[\[([^\]\[]+?)\]\]")
FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")

IGNORED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf",
    ".mp3", ".mp4", ".wav", ".mov", ".xlsx", ".csv", ".zip",
}

# --------------------------------------------------------------------------
# Vault scoping — the membership rules live in lib/vault_scope so this tool and
# frontmatter_doctor can never disagree about what "in the vault" means.
# --------------------------------------------------------------------------
def collect_vault_notes(filters: list[str], include_artifacts: bool = False) -> list[Path]:
    """All markdown notes Obsidian would actually index, minus build artifacts."""
    notes: list[Path] = []
    for md in REPO_ROOT.rglob("*.md"):
        rel = md.relative_to(REPO_ROOT).as_posix()
        if is_ignored(rel, filters):
            continue
        if not include_artifacts and rel.startswith(ARTIFACT_PREFIXES):
            continue
        notes.append(md)
    return sorted(notes)


# --------------------------------------------------------------------------
# Link parsing + Obsidian-compatible resolution
# --------------------------------------------------------------------------
def strip_code(text: str) -> str:
    text = FENCED_CODE_RE.sub("", text)
    return INLINE_CODE_RE.sub("", text)


def extract_links(text: str) -> list[str]:
    """Return raw link targets, stripping `|alias` and `#anchor` / `^block`."""
    out: list[str] = []
    for match in WIKILINK_RE.finditer(strip_code(text)):
        raw = match.group(1).split("|")[0]
        raw = raw.split("#")[0].split("^")[0].strip()
        if raw:
            out.append(raw)
    return out


def build_index(notes: list[Path]) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Return (by_relpath, by_basename) lookup tables keyed lowercase."""
    by_path: dict[str, str] = {}
    by_base: dict[str, list[str]] = defaultdict(list)
    for note in notes:
        rel = note.relative_to(REPO_ROOT).as_posix()
        by_path[rel.lower()] = rel
        by_path[rel[:-3].lower()] = rel  # without .md
        by_base[note.stem.lower()].append(rel)
    return by_path, dict(by_base)


def resolve_link(
    target: str, by_path: dict[str, str], by_base: dict[str, list[str]]
) -> str | None:
    """Resolve one wikilink to an in-vault note path, Obsidian-style."""
    t = target.strip().replace("\\", "/").lstrip("./")
    if not t:
        return None
    if Path(t).suffix.lower() in IGNORED_EXTENSIONS:
        return None  # attachment, not a note — out of scope

    # 1. Exact vault-relative path (with or without .md).
    hit = by_path.get(t.lower())
    if hit:
        return hit

    # 2. Basename match anywhere in the vault (Obsidian's default behaviour).
    stem = Path(t).stem.lower()
    candidates = by_base.get(stem)
    if candidates:
        # Prefer a candidate whose path ends with the written target.
        suffix = t.lower().removesuffix(".md")
        for cand in candidates:
            if cand.lower().removesuffix(".md").endswith(suffix):
                return cand
        # Otherwise the shortest path wins (matches newLinkFormat: "shortest").
        return min(candidates, key=lambda p: (p.count("/"), len(p)))

    return None


# --------------------------------------------------------------------------
# Frontmatter
# --------------------------------------------------------------------------
def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Frontmatter fields, or None when the note has no frontmatter block."""
    block, _body, _eol = fm.split(text)
    if block is None:
        return None
    return fm.parse(block)


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------
CODE_SUFFIXES = (".py", ".js", ".mjs", ".ts", ".tsx", ".json", ".sh", ".sql", ".toml", ".yml", ".yaml")


_CODE_INDEX: dict[str, list[str]] | None = None


def build_code_index() -> dict[str, list[str]]:
    """One pruned walk of the repo -> {basename_stem: [relpaths]} for code files.

    Built once and cached. A naive `rglob` per lookup walks `node_modules` and
    turns a 5-second audit into a multi-minute one.
    """
    global _CODE_INDEX
    if _CODE_INDEX is not None:
        return _CODE_INDEX
    index: dict[str, list[str]] = defaultdict(list)
    stack = [REPO_ROOT]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            name = entry.name
            if entry.is_dir():
                if name in HARD_IGNORES or name.startswith(".git"):
                    continue
                rel_dir = entry.relative_to(REPO_ROOT).as_posix() + "/"
                if rel_dir.startswith(ARTIFACT_PREFIXES):
                    continue
                stack.append(entry)
            elif entry.suffix.lower() in CODE_SUFFIXES or entry.suffix.lower() == ".md":
                index[entry.stem.lower()].append(
                    entry.relative_to(REPO_ROOT).as_posix()
                )
    _CODE_INDEX = dict(index)
    return _CODE_INDEX


def resolve_repo_file(target: str) -> str | None:
    """Resolve a wikilink target to a real repo file/dir that is NOT a vault note.

    Used by --fix-links to turn a permanently-red wikilink into an accurate
    inline code path. Returns a repo-relative POSIX path, or None if unknown.
    """
    t = target.strip().replace("\\", "/")
    if t.startswith("../"):
        return t  # sibling repo — outside the vault, quote it literally

    if (REPO_ROOT / t).exists():
        return t
    for suf in CODE_SUFFIXES:
        if (REPO_ROOT / (t + suf)).is_file():
            return t + suf

    # Basename lookup — catches links that went stale when a file moved.
    hits = set(build_code_index().get(Path(t).stem.lower(), []))
    if len(hits) == 1:
        return hits.pop()
    return None


def plan_link_fixes(report: dict, by_path: dict[str, str]) -> dict[str, list[tuple[str, str, str]]]:
    """Return {source_note: [(raw_target, replacement_markdown, reason), ...]}.

    Three deterministic, meaning-preserving repairs:
      skill-dir  — `[[skills/x]]` where `skills/x/SKILL.md` is a real note.
      code-path  — target is a real repo file/dir, not a note -> inline code.
      cross-repo — target lives outside this repo (`../`) -> inline code.
    Anything else is left alone and surfaced as `unfixable` for human judgment.
    """
    plans: dict[str, list[tuple[str, str, str]]] = {}
    for src, links in report["broken_links"].items():
        for raw in links:
            t = raw.strip().replace("\\", "/")
            # 1. Folder note: [[skills/foo]] -> [[skills/foo/SKILL]]
            if (t.rstrip("/") + "/skill").lower() in by_path:
                plans.setdefault(src, []).append(
                    (raw, f"[[{t.rstrip('/')}/SKILL]]", "skill-dir")
                )
                continue
            # 2 & 3. Real file/dir, or sibling repo -> accurate inline code path.
            actual = resolve_repo_file(t)
            if actual:
                reason = "cross-repo" if actual.startswith("../") else "code-path"
                plans.setdefault(src, []).append((raw, f"`{actual}`", reason))
    return plans


def apply_link_fixes(plans: dict[str, list[tuple[str, str, str]]]) -> int:
    """Rewrite planned links in place. Returns number of links changed."""
    changed = 0
    for src, fixes in plans.items():
        path = REPO_ROOT / src
        # newline="" on BOTH read and write: no universal-newline translation,
        # so a CRLF file stays CRLF. Silently rewriting EOLs breaks the repo's
        # checksum gates (see memory: pattern_eol_normalize_checksum_gates).
        with open(path, "r", encoding="utf-8", newline="") as fh:
            text = fh.read()
        original = text
        for raw, replacement, _reason in fixes:
            # Match the exact link incl. optional |alias, outside code spans.
            pattern = re.compile(
                r"\[\[" + re.escape(raw) + r"(\|[^\]\[]*)?\]\]"
            )
            text, n = pattern.subn(replacement, text)
            changed += n
        if text != original:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
    return changed


LINKS_HEADING = "## Obsidian Links"


def reconnect_orphans(
    report: dict, hubs: list[str], scopes: list[str], dry_run: bool,
    include_weak: bool = False,
) -> list[tuple[str, list[str]]]:
    """Append an `## Obsidian Links` section to orphan notes, linking them to hubs.

    Only touches notes the audit proved are orphans (zero in, zero out) — or,
    with include_weak, also one-directional nodes — and that fall inside an
    explicit --scope. Never rewrites an existing links section.
    """
    done: list[tuple[str, list[str]]] = []
    candidates = list(report["orphans"])
    if include_weak:
        candidates += [w for w in report["weak_nodes"] if w not in set(candidates)]
    for rel in candidates:
        if scopes and not any(rel.startswith(s.rstrip("/") + "/") for s in scopes):
            continue
        # Never append to a generated doc (it gets re-emitted) or a vendored
        # LOCKSTEP block (hash-pinned in harness.lock, no local re-sync tool).
        if is_protected(rel):
            continue
        targets = [h for h in hubs if h != rel.removesuffix(".md")]
        if not targets:
            continue
        path = REPO_ROOT / rel
        with open(path, "r", encoding="utf-8", newline="") as fh:
            text = fh.read()
        if LINKS_HEADING in text:
            continue
        eol = "\r\n" if "\r\n" in text[:2000] else "\n"
        block = (
            eol + eol + LINKS_HEADING + eol
            + eol.join(f"- [[{t}]]" for t in targets) + eol
        )
        if not dry_run:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text.rstrip("\r\n") + block)
        done.append((rel, targets))
    return done


def audit(include_artifacts: bool = False) -> dict:
    filters = load_ignore_filters()
    notes = collect_vault_notes(filters, include_artifacts=include_artifacts)
    by_path, by_base = build_index(notes)

    outbound: dict[str, set[str]] = {}
    inbound: dict[str, set[str]] = defaultdict(set)
    broken: dict[str, list[str]] = defaultdict(list)
    frontmatter: dict[str, dict] = {}

    for note in notes:
        rel = note.relative_to(REPO_ROOT).as_posix()
        try:
            text = note.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        fm = parse_frontmatter(text)
        frontmatter[rel] = {
            "has_frontmatter": fm is not None,
            "has_tags": bool(fm and fm.get("tags")),
            "has_last_updated": bool(fm and (fm.get("last_updated") or fm.get("updated"))),
        }

        targets: set[str] = set()
        for raw in extract_links(text):
            resolved = resolve_link(raw, by_path, by_base)
            if resolved is None:
                if Path(raw).suffix.lower() in IGNORED_EXTENSIONS:
                    continue
                if raw not in broken[rel]:
                    broken[rel].append(raw)
            elif resolved != rel:
                targets.add(resolved)
        outbound[rel] = targets
        for tgt in targets:
            inbound[tgt].add(rel)

    orphans = sorted(
        rel for rel in outbound if not outbound[rel] and not inbound.get(rel)
    )
    weak = sorted(
        rel
        for rel in outbound
        if rel not in orphans and (len(outbound[rel]) + len(inbound.get(rel, ()))) < 2
    )

    return {
        "vault_notes": len(notes),
        "ignore_filters": filters,
        "broken_links": {k: v for k, v in broken.items() if v},
        "broken_count": sum(len(v) for v in broken.values()),
        "orphans": orphans,
        "weak_nodes": weak,
        "frontmatter": frontmatter,
        "edges": sum(len(v) for v in outbound.values()),
        "_by_path": by_path,
    }


def frontmatter_gaps(report: dict) -> list[tuple[str, list[str]]]:
    gaps: list[tuple[str, list[str]]] = []
    for rel, fm in sorted(report["frontmatter"].items()):
        missing = []
        if not fm["has_frontmatter"]:
            missing.append("frontmatter")
        else:
            if not fm["has_tags"]:
                missing.append("tags")
            if not fm["has_last_updated"]:
                missing.append("last_updated")
        if missing:
            gaps.append((rel, missing))
    return gaps


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--broken-only", action="store_true")
    ap.add_argument("--orphans-only", action="store_true")
    ap.add_argument("--frontmatter", action="store_true", help="report tags/last_updated gaps")
    ap.add_argument("--limit", type=int, default=0, help="cap list output (0 = no cap)")
    ap.add_argument("--strict", action="store_true", help="exit 1 when broken links exist")
    ap.add_argument("--include-artifacts", action="store_true",
                    help="also scan generated trees (sidecar bundle, evals, caches)")
    ap.add_argument("--fix-links", action="store_true",
                    help="apply deterministic link repairs (skill-dir / code-path / cross-repo)")
    ap.add_argument("--dry-run", action="store_true", help="with --fix-links/--reconnect, plan only")
    ap.add_argument("--reconnect", action="store_true",
                    help="append an Obsidian Links section to orphans in --scope, pointing at --hub")
    ap.add_argument("--scope", action="append", default=[],
                    help="restrict --reconnect to a directory (repeatable, required)")
    ap.add_argument("--hub", action="append", default=[],
                    help="hub note to link orphans to, e.g. docs/adr/INDEX (repeatable)")
    ap.add_argument("--include-weak", action="store_true",
                    help="with --reconnect, also link one-directional (weak) nodes")
    args = ap.parse_args()

    report = audit(include_artifacts=args.include_artifacts)
    by_path = report.pop("_by_path")

    if args.reconnect:
        if not args.scope or not args.hub:
            print("--reconnect requires at least one --scope and one --hub", file=sys.stderr)
            return 2
        done = reconnect_orphans(
            report, args.hub, args.scope, args.dry_run, include_weak=args.include_weak
        )
        verb = "Would link" if args.dry_run else "Linked"
        print(f"{verb} {len(done)} orphan(s) to {', '.join(args.hub)}\n")
        for rel, targets in done:
            print(f"  {rel}  ->  {', '.join(targets)}")
        if args.dry_run:
            print("\n(dry run — nothing written)")
        return 0

    if args.fix_links:
        plans = plan_link_fixes(report, by_path)
        planned = sum(len(v) for v in plans.values())
        fixable_targets = {raw for v in plans.values() for raw, _, _ in v}
        all_targets = {raw for v in report["broken_links"].values() for raw in v}
        print(f"LINK REPAIR PLAN — {planned} link(s) across {len(plans)} file(s)\n")
        for src, fixes in sorted(plans.items()):
            print(f"  {src}")
            for raw, replacement, reason in fixes:
                print(f"      [[{raw}]]  ->  {replacement}   ({reason})")
        unfixable = sorted(all_targets - fixable_targets)
        if unfixable:
            print(f"\n  NOT auto-fixable ({len(unfixable)} unique targets — need human retarget):")
            for t in unfixable:
                print(f"      [[{t}]]")
        if args.dry_run:
            print("\n(dry run — nothing written)")
            return 0
        changed = apply_link_fixes(plans)
        print(f"\nApplied {changed} link repair(s).")
        return 0

    if args.json:
        payload = dict(report)
        if not args.frontmatter:
            payload.pop("frontmatter", None)
        else:
            payload["frontmatter_gaps"] = frontmatter_gaps(report)
            payload.pop("frontmatter", None)
        print(json.dumps(payload, indent=2))
        return 1 if (args.strict and report["broken_count"]) else 0

    def cap(items: list) -> list:
        return items[: args.limit] if args.limit else items

    show_all = not (args.broken_only or args.orphans_only or args.frontmatter)

    print(
        f"OBSIDIAN GRAPH DOCTOR — {report['vault_notes']} in-vault notes, "
        f"{report['edges']} resolved edges"
    )
    print(f"  ignore filters active: {len(report['ignore_filters'])}\n")

    if show_all or args.broken_only:
        print(f"=== BROKEN LINKS ({report['broken_count']}) ===")
        if not report["broken_links"]:
            print("  none\n")
        else:
            for src, links in sorted(
                report["broken_links"].items(), key=lambda kv: -len(kv[1])
            ):
                print(f"  {src} ({len(links)})")
                for link in cap(links):
                    print(f"      [[{link}]]")
            print()

    if show_all or args.orphans_only:
        print(f"=== ORPHANS — zero in + zero out ({len(report['orphans'])}) ===")
        for rel in cap(report["orphans"]):
            print(f"  {rel}")
        if not report["orphans"]:
            print("  none")
        print()
        print(f"=== WEAK NODES — fewer than 2 total links ({len(report['weak_nodes'])}) ===")
        for rel in cap(report["weak_nodes"]):
            print(f"  {rel}")
        if not report["weak_nodes"]:
            print("  none")
        print()

    if args.frontmatter:
        gaps = frontmatter_gaps(report)
        print(f"=== FRONTMATTER GAPS ({len(gaps)}) ===")
        for rel, missing in cap(gaps):
            print(f"  {rel:<70} missing: {', '.join(missing)}")
        if not gaps:
            print("  none")
        print()

    return 1 if (args.strict and report["broken_count"]) else 0


if __name__ == "__main__":
    sys.exit(main())
