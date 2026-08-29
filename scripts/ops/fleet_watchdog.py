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
import os
import re
import subprocess
import sys
import time
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


def _process_table() -> str | None:
    """Every running command line, lowercased. None means UNREADABLE.

    THE None MATTERS MORE THAN THE STRING (2026-08-28). This returned "" on any
    failure, and "" makes every `ident in table` test False — so an unreadable
    process table was indistinguishable from "the entire fleet is dead", and the
    watchdog's response to that is to start the entire fleet. Every 5 minutes.

    That is not hypothetical. Four bravo-scheduler instances and duplicate
    event-routers were found running side by side (started 21:26, 23:56, 00:01,
    00:10), which means every cron job in the empire was executing up to FOUR
    TIMES: four concurrent inbound-email sweeps racing the same mailbox, each
    classifying the same mail, each marking \\Seen, each writing the ledger.
    Eight email_engine processes were live at once. It also feeds itself — more
    duplicates means more load, more load means a slower table read, and a
    slower read means more duplicates.

    So this now fails CLOSED: if we cannot prove a daemon is down, we do not
    start one. A supervisor that multiplies the fleet is worse than one that
    pauses.

    WMI is the ONLY source, deliberately. psutil is five times faster (3s vs
    14.3s) and was tried here first — it returns an EMPTY cmdline for 163 of 579
    processes on this machine, including every detached pythonw daemon this file
    supervises. It reported bravo-scheduler, event-router and both bridges as
    DOWN while all four were running. Had that shipped, the watchdog would have
    started a second copy of each every five minutes: the exact duplication this
    function exists to prevent, caused by the fix for it. Speed is worth nothing
    to a supervisor that cannot see its own fleet.

    A self-check ("can this table see ME?") is not sufficient to catch that, and
    was tried too: psutil CAN see this process — a normal console python — while
    being blind to the detached pythonw daemons. A source that sees the observer
    but not the observed passes that check and is still useless. Hence one
    source, verified, with no silent fallback.
    """
    # Self-check on our own PID, not on this file's name.
    #
    # The first version looked for "fleet_watchdog.py" in the table, which is
    # only present when this module is the __main__ script. Every consumer
    # IMPORTS it — harness_eval, cron_health_check, local_bridge — so for them
    # the running command line is harness_eval.py and the check failed on a
    # perfectly good table, returning UNREADABLE and (now that this fails
    # closed) turning the harness gate red. The PID is what actually identifies
    # "this process" regardless of who called us.
    me = f"|{os.getpid()}|"

    def _verified(table: str | None) -> str | None:
        # A source that cannot find THIS process cannot be trusted to claim
        # another one is absent.
        if table and me in table:
            return table
        return None

    # CIM first. Same WMI data as wmic, but the modern client: wmic is
    # deprecated on Windows 11, measured 14.3s here, and returned nothing usable
    # often enough to fail the harness check outright — which, now that this
    # fails closed, turns every flake into a red gate.
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             # "|<pid>|<cmdline>" per line so the PID self-check has an
             # unambiguous token to match and cannot collide with a substring
             # of some other number in a command line.
             "Get-CimInstance Win32_Process | "
             "ForEach-Object { '|' + $_.ProcessId + '|' + $_.CommandLine }"],
            capture_output=True, text=True, timeout=90,
            errors="ignore", creationflags=_NO_WINDOW)
        table = _verified((proc.stdout or "").lower())
        if table:
            return table
    except Exception:  # noqa: BLE001
        pass

    try:
        proc = subprocess.run(
            ["wmic", "process", "get", "ProcessId,CommandLine", "/format:csv"],
            capture_output=True, text=True, timeout=90,
            errors="ignore", creationflags=_NO_WINDOW)
        # CSV rows are Node,CommandLine,ProcessId — normalise the PID into the
        # same |<pid>| token the self-check looks for.
        raw = (proc.stdout or "").lower()
        lines = []
        for line in raw.splitlines():
            parts = line.rsplit(",", 1)
            if len(parts) == 2 and parts[1].strip().isdigit():
                lines.append(f"|{parts[1].strip()}|{parts[0]}")
        table = _verified("\n".join(lines) if lines else None)
        if table:
            return table
    except Exception:  # noqa: BLE001
        pass

    return None  # UNREADABLE — callers must not treat this as "nothing running"


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


def _windows_session_id() -> int | None:
    """This process's Windows session, or None if it cannot be determined."""
    if os.name != "nt":
        return None
    try:
        import ctypes  # noqa: PLC0415
        sid = ctypes.c_ulong()
        if ctypes.windll.kernel32.ProcessIdToSessionId(
                ctypes.c_ulong(os.getpid()), ctypes.byref(sid)):
            return int(sid.value)
    except Exception:  # noqa: BLE001
        pass
    return None


class WrongSession(RuntimeError):
    """This watchdog is running in Windows Session 0.

    A Session-0 process cannot read the command line of a Session-1 process, so
    from there the entire user-session fleet looks ABSENT — and this watchdog's
    response to an absent fleet is to start it. That produces a second, invisible
    copy of every daemon.

    This is the fourth recurrence of the session/PM2 class on this machine
    (2026-08-07 wrong PM2_HOME, 08-14 elevated daemon, 08-27 S4U/session-0,
    08-28 duplicate schedulers). The "PM2 Resurrect" task was LogonType=S4U,
    which is exactly how a supervisor ends up here. Refusing to run is the
    launcher-level abort that class has needed for three incidents.
    """


class ProcessTableUnreadable(RuntimeError):
    """The OS process table could not be read, so liveness is UNKNOWN.

    Raised rather than returning a row set, because every caller of status()
    treats `running: False` as "start it" or "alert on it", and both are wrong
    when the truth is "we could not look".
    """


_ROW_PID = re.compile(r"^\|\d+\|")
_TOKENS = re.compile(r'"[^"]*"|\S+')
# Flags whose VALUE is inline code, never a script path. A process running
# inline code is a probe or a one-liner, never a supervised daemon — and it is
# the single most common way a daemon's name appears in a command line that is
# not that daemon.
_INLINE_CODE_FLAGS = {"-c", "/c", "-e", "--eval"}


def _table_rows(table: str) -> list[str]:
    """One command line per element.

    A command line can itself contain newlines (a shell invoked with a heredoc
    body is the common case here), so a line that does not open a new
    `|<pid>|` record is a CONTINUATION of the previous one, not a row of its
    own. Splitting naively would shred one process's arguments into several
    fake processes — and those fragments are exactly what used to satisfy the
    substring liveness test below.
    """
    lines = table.splitlines()
    # The continuation rule only has meaning when rows are actually delimited.
    # A table with no `|pid|` records at all (hand-built fixtures, and any
    # future source that emits bare command lines) is one process per line —
    # folding those together would merge the whole fleet into a single row.
    if not any(_ROW_PID.match(line) for line in lines):
        return lines
    rows: list[str] = []
    for line in lines:
        if _ROW_PID.match(line) or not rows:
            rows.append(_ROW_PID.sub("", line))
        else:
            rows[-1] += "\n" + line
    return rows


def _cmdline_target(cmdline: str) -> str:
    """What this command line is actually EXECUTING: its script or -m module.

    Not "what it mentions". `python -m pyflakes scripts/scheduler.py` mentions
    the scheduler; it is a linter. `bash -c "... scheduler.py ..."` mentions it;
    it is a shell. Both used to count as a live bravo-scheduler.
    """
    toks = [t.strip('"') for t in _TOKENS.findall(cmdline)]
    rest = toks[1:]  # drop the interpreter itself
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok == "-m":
            return rest[i + 1] if i + 1 < len(rest) else ""
        if tok in _INLINE_CODE_FLAGS:
            return ""
        if tok.startswith("-") or tok.startswith("/"):
            i += 1
            continue
        return tok
    return ""


def _row_runs(cmdline: str, ident: str) -> bool:
    """True only if this command line is running THIS daemon."""
    target = _cmdline_target(cmdline)
    if not target:
        return False
    return target == ident or target.replace("\\", "/").rsplit("/", 1)[-1] == ident


def status() -> list[dict]:
    table = _process_table()
    # `not table`, not `table is None`: an EMPTY table is the precise shape of
    # the original bug — every `ident in ""` is False, so the whole fleet reads
    # as dead and the watchdog starts a duplicate of everything. Both spellings
    # of "no evidence" must land here.
    if not table:
        raise ProcessTableUnreadable(
            "could not read the process table (wmic returned nothing usable) — "
            "refusing to report the fleet as down on no evidence")
    off = disabled_names()
    # Per-ROW matching, not `ident in table` (fixed 2026-08-29). The old test
    # was a substring search over the entire concatenated process table, so ANY
    # process whose command line merely contained "scheduler.py" — a grep, an
    # editor, `python -m pyflakes scripts/scheduler.py`, a shell whose heredoc
    # body quoted the path — proved bravo-scheduler was alive.
    #
    # Caught live: the scheduler was killed, `up` reported "nothing to start —
    # everything up or disabled", and the fleet stayed down. The false green
    # came from this session's own diagnostic shell. A supervisor that a
    # bystander command can talk out of restarting a dead daemon is not a
    # supervisor. It is the mirror image of the duplicate-fleet bug: that one
    # started daemons on no evidence, this one refuses to on false evidence.
    cmdlines = _table_rows(table)
    rows = []
    for app in manifest():
        ident = _identity(app)
        rows.append({**app, "ident": ident,
                     "running": bool(ident and any(_row_runs(c, ident)
                                                   for c in cmdlines)),
                     "disabled": app["name"] in off})
    return rows


def classify(row: dict) -> str:
    """The state of one daemon: 'running' | 'disabled' | 'unrunnable' | 'down'.

    ONE DEFINITION, deliberately. `status()` returns raw flags, and every
    consumer used to re-derive meaning from them by hand — harness_eval,
    cron_health_check, dashboard_email_queue_monitor, local_bridge and
    machine_parity each had their own predicate, and they did not agree: some
    treated an operator-disabled daemon as an outage, some as fine; some folded
    an unrunnable manifest entry into "down", some reported it separately.

    This subsystem has form for exactly this. test_parity_liveness_has_exactly
    _one_definition exists because liveness had TWO definitions, and its
    docstring calls that "the fifth instance in this subsystem after two claim
    mechanisms, two coverage implementations, two ownership maps and two
    identity lists". Five more hand-rolled copies is how the sixth happens.

    The distinctions matter and are why this is not just a boolean:
      disabled   — the operator stopped it. Not an outage. Paging about a
                   deliberate stop is how a gate teaches people to ignore it.
      unrunnable — the MANIFEST is broken (no script recorded), so no restart
                   can fix it. Real, but a config defect, and folding it into
                   "down" pins every alert permanently red.
      down       — supposed to be running, is not. The actual alarm.
    """
    if row.get("disabled"):
        return "disabled"
    if row.get("running"):
        return "running"
    if row.get("unrunnable"):
        return "unrunnable"
    return "down"


def down_names(rows: list[dict] | None = None) -> list[str]:
    """Names of daemons that are a genuine outage — the ONLY thing worth paging
    on. Excludes operator-disabled and unrunnable-manifest entries."""
    return sorted(r["name"] for r in (rows if rows is not None else status())
                  if classify(r) == "down")


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


RUN_LOCK = PROJECT_ROOT / "state" / "fleet_watchdog.lock"
LOCK_STALE_SEC = 600


def _acquire_run_lock() -> bool:
    """O_EXCL lock so two watchdog passes cannot both decide to start the fleet.

    The Task Scheduler fires this every 5 minutes while a pass can take longer
    than that on a loaded box (the process-table read alone measured 14.3s via
    wmic). Two overlapping passes each see a daemon as down and each start one,
    which is half of how four schedulers came to exist.
    """
    try:
        RUN_LOCK.parent.mkdir(parents=True, exist_ok=True)
        if RUN_LOCK.exists():
            age = time.time() - RUN_LOCK.stat().st_mtime
            if age > LOCK_STALE_SEC:
                RUN_LOCK.unlink(missing_ok=True)  # previous pass died holding it
            else:
                return False
        fd = os.open(str(RUN_LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except Exception:  # noqa: BLE001 - a lock failure must not disable supervision
        return True


def _release_run_lock() -> None:
    try:
        RUN_LOCK.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


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

    # A Session-0 supervisor cannot see the user-session fleet and would start a
    # duplicate of every daemon. Only block the MUTATING pass — `status` from
    # session 0 is merely uninformative, but `up` from session 0 is destructive.
    if a.cmd == "up":
        session = _windows_session_id()
        if session == 0:
            msg = ("REFUSING to supervise from Windows Session 0 — a session-0 "
                   "process cannot see session-1 daemons, so every one of them "
                   "would look absent and be started again as an invisible "
                   "duplicate. Set this task's principal to Interactive.")
            _log(f"ABORTED: {msg}")
            print(f"ABORTED: {msg}", file=sys.stderr)
            return 1

    # Only the mutating pass needs the lock; read-only status must stay callable
    # from the health checks that now depend on it.
    if a.cmd == "up" and not _acquire_run_lock():
        _log("skipped: another watchdog pass holds the lock")
        print("skipped: another watchdog pass is already running")
        return 0
    try:
        return _dispatch(a)
    except ProcessTableUnreadable as exc:
        # Never fall through to "start everything" on no evidence.
        _log(f"ABORTED: {exc}")
        print(f"ABORTED: {exc}", file=sys.stderr)
        return 1
    finally:
        if a.cmd == "up":
            _release_run_lock()


def _dispatch(a) -> int:
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
