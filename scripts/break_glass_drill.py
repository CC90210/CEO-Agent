#!/usr/bin/env python3
"""break_glass_drill — quarterly dry-run of the emergency runbook.

Walks the BREAK_GLASS.md preconditions and reports DRIFT between the doc and reality:
can we stop everything, revoke keys, and restore from a bundle? It changes nothing —
it only checks that the levers the runbook tells CC to pull still exist. Wire to cron
`break_glass_drill` (quarterly); the n8n handler for that action_type sends the report
to Telegram.

Usage: python break_glass_drill.py [--json]
"""
from __future__ import annotations
import json
import shutil
import subprocess
import sys
from pathlib import Path

CAPABILITY_META = {
    "category": "governance.resilience",
    "lifecycle": "active",
    "risk": "read_only",
    "triggers": ["break glass drill", "emergency recovery audit", "verify disaster recovery"],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": True, "confirm": False},
}

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO = Path(__file__).resolve().parents[1]


def _check(name, ok, detail=""):
    return {"check": name, "ok": bool(ok), "detail": detail}


def run() -> dict:
    checks = []
    # 1. STOP: is pm2 reachable (the kill switch)?
    pm2 = shutil.which("pm2")
    checks.append(_check("stop: pm2 on PATH", pm2 is not None, pm2 or "pm2 not found — `npm i -g pm2`"))
    # 2. REVOKE: do the credential wrappers exist (the rotate-then-verify path)?
    wrappers = ["stripe_tool.py", "google_tool.py", "supabase_tool.py"]
    found = [w for w in wrappers if (REPO / "scripts" / w).exists() or list(REPO.glob(f"scripts/**/{w}"))]
    checks.append(_check("revoke: credential CLI wrappers present", len(found) == len(wrappers),
                         f"{len(found)}/{len(wrappers)}: {found}"))
    _env_ok = (REPO / ".env.agents").exists()
    checks.append(_check("revoke: .env.agents exists (target of rotation)", _env_ok,
                         "" if _env_ok else "NOT FOUND — secrets live here"))
    # 3. RESTORE: is the backup dir recorded + do bundles exist + verify one?
    bdir_f = REPO / "state" / ".v3_backup_dir"
    bdir = bdir_f.read_text(encoding="utf-8").strip() if bdir_f.exists() else ""
    bundles = list(Path(bdir).glob("*.bundle")) if bdir and Path(bdir).is_dir() else []
    checks.append(_check("restore: backup dir recorded + populated", bool(bundles),
                         f"{len(bundles)} bundles in {bdir or '(unrecorded)'}"))
    if bundles:
        v = subprocess.run(["git", "-C", str(REPO), "bundle", "verify", str(bundles[0])],  # noqa: SUBPROCESS (quarterly/on-demand git read)
                           capture_output=True, text=True)
        checks.append(_check("restore: newest bundle verifies", "complete history" in v.stdout,
                             bundles[0].name))
    # 4. WHERE: state DB + guard logs (the forensics) present?
    checks.append(_check("state DB present", (REPO / "state" / "empire_state.db").exists(), ""))
    logs = [l for l in ("exec_guard.log", "secret_guard.log") if (REPO / "state" / l).exists()]
    checks.append(_check("guard audit logs present", len(logs) == 2, f"{logs}"))
    # 5. The doc itself reachable?
    doc = list((REPO.parent).glob("empire-harness/docs/BREAK_GLASS.md")) or \
        list(Path("C:/Users/User/empire-harness/docs").glob("BREAK_GLASS.md"))
    checks.append(_check("runbook BREAK_GLASS.md reachable", bool(doc),
                         str(doc[0]) if doc else "not found"))

    drift = [c for c in checks if not c["ok"]]
    return {"drill": "break_glass", "checks": checks, "drift_count": len(drift),
            "status": "OK" if not drift else "DRIFT"}


def main() -> int:
    r = run()
    if "--json" in sys.argv:
        print(json.dumps(r, indent=2))
    else:
        print(f"=== break-glass drill: {r['status']} ({r['drift_count']} drift) ===")
        for c in r["checks"]:
            print(f"  {'✓' if c['ok'] else '✗'} {c['check']:<42} {c['detail'][:50]}")
        if r["drift_count"]:
            print("\n  ⚠ DRIFT — the runbook references something that moved. Update BREAK_GLASS.md.")
    return 1 if r["drift_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
