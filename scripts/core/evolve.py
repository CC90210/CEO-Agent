#!/usr/bin/env python3
"""evolve.py — promote recurring lessons into permanent capability.

THE GAP THIS FILLS. The fleet already *records* lessons: bravo_sleep writes
memory/MISTAKES.md and memory/PATTERNS.md, agent_self_improvement rebuilds the
capability graph and flags stale memory, skills/retro runs a session
retrospective. Nothing PROMOTES. A pattern can be marked `[V]` (validated —
used 3+ times, per Rule 9) and still live only as a memory line: not a skill,
not an SOP, not routable, invisible to `capability_query.py resolve`. The next
agent re-derives it from scratch.

This closes that loop. It reads the validated set, asks which entries have no
owning skill or SOP, and reports them as promotion candidates — with --apply,
scaffolding a real skill directory the graph can route to.

Deliberately conservative: it SCAFFOLDS, it does not author. A skill written by
a heuristic would be exactly the "mock data" defect (Anti-Slop #3) applied to
documentation. The stub carries the evidence and a TODO; a human or an agent
with context fills the body.

Usage:
    python scripts/core/evolve.py scan               # candidates, changes nothing
    python scripts/core/evolve.py scan --json
    python scripts/core/evolve.py promote "<pattern text>" --kind skill
    python scripts/core/evolve.py promote "<pattern text>" --kind sop --apply
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

PATTERNS = PROJECT_ROOT / "memory" / "PATTERNS.md"
MISTAKES = PROJECT_ROOT / "memory" / "MISTAKES.md"
SKILLS_DIR = PROJECT_ROOT / "skills"
SOP_DIR = PROJECT_ROOT / "docs" / "sop"

# Words too generic to match a skill on. Without this, "the" or "agent" matches
# half the catalogue and every pattern looks already-covered — a false negative
# that would make this tool silently useless.
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "for", "with", "from", "into", "then",
    "when", "that", "this", "it", "is", "are", "be", "to", "of", "on", "in", "at",
    "by", "not", "no", "never", "always", "must", "should", "use", "using", "run",
    "before", "after", "every", "each", "any", "all", "one", "two", "new", "old",
    "agent", "bravo", "cc", "file", "code", "script", "check", "fix", "add",
}
MIN_TOKEN_LEN = 4
# A scaffold may only claim a SINGLE-word trigger when the word is long enough to
# be domain vocabulary rather than everyday English. Below this, emit the phrase
# alone — see scaffold_triggers().
SINGLE_WORD_MIN = 9


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z_]{%d,}" % MIN_TOKEN_LEN, text.lower())
            if w not in STOPWORDS}


# PATTERNS.md entries are `### [V] Title (YYYY-MM-DD)` followed by a body
# paragraph. Verified against the file, not assumed: an earlier version of this
# parser split on the literal "[V]" anywhere in a line and captured the text
# AFTER it, which on a heading yields the trailing date and on a prose line
# yields a mid-sentence fragment. Every candidate it produced was garbage.
PATTERN_HEADING_RE = re.compile(
    r"^#{2,4}\s*\[(?P<marker>[PV])\]\s*(?P<title>.+?)\s*(?:\((?P<date>[\d-]+)\))?\s*$")


def validated_patterns(include_probationary: bool = False) -> list[dict]:
    """`### [V] Title` entries in PATTERNS.md — validated = applied 3+ times (Rule 9).

    Returns title + the body paragraph beneath it, since the title alone is too
    short to match meaningfully against a skill's vocabulary.
    """
    if not PATTERNS.exists():
        return []
    lines = PATTERNS.read_text(encoding="utf-8").splitlines()
    out: list[dict] = []
    for i, line in enumerate(lines):
        m = PATTERN_HEADING_RE.match(line.strip())
        if not m:
            continue
        if m.group("marker") != "V" and not include_probationary:
            continue
        body: list[str] = []
        for nxt in lines[i + 1: i + 8]:
            if nxt.strip().startswith("#"):
                break
            if nxt.strip():
                body.append(nxt.strip())
        out.append({
            "line": i + 1,
            "marker": m.group("marker"),
            "title": m.group("title").strip(),
            "date": m.group("date"),
            "text": (m.group("title").strip() + " — " + " ".join(body))[:600],
        })
    return out


def existing_coverage() -> list[dict]:
    """Everything that already owns knowledge: skills and SOPs."""
    cov = []
    for p in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        if "_archive" in p.parts:
            continue
        cov.append({"kind": "skill", "name": p.parent.name,
                    "tokens": tokens(p.read_text(encoding="utf-8")[:4000])})
    if SOP_DIR.is_dir():
        for p in sorted(SOP_DIR.glob("*.md")):
            cov.append({"kind": "sop", "name": p.stem,
                        "tokens": tokens(p.read_text(encoding="utf-8")[:4000])})
    return cov


def best_owner(pattern_tokens: set[str], coverage: list[dict]) -> tuple[float, dict | None]:
    """Jaccard-ish overlap against each owner. Returns (score, owner)."""
    best, best_owner_ = 0.0, None
    for c in coverage:
        if not pattern_tokens:
            continue
        overlap = len(pattern_tokens & c["tokens"]) / len(pattern_tokens)
        if overlap > best:
            best, best_owner_ = overlap, c
    return best, best_owner_


COVERED_THRESHOLD = 0.5


def scan() -> dict:
    pats = validated_patterns()
    cov = existing_coverage()
    covered, candidates = [], []
    for p in pats:
        tk = tokens(p["text"])
        score, owner = best_owner(tk, cov)
        rec = {**p, "score": round(score, 2),
               "owner": f"{owner['kind']}:{owner['name']}" if owner else None}
        (covered if score >= COVERED_THRESHOLD else candidates).append(rec)
    candidates.sort(key=lambda r: r["score"])
    return {
        "validated_total": len(pats),
        "owners_scanned": len(cov),
        "covered": len(covered),
        "candidates": candidates,
    }


SKILL_STUB = """---
name: {slug}
description: {desc}
triggers: [{triggers}]
tier: standard
mutability: EVOLVING
tags: [skill, promoted, evolve]
last_updated: {today}
---

# {title}

> **PROMOTED FROM MEMORY {today}** by `scripts/core/evolve.py`. This pattern was marked
> `[V]` (validated — applied 3+ times) in `memory/PATTERNS.md` but had no owning skill, so
> it was invisible to `capability_query.py resolve` and every agent re-derived it.

## The pattern

{text}

## TODO — fill before this skill is trustworthy

This is a SCAFFOLD, not a finished skill. `evolve.py` deliberately does not author the body:
a heuristic-written skill is mock data wearing documentation's clothes (Anti-Slop #3). Add:

- [ ] **When to use** — the trigger conditions, and when NOT to (calibration)
- [ ] **The procedure** — exact commands, with real paths verified against source
- [ ] **The incident** — what actually went wrong that made this a pattern
- [ ] **`triggers:`** — the ones above are auto-derived from the title so the graph can route
      this at all (a trigger-less skill is drift, and fails `harness_eval`). They are a
      starting point, not a decision. Narrow or replace them, then verify BOTH directions:
      `python scripts/capability_query.py resolve "<intent this should own>"` and
      `python -m pytest scripts/tests/test_routing_accuracy.py -q` (the golden set must stay
      green — a broad trigger steals routes from the skill that should have won)

Then: `python scripts/build_capability_graph.py && python scripts/build_capability_graph.py --emit-docs`

## Related

[[memory/PATTERNS]] · [[brain/EXECUTION_RULES]]
"""


def _slug_source(text: str) -> str:
    """Slug from the TITLE half of "Title — body", not the whole paragraph."""
    return text.split(" — ", 1)[0] if " — " in text else text


def slugify(text: str) -> str:
    text = _slug_source(text)
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return "-".join(s.split("-")[:6])[:48] or "promoted-pattern"


def scaffold_triggers(text: str) -> list[str]:
    """Narrow, title-derived triggers so the scaffold is routable from birth.

    `triggers: []` is NOT an option: build_capability_graph flags a trigger-less
    skill as drift ("agent can't route to it"), which fails harness_eval's
    capability-graph check. A tool whose own output turns the substrate red is
    worse than no tool — caught by self-review 2026-07-29, after this shipped
    emitting an empty list.

    Equally, broad triggers steal routes: the resolver scores 2.0 per overlapping
    WORD, so a generic term outbids the skill that should own it (review-harvest
    stole "review the code before shipping" from code-review the same day). So:
    derive from the TITLE's distinctive tokens only, longest-first, and cap at 3.
    The TODO block still tells the author to refine them.
    """
    title = _slug_source(text)
    words = [w for w in re.findall(r"[a-z]{4,}", title.lower()) if w not in STOPWORDS]
    if not words:
        return [slugify(text).replace("-", " ")]

    # The multi-word phrase ONLY, plus at most one genuinely distinctive single
    # word (>= SINGLE_WORD_MIN chars). An earlier version emitted any long-ish
    # word, which produced triggers like "notify" — and "notify cc on telegram"
    # promptly resolved to the stub over the real Telegram skills. The golden
    # routing set did not catch it, because that phrase is not in the golden set:
    # a regression suite is necessary, not sufficient. Short words are generic by
    # nature; a 9+ character word is usually domain vocabulary.
    out = [" ".join(words[:4])]
    for w in sorted(set(words), key=len, reverse=True):
        if len(w) >= SINGLE_WORD_MIN:
            out.append(w)
            break

    seen, uniq = set(), []
    for t in out:
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq[:2]


def promote(text: str, kind: str, apply: bool) -> dict:
    slug = slugify(text)
    today = date.today().isoformat()
    title = text[:70].rstrip(" .") if text else slug

    if kind == "skill":
        target = SKILLS_DIR / slug / "SKILL.md"
        body = SKILL_STUB.format(
            slug=slug, today=today, title=title, text=text,
            triggers=", ".join(f'"{t}"' for t in scaffold_triggers(text)),
            desc=(f"{text[:180]} Promoted from a validated memory pattern on {today}; "
                  f"see the TODO block before relying on it."))
    else:
        target = SOP_DIR / f"{slug.replace('-', '_').upper()}.md"
        body = (f"---\ntags: [docs, sop, promoted, evolve]\nlast_updated: {today}\n"
                f"freshness_threshold_days: 180\n---\n\n# {title}\n\n"
                f"> **PROMOTED FROM MEMORY {today}** by `scripts/core/evolve.py`.\n\n"
                f"{text}\n\n## TODO\n\n- [ ] Expand into a runnable procedure with verified commands\n"
                f"- [ ] Link from the relevant skill and from [[brain/EXECUTION_RULES]]\n")

    # Repo-relative when possible, absolute otherwise. A bare relative_to()
    # raises ValueError for any path outside PROJECT_ROOT, which turns a display
    # concern into a crash — the same latent trap found in
    # obsidian_graph_doctor._has_materialized_private_note on 2026-07-29.
    try:
        shown = str(target.relative_to(PROJECT_ROOT))
    except ValueError:
        shown = str(target)

    result = {"slug": slug, "kind": kind, "target": shown, "applied": False}
    if target.exists():
        result["skipped"] = "already exists"
        return result
    if apply:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        result["applied"] = True
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Promote validated memory into capability")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="validated patterns with no owning skill/SOP")
    s.add_argument("--json", action="store_true")
    s.add_argument("--limit", type=int, default=15)

    p = sub.add_parser("promote", help="scaffold a skill or SOP from a pattern")
    p.add_argument("text")
    p.add_argument("--kind", choices=["skill", "sop"], default="skill")
    p.add_argument("--apply", action="store_true", help="write the file (default: dry run)")
    p.add_argument("--json", action="store_true")

    a = ap.parse_args()

    if a.cmd == "scan":
        r = scan()
        if a.json:
            print(json.dumps(r, indent=2))
            return
        print(f"validated patterns : {r['validated_total']}")
        print(f"owners scanned     : {r['owners_scanned']} (skills + SOPs)")
        print(f"already covered    : {r['covered']}")
        print(f"promotion candidates: {len(r['candidates'])}\n")
        for c in r["candidates"][: a.limit]:
            near = f"nearest {c['owner']} @ {c['score']}" if c["owner"] else "no near owner"
            print(f"  [{c['marker']}] {c['title'][:88]}")
            print(f"      PATTERNS.md:{c['line']}  ({near})")
        if len(r["candidates"]) > a.limit:
            print(f"\n  … {len(r['candidates']) - a.limit} more (--limit to see)")
        print("\npromote with: python scripts/core/evolve.py promote \"<text>\" --kind skill --apply")
        return

    r = promote(a.text, a.kind, a.apply)
    print(json.dumps(r, indent=2) if a.json else
          f"{'WROTE' if r['applied'] else 'DRY RUN'}: {r['target']}"
          + (f"  ({r['skipped']})" if r.get("skipped") else ""))


if __name__ == "__main__":
    main()
