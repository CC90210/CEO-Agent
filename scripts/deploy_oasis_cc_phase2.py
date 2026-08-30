"""deploy_oasis_cc_phase2.py — gated deploy of OASIS Command Center to Workers.

Prepared 2026-08-30 for execution on CC's final sign-off. Default run is
PREFLIGHT ONLY (no mutation): it proves every precondition and prints exactly
what is missing. `--execute` performs the deploy after the same preflight
passes; a failing check aborts before anything is touched.

    python scripts/deploy_oasis_cc_phase2.py             # preflight, safe
    python scripts/deploy_oasis_cc_phase2.py --execute   # deploy on sign-off

DELIBERATELY OUT OF SCOPE — each is its own gated step, never bundled here:
  * DNS / custom-domain attach (CC-executed, needs the zone-owning token)
  * The cron flip: CRON_FORWARD + removing cron-driver.yml's schedule triggers
    MUST happen together in one PR (see brain/WAVE3_OASIS_CC_RUNBOOK.md Phase C).
    The GH Actions driver is the ACTIVE firer; Vercel's scheduler died 2026-08-06.
  * Vercel retirement (14-day soak + explicit per-project approval).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

CAPABILITY_META = {
    "category": "release.cloudflare",
    "lifecycle": "active",
    "risk": "external_write",
    "triggers": [
        "deploy oasis command center to cloudflare",
        "phase 2 cutover oasis cc",
    ],
    "owner": "bravo",
    "project": "oasis",
    "bridge": {"visible": False},
}

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from lib.subprocess_helpers import safe_run  # noqa: E402

TOOL = ROOT / "scripts" / "integrations" / "wrangler_tool.py"
REGISTRY = ROOT / "config" / "cloudflare" / "apps.json"
APP = "oasis-command-center"
# Measured 2026-08-30: 8.13MiB gzip. Free plan caps at 3MiB, paid at 10MiB.
FREE_CAP_MIB = 3
PAID_CAP_MIB = 10


def run(args: list[str], **kw) -> subprocess.CompletedProcess:
    return safe_run([sys.executable, str(TOOL), *args], capture_output=True,
                    text=True, encoding="utf-8", errors="replace", cwd=str(ROOT), **kw)


def app_dir() -> Path:
    """From the registry — never a second hardcoded copy of the app's path."""
    return Path(json.loads(REGISTRY.read_text(encoding="utf-8"))["apps"][APP]["dir"])


def preflight() -> tuple[bool, list[str]]:
    """Returns (ok, blockers). Read-only."""
    blockers: list[str] = []

    who = run(["whoami"])
    if who.returncode != 0 or "Account ID" not in (who.stdout or ""):
        blockers.append("wrangler whoami failed — token missing or wrong account")
    else:
        print("  [ok] cloudflare auth")

    plan = run(["secrets-plan", "--app", APP])
    try:
        gaps = json.loads(plan.stdout or "{}").get("missing_from_env_agents", [])
    except json.JSONDecodeError:
        gaps = ["<secrets-plan output unparseable>"]
    if gaps:
        blockers.append(f"{len(gaps)} secret(s) still unfilled: {', '.join(gaps[:6])}"
                        + ("…" if len(gaps) > 6 else ""))
    else:
        print("  [ok] all manifest secrets present")

    # Note: CRON_SECRET / CRON_ATTEST_SECRET readiness is already covered by
    # secrets-plan above; they gate the CRON FLIP, not this deploy.
    worker = app_dir() / ".open-next" / "worker.js"
    if not worker.exists():
        blockers.append("no .open-next/worker.js — run: wrangler_tool.py build --app " + APP)
    else:
        print("  [ok] worker artifact present")

    workers = run(["list-workers"])
    deployed = APP in (workers.stdout or "")
    print(f"  [info] {APP} currently deployed: {deployed}")
    print(f"  [info] bundle measured 8.13MiB gzip — needs Workers PAID "
          f"(free cap {FREE_CAP_MIB}MiB, paid {PAID_CAP_MIB}MiB)")
    return (not blockers), blockers


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true",
                    help="deploy after preflight passes (default: preflight only)")
    args = ap.parse_args()

    print(f"=== OASIS CC Phase 2 preflight ({'EXECUTE' if args.execute else 'DRY'}) ===")
    ok, blockers = preflight()
    if not ok:
        print("\nBLOCKED:")
        for b in blockers:
            print(f"  - {b}")
        return 1
    print("\npreflight: PASS")

    if not args.execute:
        print("dry run — re-run with --execute on CC's sign-off.")
        return 0

    print("\n=== deploying (build -> deploy -> secrets) ===")
    proc = subprocess.run([sys.executable, str(TOOL), "deploy", "--app", APP], cwd=str(ROOT))
    if proc.returncode != 0:
        print("DEPLOY FAILED — if the cause is size limit 10027, Workers Paid is not enabled.")
        return proc.returncode

    print("\nDeployed. NEXT, as separate gated steps (never automatic):")
    print("  1. e2e parity vs Vercel production on the workers.dev URL")
    print("  2. cron flip: CRON_FORWARD=true AND remove cron-driver.yml schedules — one PR")
    print("  3. DNS cutover (CC, zone-owning token) per the cutover checklist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
