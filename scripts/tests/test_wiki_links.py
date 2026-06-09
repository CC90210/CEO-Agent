"""Wiki-link integrity test (audit Phase 7).

A fresh clone of this repo should load with ZERO dangling `[[wiki-links]]` in its
brain. Every `[[target]]` in a tracked .md file (outside code blocks) must resolve
to one of:
  (a) a tracked file (by path, by basename, or by stem — Obsidian-style),
  (b) a tracked `<name>.template.md` (the public stub for a gitignored local file
      like memory/PATTERNS.md),
  (c) a cross-repo link — target starts with `../` OR the line carries the
      `(sibling repo)` marker, or
  (d) a documented local-only operator store (`memory/`, `APPS_CONTEXT/`,
      `runtime/`, `data/`) — these dirs hold gitignored per-operator content by
      design (see memory/INDEX.md, APPS_CONTEXT/README.md).

Links inside fenced code blocks or inline `code` spans are skipped — they're
syntax examples (e.g. the skill-authoring docs literally show `[[wiki-link]]`),
not live links.

Run:
  python -m pytest scripts/tests/test_wiki_links.py -q
  python scripts/tests/test_wiki_links.py          # prints the unresolved list
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LINK_RE = re.compile(r"(?<!!)\[\[([^\]]+)\]\]")


def _tracked() -> list[str]:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files"],
                             capture_output=True, text=True, encoding="utf-8", errors="ignore").stdout
        return [ln.strip() for ln in out.splitlines() if ln.strip()]
    except Exception:  # noqa: BLE001
        return []


def find_broken() -> list[tuple[str, int, str]]:
    tracked = _tracked()
    paths = {p.lower() for p in tracked}
    basenames = {Path(p).name.lower() for p in tracked}
    md_stems = {Path(p).stem.lower() for p in tracked if p.endswith(".md")}
    template_keys = {
        Path(p).name[: -len(".template.md")].lower()
        for p in tracked if p.endswith(".template.md")
    }
    LOCAL_ONLY_PREFIXES = ("memory/", "apps_context/", "runtime/", "data/")
    broken: list[tuple[str, int, str]] = []
    for rel in tracked:
        if not rel.endswith(".md"):
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        in_fence = False
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            line_low = line.lower()
            for m in LINK_RE.finditer(line):
                # inline `code` span → syntax example, skip
                if line[: m.start()].count("`") % 2 == 1:
                    continue
                target = m.group(1).split("|")[0].split("#")[0].strip()
                if not target:
                    continue
                low = target.lower()
                if target.startswith("../") or "(sibling repo)" in line_low:
                    continue  # (c) cross-repo
                if any(low.startswith(p) for p in LOCAL_ONLY_PREFIXES):
                    continue  # (d) documented local-only operator store
                cand = low if low.endswith(".md") else low + ".md"
                if cand in paths:
                    continue  # (a) by path
                base = Path(low).name
                base_md = base if base.endswith(".md") else base + ".md"
                if base_md in basenames:
                    continue  # (a) by basename
                stem = Path(low).stem
                if stem in md_stems:
                    continue  # (a) by stem
                if stem in template_keys:
                    continue  # (b) template stub
                # (a, extended) Obsidian links to code files / dirs:
                if low in paths:
                    continue  # exact tracked path (.py / .json / .gitignore / ...)
                if (low + ".py") in paths:
                    continue  # [[scripts/scan_secrets]] -> scripts/scan_secrets.py
                if (base + ".py") in basenames:
                    continue  # basename match: [[scripts/agent_inbox]] -> scripts/core/agent_inbox.py
                if any(p.startswith(low + "/") for p in paths):
                    continue  # directory link with tracked content (skills/<name>/, browser/<dir>/)
                broken.append((rel, i, target))
    return broken


class TestWikiLinks(unittest.TestCase):
    def test_no_dangling_wiki_links(self):
        broken = find_broken()
        if broken:
            msg = "\n".join(f"  {f}:{ln}  [[{t}]]" for f, ln, t in broken[:60])
            self.fail(f"{len(broken)} unresolved wiki-link(s):\n{msg}")


if __name__ == "__main__":
    broken = find_broken()
    print(f"{len(broken)} unresolved wiki-links")
    from collections import Counter
    by_target = Counter(t for _, _, t in broken)
    for t, c in by_target.most_common(40):
        print(f"  x{c:<3} [[{t}]]")
    sys.exit(1 if broken else 0)
