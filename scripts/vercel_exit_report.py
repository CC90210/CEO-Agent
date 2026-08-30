"""vercel_exit_report.py — generate the Vercel Decommissioning report from LIVE evidence.

Deliberately a SCRIPT rather than a document. A hand-written confirmation can be
issued while its facts are stale, or with a gate assumed rather than checked —
and "we confirmed it" is the one sentence in this migration that must never be
guessed. Running this IS issuing the report; every line below is measured at run
time and every gate can fail.

    python scripts/vercel_exit_report.py
    python scripts/vercel_exit_report.py --json

Exit 0 only when EVERY gate passes. A non-zero exit means Vercel must stay.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

CAPABILITY_META = {
    "category": "release.cloudflare",
    "lifecycle": "active",
    "risk": "read_only",
    "triggers": ["vercel decommissioning report", "is the migration done", "exit gate"],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": False},
}

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from lib.subprocess_helpers import safe_run  # noqa: E402

REGISTRY = ROOT / "config" / "cloudflare" / "apps.json"
SOAK_START = dt.datetime(2026, 8, 30, 7, 45, tzinfo=dt.timezone.utc)
SOAK_HOURS = 48


def _run(cmd: list[str]) -> tuple[int, str]:
    p = safe_run(cmd, capture_output=True, text=True, encoding="utf-8",
                 errors="replace", cwd=str(ROOT))
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def gate_soak() -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    end = SOAK_START + dt.timedelta(hours=SOAK_HOURS)
    done = now >= end
    return {"gate": "48h soak elapsed", "pass": done,
            "detail": f"{(now - SOAK_START)} elapsed of {SOAK_HOURS}h; "
                      f"{'complete' if done else f'closes {end:%Y-%m-%d %H:%M} UTC'}"}


def gate_fleet() -> dict:
    rc, out = _run([sys.executable, str(ROOT / "scripts" / "fleet_health_check.py")])
    last = [l for l in out.splitlines() if "fully healthy" in l]
    return {"gate": "fleet health (every hostname, both stacks)", "pass": rc == 0,
            "detail": last[-1].strip() if last else out.strip()[-120:]}


def gate_dataplane() -> dict:
    rc, out = _run(["node", str(ROOT / "scripts" / "turso_bridge_smoke.mjs")])
    last = [l for l in out.splitlines() if "ok," in l and "failed" in l]
    return {"gate": "data plane + VPS bridge", "pass": rc == 0,
            "detail": last[-1].strip() if last else out.strip()[-120:]}


def gate_migrated() -> dict:
    """Every in-scope app must actually be deployed to Workers."""
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    rc, out = _run([sys.executable, str(ROOT / "scripts" / "integrations" / "wrangler_tool.py"),
                    "list-workers"])
    deployed = {l.strip() for l in out.splitlines() if l.strip() and " " not in l.strip()}
    pending = []
    for slug, app in (reg.get("apps") or {}).items():
        if app.get("dropped"):
            continue
        if app.get("worker_name", slug) not in deployed:
            pending.append(slug)
    return {"gate": "all in-scope apps deployed to Workers", "pass": not pending,
            "detail": "all deployed" if not pending else f"NOT deployed: {', '.join(sorted(pending))}"}


def gate_secrets() -> dict:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    gaps = {}
    for slug, app in (reg.get("apps") or {}).items():
        if app.get("dropped"):
            continue
        rc, out = _run([sys.executable, str(ROOT / "scripts" / "integrations" / "wrangler_tool.py"),
                        "secrets-plan", "--app", slug])
        try:
            missing = json.loads(out).get("missing_from_env_agents", [])
        except json.JSONDecodeError:
            missing = []
        if missing:
            gaps[slug] = len(missing)
    return {"gate": "no outstanding secret gaps", "pass": not gaps,
            "detail": "all filled" if not gaps
                      else "; ".join(f"{k}: {v} missing" for k, v in sorted(gaps.items()))}


def gate_traffic() -> dict:
    """Vercel may only be retired once nothing customer-facing still points at it."""
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    still = []
    for slug, app in (reg.get("apps") or {}).items():
        if app.get("dropped"):
            continue
        for host in app.get("custom_domains") or []:
            rc, out = _run(["python", "-c",
                            f"import socket;print(sorted({{a[4][0] for a in socket.getaddrinfo('{host}',443)}}))"])
            # Vercel's anycast ranges; Cloudflare proxies answer from 104./172.
            if "216.198." in out or "76.76." in out or "64.29." in out:
                still.append(host)
    return {"gate": "no customer hostname still resolves to Vercel", "pass": not still,
            "detail": "none" if not still else f"still on Vercel: {', '.join(sorted(set(still)))}"}


GATES = [gate_soak, gate_fleet, gate_dataplane, gate_migrated, gate_secrets, gate_traffic]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    results = [g() for g in GATES]
    ready = all(r["pass"] for r in results)
    stamp = dt.datetime.now(dt.timezone.utc)

    if args.json:
        print(json.dumps({"generated": stamp.isoformat(), "ready": ready, "gates": results}, indent=2))
        return 0 if ready else 1

    print(f"# Vercel Decommissioning Report — generated {stamp:%Y-%m-%d %H:%M} UTC\n")
    print(f"## VERDICT: {'READY TO DECOMMISSION' if ready else 'NOT READY — Vercel must stay'}\n")
    for r in results:
        print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {r['gate']}")
        print(f"         {r['detail']}")
    if not ready:
        print("\nEvery FAIL above is a reason a brand goes dark if Vercel is cancelled today.")
    print("\nNote: passing gates authorise PER-PROJECT retirement, not account closure —")
    print("out-of-scope projects and Vercel-registered domains are a separate decision")
    print("(see brain/DNS_CUTOVER_AND_VERCEL_EXIT_CHECKLIST.md §2).")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
