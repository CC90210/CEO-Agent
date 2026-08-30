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
import socket
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
# 2026-08-30: CC lowered this from 48h to 12h to accelerate the exit. That is an
# operator risk decision, recorded here rather than silently applied — and what
# the shortened window gives up is specific, not theoretical:
#   * The 28 OASIS CC crons include daily (0 3 * * *), twice-daily and WEEKLY
#     (40 13 * * 1) schedules. A 12h window cannot observe a single full cycle
#     of any of them, so a break in a once-a-day job is invisible to this gate.
#   * Slow-accumulating faults — memory growth, connection-pool exhaustion, cache
#     churn — are what a multi-day soak is actually for.
# What 12h DOES prove is real: request-path health, DNS/TLS settling, and the
# data plane, all of which have been green throughout.
SOAK_HOURS = 12


def _run(cmd: list[str]) -> tuple[int, str]:
    p = safe_run(cmd, capture_output=True, text=True, encoding="utf-8",
                 errors="replace", cwd=str(ROOT))
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def gate_soak() -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    end = SOAK_START + dt.timedelta(hours=SOAK_HOURS)
    done = now >= end
    return {"gate": f"{SOAK_HOURS}h soak elapsed", "pass": done,
            "detail": f"{(now - SOAK_START)} elapsed of {SOAK_HOURS}h; "
                      f"{'complete' if done else f'closes {end:%Y-%m-%d %H:%M} UTC'}"}


# Failures that predate the migration and are NOT regressions. A health gate
# that can never pass is not a gate — it is a permanently-red light that
# teaches its reader to skip the whole report. Each entry needs a reason and a
# removal condition, or this list becomes a place to hide real breakage.
KNOWN_BROKEN = {
    # Vercel lists apply.sunbizfunding.com on agent-dashboard, but the record
    # has never existed in DNS. Predates the migration; unrelated to Workers.
    # REMOVE WHEN: the subdomain is either created or detached from the project.
    "agent-dashboard": "apply.sunbizfunding.com has no DNS record (pre-existing)",
}


def gate_fleet() -> dict:
    """Alarms on a NEW unhealthy app, not on the known-broken baseline."""
    rc, out = _run([sys.executable, str(ROOT / "scripts" / "fleet_health_check.py"), "--json"])
    try:
        report = json.loads(out[out.index("["):out.rindex("]") + 1])
    except (ValueError, json.JSONDecodeError):
        return {"gate": "fleet health (every hostname, both stacks)", "pass": False,
                "detail": f"COULD NOT PARSE fleet_health_check output (rc={rc})"}
    unhealthy = {r["app"]: r.get("verdict", "?") for r in report if r.get("verdict") != "ok"}
    new = {a: v for a, v in unhealthy.items() if a not in KNOWN_BROKEN}
    total = len(report)
    if new:
        detail = "NEW: " + "; ".join(f"{a}: {v}" for a, v in sorted(new.items()))
    else:
        baseline = ", ".join(sorted(unhealthy)) or "none"
        detail = f"{total - len(unhealthy)}/{total} ok; known-broken only ({baseline})"
    return {"gate": "fleet health (every hostname, both stacks)", "pass": not new,
            "detail": detail}


# Apps deployed KNOWINGLY INCOMPLETE. A probe failure here is outstanding work,
# not a regression — the distinction is the whole point of the health/work split,
# and calling incomplete work a regression would make the alarm meaningless.
# Same contract as KNOWN_BROKEN: a reason and a removal condition, or it becomes
# a hiding place. gate_secrets still reports these loudly, so nothing is buried.
KNOWN_INCOMPLETE = {
    # Deployed 2026-08-30 with 26 sensitive secrets outstanding. Its cron routes
    # 500 because CRON_SECRET is unset (lib/cron-auth.ts fails closed).
    # REMOVE WHEN: CRON_SECRET is filled and secrets-plan reports 0 gaps.
    "oasis-command-center": "deployed with 26 secrets outstanding; cron routes 500 without CRON_SECRET",
}


def gate_dataplane() -> dict:
    """Alarms on a data-plane failure in an app that is supposed to be complete."""
    rc, out = _run(["node", str(ROOT / "scripts" / "turso_bridge_smoke.mjs"), "--json"])
    try:
        report = json.loads(out[out.index("["):out.rindex("]") + 1])
    except (ValueError, json.JSONDecodeError):
        return {"gate": "data plane + VPS bridge", "pass": False,
                "detail": f"COULD NOT PARSE turso_bridge_smoke output (rc={rc})"}
    failed = [r["app"] for r in report if r.get("verdict") == "FAIL"]
    new = [a for a in failed if a not in KNOWN_INCOMPLETE]
    ok = len([r for r in report if r.get("verdict") == "ok"])
    if new:
        detail = "FAILING: " + ", ".join(sorted(new))
    else:
        held = ", ".join(sorted(failed)) or "none"
        detail = f"{ok}/{len(report)} ok; known-incomplete only ({held})"
    return {"gate": "data plane + VPS bridge", "pass": not new, "detail": detail}


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
    gaps, unreadable = {}, []
    for slug, app in (reg.get("apps") or {}).items():
        if app.get("dropped"):
            continue
        rc, out = _run([sys.executable, str(ROOT / "scripts" / "integrations" / "wrangler_tool.py"),
                        "secrets-plan", "--app", slug])
        try:
            missing = json.loads(out).get("missing_from_env_agents", [])
        except json.JSONDecodeError:
            # FAIL CLOSED. Treating an unparseable answer as "no gaps" would
            # turn a broken check into a PASS on the gate that authorises
            # deleting production deployments.
            unreadable.append(slug)
            continue
        if missing:
            gaps[slug] = len(missing)
    bits = [f"{k}: {v} missing" for k, v in sorted(gaps.items())]
    if unreadable:
        bits.append(f"COULD NOT CHECK: {', '.join(sorted(unreadable))}")
    return {"gate": "no outstanding secret gaps", "pass": not gaps and not unreadable,
            "detail": "; ".join(bits) if bits else "all filled"}


# Vercel's anycast prefixes. Cloudflare's proxy answers from 104./172./162.,
# so a hostname resolving into these ranges is still being served by Vercel.
VERCEL_PREFIXES = ("216.198.", "216.150.", "76.76.", "64.29.")


def gate_traffic() -> dict:
    """Vercel may only be retired once nothing customer-facing still points at it.

    Resolves in-process. The first version shelled out to `python -c` with the
    hostname interpolated into the source string — an injection shape, one
    subprocess per host, and a resolution failure printed a traceback that the
    substring test then read as "not on Vercel". A hostname that cannot resolve
    is reported as its own state, never silently as a pass.
    """
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    still, unresolved = [], []
    for slug, app in (reg.get("apps") or {}).items():
        if app.get("dropped"):
            continue
        for host in app.get("custom_domains") or []:
            try:
                ips = {a[4][0] for a in socket.getaddrinfo(host, 443)}
            except OSError:
                unresolved.append(host)
                continue
            if any(ip.startswith(VERCEL_PREFIXES) for ip in ips):
                still.append(host)
    ok = not still and not unresolved
    bits = []
    if still:
        bits.append(f"still on Vercel: {', '.join(sorted(set(still)))}")
    if unresolved:
        bits.append(f"does not resolve: {', '.join(sorted(set(unresolved)))}")
    return {"gate": "no customer hostname still resolves to Vercel", "pass": ok,
            "detail": "; ".join(bits) if bits else "none"}


# Two kinds of "not ready", and conflating them makes this unschedulable.
#
#   HEALTH  things that are TRUE TODAY and must stay true. A failure here is a
#           REGRESSION — something that was working broke. Worth waking someone.
#   WORK    things known to be outstanding (the soak has not elapsed, apps are
#           not migrated yet, secrets are unfilled). These are false right now
#           BY DESIGN and will stay false for days.
#
# Exiting non-zero on WORK would page the operator on every scheduled run until
# the migration finishes, which is precisely how a monitor teaches its reader to
# ignore it. Exit codes: 0 = green light, 1 = REGRESSION, 2 = work outstanding.
HEALTH_GATES = [gate_fleet, gate_dataplane]
WORK_GATES = [gate_soak, gate_migrated, gate_secrets, gate_traffic]
# Display order (soak first reads best); membership comes from the typed lists
# above so there is only one place to classify a gate.
GATES = [gate_soak, gate_fleet, gate_dataplane, gate_migrated, gate_secrets, gate_traffic]

_UNCLASSIFIED = [g.__name__ for g in GATES if g not in HEALTH_GATES and g not in WORK_GATES]
if _UNCLASSIFIED:
    # Fail at import, loudly. An unclassified gate would silently be treated as
    # "work" — so a new HEALTH check would never raise the regression alarm it
    # was written to raise, and nobody would notice until it mattered.
    raise RuntimeError(
        f"gate(s) not classified as health or work: {', '.join(_UNCLASSIFIED)}. "
        "Add each to HEALTH_GATES (must stay true) or WORK_GATES (known outstanding)."
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    health = {g.__name__ for g in HEALTH_GATES}
    results = []
    for g in GATES:
        r = g()
        r["kind"] = "health" if g.__name__ in health else "work"
        results.append(r)
    ready = all(r["pass"] for r in results)
    regressed = [r for r in results if r["kind"] == "health" and not r["pass"]]
    # 0 green light · 1 REGRESSION (page someone) · 2 work still outstanding (quiet)
    code = 0 if ready else (1 if regressed else 2)
    stamp = dt.datetime.now(dt.timezone.utc)

    if args.json:
        print(json.dumps({"generated": stamp.isoformat(), "ready": ready,
                          "regressed": [r["gate"] for r in regressed],
                          "exit": code, "gates": results}, indent=2))
        return code

    print(f"# Vercel Decommissioning Report — generated {stamp:%Y-%m-%d %H:%M} UTC\n")
    print(f"## VERDICT: {'READY TO DECOMMISSION' if ready else 'NOT READY — Vercel must stay'}\n")
    for r in results:
        mark = "PASS" if r["pass"] else ("REGRESSED" if r["kind"] == "health" else "pending")
        print(f"  [{mark:9}] ({r['kind']}) {r['gate']}")
        print(f"              {r['detail']}")
    if regressed:
        print("\n*** REGRESSION: something that was working has broken. This is not")
        print("    'the migration is unfinished' — investigate before doing anything else.")
    elif not ready:
        print("\nNothing has regressed. The outstanding items are known work, not faults —")
        print("but each is still a reason a brand goes dark if Vercel is cancelled today.")
    print("\nNote: passing gates authorise PER-PROJECT retirement, not account closure —")
    print("out-of-scope projects and Vercel-registered domains are a separate decision")
    print("(see brain/DNS_CUTOVER_AND_VERCEL_EXIT_CHECKLIST.md §2).")
    print(f"\nexit {code}: "
          f"{'GREEN LIGHT' if code == 0 else 'REGRESSION — investigate' if code == 1 else 'work outstanding (expected)'}")
    return code


if __name__ == "__main__":
    sys.exit(main())
