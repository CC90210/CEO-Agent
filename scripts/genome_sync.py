"""genome_sync.py — stamp the germline seed (PERSONAL.md) into every runtime entry point.

The genome mechanism (2026-07-09): PERSONAL.md is the seed of record. Each
`<!-- LOCKSTEP:name --> ... <!-- /LOCKSTEP:name -->` block it defines is stamped
byte-identical into all six runtime entry points (CLAUDE/GEMINI/ANTIGRAVITY/
AGENTS/OPENCODE/ZCODE.md) and the `.gemini/rules/` mirrors are refreshed as
byte-copies of the roots. One edit in the seed → every chassis boots the same
agent. `scripts/tests/test_entrypoint_parity.py` enforces block byte-identity;
`scripts/agent_genome.py` verifies seed↔expression match as gene G2.

CLI:
  python scripts/genome_sync.py            # stamp blocks + refresh mirrors
  python scripts/genome_sync.py --check    # verify only, exit 1 on drift (CI-able)

Rules:
  - Blocks are REPLACED between existing markers only. A missing marker pair in
    an entry point is an error (insertion is a deliberate one-time act, not an
    implicit side effect) — add the empty marker pair where you want the block,
    then run the sync.
  - Content OUTSIDE the markers is per-runtime (chassis narration) and is never
    touched.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "PERSONAL.md"

# Self-configuring (portable across agent repos): genome.json at the repo root
# may override entry_points (Atlas/Maven ship 5 — no ZCODE.md) and mirror_dir
# ("" = no mirrors). Defaults are Bravo's layout. Keep this file byte-identical
# across siblings — per-repo differences live in genome.json, never in code.
_DEFAULT_ENTRY_POINTS = ["CLAUDE.md", "GEMINI.md", "ANTIGRAVITY.md", "AGENTS.md", "OPENCODE.md", "ZCODE.md"]
_cfg: dict = {}
if (ROOT / "genome.json").exists():
    try:
        _cfg = json.loads((ROOT / "genome.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"WARN: genome.json unparseable ({e}) — using defaults", file=sys.stderr)
ENTRY_POINTS = _cfg.get("entry_points", _DEFAULT_ENTRY_POINTS)
_mirror = _cfg.get("mirror_dir", ".gemini/rules")
MIRROR_DIR = (ROOT / _mirror) if _mirror else (ROOT / "__no_mirror__")

LOCKSTEP_RE = re.compile(
    r"<!--\s*LOCKSTEP:([A-Za-z0-9_-]+)\s*-->(.*?)<!--\s*/LOCKSTEP:\1\s*-->",
    re.DOTALL,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


OPENER_RE = re.compile(r"<!--\s*LOCKSTEP:([A-Za-z0-9_-]+)\s*-->")
CLOSER_RE = re.compile(r"<!--\s*/LOCKSTEP:([A-Za-z0-9_-]+)\s*-->")


def _blocks(text: str, where: str = "?") -> dict[str, str]:
    """Extract LOCKSTEP blocks, REJECTING malformed multiplicity.

    Duplicate or nested same-name markers would let one copy match the seed
    while a stale copy keeps shipping in the prompt (Codex 2026-07-09) —
    exactly one opener + one closer per block name per file, or we abort."""
    from collections import Counter
    openers = Counter(m.group(1) for m in OPENER_RE.finditer(text))
    closers = Counter(m.group(1) for m in CLOSER_RE.finditer(text))
    bad = {n for n in (set(openers) | set(closers))
           if openers.get(n, 0) != 1 or closers.get(n, 0) != 1}
    if bad:
        raise SystemExit(
            f"ERROR {where}: malformed LOCKSTEP markers (duplicate/nested/unclosed): "
            f"{sorted(bad)} — fix the markers by hand before syncing.")
    return {m.group(1): m.group(2) for m in LOCKSTEP_RE.finditer(text)}


def _stamp(text: str, name: str, content: str) -> str:
    pattern = re.compile(
        rf"(<!--\s*LOCKSTEP:{re.escape(name)}\s*-->).*?(<!--\s*/LOCKSTEP:{re.escape(name)}\s*-->)",
        re.DOTALL,
    )
    return pattern.sub(lambda m: m.group(1) + content + m.group(2), text, count=1)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Stamp PERSONAL.md LOCKSTEP blocks into all entry points")
    p.add_argument("--check", action="store_true", help="verify only; exit 1 on drift")
    args = p.parse_args(argv)

    if not SEED.exists():
        print("ERROR: PERSONAL.md seed missing", file=sys.stderr)
        return 1
    seed_blocks = _blocks(SEED.read_text(encoding="utf-8"), where="PERSONAL.md")
    if not seed_blocks:
        print("ERROR: seed defines no LOCKSTEP blocks", file=sys.stderr)
        return 1

    drift = 0
    stamped = 0
    for name in ENTRY_POINTS:
        f = ROOT / name
        if not f.exists():
            print(f"ERROR: entry point missing: {name}", file=sys.stderr)
            drift += 1
            continue
        text = f.read_text(encoding="utf-8")
        have = _blocks(text, where=name)
        for block, content in seed_blocks.items():
            if block not in have:
                print(f"DRIFT {name}: marker pair LOCKSTEP:{block} missing "
                      f"(add the empty pair where the block belongs, then re-run)")
                drift += 1
                continue
            if have[block] != content:
                if args.check:
                    print(f"DRIFT {name}: LOCKSTEP:{block} differs from seed")
                    drift += 1
                else:
                    text = _stamp(text, block, content)
                    stamped += 1
        if not args.check and text != f.read_text(encoding="utf-8"):
            f.write_text(text, encoding="utf-8")
            print(f"stamped: {name}")

    # Mirrors: byte-copies of the roots (Gemini CLI rules dir).
    if MIRROR_DIR.is_dir():
        for name in ENTRY_POINTS:
            src, dst = ROOT / name, MIRROR_DIR / name
            if not src.exists():
                continue
            if not dst.exists() or dst.read_bytes() != src.read_bytes():
                if args.check:
                    print(f"DRIFT mirror: .gemini/rules/{name} differs from root")
                    drift += 1
                else:
                    dst.write_bytes(src.read_bytes())
                    print(f"mirrored: .gemini/rules/{name}")

    if args.check:
        print("genome-sync check: " + ("CLEAN" if drift == 0 else f"{drift} drift(s)"))
        return 0 if drift == 0 else 1
    print(f"genome-sync: {stamped} block(s) stamped across entry points; mirrors refreshed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
