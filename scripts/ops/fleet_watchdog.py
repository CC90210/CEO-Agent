# bridge_mutating: true
#
# `status` is read-only; `up` starts daemons and `install-task` writes a
# scheduled task. Starting the scheduler resumes cron execution, which is an
# outward effect. Over-confirming a status read costs a tap.
"""fleet_watchdog — keep Bravo's daemons up WITHOUT depending on PM2.

WHY THIS EXISTS
---------------
On 2026-08-28 the coordination bridge was found dead for two days. The cause was
not the bridge: PM2 could not be talked to at all. `pm2` returns EPERM on its
named pipe — with zero daemons running, and on a fresh PM2_HOME — so it is a
machine-level block on node named pipes, and unblocking it needs an elevated
shell that an agent does not have.

Meanwhile three daemons stayed down, including `bravo-scheduler`, which means no
cron ran for two days. Waiting for a machine-level fix before the fleet can run
is the wrong dependency: the supervisor is supposed to serve the fleet, not the
other way round.

So this is a supervisor that needs nothing PM2 needs. No named pipes, no daemon,
no RPC. It reads the fleet manifest, asks the OS process table what is running,
starts what is not, and is itself driven by Windows Task Scheduler — which is
already proven working on this machine (the PM2 Resurrect task runs and exits 0;
it is pm2 ITSELF that then fails).

DESIGN NOTES
------------
* MANIFEST = ~/.pm2/dump.pm2, filtered to THIS repo. It is the accurate record
  of what was actually running, and it already exists. Other agents' processes
  (Maven in CMO-Agent, Atlas in CFO-Agent) are deliberately out of scope — this
  supervises Bravo's fleet, not the machine's.
* NEVER invoke pm2. Calling pm2 while its pipe is blocked SPAWNS AN ORPHAN
  DAEMON; 23 accumulated that way, several from health checks. A supervisor that
  degrades the thing it supervises is worse than none.
* NEVER double-start. Every start is preceded by a process-table check, matched
  on the script path rather than the interpreter name — `pythonw.exe` matches
  dozens of unrelated processes and would report a false UP.
* An operator STOP must stick. A name listed in state/fleet_disabled.json is
  never started; otherwise a deliberate `stop` silently reverses within minutes,
  which is worse than a daemon being down because it is invisible.

  python scripts/ops/fleet_watchdog.py status
  python scripts/ops/fleet_watchdog.py up [--only bravo-scheduler] [--dry-run]
  python scripts/ops/fleet_watchdog.py disable <name> / enable <name>
  python scripts/ops/fleet_watchdog.py install-task     # every 5 min, user-level
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DUMP = Path.home() / ".pm2" / "dump.pm2"
LOG = PROJECT_ROOT / "state" / "fleet_watchdog.log"
DISABLED = PROJECT_ROOT / "state" / "fleet_disabled.json"
TASK_NAME = "Bravo Fleet Watchdog"
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
DETACHED = 0x00000008 if sys.platform == "win32" else 0


def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "msg": msg})
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def disabled_names() -> set[str]:
    try:
        return set(json.loads(DISABLED.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001
        return set()


def _ecosystem_apps() -> dict[str, dict]:
    """Launch specs from ecosystem.config.js, keyed by name.

    This is the VERSION-CONTROLLED source and it is more complete than
    dump.pm2: the dump had no `script` for bravo-ig-dm or breeze-live-watch,
    so they were unrunnable from the dump alone, while ecosystem.config.js
    carries the full spec for the former. Preferring the committed config over
    machine state is the same rule the rest of this repo follows.

    Read via node because it is a JS module; a Python parse would be a second,
    drifting definition of the same file.
    """
    eco = PROJECT_ROOT / "ecosystem.config.js"
    if not eco.exists():
        return {}
    js = ("const c=require(process.argv[1]);const a=c.apps||c;"
          "console.log(JSON.stringify(a.map(x=>({name:x.name,script:x.script,"
          "args:x.args,interp:x.interpreter,cwd:x.cwd}))));")
    try:
        out = subprocess.run(["node", "-e", js, str(eco)], capture_output=True,
                             text=True, timeout=60, creationflags=_NO_WINDOW).stdout
        return {a["name"]: a for a in json.loads(out) if a.get("name")}
    except Exception as e:  # noqa: BLE001
        print(f"[fleet] could not read ecosystem.config.js ({type(e).__name__}) — "
              f"falling back to dump.pm2 only", file=sys.stderr)
        return {}


def manifest() -> list[dict]:
    """Bravo's managed processes, scoped to this repo.

    dump.pm2 says WHAT was running; ecosystem.config.js says HOW to run it.
    Names come from the dump (machine truth), launch specs prefer the committed
    config and fall back to the dump.
    """
    eco = _ecosystem_apps()
    try:
        apps = json.loads(DUMP.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"[fleet] cannot read {DUMP}: {type(e).__name__}: {e}", file=sys.stderr)
        return []
    out = []
    root = str(PROJECT_ROOT).replace("/", "\\").lower()
    for a in apps:
        cwd = str(a.get("cwd") or "").replace("/", "\\").lower()
        if root not in cwd:
            continue          # another agent's repo — not ours to supervise
        name = a.get("name")
        # Committed spec wins; dump.pm2 fills the gaps it left.
        e = eco.get(name) or {}
        script = str(e.get("script") or a.get("script") or "")
        args = e.get("args") or a.get("args") or []
        if isinstance(args, str):
            args = args.split()
        interp = str(e.get("interp") or a.get("exec_interpreter") or "")
        # A runnable entry needs an actual TARGET, not just arguments.
        # `breeze-live-watch` records args ['loop','--interval','300'] and NO
        # script, so a naive build produces `pythonw.exe loop --interval 300`,
        # which tries to execute a file called `loop`. The dry run caught it.
        # Skipping silently would be worse than starting garbage — the operator
        # would think it was supervised — so unrunnable entries are surfaced.
        module_form = any(str(x) == "-m" for x in args)
        if not script and not module_form:
            out.append({"name": name, "script": "", "args": args,
                        "interp": interp, "cwd": str(a.get("cwd")),
                        "unrunnable": "no script recorded in dump.pm2 — cannot "
                                      "reconstruct the command; re-save it from a "
                                      "working pm2, or add it to the manifest by hand"})
            continue
        out.append({"name": name, "script": script, "args": args,
                    "interp": interp, "cwd": str(a.get("cwd")), "unrunnable": ""})
    return out


def _process_table() -> str:
    try:
        return subprocess.run(["wmic", "process", "get", "CommandLine"],
                              capture_output=True, text=True, timeout=60,
                              errors="ignore", creationflags=_NO_WINDOW).stdout.lower()
    except Exception:  # noqa: BLE001
        return ""


def _identity(app: dict) -> str:
    """The string that uniquely identifies this app in a command line.

    Deliberately the SCRIPT (or its distinguishing module arg), never the
    interpreter: matching on `pythonw.exe` would report every python process as
    this daemon and the watchdog would never start anything.
    """
    script = app["script"]
    base = Path(script).name if script else ""
    if base and base.lower() not in ("python.exe", "pythonw.exe", "node.exe", ""):
        return base.lower()
    # interpreter-as-script (e.g. `pythonw -m bravo_cli.bridge_chat_server`):
    # the module name is what distinguishes it.
    for a in app["args"]:
        if "." in str(a) and not str(a).startswith("-"):
            return str(a).lower()
    return (app["name"] or "").lower()


def status() -> list[dict]:
    table = _process_table()
    off = disabled_names()
    rows = []
    for app in manifest():
        ident = _identity(app)
        rows.append({**app, "ident": ident,
                     "running": bool(ident and ident in table),
                     "disabled": app["name"] in off})
    return rows


def start(app: dict, dry: bool = False) -> tuple[bool, str]:
    if app.get("unrunnable"):
        return False, app["unrunnable"]
    cmd: list[str] = []
    if app["interp"] and app["interp"].lower() not in ("none", ""):
        cmd.append(app["interp"])
    if app["script"]:
        cmd.append(app["script"])
    cmd.extend(str(a) for a in app["args"])
    if not cmd:
        return False, "no launchable command"
    if dry:
        return True, "DRY: " + " ".join(cmd)
    try:
        subprocess.Popen(cmd, cwd=app["cwd"] or str(PROJECT_ROOT),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=_NO_WINDOW | DETACHED, close_fds=True)
        _log(f"started {app['name']}: {' '.join(cmd)}")
        return True, " ".join(cmd)
    except Exception as e:  # noqa: BLE001
        _log(f"FAILED to start {app['name']}: {type(e).__name__}: {e}")
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("status"); ps.add_argument("--json", action="store_true")
    pu = sub.add_parser("up")
    pu.add_argument("--only"); pu.add_argument("--dry-run", action="store_true")
    pu.add_argument("--json", action="store_true")
    pd = sub.add_parser("disable"); pd.add_argument("name")
    pe = sub.add_parser("enable"); pe.add_argument("name")
    sub.add_parser("install-task")
    a = p.parse_args()

    if a.cmd == "status":
        rows = status()
        if a.json:
            print(json.dumps(rows, indent=2, default=str)); return 0
        down = [r for r in rows if not r["running"] and not r["disabled"]
                and not r.get("unrunnable")]
        for r in rows:
            if r.get("unrunnable"):
                state = "UNRUNNABLE"
            else:
                state = "DISABLED" if r["disabled"] else ("UP" if r["running"] else "DOWN")
            print(f"  {str(r['name']):<22} {state:<11} {r['ident']}")
            if r.get("unrunnable"):
                print(f"  {'':<22} -> {r['unrunnable']}")
        print(f"\n{len(down)} of {len(rows)} down (excluding disabled)")
        return 1 if down else 0

    if a.cmd == "up":
        rows = status()
        started, failed = [], []
        for r in rows:
            if r["disabled"]:
                continue
            if a.only and r["name"] != a.only:
                continue
            if r["running"] or r.get("unrunnable"):
                continue
            ok, detail = start(r, dry=a.dry_run)
            (started if ok else failed).append((r["name"], detail))
        for n, d in started:
            print(f"  started {n}  ({d})")
        for n, d in failed:
            print(f"  FAILED  {n}  ({d})", file=sys.stderr)
        if not started and not failed:
            print("  nothing to start — everything up or disabled")
        # Always record the PASS, not only the starts.
        #
        # Logging only on action makes "the watchdog ran and everything was up"
        # indistinguishable from "the watchdog never ran" — and the second is
        # the failure that matters. That ambiguity is exactly what let the fleet
        # sit dead for two days behind a green light, and it is APEX's own point
        # about heartbeats reporting what a job DID rather than that it ran.
        # A silent supervisor cannot be audited.
        up = sum(1 for r in rows if r["running"])
        _log(f"pass: {up}/{len(rows)} up, {len(started)} started, "
             f"{len(failed)} failed, {sum(1 for r in rows if r['disabled'])} disabled")
        return 1 if failed else 0

    if a.cmd in ("disable", "enable"):
        off = disabled_names()
        off.add(a.name) if a.cmd == "disable" else off.discard(a.name)
        DISABLED.parent.mkdir(parents=True, exist_ok=True)
        DISABLED.write_text(json.dumps(sorted(off), indent=2), encoding="utf-8")
        _log(f"{a.cmd}d {a.name}")
        print(f"{a.cmd}d {a.name}; disabled set = {sorted(off)}")
        return 0

    if a.cmd == "install-task":
        py = PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe"
        script = PROJECT_ROOT / "scripts" / "ops" / "fleet_watchdog.py"
        run = f'"{py}" "{script}" up'
        r = subprocess.run(["schtasks", "/create", "/tn", TASK_NAME, "/tr", run,
                            "/sc", "minute", "/mo", "5", "/f"],
                           capture_output=True, text=True, timeout=60,
                           creationflags=_NO_WINDOW)
        print((r.stdout or r.stderr).strip())
        if r.returncode == 0:
            _log(f"installed scheduled task '{TASK_NAME}' every 5 min")
        return r.returncode
    return 2


if __name__ == "__main__":
    sys.exit(main())
