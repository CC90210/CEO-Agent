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
* MANIFEST = the committed ecosystem.config.js plus explicitly declared sibling
  specs. ~/.pm2/dump.pm2 is optional compatibility input for legacy entries;
  deleting or corrupting the retired PM2 snapshot must not erase the fleet.
* LIFECYCLE = config/fleet_lifecycle.json. Every daemon needs a retention reason;
  future burst workers use bounded leases instead of becoming permanent drift.
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
  python scripts/ops/fleet_watchdog.py logs bravo-telegram --lines 60
  python scripts/ops/fleet_watchdog.py up [--only bravo-scheduler] [--dry-run]
  python scripts/ops/fleet_watchdog.py lifecycle
  python scripts/ops/fleet_watchdog.py lease <name> --minutes 30 --reason "..."
  python scripts/ops/fleet_watchdog.py release-lease <name>
  python scripts/ops/fleet_watchdog.py disable <name> / enable <name>
  python scripts/ops/fleet_watchdog.py install-task     # every 5 min, user-level
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DUMP = Path.home() / ".pm2" / "dump.pm2"
LOG = PROJECT_ROOT / "state" / "fleet_watchdog.log"
DISABLED = PROJECT_ROOT / "state" / "fleet_disabled.json"
LEASES = PROJECT_ROOT / "state" / "fleet_leases.json"
LIFECYCLE_CONFIG = PROJECT_ROOT / "config" / "fleet_lifecycle.json"
TASK_NAME = "Bravo Fleet Watchdog"
MAX_LEASE_MINUTES = 24 * 60
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


def _lifecycle_policy() -> dict[str, dict]:
    """Load the committed lifecycle decision for every managed process.

    Missing or malformed policy is not replaced with an implicit always-on
    default. An undocumented daemon is exactly how background-process sprawl
    returns, so _apply_lifecycle marks it unrunnable until a human-readable
    retention reason is committed.
    """
    try:
        payload = json.loads(LIFECYCLE_CONFIG.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            raise ValueError("schema_version must be 1")
        processes = payload.get("processes")
        if not isinstance(processes, dict):
            raise ValueError("processes must be an object")
    except Exception as exc:  # noqa: BLE001 - configuration boundary
        print(
            f"[fleet] cannot read lifecycle policy {LIFECYCLE_CONFIG}: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return {}

    valid: dict[str, dict] = {}
    for name, raw in processes.items():
        if not isinstance(raw, dict):
            continue
        mode = str(raw.get("mode") or "")
        reason = str(raw.get("reason") or "").strip()
        if mode not in {"always_on", "on_demand"} or not reason:
            continue
        valid[str(name)] = {**raw, "mode": mode, "reason": reason}
    return valid


def _apply_lifecycle(rows: "Sequence[dict]") -> list[dict]:
    """Attach committed lifecycle metadata and fail closed on omissions."""
    policy = _lifecycle_policy()
    out: list[dict] = []
    for source in rows:
        row = dict(source)
        meta = policy.get(str(row.get("name") or ""))
        if meta:
            row["lifecycle"] = meta["mode"]
            row["lifecycle_reason"] = meta["reason"]
            row["lifecycle_owner"] = str(meta.get("owner") or "")
        else:
            row["lifecycle"] = "unclassified"
            row["lifecycle_reason"] = (
                "No committed lifecycle policy; automatic launch is blocked"
            )
            row["lifecycle_owner"] = ""
            defect = "missing committed lifecycle metadata"
            prior = str(row.get("unrunnable") or "")
            row["unrunnable"] = f"{prior}; {defect}" if prior else defect
        out.append(row)
    return out


def _read_leases() -> dict[str, dict]:
    """Read runtime on-demand leases. A missing file simply means no leases."""
    try:
        payload = json.loads(LEASES.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("lease registry must be an object")
        return {str(k): v for k, v in payload.items() if isinstance(v, dict)}
    except FileNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001 - fail closed for on-demand work
        print(
            f"[fleet] cannot read lease registry {LEASES}: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return {}


def _write_leases(leases: dict[str, dict]) -> None:
    """Atomically replace the lease registry so readers never see half JSON."""
    LEASES.parent.mkdir(parents=True, exist_ok=True)
    temp = LEASES.with_name(f"{LEASES.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(leases, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, LEASES)


def lease_active(name: str, *, now: "float | None" = None) -> bool:
    lease = _read_leases().get(name) or {}
    try:
        return float(lease.get("expires_at")) > (time.time() if now is None else now)
    except (TypeError, ValueError):
        return False


def grant_lease(name: str, *, minutes: int, reason: str,
                now: "float | None" = None) -> tuple[bool, str]:
    """Grant a bounded lease to a process explicitly classified on-demand."""
    if not 1 <= minutes <= MAX_LEASE_MINUTES:
        return False, f"minutes must be between 1 and {MAX_LEASE_MINUTES}"
    reason = reason.strip()
    if not reason:
        return False, "a lease reason is required"
    app = next((row for row in manifest() if row.get("name") == name), None)
    if app is None:
        return False, f"unknown daemon: {name}"
    if app.get("lifecycle") != "on_demand":
        return False, f"{name} is {app.get('lifecycle')}, not on_demand"
    issued = time.time() if now is None else now
    expires = issued + (minutes * 60)
    leases = _read_leases()
    leases[name] = {
        "issued_at": issued,
        "expires_at": expires,
        "reason": reason,
        "issued_by_pid": os.getpid(),
    }
    _write_leases(leases)
    _log(
        f"lifecycle lease granted: {name}, {minutes}m, "
        f"expires_at={expires}, reason={reason}"
    )
    return True, f"leased until {datetime.fromtimestamp(expires, timezone.utc).isoformat()}"


def release_lease(name: str) -> tuple[bool, str]:
    leases = _read_leases()
    existed = name in leases
    leases.pop(name, None)
    _write_leases(leases)
    _log(f"lifecycle lease released: {name} (existed={existed})")
    return True, "released" if existed else "no active lease"


def _ecosystem_apps(eco_path: "Path | None" = None) -> dict[str, dict]:
    """Launch specs from an ecosystem.config.js, keyed by name.

    Defaults to this repo's config; SIBLING_APPS passes a sibling's path so the
    same reader serves both rather than a second, drifting parser.

    This is the VERSION-CONTROLLED source and it is more complete than
    dump.pm2: the dump had no `script` for bravo-ig-dm or breeze-live-watch,
    so they were unrunnable from the dump alone, while ecosystem.config.js
    carries the full spec for the former. Preferring the committed config over
    machine state is the same rule the rest of this repo follows.

    Read via node because it is a JS module; a Python parse would be a second,
    drifting definition of the same file.
    """
    eco = eco_path or (PROJECT_ROOT / "ecosystem.config.js")
    if not eco.exists():
        return {}
    js = ("const c=require(process.argv[1]);const a=c.apps||c;"
          "console.log(JSON.stringify(a.map(x=>({name:x.name,script:x.script,"
          "args:x.args,interp:x.interpreter,cwd:x.cwd,env:x.env}))));")
    try:
        out = subprocess.run(["node", "-e", js, str(eco)], capture_output=True,
                             text=True, timeout=60, creationflags=_NO_WINDOW).stdout
        return {a["name"]: a for a in json.loads(out) if a.get("name")}
    except Exception as e:  # noqa: BLE001
        print(f"[fleet] could not read ecosystem.config.js ({type(e).__name__}) — "
              f"falling back to dump.pm2 only", file=sys.stderr)
        return {}


# ── Sibling agents this watchdog also supervises ───────────────────────────
#
# The repo filter below exists so we never adopt a process that merely happens
# to be in dump.pm2. But three of CC's daemons live in sibling repos, and the
# filter meant NOTHING supervised them: PM2 was retired on 2026-08-27 and this
# watchdog replaced it only for Business-Empire-Agent. Atlas's and Maven's
# Telegram bridges were simply dead, and the Command Center's worker board
# rendered them "Down — stopped reporting" with no process behind the label.
#
# Declared explicitly, by name, from each sibling's own committed
# ecosystem.config.js — never by scanning dump.pm2 for anything foreign. An
# allowlist adopts what CC decided to run; a scan adopts whatever was there.
SIBLING_APPS: dict[str, tuple[Path, str]] = {
    "atlas-telegram": (Path.home() / "APPS" / "CFO-Agent", "atlas-telegram"),
    "maven-telegram": (Path.home() / "CMO-Agent", "maven-telegram"),
}


def _sibling_manifest() -> list[dict]:
    """Launch specs for the declared sibling daemons.

    A sibling whose repo or config is missing is reported UNRUNNABLE rather
    than skipped: silence would put it back in the state this function exists
    to end, where nothing runs it and nothing says so.
    """
    rows: list[dict] = []
    for name, (repo, app_name) in SIBLING_APPS.items():
        eco = repo / "ecosystem.config.js"
        if not eco.exists():
            rows.append({"name": name, "script": "", "args": [], "interp": "",
                         "cwd": str(repo),
                         "unrunnable": f"no ecosystem.config.js at {eco}"})
            continue
        spec = _ecosystem_apps(eco).get(app_name)
        if not spec:
            rows.append({"name": name, "script": "", "args": [], "interp": "",
                         "cwd": str(repo),
                         "unrunnable": f"{app_name!r} not declared in {eco}"})
            continue
        args = spec.get("args") or []
        if isinstance(args, str):
            args = args.split()
        cwd = Path(str(spec.get("cwd") or repo))
        script = str(spec.get("script") or "")
        # ABSOLUTE, deliberately. Two repos can hold a `telegram_agent.js`, and
        # a relative one makes the two indistinguishable in the process table —
        # see _identity. It also removes any dependence on the child inheriting
        # the right working directory.
        if script and not Path(script).is_absolute():
            script = str((cwd / script).resolve())
        rows.append({"name": name,
                     "script": script,
                     "args": args,
                     "interp": str(spec.get("interp") or ""),
                     "cwd": str(cwd),
                     "unrunnable": ""})
    return rows


def manifest() -> list[dict]:
    """Bravo's managed processes, plus the declared sibling daemons.

    ecosystem.config.js is the durable source of truth. dump.pm2 is optional
    compatibility input for legacy processes that have not yet been moved into
    the committed config; it has been frozen since PM2 was retired. Launch
    specs prefer the committed config and fall back to a usable dump. Siblings
    come from SIBLING_APPS because they are deliberately outside the repo
    filter below.
    """
    eco = _ecosystem_apps()
    apps = []
    try:
        apps = json.loads(DUMP.read_text(encoding="utf-8"))
        if not isinstance(apps, list):
            raise ValueError("expected a JSON array")
        apps = [app for app in apps if isinstance(app, dict)]
    except FileNotFoundError:
        # PM2 has been retired. Its snapshot is compatibility input, not a
        # dependency, so a machine that never had PM2 should stay quiet.
        pass
    except Exception as e:  # noqa: BLE001
        # A PRESENT but corrupt/unreadable snapshot remains useful evidence.
        print(f"[fleet] cannot read {DUMP}: {type(e).__name__}: {e}", file=sys.stderr)
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
    # This repo's committed apps that the dump never recorded (2026-09-11).
    # Nothing has rewritten dump.pm2 since PM2 was retired on 2026-08-27, so
    # taking names from it alone meant a daemon added to ecosystem.config.js
    # after that date was never started or restarted, and read as absent to
    # everything that asks this module. OASIS's dashboard email sender and its
    # monitor were the first two. Same repo filter as the dump: a copy of this
    # repo at another path (a worktree) must not adopt the canonical
    # checkout's daemons.
    listed = {r["name"] for r in out}
    for name, e in eco.items():
        if name in listed:
            continue
        cwd = str(e.get("cwd") or PROJECT_ROOT)
        if root not in cwd.replace("/", "\\").lower():
            continue
        script = str(e.get("script") or "")
        args = e.get("args") or []
        if isinstance(args, str):
            args = args.split()
        row = {"name": name, "script": script, "args": args,
               "interp": str(e.get("interp") or ""), "cwd": cwd, "unrunnable": "",
               # The env block applies ONLY to apps adopted here. The dump's
               # daemons have run without theirs since the watchdog replaced
               # PM2, and handing it to them now would change live behaviour
               # on whatever restart comes next: bravo-scheduler's block turns
               # on the email auto-reply path (EMAIL_BRAIN_AUTO_SEND),
               # claude-bridge's sets IS_SANDBOX, and every block sets
               # EMPIRE_TURSO_PATCH_REQUIRED. That is CC's call, not a side
               # effect of adopting new daemons.
               "env": e.get("env") or {}}
        if not script and not any(str(x) == "-m" for x in args):
            row["unrunnable"] = ("no script declared in ecosystem.config.js — "
                                 "cannot build the command")
        out.append(row)
    # Siblings last, and never overriding a same-named local app.
    known = {r["name"] for r in out}
    out.extend(r for r in _sibling_manifest() if r["name"] not in known)
    return _apply_lifecycle(out)


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
             # "|<pid>|<parent-pid>|<cmdline>" per line. Parentage collapses
             # a .venv launcher plus its interpreter child into one daemon
             # tree while preserving the self-check's |<pid>| token.
             "Get-CimInstance Win32_Process | "
             "ForEach-Object { '|' + $_.ProcessId + '|' + "
             "$_.ParentProcessId + '|' + $_.CommandLine }"],
            capture_output=True, text=True, timeout=90,
            errors="ignore", creationflags=_NO_WINDOW)
        table = _verified((proc.stdout or "").lower())
        if table:
            return table
    except Exception:  # noqa: BLE001
        pass

    try:
        proc = subprocess.run(
            ["wmic", "process", "get",
             "ProcessId,ParentProcessId,CommandLine", "/format:csv"],
            capture_output=True, text=True, timeout=90,
            errors="ignore", creationflags=_NO_WINDOW)
        # CSV rows are Node,CommandLine,ProcessId — normalise the PID into the
        # same |<pid>| token the self-check looks for.
        raw = proc.stdout or ""
        lines = []
        for original in csv.DictReader(
                line for line in raw.splitlines() if line.strip()):
            row = {
                str(k).strip().lower(): (v or "")
                for k, v in original.items()
            }
            pid = row.get("processid", "").strip()
            parent = row.get("parentprocessid", "").strip() or "0"
            if pid.isdigit() and parent.isdigit():
                lines.append(
                    f"|{pid}|{parent}|{row.get('commandline', '')}"
                )
        table = _verified("\n".join(lines).lower() if lines else None)
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

    An ABSOLUTE script identifies by its full path (2026-09-02). A basename
    cannot separate two daemons that share one: Bravo's bridge and Maven's are
    both `telegram_agent.js`, in different repos, and on the first run after
    Maven was adopted the watchdog reported maven-telegram UP while no such
    process existed — it was matching Bravo's. A supervisor that reads one
    daemon's process as another's will never start the dead one, which is the
    exact failure this whole file exists to prevent, wearing a new hat.
    """
    script = app["script"]
    base = Path(script).name if script else ""
    is_interpreter = base.lower() in ("python.exe", "pythonw.exe", "node.exe", "")
    # The interpreter check comes FIRST. claude-bridge records its script as the
    # absolute path to pythonw.exe and is really `pythonw -m bravo_cli...`;
    # taking the absolute path there identified it as "pythonw.exe", matched
    # nothing, and reported two live daemons DOWN — which would have started a
    # duplicate of each. Verified live before this ordering was fixed.
    if script and not is_interpreter and Path(script).is_absolute():
        return str(script).replace("\\", "/").lower()
    if base and not is_interpreter:
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


_ROW_PID = re.compile(r"^\|(?P<pid>\d+)\|")
_ROW_WITH_PARENT = re.compile(r"^\|(?P<pid>\d+)\|(?P<parent_pid>\d+)\|")
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
            parent = _ROW_WITH_PARENT.match(line)
            rows.append(
                _ROW_WITH_PARENT.sub("", line)
                if parent else _ROW_PID.sub("", line)
            )
        else:
            rows[-1] += "\n" + line
    return rows


def _table_process_rows(table: str) -> list[dict]:
    """Return PID, parent PID and command line for each process record.

    Historic ``|pid|command`` records and bare command-line fixtures remain
    readable. With no parent evidence, each matching row is conservatively an
    independent root: this can warn, but can never hide duplicate processes.
    """
    lines = table.splitlines()
    if not any(_ROW_PID.match(line) for line in lines):
        return [
            {"pid": None, "parent_pid": None, "cmdline": line}
            for line in lines
            if line
        ]
    rows: list[dict] = []
    for line in lines:
        parent = _ROW_WITH_PARENT.match(line)
        legacy = _ROW_PID.match(line)
        if parent:
            rows.append({
                "pid": int(parent.group("pid")),
                "parent_pid": int(parent.group("parent_pid")),
                "cmdline": line[parent.end():],
            })
        elif legacy:
            rows.append({
                "pid": int(legacy.group("pid")),
                "parent_pid": None,
                "cmdline": line[legacy.end():],
            })
        elif rows:
            rows[-1]["cmdline"] += "\n" + line
    return rows


def _matching_process_rows(table: str, ident: str, *,
                           other_idents: "Sequence[str]" = ()) -> list[dict]:
    if not ident:
        return []
    return [
        row for row in _table_process_rows(table)
        if _row_runs(row["cmdline"], ident)
        and not _claimed_elsewhere(row["cmdline"], ident, other_idents)
    ]


def _root_process_rows(rows: "Sequence[dict]") -> list[dict]:
    """Independent roots, collapsing a matching launcher/child chain."""
    matching_pids = {
        row["pid"] for row in rows if isinstance(row.get("pid"), int)
    }
    return [
        row for row in rows
        if row.get("pid") is None or row.get("parent_pid") not in matching_pids
    ]


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
    """True only if this command line is running THIS daemon.

    Both sides are slash-normalised (2026-09-02). A full-path ident is stored
    with forward slashes while Windows reports the command line with
    backslashes, so atlas-telegram read DOWN with its own PID plainly visible
    in the process table. Comparing two spellings of one path is not a
    comparison.
    """
    target = _cmdline_target(cmdline)
    if not target:
        return False
    target = target.replace("\\", "/")
    ident = ident.replace("\\", "/")
    return target == ident or target.rsplit("/", 1)[-1] == ident


def _row_runs_exact(cmdline: str, ident: str) -> bool:
    """_row_runs WITHOUT the basename fallback: a full-path claim, or nothing."""
    target = _cmdline_target(cmdline)
    if not target or not ident:
        return False
    return target.replace("\\", "/") == ident.replace("\\", "/")


def _claimed_elsewhere(cmdline: str, ident: str,
                       other_idents: "Sequence[str]") -> bool:
    """True when a DIFFERENT daemon claims this command line by its FULL path.

    _row_runs falls back to comparing basenames so a daemon launched with a
    relative script (`node telegram_agent.js`, which is how this repo's own
    entries are recorded) is still recognised. That fallback cannot tell apart
    two files that share a name — and two do: Bravo's telegram_agent.js and
    Maven's, in different repos.

    2026-09-03, proven against the live process table:
        bravo-telegram ident 'telegram_agent.js'                  -> [18404, 40180]
        maven-telegram ident 'c:/users/user/cmo-agent/telegram_agent.js' -> [40180]
    40180 is Maven's. So Stop or Restart on bravo-telegram issued
    `taskkill /PID 40180 /T /F` against another agent's Telegram bridge. Only
    bravo-telegram went into fleet_disabled.json, so the next 5-minute pass
    revived Maven and NOTHING in any log attributed the outage to the click —
    the same "died with no error line" signature the operator was chasing.
    The read side had the mirror defect: with Bravo's daemon dead and Maven's
    alive, status() reported bravo-telegram UP and never restarted it.

    An exact full-path claim settles ownership: that process is theirs, and our
    basename match was a coincidence of naming. Making the ident absolute
    instead would have been wrong — this repo's own command lines are relative,
    so an absolute ident matches neither spelling and reports live daemons DOWN,
    which is how the supervisor starts a duplicate of everything.
    """
    if _row_runs_exact(cmdline, ident):
        return False  # our own claim is exact; nothing outranks it
    return any(_row_runs_exact(cmdline, other) for other in other_idents)


def _other_idents(name: str, apps: "Sequence[dict] | None" = None) -> list[str]:
    """Every OTHER manifest entry's identity, for ownership arbitration."""
    out: list[str] = []
    for other in (apps if apps is not None else manifest()):
        if other.get("name") == name:
            continue
        ident = _identity(other)
        if ident:
            out.append(ident)
    return out


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
    apps = manifest()
    rows = []
    for app in apps:
        ident = _identity(app)
        # A row only counts as OURS if no other daemon claims it by full path —
        # see _claimed_elsewhere. Without this, Bravo's telegram bridge read as
        # running off Maven's process and would never have been restarted.
        others = _other_idents(app["name"], apps)
        matches = _matching_process_rows(table, ident, other_idents=others)
        roots = _root_process_rows(matches)
        rows.append({
            **app,
            "ident": ident,
            "running": bool(roots),
            "pids": [
                row["pid"] for row in matches if row.get("pid") is not None
            ],
            "root_pids": [
                row["pid"] for row in roots if row.get("pid") is not None
            ],
            "root_count": len(roots),
            "disabled": app["name"] in off,
        })
    return rows


def classify(row: dict) -> str:
    """One daemon's state, including unsafe independent duplicate roots.

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
    # Duplicate roots outrank every boolean flag. Two live schedulers are not
    # "running" in the healthy sense: they execute cron/email work twice. A
    # disabled marker must not hide a failed stop that left duplicates alive.
    if int(row.get("root_count") or 0) > 1:
        return "duplicate"
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


DAEMON_LOG_DIR = PROJECT_ROOT / "state" / "logs"
DAEMON_LOG_MAX_BYTES = 2_000_000
# A daemon started more often than this in the window is not being supervised,
# it is being resuscitated. Manifest daemons are long-running; three starts in
# an hour means each one died.
CRASH_LOOP_STARTS = 3
CRASH_LOOP_WINDOW_SEC = 3600


def read_daemon_log(name: str, lines: int = 60) -> str | None:
    """Return a bounded tail from the watchdog-owned log for one daemon.

    The name becomes part of a path, so accept only manifest-name characters;
    this read-only operator surface must not become an arbitrary file reader.
    None distinguishes a missing log from an existing empty one.
    """
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise ValueError("daemon name contains unsupported characters")
    path = DAEMON_LOG_DIR / f"daemon-{name}.log"
    if not path.exists():
        return None
    if lines <= 0:
        return ""
    tail = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(tail[-lines:])


def _daemon_log_needs_rollover(name: str) -> bool:
    """Whether a watchdog-owned daemon log is over its hard size limit."""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        return False
    try:
        return (
            DAEMON_LOG_DIR / f"daemon-{name}.log"
        ).stat().st_size > DAEMON_LOG_MAX_BYTES
    except OSError:
        return False


def _roll_daemon_log(name: str) -> tuple[bool, str]:
    """Atomically retain one rolled copy of an oversized daemon log.

    The caller must first stop the daemon that owns the active stdout handle.
    ``os.replace`` either publishes the complete active file as ``.1`` or
    leaves both files untouched. There is deliberately no copy-truncate
    fallback: truncating beneath a live writer can lose the exact traceback
    this log exists to preserve.
    """
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        return False, "daemon name contains unsupported characters"
    path = DAEMON_LOG_DIR / f"daemon-{name}.log"
    try:
        if not path.exists() or path.stat().st_size <= DAEMON_LOG_MAX_BYTES:
            return True, "within limit"
        rolled = path.with_suffix(".log.1")
        os.replace(path, rolled)
        return True, f"rolled to {rolled.name}"
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _daemon_log(name: str):
    """An append handle for one daemon's stdout+stderr, or None.

    Before this, `start()` passed stdout=DEVNULL and stderr=DEVNULL. PM2 used to
    capture those streams; PM2 is no longer the supervisor, so a daemon that
    dies on boot — a SyntaxError, a missing env var, an import that raises —
    produced NOTHING anywhere. The watchdog would start it, it would exit, and
    the next pass five minutes later would start it again, forever, with the
    fleet reading "0 down" in between passes because the timing hid it.

    This is a raw file handle given to a detached child, so no logging handler
    can rotate it in place. Startup rolls a stale oversized file, and the
    five-minute ``up`` pass safely stops, rolls and immediately restarts a
    healthy writer that crosses the limit. One rolled copy is retained, which
    keeps the first useful traceback without recreating PM2's log pile.
    """
    try:
        DAEMON_LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = DAEMON_LOG_DIR / f"daemon-{name}.log"
        rolled, detail = _roll_daemon_log(name)
        if not rolled:
            _log(f"daemon log rollover deferred for {name}: {detail}")
        return open(path, "a", encoding="utf-8", errors="replace")
    except OSError:
        return None  # never block a start on a log file


def recent_starts(name: str, window_sec: int = CRASH_LOOP_WINDOW_SEC) -> int:
    """How many times this daemon has been started in the window.

    Turns an invisible crash loop into a number. The watchdog already recorded
    every start; nothing ever read them back, so a daemon dying and being
    restarted every five minutes looked identical to one that had been up all
    day."""
    if not LOG.exists():
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - window_sec
    needle = f"started {name}"
    count = 0
    try:
        for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-2000:]:
            if needle not in line:
                continue
            try:
                rec = json.loads(line)
                ts = datetime.fromisoformat(str(rec.get("ts", "")).replace("Z", "+00:00"))
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
            if ts.timestamp() >= cutoff:
                count += 1
    except OSError:
        return 0
    return count


def start(app: dict, dry: bool = False) -> tuple[bool, str]:
    if app.get("unrunnable"):
        return False, app["unrunnable"]
    cmd: list[str] = []
    interp = app["interp"] or ""
    script = app["script"] or ""
    if not interp or interp.lower() in ("none", ""):
        # PM2 infers the interpreter from the extension; we do not inherit that,
        # so a .js app declared without one was handed to CreateProcess as the
        # executable itself: "OSError [WinError 193] %1 is not a valid Win32
        # application". maven-telegram declares no interpreter and is node.
        if script.lower().endswith(".js"):
            interp = "node"
        elif script.lower().endswith(".py"):
            interp = sys.executable
    if interp and interp.lower() not in ("none", ""):
        cmd.append(interp)
        # Node's bundled CA set does not include the local Windows trust chain
        # used on this host. Keep verification ON, but make every supervised
        # Node daemon use the OS certificate store. This launch boundary covers
        # Bravo, coordination and sibling Telegram bridges without teaching
        # each application a different TLS workaround.
        if Path(interp.strip('"')).name.lower() in ("node", "node.exe"):
            cmd.append("--use-system-ca")
    if script:
        cmd.append(script)
    cmd.extend(str(a) for a in app["args"])
    if not cmd:
        return False, "no launchable command"
    if dry:
        return True, "DRY: " + " ".join(cmd)
    prior = recent_starts(app["name"])
    sink = _daemon_log(app["name"])
    try:
        # stdin=DEVNULL for the same reason stdout and stderr are redirected:
        # this watchdog runs under pythonw with no console, so an inherited
        # stdin handle does not exist. A child that touches it can die at
        # interpreter startup with 0xC0000008 STATUS_INVALID_HANDLE and no
        # output at all — and these children are long-lived daemons, so the
        # failure looks like a crash loop rather than a bad spawn. See
        # lib/subprocess_helpers._default_stdin_devnull.
        # An adopted app's env block (see manifest) is laid OVER the inherited
        # environment, never in place of it: the child still needs PATH, the
        # user profile and EMPIRE_DATA_BACKEND from the Task Scheduler session.
        # Every other row passes env=None and inherits exactly as before.
        env = app.get("env")
        child_env = ({**os.environ, **{str(k): str(v) for k, v in env.items()
                                       if v is not None}} if env else None)
        subprocess.Popen(cmd, cwd=app["cwd"] or str(PROJECT_ROOT),
                         env=child_env,
                         stdin=subprocess.DEVNULL,
                         stdout=sink or subprocess.DEVNULL,
                         stderr=subprocess.STDOUT if sink else subprocess.DEVNULL,
                         creationflags=_NO_WINDOW | DETACHED, close_fds=True)
        note = ""
        if prior + 1 >= CRASH_LOOP_STARTS:
            note = (f" [CRASH LOOP: {prior + 1} starts in "
                    f"{CRASH_LOOP_WINDOW_SEC // 60}m — see "
                    f"state/logs/daemon-{app['name']}.log]")
            # States the COUNT, not a diagnosis. An operator restarting a
            # daemon three times while deploying is indistinguishable from a
            # crash loop at this layer, and a warning that asserts the wrong
            # cause is how a real alert gets ignored. The count is the fact;
            # the log named here is where the cause is.
            print(f"WARNING: {app['name']} has been started {prior + 1} times in "
                  f"the last {CRASH_LOOP_WINDOW_SEC // 60} minutes. If that was "
                  f"not you, it is dying rather than running — its output is in "
                  f"state/logs/daemon-{app['name']}.log", file=sys.stderr)
        _log(f"started {app['name']}: {' '.join(cmd)}{note}")
        return True, " ".join(cmd) + note
    except Exception as e:  # noqa: BLE001
        _log(f"FAILED to start {app['name']}: {type(e).__name__}: {e}")
        return False, f"{type(e).__name__}: {e}"
    finally:
        # The child holds its own duplicate of the handle. Keeping the parent's
        # copy open would leave this short-lived process pinning the file, which
        # is what makes the next rotation fail with a sharing violation.
        if sink is not None:
            try:
                sink.close()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Stopping a daemon. Added 2026-09-02.
#
# `disable` only ever wrote a name into fleet_disabled.json. Nothing killed the
# process, so the dashboard's Stop button marked a daemon disabled and left it
# running — and the operator, reading a stopped tile over a live process, got
# the same false report this whole surface exists to remove.
#
# The PID match REUSES _row_runs. The file already carries the scar of two
# copies of "is this row my daemon" drifting apart (see status()); a kill path
# with its own private matcher is how you eventually kill the wrong process.
# ---------------------------------------------------------------------------


def _table_pid_rows(table: str) -> list[tuple[int, str]]:
    """(pid, command line) per process, with _table_rows' continuation rule.

    Same folding as _table_rows — a command line containing newlines is ONE
    process — but the PID is kept instead of stripped, because a kill needs it.
    """
    return [
        (row["pid"], row["cmdline"])
        for row in _table_process_rows(table)
        if row.get("pid") is not None
    ]


def pids_for(ident: str, *, other_idents: "Sequence[str]" = ()) -> list[int]:
    """Independent root PIDs executing this daemon's script/module.

    A Windows venv launcher and the interpreter it starts both show the same
    command line. Returning both made stop issue redundant taskkills; more
    importantly, counting both would call every Python daemon a duplicate.
    Parent relationships collapse that pair while preserving truly separate
    roots.

    Raises ProcessTableUnreadable rather than returning [] on no evidence: an
    empty list here would read as "already stopped" and silently succeed.

    `other_idents` is every OTHER daemon's identity. A PID one of them claims by
    full path is not ours, however well it matches our basename — this is the
    only thing standing between a Stop on bravo-telegram and a taskkill of
    Maven's bridge. Callers that omit it get the old, unarbitrated behaviour, so
    it is passed explicitly by stop().
    """
    table = _process_table()
    if not table:
        raise ProcessTableUnreadable(
            "could not read the process table — refusing to report a daemon "
            "as stopped without seeing the process list")
    matches = _matching_process_rows(table, ident, other_idents=other_idents)
    return [
        row["pid"] for row in _root_process_rows(matches)
        if row.get("pid") is not None
    ]


def stop(app: dict) -> tuple[bool, str]:
    """Kill every process running this daemon. /T takes the tree, because a
    .venv launcher stub re-execs the real interpreter as a child — killing only
    the parent leaves the daemon alive and orphaned."""
    ident = _identity(app)
    # Ownership arbitration BEFORE any taskkill: a PID another daemon claims by
    # full path is not ours to kill. See _claimed_elsewhere.
    others = _other_idents(app["name"])
    try:
        pids = pids_for(ident, other_idents=others)
    except ProcessTableUnreadable as exc:
        return False, str(exc)
    if not pids:
        return True, "already stopped"
    # Judge the OUTCOME, not taskkill's exit code. /T kills the whole tree, so
    # a daemon's second PID (the .venv launcher stub re-execs the real
    # interpreter) is usually ALREADY GONE by the time its own taskkill runs —
    # which exits non-zero for "process not found". Trusting exit codes here
    # reported a successful stop as a failure, and `restart` then aborted
    # before starting again, leaving the daemon down. Verified live 2026-09-02.
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, text=True, timeout=30,
                           creationflags=_NO_WINDOW)
        except Exception as exc:  # noqa: BLE001
            _log(f"stop {app['name']}: taskkill {pid} raised {exc}")
    # The kill is asynchronous; give the OS a moment to reap before asking.
    for _ in range(10):
        time.sleep(0.3)
        try:
            remaining = pids_for(ident, other_idents=others)
        except ProcessTableUnreadable:
            continue
        if not remaining:
            _log(f"stopped {app['name']} (pids {pids})")
            return True, f"stopped (was {pids})"
    return False, f"still running after kill: {remaining}"


def _write_disabled(off: set) -> None:
    """Single writer for fleet_disabled.json — start/stop and enable/disable
    both mutate it, and two inline copies of the write would drift."""
    DISABLED.parent.mkdir(parents=True, exist_ok=True)
    DISABLED.write_text(json.dumps(sorted(off), indent=2), encoding="utf-8")


def _app_by_name(name: str) -> dict | None:
    for row in status():
        if row["name"] == name:
            return row
    return None


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
            # Ask whether the holder is alive rather than only waiting out the
            # clock (2026-09-02). This lock records its holder's pid and never
            # asked about it, so a pass killed mid-run stopped ALL supervision
            # for up to LOCK_STALE_SEC — two skipped passes at a 5-minute
            # cadence, during which any daemon that died stayed dead. The same
            # defect was found idling the Instagram poller on a lock whose
            # holder had been gone the whole time.
            #
            # The age fence stays: pid_is_gone fails closed on anything it
            # cannot answer, and only elapsed time catches a recycled pid.
            # Imported HERE, not at module scope. This file is the supervisor;
            # nothing about a helper module may be able to stop it running, and
            # it is invoked both as a script (sys.path[0] = scripts/ops) and as
            # an import from callers that already have scripts/ on the path.
            # A failure to import simply leaves the age fence in charge.
            holder_dead = False
            try:
                sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
                from lib.subprocess_helpers import pid_is_gone  # noqa: PLC0415

                holder_dead = pid_is_gone(int(RUN_LOCK.read_text(encoding="utf-8").strip()))
            except (OSError, ValueError, ImportError):
                pass  # unreadable holder or missing helper — the age fence decides
            if age > LOCK_STALE_SEC or holder_dead:
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


def _configure_console_encoding() -> None:
    """Keep diagnostic/log output from crashing on Windows' cp1252 console."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, TypeError, ValueError):
            # Captured/test streams may expose but reject reconfiguration. The
            # command still works for ASCII output, and read_daemon_log itself
            # already decodes malformed log bytes with replacement.
            pass


def main() -> int:
    _configure_console_encoding()
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("status"); ps.add_argument("--json", action="store_true")
    pl = sub.add_parser("logs"); pl.add_argument("name")
    pl.add_argument("--lines", type=int, default=60)
    pu = sub.add_parser("up")
    pu.add_argument("--only"); pu.add_argument("--dry-run", action="store_true")
    pu.add_argument("--json", action="store_true")
    plc = sub.add_parser("lifecycle")
    plc.add_argument("--json", action="store_true")
    ple = sub.add_parser("lease")
    ple.add_argument("name")
    ple.add_argument("--minutes", type=int, required=True)
    ple.add_argument("--reason", required=True)
    prl = sub.add_parser("release-lease")
    prl.add_argument("name")
    pd = sub.add_parser("disable"); pd.add_argument("name")
    pe = sub.add_parser("enable"); pe.add_argument("name")
    # One verb per dashboard button. The UI used to shell `pm2 <action>`, which
    # EPERMs on this machine AND leaks an orphan god daemon per click.
    pst = sub.add_parser("start"); pst.add_argument("name")
    psp = sub.add_parser("stop"); psp.add_argument("name")
    prs = sub.add_parser("restart"); prs.add_argument("name")
    sub.add_parser("install-task")
    a = p.parse_args()

    # A Session-0 supervisor cannot see the user-session fleet and would start a
    # duplicate of every daemon. Only block the MUTATING pass — `status` from
    # session 0 is merely uninformative, but `up` from session 0 is destructive.
    if a.cmd in ("up", "start", "restart"):
        session = _windows_session_id()
        if session == 0:
            msg = ("REFUSING to supervise from Windows Session 0 — a session-0 "
                   "process cannot see session-1 daemons, so every one of them "
                   "would look absent and be started again as an invisible "
                   "duplicate. Set this task's principal to Interactive.")
            _log(f"ABORTED: {msg}")
            print(f"ABORTED: {msg}", file=sys.stderr)
            return 1

    # Every action that can launch or reconcile a daemon shares one lock;
    # read-only status must stay callable from health checks that depend on it.
    lock_commands = {"up", "start", "restart", "lease", "release-lease"}
    if a.cmd in lock_commands and not _acquire_run_lock():
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
        if a.cmd in lock_commands:
            _release_run_lock()


def _dispatch(a) -> int:
    if a.cmd == "logs":
        try:
            content = read_daemon_log(a.name, a.lines)
        except (OSError, ValueError) as exc:
            print(f"cannot read daemon log: {exc}", file=sys.stderr)
            return 2
        if content is None:
            print(f"no watchdog log for {a.name}", file=sys.stderr)
            return 1
        if content:
            print(content)
        return 0

    if a.cmd == "lifecycle":
        leases = _read_leases()
        rows = [{
            "name": row["name"],
            "mode": row.get("lifecycle"),
            "reason": row.get("lifecycle_reason"),
            "owner": row.get("lifecycle_owner"),
            "lease": leases.get(row["name"]),
            "lease_active": lease_active(row["name"]),
            "unrunnable": row.get("unrunnable") or "",
        } for row in manifest()]
        if a.json:
            print(json.dumps(rows, indent=2, default=str))
        else:
            for row in rows:
                lease = " active lease" if row["lease_active"] else ""
                print(
                    f"  {row['name']:<30} {row['mode']:<12}{lease}  "
                    f"{row['reason']}"
                )
        return 1 if any(row["mode"] == "unclassified" for row in rows) else 0

    if a.cmd == "lease":
        ok, detail = grant_lease(
            a.name, minutes=a.minutes, reason=a.reason
        )
        print(f"lease {a.name}: {detail}")
        return 0 if ok else 1

    if a.cmd == "release-lease":
        ok, detail = release_lease(a.name)
        print(f"release-lease {a.name}: {detail}")
        return 0 if ok else 1

    if a.cmd == "status":
        rows = status()
        if a.json:
            print(json.dumps(rows, indent=2, default=str)); return 0
        states = {r["name"]: classify(r) for r in rows}
        unhealthy = [
            r for r in rows if states[r["name"]] in {"down", "duplicate"}
        ]
        for r in rows:
            state = states[r["name"]].upper()
            print(f"  {str(r['name']):<22} {state:<11} {r['ident']}")
            if r.get("root_count"):
                print(
                    f"  {'':<22} -> {r['root_count']} root tree(s); "
                    f"roots={r.get('root_pids', [])}; pids={r.get('pids', [])}"
                )
            if r.get("unrunnable"):
                print(f"  {'':<22} -> {r['unrunnable']}")
        print(
            f"\n{len(unhealthy)} of {len(rows)} unhealthy "
            "(down or duplicate; excluding disabled/unrunnable)"
        )
        return 1 if unhealthy else 0

    if a.cmd == "up":
        rows = status()
        started, stopped, reconciled, failed = [], [], [], []
        for r in rows:
            if r["disabled"]:
                continue
            if a.only and r["name"] != a.only:
                continue
            state = classify(r)
            if r.get("lifecycle") == "on_demand" and not lease_active(r["name"]):
                if state in {"running", "duplicate"}:
                    if a.dry_run:
                        stopped.append((r["name"], "DRY: stop after lease expiry"))
                    else:
                        ok, detail = stop(r)
                        (stopped if ok else failed).append((r["name"], detail))
                continue
            if state == "duplicate":
                roots = r.get("root_pids") or []
                if a.dry_run:
                    reconciled.append((
                        r["name"],
                        f"DRY: stop roots {roots}, then start exactly one",
                    ))
                    continue
                stopped_ok, stopped_detail = stop(r)
                if not stopped_ok:
                    failed.append((
                        r["name"], f"duplicate cleanup failed: {stopped_detail}",
                    ))
                    continue
                started_ok, started_detail = start(r)
                if started_ok:
                    reconciled.append((
                        r["name"],
                        f"{stopped_detail}; started one ({started_detail})",
                    ))
                else:
                    failed.append((
                        r["name"],
                        f"duplicates stopped but restart failed: {started_detail}",
                    ))
                continue
            if state == "running" and _daemon_log_needs_rollover(r["name"]):
                if a.dry_run:
                    reconciled.append((
                        r["name"],
                        "DRY: supervised restart to rotate oversized daemon log",
                    ))
                    continue
                stopped_ok, stopped_detail = stop(r)
                if not stopped_ok:
                    failed.append((
                        r["name"],
                        f"log rotation could not stop daemon: {stopped_detail}",
                    ))
                    continue
                rolled_ok, rolled_detail = _roll_daemon_log(r["name"])
                started_ok, started_detail = start(r)
                # start() retries the same safe rollover before opening the new
                # output handle. A transient reader may therefore release the
                # file between the explicit attempt and restart.
                rolled_ok = rolled_ok or not _daemon_log_needs_rollover(r["name"])
                if rolled_ok and started_ok:
                    reconciled.append((
                        r["name"],
                        f"rotated log via supervised restart ({rolled_detail}; "
                        f"{started_detail})",
                    ))
                elif started_ok:
                    failed.append((
                        r["name"],
                        f"daemon restored but log rotation failed: {rolled_detail}",
                    ))
                else:
                    failed.append((
                        r["name"],
                        f"log rotation stopped daemon but restart failed: "
                        f"{started_detail}",
                    ))
                continue
            if state in {"running", "unrunnable"}:
                continue
            ok, detail = start(r, dry=a.dry_run)
            (started if ok else failed).append((r["name"], detail))
        for n, d in started:
            print(f"  started {n}  ({d})")
        for n, d in stopped:
            print(f"  stopped {n}  ({d})")
        for n, d in reconciled:
            print(f"  reconciled {n}  ({d})")
        for n, d in failed:
            print(f"  FAILED  {n}  ({d})", file=sys.stderr)
        if not started and not stopped and not reconciled and not failed:
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
             f"{len(stopped)} lease-stopped, {len(reconciled)} reconciled, "
             f"{len(failed)} failed, "
             f"{sum(1 for r in rows if r['disabled'])} disabled")
        return 1 if failed else 0

    if a.cmd in ("start", "stop", "restart"):
        app = _app_by_name(a.name)
        if app is None:
            print(f"unknown daemon: {a.name}", file=sys.stderr)
            return 2
        if (a.cmd in {"start", "restart"}
                and app.get("lifecycle") == "on_demand"
                and not lease_active(a.name)):
            print(
                f"{a.name} requires an active lease; use: fleet_watchdog.py "
                f"lease {a.name} --minutes <n> --reason <why>",
                file=sys.stderr,
            )
            return 2
        off = disabled_names()
        if a.cmd == "stop":
            # Disable FIRST. Killing without disabling just hands the daemon to
            # the next 5-minute pass, which restarts it — a Stop button whose
            # effect expires in under five minutes is not a stop.
            off.add(a.name)
            _write_disabled(off)
            ok, detail = stop(app)
        elif a.cmd == "start":
            # Enable FIRST: `up` skips disabled rows, so a Start on a stopped
            # daemon would report success and do nothing.
            off.discard(a.name)
            _write_disabled(off)
            fresh = _app_by_name(a.name) or app
            if classify(fresh) == "duplicate":
                ok, detail = stop(fresh)
                if ok:
                    ok, detail = start(fresh)
            elif fresh.get("running"):
                # `up` has always skipped running apps; this verb did not, so a
                # dashboard Start on a healthy daemon — or a click racing the
                # 5-minute pass — quietly produced a SECOND copy. Duplicate
                # daemons are how every cron in the empire once ran four times.
                ok, detail = True, "already running"
            else:
                ok, detail = start(fresh)
        else:  # restart — deliberately does NOT touch the disabled set
            if a.name in off:
                print(f"{a.name} is disabled; use start", file=sys.stderr)
                return 2
            ok, detail = stop(app)
            if ok:
                ok, detail = start(_app_by_name(a.name) or app)
        print(f"{a.cmd} {a.name}: {detail}")
        _log(f"{a.cmd} {a.name}: {detail} (ok={ok})")
        return 0 if ok else 1

    if a.cmd in ("disable", "enable"):
        off = disabled_names()
        off.add(a.name) if a.cmd == "disable" else off.discard(a.name)
        _write_disabled(off)
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
