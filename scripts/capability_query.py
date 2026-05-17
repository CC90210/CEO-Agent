"""
Capability Query — runtime tool-tree resolver for agents.

Reads brain/CAPABILITY_GRAPH.json and answers "what can this agent do?"
questions. This is the layer agents call at decision time:

  - "What skill should I use for outreach?" -> resolve(intent="outreach")
  - "Which scripts does autonomous-loop depend on?" -> deps("skill:autonomous-loop")
  - "Show me everything tagged finance." -> by_tag("finance")
  - "Is there a workflow for /ship?" -> find_workflow("ship")

The graph is rebuilt by `scripts/build_capability_graph.py`. This script is
read-only — never mutates state. Callable from Python (import) or CLI.

USAGE
-----
    python scripts/capability_query.py resolve "scrape leads"
    python scripts/capability_query.py deps skill:autonomous-loop
    python scripts/capability_query.py by-tag finance --json
    python scripts/capability_query.py by-owner bravo --json
    python scripts/capability_query.py drift --json
    python scripts/capability_query.py stats --json
    python scripts/capability_query.py check-deps skill:outreach-send  # V6.8.1 / ADR-0001
    python scripts/capability_query.py find-workflow ship
    python scripts/capability_query.py get skill:hyperthink

PYTHON API
----------
    from capability_query import Graph
    g = Graph.load()
    skill = g.resolve_intent("send a follow-up email to a warm lead")
    deps  = g.dependencies(skill["id"])
    sibs  = g.by_tag("outreach")
    health = g.check_deps(skill["id"])  # V6.8.1: enforces ADR-0001 requires:
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GRAPH_PATH = PROJECT_ROOT / "brain" / "CAPABILITY_GRAPH.json"
DAEMON_FRESHNESS_SEC = 120  # PID file must have been touched within 2 minutes


class Graph:
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.nodes: list[dict[str, Any]] = data.get("nodes", [])
        self.edges: list[dict[str, str]] = data.get("edges", [])
        self._by_id = {n["id"]: n for n in self.nodes}

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Graph":
        p = path or GRAPH_PATH
        if not p.exists():
            raise FileNotFoundError(
                f"{p} missing — run `python scripts/build_capability_graph.py` first."
            )
        return cls(json.loads(p.read_text(encoding="utf-8")))

    # ── Resolvers ────────────────────────────────────────────────────────
    def get(self, node_id: str) -> Optional[dict[str, Any]]:
        return self._by_id.get(node_id)

    def by_kind(self, kind: str) -> list[dict[str, Any]]:
        return [n for n in self.nodes if n.get("kind") == kind]

    def by_tag(self, tag: str) -> list[dict[str, Any]]:
        t = tag.lower()
        return [n for n in self.nodes
                if any(t == str(x).lower() for x in (n.get("tags") or []))]

    def by_owner(self, owner: str) -> list[dict[str, Any]]:
        o = owner.lower()
        return [n for n in self.nodes if str(n.get("owner", "")).lower() == o]

    def resolve_intent(self, intent: str, kind: str = "skill", limit: int = 5,
                       include_disabled: bool = False, include_archived: bool = False) -> list[dict[str, Any]]:
        """Score every node by trigger overlap + description token match.

        Skips skills with `disable-model-invocation: true` (auto-generated CLI references
        that pollute trigger resolution) and `archived: <date>` (superseded skills not yet
        physically removed) unless explicitly opted in via include_disabled / include_archived.
        """
        words = set(re.findall(r"\w+", intent.lower()))
        if not words:
            return []
        scored: list[tuple[float, dict[str, Any]]] = []
        for n in self.nodes:
            if kind and n.get("kind") != kind:
                continue
            if not include_disabled and n.get("disable_model_invocation"):
                continue
            if not include_archived and n.get("archived"):
                continue
            score = 0.0
            triggers = n.get("triggers") or []
            if isinstance(triggers, list):
                for t in triggers:
                    t_words = set(re.findall(r"\w+", str(t).lower()))
                    overlap = len(words & t_words)
                    if overlap:
                        score += overlap * 2.0  # triggers weighted higher
            desc_words = set(re.findall(r"\w+", str(n.get("description", "")).lower()))
            score += len(words & desc_words) * 0.5
            name_words = set(re.findall(r"\w+", str(n.get("name", "")).lower()))
            score += len(words & name_words) * 1.0
            if score > 0:
                scored.append((score, n))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"score": round(s, 2), **n} for s, n in scored[:limit]]

    def dependencies(self, node_id: str) -> dict[str, list[dict[str, Any]]]:
        """What does this node use / require / call?"""
        out_uses = [self._by_id[e["to"]] for e in self.edges
                    if e["from"] == node_id and e.get("kind") == "uses"
                    and e["to"] in self._by_id]
        out_req = [self._by_id[e["to"]] for e in self.edges
                   if e["from"] == node_id and e.get("kind") == "requires"
                   and e["to"] in self._by_id]
        return {"uses": out_uses, "requires": out_req}

    def dependents(self, node_id: str) -> list[dict[str, Any]]:
        """Who uses or requires this node?"""
        return [self._by_id[e["from"]] for e in self.edges
                if e["to"] == node_id and e["from"] in self._by_id]

    def find_workflow(self, name: str) -> Optional[dict[str, Any]]:
        """Find a workflow by partial name match."""
        n = name.lower().lstrip("/")
        for w in self.by_kind("workflow"):
            if n in str(w.get("name", "")).lower():
                return w
        return None

    def check_deps(self, node_id: str) -> dict[str, Any]:
        """Check declared `requires:` for a skill against the live environment.

        Per ADR-0001: a skill that declares `requires: [env:KEY, daemon:NAME,
        state:PATH]` MUST have those resources available, or the skill is in
        hard-dependency violation. Soft-dependency skills do not declare a
        `requires:` field; this check is a no-op for them (returns "ok").

        Returns a structured report:
            {
              "node": "skill:foo",
              "requires": {"env": [...], "daemons": [...], "state": [...]},
              "missing": {"env": [...], "daemons": [...], "state": [...]},
              "ok": bool,
              "pointer": "<one-line setup hint>" | None
            }
        """
        node = self.get(node_id)
        if not node:
            return {"node": node_id, "ok": False, "error": "node not found"}
        req = node.get("requires") or {}
        if not isinstance(req, dict):
            req = {}
        missing: dict[str, list[str]] = {"env": [], "daemons": [], "state": []}

        for var in req.get("env") or []:
            if not os.environ.get(var):
                missing["env"].append(var)

        state_dir = PROJECT_ROOT / "state"
        now = time.time()
        for daemon in req.get("daemons") or []:
            pid_file = state_dir / f"{daemon}.pid"
            ok = False
            if pid_file.exists():
                try:
                    mtime = pid_file.stat().st_mtime
                    if (now - mtime) < DAEMON_FRESHNESS_SEC:
                        ok = True
                except OSError:
                    pass
            if not ok:
                missing["daemons"].append(daemon)

        for path in req.get("state") or []:
            full = path if Path(path).is_absolute() else PROJECT_ROOT / path
            if not Path(full).exists():
                missing["state"].append(path)

        ok = not any(missing[k] for k in missing)
        pointer = None
        if not ok:
            hints = []
            if missing["env"]:
                hints.append(f"set env vars: {', '.join(missing['env'])}")
            if missing["daemons"]:
                hints.append(f"start daemons (pm2 start ...): {', '.join(missing['daemons'])}")
            if missing["state"]:
                hints.append(f"initialize state files: {', '.join(missing['state'])}")
            pointer = "; ".join(hints) if hints else None

        return {
            "node": node_id,
            "requires": req,
            "missing": missing,
            "ok": ok,
            "pointer": pointer,
        }


def _print(obj: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, indent=2, default=str))
    elif isinstance(obj, list):
        for n in obj:
            score = f"({n.get('score'):.1f})" if "score" in n else "       "
            print(f"  {score}  {n.get('kind','?'):8s}  {n.get('name','?'):35s}  {str(n.get('description', ''))[:80]}")
    elif isinstance(obj, dict):
        print(json.dumps(obj, indent=2, default=str))
    else:
        print(obj)


def main() -> int:
    p = argparse.ArgumentParser(description="Query the capability graph.")
    p.add_argument("--json", dest="output_json", action="store_true")
    sub = p.add_subparsers(dest="command")

    pr = sub.add_parser("resolve", help="Resolve intent to top-N skills/tools")
    pr.add_argument("intent", help="Natural-language intent, e.g. 'draft outreach email'")
    pr.add_argument("--kind", default="skill", choices=["skill", "script", "agent", "workflow", "any"])
    pr.add_argument("--limit", type=int, default=5)
    pr.add_argument("--include-disabled", action="store_true",
                    help="Include skills with disable-model-invocation: true (auto-generated CLI refs).")
    pr.add_argument("--include-archived", action="store_true",
                    help="Include skills with archived: <date> in frontmatter.")

    pd = sub.add_parser("deps", help="Dependencies of a node (skill:foo)")
    pd.add_argument("node_id")

    pdep = sub.add_parser("dependents", help="What depends on this node?")
    pdep.add_argument("node_id")

    pt = sub.add_parser("by-tag", help="All nodes with the given tag")
    pt.add_argument("tag")

    po = sub.add_parser("by-owner", help="All nodes owned by an agent")
    po.add_argument("owner")

    sub.add_parser("drift", help="Show capabilities flagged as malformed")
    sub.add_parser("stats", help="Totals across kinds")

    pw = sub.add_parser("find-workflow", help="Find a workflow by name")
    pw.add_argument("name")

    pgn = sub.add_parser("get", help="Fetch one node by ID")
    pgn.add_argument("node_id")

    pcd = sub.add_parser("check-deps", help="Check declared `requires:` against current environment (per ADR-0001)")
    pcd.add_argument("node_id", help="e.g. skill:outreach-send")

    args = p.parse_args()
    try:
        g = Graph.load()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    out_json = getattr(args, "output_json", False)

    if args.command == "resolve":
        kind = None if args.kind == "any" else args.kind
        results = g.resolve_intent(
            args.intent, kind=kind or "skill", limit=args.limit,
            include_disabled=getattr(args, "include_disabled", False),
            include_archived=getattr(args, "include_archived", False),
        )
        _print(results, out_json)
    elif args.command == "deps":
        _print(g.dependencies(args.node_id), True)
    elif args.command == "dependents":
        _print(g.dependents(args.node_id), out_json)
    elif args.command == "by-tag":
        _print(g.by_tag(args.tag), out_json)
    elif args.command == "by-owner":
        _print(g.by_owner(args.owner), out_json)
    elif args.command == "drift":
        _print(g.data.get("drift", []), True)
    elif args.command == "stats":
        _print(g.data.get("totals", {}), True)
    elif args.command == "find-workflow":
        result = g.find_workflow(args.name)
        _print(result or {"error": f"no workflow matching '{args.name}'"}, True)
    elif args.command == "get":
        _print(g.get(args.node_id) or {"error": f"no node {args.node_id}"}, True)
    elif args.command == "check-deps":
        report = g.check_deps(args.node_id)
        _print(report, True)
        return 0 if report.get("ok") else 1
    else:
        p.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
