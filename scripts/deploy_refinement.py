"""deploy_refinement.py — push Bravo's refinement executor to the sibling agents.

WHY THIS EXISTS. `scripts/core/refine.py` runs in three repos, and every doc says "fix
bugs in Bravo and redeploy; never fork the sibling copy." Until now that instruction had
no command behind it — the deploy was a hand ritual (copy the file, sed the owner, patch
the docstring) performed once per sibling from memory. A manual ritual is a drift
generator: `scripts/tests/test_fleet_parity.py` would eventually go red and the only way
back would be to reconstruct the ritual correctly under pressure.

This is that ritual, executed the same way every time.

WHAT IT DOES NOT DO. It does not touch a sibling's SKILL.md, CONTEXT.md or brain/STATE.md.
Those are per-agent by design: each documents the evidence commands that actually exist in
that repo (Bravo's `harness_eval.py` and `task_outcomes.py` are absent in both siblings,
and Atlas also lacks `build_capability_graph.py`). Copying those files would be the exact
dead-surface bug this fleet keeps rediscovering. Only the executor and its tests are
shared code.

Dry run by default. Nothing is written without --apply.

    python scripts/deploy_refinement.py            # show what would change
    python scripts/deploy_refinement.py --apply
    python scripts/deploy_refinement.py --apply --only maven
"""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

CAPABILITY_META = {
    "category": "governance.self_improvement",
    "lifecycle": "manual",
    "risk": "local_write",
    "triggers": [
        "redeploy refine.py to the sibling agents",
        "sync the refinement executor across the fleet",
        "fix fleet parity drift",
    ],
    "owner": "bravo",
    "project": "empire",
    "bridge": {
        # Writes into OTHER repos. Never reachable from the chat bridge.
        "visible": False,
        "confirm": True,
    },
}

BRAVO = Path(__file__).resolve().parents[1]

# agent -> repo root. Relative to Bravo's parent so a moved checkout still resolves.
SIBLINGS = {
    "maven": BRAVO.parent / "CMO-Agent",
    "atlas": BRAVO.parent / "APPS" / "CFO-Agent",
}

# Files copied verbatim (modulo the per-agent rewrites below).
SHARED = (
    Path("scripts") / "core" / "refine.py",
    Path("scripts") / "tests" / "test_refine.py",
)

def _localise(text: str, agent: str) -> str:
    """Apply the only two per-agent differences the parity test permits.

    Works line-by-line with keepends, so it is indifferent to whether Bravo's copy is
    CRLF or LF and preserves whichever it is. An earlier version matched `\\n`
    explicitly and died on Bravo's CRLF file — caught by the fail-loud guard below,
    which is exactly why that guard raises instead of silently returning the input.
    """
    lines = text.splitlines(keepends=True)
    owner_done = doc_done = False

    for i, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        eol = line[len(stripped):]

        if not owner_done and stripped == '    "owner": "bravo",':
            lines[i] = f'    "owner": "{agent}",{eol}'
            owner_done = True
            continue

        if not doc_done and stripped.startswith("FLEET-PORTABLE. This file is deployed verbatim"):
            lines[i] = (
                "FLEET-PORTABLE. Canonical copy lives in Bravo (`~/Business-Empire-Agent`) "
                f"and is{eol}"
            )
            # the sentence wraps onto the next line; replace it too
            if i + 1 < len(lines) and "CAPABILITY_META" in lines[i + 1]:
                nxt = lines[i + 1]
                eol2 = nxt[len(nxt.rstrip("\r\n")):]
                lines[i + 1] = (
                    'deployed here verbatim; only `CAPABILITY_META["owner"]` differs '
                    f"(here: {agent}).{eol2}"
                )
            doc_done = True

    if not owner_done:
        raise SystemExit(
            'FATAL: could not find the line `    "owner": "bravo",` in the source — '
            "CAPABILITY_META shape changed. Fix this script before deploying, or the "
            "sibling silently keeps owner=bravo and mislabels its refinements."
        )
    if not doc_done:
        print(
            "  warning: FLEET-PORTABLE docstring paragraph not found — deploying anyway, "
            "but the sibling's docstring will name the wrong agent.",
            file=sys.stderr,
        )
    return "".join(lines)


def _read(p: Path) -> str:
    with open(p, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def deploy(agent: str, repo: Path, apply: bool) -> dict:
    result = {"agent": agent, "repo": str(repo), "files": [], "skipped": None}
    if not repo.exists():
        result["skipped"] = "repo not present on this machine"
        return result

    for rel in SHARED:
        src = BRAVO / rel
        if not src.exists():
            result["files"].append({"path": str(rel), "state": f"MISSING IN BRAVO: {src}"})
            continue
        want = _read(src)
        if rel.name == "refine.py":
            want = _localise(want, agent)

        dst = repo / rel
        have = _read(dst) if dst.exists() else None
        if have == want:
            result["files"].append({"path": str(rel), "state": "identical"})
            continue

        n = 0
        if have is not None:
            n = sum(
                1
                for l in difflib.unified_diff(have.split("\n"), want.split("\n"), lineterm="", n=0)
                if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))
            )
        state = "would create" if have is None else f"would update ({n} lines differ)"
        if apply:
            _write(dst, want)
            state = "created" if have is None else f"updated ({n} lines)"
        result["files"].append({"path": str(rel), "state": state})
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Deploy refine.py to the sibling agents")
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--only", choices=sorted(SIBLINGS), help="one agent instead of all")
    args = ap.parse_args(argv)

    targets = {args.only: SIBLINGS[args.only]} if args.only else SIBLINGS
    changed = False
    for agent, repo in sorted(targets.items()):
        r = deploy(agent, repo, args.apply)
        print(f"{agent}  ({r['repo']})")
        if r["skipped"]:
            print(f"    skipped — {r['skipped']}")
            continue
        for f in r["files"]:
            print(f"    {f['state']:<32} {f['path']}")
            if f["state"] != "identical":
                changed = True

    if not args.apply and changed:
        print("\nDry run. Re-run with --apply to write.")
    if args.apply and changed:
        print(
            "\nDeployed. Now verify from Bravo:\n"
            "    python -m pytest scripts/tests/test_fleet_parity.py -q\n"
            "and re-run each sibling's own suite:\n"
            "    python -m pytest scripts/tests/test_refine.py -q"
        )
    if not changed:
        print("\nAll siblings already match Bravo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
