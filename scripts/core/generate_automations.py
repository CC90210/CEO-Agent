"""Automation Register — what actually runs in the empire, from live sources.

Writes brain/AUTOMATIONS.md: every scheduled job, daemon, hook and OS task, what
it does, when it fires, and whether it is currently healthy.

WHY THIS EXISTS
---------------
Nothing answered "what is running?" in one place. `brain/INVENTORY.md` has
counts (and drifts — it read 37 cron jobs while the live registry held 41),
`fleet_health.py` covers agent pulses, and the rest was spread across
cron_engine.SEED_JOBS, a PM2 manifest, a hooks config and Task Scheduler. An
operator asking a simple question got a research project, and an agent booting
into a session had no single artifact to read.

The output is a COMMITTED DOCUMENT, deliberately. A CLI that prints live state
is only true while you watch it; a generated file is readable by any session at
boot, which is what makes "what runs at 3am?" answerable without running
anything. The generator is the same code path, so the document cannot drift
from the live answer — re-run it and the file is current.

FAILS LOUD, NEVER SILENTLY SHORT
--------------------------------
If a source is unreachable the section says so and the run exits non-zero. A
register that quietly omits the cron table because Turso blinked is worse than
no register: it reads as "these are all my automations" while hiding a third of
them. Every section reports its own provenance.

CLI:
  python scripts/core/generate_automations.py            # write brain/AUTOMATIONS.md
  python scripts/core/generate_automations.py --json     # machine-readable
  python scripts/core/generate_automations.py --check    # exit 1 if stale (>7d) or missing
  python scripts/core/generate_automations.py --dry-run  # print, do not write
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = PROJECT_ROOT / "brain" / "AUTOMATIONS.md"
STALE_DAYS = 7

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    from _subprocess_helpers import WINDOWLESS_FLAGS  # type: ignore
except Exception:  # pragma: no cover
    WINDOWLESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# --- collectors: each returns (payload, error_or_None) -----------------------

def collect_cron() -> tuple[list[dict], str | None]:
    """Live cron registry, joined to the declared SEED_JOBS entry.

    The LIVE table is the source of truth for what fires; SEED_JOBS is the
    source of truth for what it does. Reporting either alone has misled before:
    a job disabled in the DB still looks active in SEED_JOBS, and a job in the
    DB with no seed entry has no description at all.
    """
    try:
        from integrations.supabase_tool import get_client  # noqa: PLC0415
        from lib.secret_loader import load_env  # noqa: PLC0415
        db = get_client(dict(load_env()))
        rows = db.table("cron_jobs").select(
            "name,is_active,schedule,last_result,last_run_at").limit(500).execute().data or []
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {exc}"

    seeds = {}
    try:
        from core.cron_engine import SEED_JOBS  # noqa: PLC0415
        for j in SEED_JOBS:
            seeds[str(j.get("name") or "")] = j
    except Exception:  # noqa: BLE001
        pass

    # Reuse the harness's OWN suppression rather than re-deriving "failing".
    # The nightly harness eval's row records its own scoreboard, so a run that
    # scored 13/14 stamps last_result="ERROR: ... HARNESS EVAL — 13/14", and a
    # naive reader reports the eval as broken forever. harness_eval and
    # cron_health_check already share one rule for this; a third copy here would
    # be the fourth place this subsystem has kept two definitions of one fact.
    try:
        from harness_eval import is_self_scored_failure  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        def is_self_scored_failure(_job):  # type: ignore[misc]
            return False

    out = []
    for r in rows:
        name = str(r.get("name") or "")
        seed = seeds.get(name, {})
        cfg = seed.get("action_config") or {}
        last = str(r.get("last_result") or "")
        out.append({
            "name": name,
            "active": bool(r.get("is_active")),
            "schedule": str(r.get("schedule") or "?"),
            "does": str(seed.get("description") or "").strip(),
            "runs": str(cfg.get("script") or seed.get("action_type") or ""),
            "last_run": str(r.get("last_run_at") or "")[:16],
            "failing": (last.upper().startswith(("ERROR", "FAILED"))
                        and not is_self_scored_failure(r)),
            "declared": name in seeds,
        })
    return sorted(out, key=lambda x: (not x["active"], x["name"])), None


def collect_daemons() -> tuple[list[dict], str | None]:
    try:
        from ops.fleet_watchdog import classify, status  # noqa: PLC0415
        return [{"name": r.get("name"), "state": classify(r),
                 "ident": r.get("ident") or "",
                 "note": r.get("unrunnable") or ""} for r in status()], None
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {exc}"


def collect_hooks() -> tuple[dict, str | None]:
    p = PROJECT_ROOT / ".claude" / "settings.local.json"
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {}, f"{type(exc).__name__}: {exc}"
    out: dict[str, list[str]] = {}
    for event, matchers in (cfg.get("hooks") or {}).items():
        names = []
        for m in matchers if isinstance(matchers, list) else []:
            for h in (m.get("hooks") or []):
                cmd = str(h.get("command") or "")
                names.append(Path(cmd.split()[-1]).name if cmd else "?")
        out[event] = names
    return out, None


def collect_timings(limit: int = 12) -> tuple[list[dict], str | None]:
    """Slowest automations by median duration, from state/cron_timings.jsonl.

    Answers "what is eating the machine", which nothing could answer before —
    cron_jobs has no duration column and the scheduler timed only its own loop.
    MEDIAN, not mean: one 300s timeout would otherwise make an ordinarily-fast
    job look permanently slow, and it is the typical cost that decides whether a
    schedule is sane.

    An empty file is not an error. It means the scheduler has not dispatched
    since timing was added, and saying so is better than showing nothing.
    """
    p = PROJECT_ROOT / "state" / "cron_timings.jsonl"
    if not p.is_file():
        return [], None
    from collections import defaultdict  # noqa: PLC0415
    runs: dict[str, list[float]] = defaultdict(list)
    fails: dict[str, int] = defaultdict(int)
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            job = str(r.get("job") or "?")
            runs[job].append(float(r.get("seconds") or 0))
            if not r.get("ok", True):
                fails[job] += 1
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {exc}"

    out = []
    for job, vals in runs.items():
        s = sorted(vals)
        med = s[len(s) // 2]
        out.append({"job": job, "runs": len(s), "median": med,
                    "worst": s[-1], "failures": fails.get(job, 0)})
    out.sort(key=lambda x: -x["median"])
    return out[:limit], None


def collect_os_tasks() -> tuple[list[dict], str | None]:
    """Windows Task Scheduler entries that drive this empire."""
    if sys.platform != "win32":
        return [], None
    ps = ("Get-ScheduledTask | Where-Object { $_.TaskName -match 'Bravo|PM2|OASIS' } | "
          "ForEach-Object { $_.TaskName + '|' + $_.State }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True, timeout=90,
                           errors="ignore", creationflags=WINDOWLESS_FLAGS)
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {exc}"
    out = []
    for line in (r.stdout or "").splitlines():
        if "|" in line:
            name, _, state = line.strip().partition("|")
            out.append({"name": name.strip(), "state": state.strip()})
    return out, None


# --- render ------------------------------------------------------------------

def render(data: dict) -> str:
    now = datetime.now(timezone.utc)
    L = [
        "---",
        f"last_updated: {now.strftime('%Y-%m-%d')}",
        "tags: [brain, operations, automations, generated]",
        "---",
        "",
        "# AUTOMATIONS.md — What Actually Runs (auto-generated)",
        "",
        "> Generated by `scripts/core/generate_automations.py` — do not hand-edit.",
        "> Refreshed daily by the `Daily Automation Register` cron, or on demand.",
        f"> Generated at: {now.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "Read this to answer *what runs, when, and is it healthy* without running",
        "anything. Sources: the live `cron_jobs` table, `cron_engine.SEED_JOBS`,",
        "the fleet manifest, `.claude/settings.local.json`, and Task Scheduler.",
        "",
        "Related: [[EXECUTION_RULES]] · [[DATA_LIFECYCLE]] · [[V6_ARCHITECTURE]]",
        "",
    ]

    errs = [f"`{k}`: {v}" for k, v in data["errors"].items() if v]
    if errs:
        L += ["## ⚠️ INCOMPLETE — a source was unreadable", "",
              "This register is **not** the full picture right now:", ""]
        L += [f"- {e}" for e in errs]
        L += ["", "Fix the source and re-run; do not treat the sections below as complete.", ""]

    crons = data["crons"]
    active = [c for c in crons if c["active"]]
    failing = [c for c in active if c["failing"]]
    L += ["## Scheduled jobs", "",
          f"**{len(active)} active** of {len(crons)} registered"
          + (f" · **{len(failing)} currently failing**" if failing else " · none failing"),
          ""]
    if failing:
        L += ["Failing now:", ""] + [f"- `{c['name']}` — last run {c['last_run'] or '?'}"
                                     for c in failing] + [""]
    L += ["| Job | Schedule | Runs | What it does |", "|---|---|---|---|"]
    for c in active:
        does = (c["does"][:110] + "…") if len(c["does"]) > 110 else (c["does"] or "—")
        does = does.replace("|", "/").replace("\n", " ")
        L.append(f"| {'🔴 ' if c['failing'] else ''}{c['name']} | `{c['schedule']}` "
                 f"| `{c['runs'] or '—'}` | {does} |")
    inactive = [c for c in crons if not c["active"]]
    if inactive:
        L += ["", f"<details><summary>{len(inactive)} inactive</summary>", ""]
        L += [f"- {c['name']} (`{c['schedule']}`)" for c in inactive]
        L += ["", "</details>", ""]

    L += ["", "## Daemons (long-running)", ""]
    ds = data["daemons"]
    if ds:
        L += ["| Daemon | State | Process |", "|---|---|---|"]
        for d in ds:
            mark = {"running": "✅", "disabled": "⏸️",
                    "unrunnable": "⚠️", "down": "🔴"}.get(d["state"], "?")
            note = f" — {d['note'][:60]}" if d["note"] else ""
            L.append(f"| {d['name']} | {mark} {d['state']}{note} | `{d['ident']}` |")
    else:
        L.append("_none reported_")

    L += ["", "## Guard hooks (fire on agent actions)", ""]
    hooks = data["hooks"]
    if hooks:
        for event in sorted(hooks):
            L.append(f"- **{event}** → {', '.join(hooks[event]) or '—'}")
    else:
        L.append("_none configured_")

    tm = data.get("timings") or []
    L += ["", "## What it costs (slowest by median duration)", ""]
    if tm:
        L += ["Median, not mean — one 300s timeout would otherwise make an",
              "ordinarily-fast job look permanently slow.", "",
              "| Job | Median | Worst | Runs | Failures |", "|---|---|---|---|---|"]
        for t_ in tm:
            L.append(f"| {t_['job']} | {t_['median']:.0f}s | {t_['worst']:.0f}s "
                     f"| {t_['runs']} | {t_['failures'] or '—'} |")
    else:
        L.append("_no timings recorded yet — the scheduler has not dispatched "
                 "since duration tracking was added_")

    tasks = data["os_tasks"]
    if tasks:
        L += ["", "## OS scheduled tasks", ""]
        for t in tasks:
            L.append(f"- {t['name']} — {t['state']}")

    L += ["", "---", "",
          f"Totals: {len(active)} active jobs · {sum(1 for d in ds if d['state'] == 'running')}"
          f" running daemons · {sum(len(v) for v in hooks.values())} hook matchers"
          f" · {len(tasks)} OS tasks", ""]
    return "\n".join(L)


def build() -> dict:
    crons, e1 = collect_cron()
    daemons, e2 = collect_daemons()
    hooks, e3 = collect_hooks()
    tasks, e4 = collect_os_tasks()
    timings, e5 = collect_timings()
    return {"crons": crons, "daemons": daemons, "hooks": hooks, "os_tasks": tasks,
            "timings": timings,
            "errors": {"cron_jobs": e1, "fleet": e2, "hooks": e3, "os_tasks": e4,
                       "timings": e5}}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--json", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--check", action="store_true",
                   help=f"exit 1 if the register is missing or older than {STALE_DAYS}d")
    args = p.parse_args()

    if args.check:
        if not OUT_PATH.is_file():
            print(f"ERROR: {OUT_PATH.name} missing — run this script")
            return 1
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(
            OUT_PATH.stat().st_mtime, tz=timezone.utc)
        if age > timedelta(days=STALE_DAYS):
            print(f"ERROR: {OUT_PATH.name} is {age.days}d old (max {STALE_DAYS}d)")
            return 1
        print(f"{OUT_PATH.name} is current ({age.days}d old)")
        return 0

    data = build()
    text = render(data)
    broken = [k for k, v in data["errors"].items() if v]

    if args.json:
        print(json.dumps({**data, "ok": not broken}, separators=(",", ":"), default=str))
    elif args.dry_run:
        print(text)
    else:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(text, encoding="utf-8")
        active = sum(1 for c in data["crons"] if c["active"])
        running = sum(1 for d in data["daemons"] if d["state"] == "running")
        # ONE line last: scheduler stores only the final stdout line.
        print(f"wrote {OUT_PATH.relative_to(PROJECT_ROOT)} — {active} active jobs, "
              f"{running} daemons running"
              + (f", INCOMPLETE ({', '.join(broken)} unreadable)" if broken else ""))

    if broken:
        print(f"ERROR: automation register incomplete — unreadable: {', '.join(broken)}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
