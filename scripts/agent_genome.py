"""agent_genome.py — verify an agent repo fully expresses the genome.

The genome (2026-07-09): every agent in CC's fleet is an EXPRESSION of a
portable core — ten genes that turn a bare model into a fully-capable agent:

  G1 seed        one canonical identity+wiring file (PERSONAL.md)
  G2 expression  runtime entry points carry the seed's LOCKSTEP blocks, byte-identical
  G3 identity    deep identity + operator profile (SOUL.md + USER.md)
  G4 capability  intent -> skill/tool resolution (capability graph + resolver)
  G5 memory      lesson-capture tiers (MISTAKES / PATTERNS / DECISIONS)
  G6 retrieval   lessons found before work repeats (FTS retriever)
  G7 learning    a consolidation loop that runs without being asked
  G8 model       subscription-CLI model access, API-key-free
  G9 guards      secret/exec/state protection in enforce mode
  G10 eval       a verifiable self-check (harness_eval or equivalent)

This tool checks STRUCTURE (is the gene present and wired); harness_eval.py
checks LIVE HEALTH (is the phenotype currently green). Together they are the
genome's fitness function.

Repo-agnostic: defaults describe Bravo's layout; a sibling drops a `genome.json`
at its repo root to override per-gene paths (e.g. Atlas: {"model_access":
["cfo/claude_auth.py"]}). Run against a sibling READ-ONLY with --repo.

CLI:
  python scripts/agent_genome.py                 # verify this repo
  python scripts/agent_genome.py --json          # machine-readable
  python scripts/agent_genome.py --repo <path>   # verify a sibling (read-only)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

LOCKSTEP_RE = re.compile(
    r"<!--\s*LOCKSTEP:([A-Za-z0-9_-]+)\s*-->(.*?)<!--\s*/LOCKSTEP:\1\s*-->",
    re.DOTALL,
)

# Bravo-shaped defaults. Every value is a list of candidate paths — the gene is
# expressed if ANY candidate exists. genome.json at the target repo root
# overrides per key.
DEFAULTS: dict[str, list[str]] = {
    "seed": ["PERSONAL.md"],
    "entry_points": ["CLAUDE.md", "GEMINI.md", "ANTIGRAVITY.md", "AGENTS.md", "OPENCODE.md", "ZCODE.md"],
    "identity": ["brain/SOUL.md"],
    "operator": ["brain/USER.md"],
    "capability_graph": ["brain/CAPABILITY_GRAPH.json"],
    "capability_resolver": ["scripts/capability_query.py"],
    "memory_tiers": ["memory/MISTAKES.md", "memory/PATTERNS.md", "memory/DECISIONS.md"],  # ALL required
    "retrieval": ["scripts/core/memory_retriever.py"],
    "learning_loop": ["scripts/bravo_sleep.py", "scripts/agent_sleep.py", "scripts/core/agent_self_improvement.py"],
    "model_access": ["scripts/lib/claude_cli.py", "cfo/claude_auth.py", "scripts/lib/claude_auth.py"],
    "guards": [".claude/settings.json", ".claude/settings.local.json", ".claude/settings.hooks.template.json"],
    "eval": ["scripts/harness_eval.py", "scripts/agent_genome.py"],
    "learning_loop_extra": [],  # reserved
}


def _load_manifest(repo: Path) -> dict[str, list[str]]:
    cfg = dict(DEFAULTS)
    gj = repo / "genome.json"
    if gj.exists():
        try:
            override = json.loads(gj.read_text(encoding="utf-8"))
            for k, v in override.items():
                if isinstance(v, (list, str)):
                    cfg[k] = v  # lists = candidate paths; strings (e.g. mirror_dir, name) pass through
        except json.JSONDecodeError as e:
            print(f"WARN: genome.json unparseable ({e}) — using defaults", file=sys.stderr)
    return cfg


def _read(repo: Path, rel: str) -> str:
    try:
        return (repo / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _any(repo: Path, candidates: list[str]) -> str | None:
    for c in candidates:
        if (repo / c).exists():
            return c
    return None


def verify(repo: Path) -> list[dict]:
    cfg = _load_manifest(repo)
    genes: list[dict] = []

    def gene(gid: str, name: str, ok: bool, detail: str):
        genes.append({"gene": gid, "name": name, "ok": ok, "detail": detail})

    # G1 seed
    seed_rel = _any(repo, cfg["seed"])
    seed_blocks: dict[str, str] = {}
    if seed_rel:
        seed_blocks = {m.group(1): m.group(2) for m in LOCKSTEP_RE.finditer(_read(repo, seed_rel))}
    gene("G1", "seed (canonical identity+wiring file)",
         bool(seed_rel and seed_blocks),
         f"{seed_rel} with {len(seed_blocks)} LOCKSTEP block(s)" if seed_rel
         else f"missing (looked for {cfg['seed']})")

    # G2 expression — entry points exist, carry the seed's blocks byte-identical,
    # AND (when a mirror dir exists) every mirror is a byte-copy of its root.
    # Mirrors are runtime expressions too — Gemini boots from .gemini/rules/,
    # so a drifted mirror is exactly the failure this gene exists to catch.
    eps = [e for e in cfg["entry_points"] if (repo / e).exists()]
    missing_eps = [e for e in cfg["entry_points"] if e not in eps]
    if not seed_blocks:
        gene("G2", "expression (entry points carry the seed)", False,
             "cannot check — no seed blocks (fix G1 first)")
    else:
        drift: list[str] = []
        for e in eps:
            have = {m.group(1): m.group(2) for m in LOCKSTEP_RE.finditer(_read(repo, e))}
            for b, content in seed_blocks.items():
                if have.get(b) != content:
                    drift.append(f"{e}:{b}")
        _mirror_rel = cfg.get("mirror_dir", [".gemini/rules"])
        _mirror_rel = _mirror_rel[0] if isinstance(_mirror_rel, list) else _mirror_rel
        mirror_dir = (repo / _mirror_rel) if _mirror_rel else (repo / "__no_mirror__")
        mirror_issues: list[str] = []
        if mirror_dir.is_dir():
            for e in eps:
                m = mirror_dir / e
                if not m.exists():
                    mirror_issues.append(f"mirror missing: {e}")
                elif m.read_bytes() != (repo / e).read_bytes():
                    mirror_issues.append(f"mirror drift: {e}")
        ok = not missing_eps and not drift and not mirror_issues
        gene("G2", "expression (entry points carry the seed)", ok,
             f"{len(eps)}/{len(cfg['entry_points'])} entry points, blocks identical"
             + (f", {len(eps)} mirrors byte-identical" if mirror_dir.is_dir() else "")
             if ok else
             f"missing {missing_eps}; drift {drift[:3]}; mirrors {mirror_issues[:3]}")

    # G3 identity spine
    ident, oper = _any(repo, cfg["identity"]), _any(repo, cfg["operator"])
    gene("G3", "identity spine (SOUL + USER)", bool(ident and oper),
         f"{ident} + {oper}" if ident and oper else f"identity={ident}, operator={oper}")

    # G4 capability engine
    graph_rel = _any(repo, cfg["capability_graph"])
    resolver = _any(repo, cfg["capability_resolver"])
    n_skills = 0
    if graph_rel:
        try:
            g = json.loads(_read(repo, graph_rel))
            n_skills = g.get("totals", {}).get("skills") or sum(
                1 for n in g.get("nodes", []) if n.get("kind") == "skill")
        except json.JSONDecodeError:
            graph_rel = None
    gene("G4", "capability engine (graph + resolver)", bool(graph_rel and resolver and n_skills),
         f"{graph_rel} ({n_skills} skills) + {resolver}" if graph_rel and resolver
         else f"graph={graph_rel}, resolver={resolver}")

    # G5 memory tiers — ALL required
    missing_tiers = [t for t in cfg["memory_tiers"] if not (repo / t).exists()]
    gene("G5", "memory tiers (MISTAKES/PATTERNS/DECISIONS)", not missing_tiers,
         "all present" if not missing_tiers else f"missing: {missing_tiers}")

    # G6 retrieval
    ret = _any(repo, cfg["retrieval"])
    gene("G6", "retrieval engine", bool(ret), ret or f"missing (looked for {cfg['retrieval']})")

    # G7 learning loop
    loop = _any(repo, cfg["learning_loop"])
    gene("G7", "self-improvement loop", bool(loop), loop or f"missing (looked for {cfg['learning_loop']})")

    # G8 model access — present AND no metered-API call on a code line
    ma = _any(repo, cfg["model_access"])
    ma_ok, ma_detail = bool(ma), ma or f"missing (looked for {cfg['model_access']})"
    if ma:
        for line in _read(repo, ma).splitlines():
            s = line.strip()
            # Only a real endpoint literal counts — every actual caller builds
            # the quoted https URL. Prose/docstring mentions don't.
            if "https://api.anthropic.com" in s and not s.startswith(("#", "//", "*", ">")):
                ma_ok, ma_detail = False, f"{ma} calls the metered API on a code line"
                break
    gene("G8", "model access (subscription-CLI, API-key-free)", ma_ok, ma_detail)

    # G9 guards
    guard_file = None
    for c in cfg["guards"]:
        if "EMPIRE_HOOK" in _read(repo, c) or "secret_guard" in _read(repo, c):
            guard_file = c
            break
    gene("G9", "guards (secret/exec/state chain)", bool(guard_file),
         guard_file or f"no guard chain found in {cfg['guards']}")

    # G10 eval
    ev = _any(repo, cfg["eval"])
    gene("G10", "verifiable self-check (eval)", bool(ev), ev or f"missing (looked for {cfg['eval']})")

    return genes


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Verify an agent repo expresses the genome")
    p.add_argument("--repo", default=None, help="target repo (default: this one). READ-ONLY.")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    repo = Path(args.repo).resolve() if args.repo else Path(__file__).resolve().parent.parent
    if not repo.is_dir():
        print(f"ERROR: repo not found: {repo}", file=sys.stderr)
        return 2

    genes = verify(repo)
    passed = sum(1 for g in genes if g["ok"])
    if args.json:
        print(json.dumps({"repo": str(repo), "score": f"{passed}/{len(genes)}",
                          "fully_expressed": passed == len(genes), "genes": genes}, indent=2))
    else:
        print(f"AGENT GENOME — {repo.name}: {passed}/{len(genes)} genes expressed\n")
        for g in genes:
            print(f"  {'✅' if g['ok'] else '⭕'} {g['gene']:4} {g['name']}")
            print(f"        {g['detail']}")
        print()
        print("FULLY EXPRESSED — this repo wakes any model up as a complete agent."
              if passed == len(genes) else
              "Un-expressed genes above = the exact wiring this agent is missing.")
    return 0 if passed == len(genes) else 1


if __name__ == "__main__":
    sys.exit(main())
