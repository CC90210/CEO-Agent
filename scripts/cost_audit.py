"""Cron cost audit — for each active cron job, traces its handler chain
through scheduler.py and the scripts it invokes, reports whether any link
in the chain hits an Anthropic LLM.

Static analysis only — no actual cron runs, no LLM calls. Reads
`cron_engine.py list --json`, maps action_type → handler in scheduler.py,
greps the handler + downstream scripts for `from anthropic`, `draft_critic`,
or `inbound_classifier` references.

Usage:
    python scripts/cost_audit.py              # human report
    python scripts/cost_audit.py --json       # machine output
    python scripts/cost_audit.py --include-disabled
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SCHEDULER = SCRIPTS_DIR / "scheduler.py"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
# Reuse the canonical sibling-agent path map. Avoids duplicating the
# bravo/atlas/maven path triplet across multiple maintenance scripts.
try:
    from agent_self_improvement import AGENT_ROOTS as _AGENT_ROOTS
    CROSS_AGENT_ROOTS = {k: v for k, v in _AGENT_ROOTS.items() if k != "bravo"}
except ImportError:
    CROSS_AGENT_ROOTS = {
        "atlas": Path(r"C:\Users\User\APPS\CFO-Agent"),
        "maven": Path(r"C:\Users\User\CMO-Agent"),
    }

LLM_MARKERS = (
    "from anthropic",
    "anthropic.Anthropic",
    "import anthropic",
    "draft_critic",      # commercial-email gate, calls Haiku
    "inbound_classifier",  # email-reply classifier, calls Haiku
)


def list_active_crons(include_disabled: bool = False) -> list[dict]:
    r = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "cron_engine.py"), "--json", "list"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        return []
    jobs = json.loads(r.stdout)
    if include_disabled:
        return jobs
    return [j for j in jobs if j.get("is_active")]


def find_handler(action_type: str) -> tuple[str, str] | None:
    """Locate the dispatcher branch for an action_type and return
    (handler_function_name, body_text)."""
    if not SCHEDULER.exists():
        return None
    text = SCHEDULER.read_text(encoding="utf-8", errors="replace")
    m = re.search(
        rf'action_type\s*==\s*"{re.escape(action_type)}"\s*:\s*\n\s*return\s+(\w+)\(',
        text,
    )
    if not m:
        return None
    handler_name = m.group(1)
    body_match = re.search(
        rf"def\s+{re.escape(handler_name)}\s*\([^)]*\)[^:]*:\s*\n((?:[ \t].*\n|\n)+?)(?=\ndef\s|\nclass\s|\Z)",
        text,
    )
    body = body_match.group(1) if body_match else ""
    return handler_name, body


def referenced_scripts(handler_body: str) -> list[str]:
    """Pull script filenames the handler invokes via run_script(...)."""
    return list(set(re.findall(r'run_script\(\s*"([\w_]+\.py)"', handler_body)))


def script_uses_llm(script_path: Path) -> tuple[bool, list[str]]:
    """Check a script for direct LLM markers AND for subprocess/import calls
    to other scripts that use LLM. One-level transitive. Distinguishes
    transactional-only senders (which skip draft_critic) from commercial
    senders (which trigger Haiku per-send).

    Returns (uses_llm, evidence_strings)."""
    if not script_path.exists():
        return (False, ["script missing"])

    text = script_path.read_text(encoding="utf-8", errors="replace")
    direct = [m for m in LLM_MARKERS if m in text]
    if direct:
        return (True, direct)

    # send_gateway / draft_critic / inbound_classifier reach is conditional:
    # send_gateway runs the critic ONLY when intent='commercial'. If a script
    # imports send_gateway but only sends with intent='transactional', it's
    # zero-LLM in practice.
    transitive_hits: list[str] = []
    for marker in ("send_gateway", "draft_critic", "inbound_classifier"):
        if not re.search(rf"\b(?:from|import)\s+{marker}\b", text):
            continue
        target = script_path.parent / f"{marker}.py"
        if not target.exists():
            continue
        target_text = target.read_text(encoding="utf-8", errors="replace")
        if not any(m in target_text for m in LLM_MARKERS):
            continue

        if marker == "send_gateway":
            commercial_calls = bool(re.search(r'intent\s*=\s*["\']commercial["\']', text))
            transactional_calls = bool(re.search(r'intent\s*=\s*["\']transactional["\']', text))
            if transactional_calls and not commercial_calls:
                transitive_hits.append(f"imports {marker} (transactional only — skips critic)")
                continue
        transitive_hits.append(f"imports {marker} (uses LLM)")

    # Also one-level transitive via run_script() subprocess calls
    for called in set(re.findall(r"run_script\(\s*['\"]([\w_]+\.py)['\"]", text)):
        sibling = script_path.parent / called
        if sibling.exists():
            sibling_text = sibling.read_text(encoding="utf-8", errors="replace")
            if any(m in sibling_text for m in LLM_MARKERS):
                transitive_hits.append(f"calls {called} (uses LLM)")

    # If the only LLM reach is transactional-gated, treat as zero-LLM
    real_llm = [h for h in transitive_hits if "transactional only" not in h]
    return (bool(real_llm), transitive_hits)


def cross_agent_action(action_type: str) -> Path | None:
    """For action_types like atlas_*, maven_*, return the script path in the
    sibling agent repo. Action_type's tail maps directly to filename."""
    for slug, root in CROSS_AGENT_ROOTS.items():
        if action_type.startswith(f"{slug}_"):
            tail = action_type[len(slug) + 1:]
            candidate = root / "scripts" / f"{tail}.py"
            if candidate.exists():
                return candidate
    return None


def audit_cron(job: dict) -> dict:
    action_type = job.get("action_type") or ""
    handler_info = find_handler(action_type)
    chain: list[str] = []
    llm_uses = False
    notes: list[str] = []

    if handler_info:
        handler_name, body = handler_info
        chain.append(f"scheduler.{handler_name}()")
        for script_name in referenced_scripts(body):
            sp = SCRIPTS_DIR / script_name
            uses, hits = script_uses_llm(sp)
            chain.append(f"scripts/{script_name}")
            if uses:
                llm_uses = True
                notes.extend(f"{script_name}: {h}" for h in hits)
    else:
        notes.append(f"no handler found for action_type={action_type}")

    cross = cross_agent_action(action_type)
    if cross:
        chain.append(str(cross.relative_to(REPO_ROOT.parent)).replace("\\", "/"))
        uses, hits = script_uses_llm(cross)
        if uses:
            llm_uses = True
            notes.extend(f"{cross.name}: {h}" for h in hits)

    # Special: send_gateway only runs draft_critic when intent='commercial'
    if any("draft_critic" in n or "send_gateway" in n for n in notes):
        notes.append("(critic only fires for intent=commercial; transactional sends skip)")

    return {
        "name": job.get("name"),
        "schedule": job.get("schedule"),
        "action_type": action_type,
        "active": job.get("is_active", False),
        "uses_llm": llm_uses,
        "chain": chain,
        "notes": notes,
    }


def render_human(results: list[dict]) -> str:
    lines = ["Cron Cost Audit — LLM use per active job", "=" * 50, ""]
    llm_jobs = [r for r in results if r["uses_llm"]]
    free_jobs = [r for r in results if not r["uses_llm"]]

    lines.append(f"Total: {len(results)} active jobs")
    lines.append(f"  Zero-LLM (deterministic):  {len(free_jobs)}")
    lines.append(f"  Hits LLM API key:          {len(llm_jobs)}")
    lines.append("")

    if llm_jobs:
        lines.append("⚠ JOBS THAT BURN HAIKU/SONNET TOKENS:")
        for r in llm_jobs:
            lines.append(f"  [{r['schedule']}]  {r['name']}")
            for note in r['notes'][:3]:
                lines.append(f"      → {note}")
        lines.append("")

    lines.append("✓ ZERO-LLM JOBS:")
    for r in free_jobs:
        lines.append(f"  [{r['schedule']}]  {r['name']}")
    lines.append("")
    lines.append("All Anthropic calls bill the ANTHROPIC_API_KEY in .env.agents,")
    lines.append("NOT the Claude Code subscription.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--include-disabled", action="store_true")
    args = parser.parse_args()

    jobs = list_active_crons(include_disabled=args.include_disabled)
    results = [audit_cron(j) for j in jobs]

    if args.json:
        print(json.dumps({"results": results}, indent=2))
    else:
        print(render_human(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
