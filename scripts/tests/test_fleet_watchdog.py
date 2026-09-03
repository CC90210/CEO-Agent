"""Tests for the fleet watchdog and the parity check that reports on it.

Every assertion here corresponds to something that actually went wrong on
2026-08-28, when the coordination bridge was found dead for two days while
`machine_parity` reported GREEN — at parity.

None of these behaviours had a test. The health check that is supposed to be the
fleet's early warning was itself unpinned, which is why it could drift into
lying without anything noticing.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from ops import fleet_watchdog as fw  # noqa: E402


# ---------------------------------------------------------------- identity ---

def test_identity_never_resolves_to_a_bare_interpreter():
    """`pythonw.exe` appears in dozens of unrelated command lines. Matching on it
    reports every daemon as UP — the naive check did exactly that and produced
    four false UPs while those daemons were dead."""
    app = {"name": "x", "script": r"C:\repo\.venv\Scripts\pythonw.exe",
           "args": ["-m", "bravo_cli.bridge_chat_server"], "interp": ""}
    ident = fw._identity(app)
    assert ident == "bravo_cli.bridge_chat_server"
    assert "pythonw" not in ident


def test_identity_uses_the_script_when_there_is_one():
    app = {"name": "bravo-scheduler", "script": "scripts/scheduler.py",
           "args": [], "interp": "pythonw.exe"}
    assert fw._identity(app) == "scheduler.py"


# ------------------------------------------------------------- unrunnable ---

def test_entry_without_a_target_is_flagged_not_launched(monkeypatch, tmp_path):
    """breeze-live-watch records args ['loop','--interval','300'] and NO script,
    so a naive build runs `pythonw.exe loop --interval 300` — executing a file
    called `loop`. Skipping it silently would be worse: the operator would
    believe it was supervised."""
    dump = tmp_path / "dump.pm2"
    dump.write_text(json.dumps([{
        "name": "breeze-live-watch", "script": None,
        "args": ["loop", "--interval", "300"],
        "exec_interpreter": "pythonw.exe", "cwd": str(REPO_ROOT),
    }]), encoding="utf-8")
    monkeypatch.setattr(fw, "DUMP", dump)
    monkeypatch.setattr(fw, "_ecosystem_apps", lambda *a, **k: {})
    # Siblings are declared in SIBLING_APPS, not in dump.pm2, so manifest()
    # returns them alongside this fixture's single local app (2026-09-02).
    # Pinning a total count here would only assert how many sibling agents CC
    # happens to run today; the behaviour under test is that a targetless entry
    # is FLAGGED rather than dropped or launched.
    monkeypatch.setattr(fw, "_sibling_manifest", lambda: [])
    entries = fw.manifest()
    assert len(entries) == 1
    assert entries[0]["unrunnable"], "must be flagged, not silently dropped"
    ok, detail = fw.start(entries[0], dry=True)
    assert ok is False, "an unrunnable entry must never be launched"
    assert "no script" in detail


def test_committed_spec_beats_machine_state(monkeypatch, tmp_path):
    """dump.pm2 says WHAT ran; ecosystem.config.js says HOW to run it and is more
    complete — it recovered bravo-ig-dm, which the dump stored with no script."""
    dump = tmp_path / "dump.pm2"
    dump.write_text(json.dumps([{
        "name": "bravo-ig-dm", "script": None, "args": None,
        "exec_interpreter": "pythonw.exe", "cwd": str(REPO_ROOT),
    }]), encoding="utf-8")
    monkeypatch.setattr(fw, "DUMP", dump)
    monkeypatch.setattr(fw, "_ecosystem_apps", lambda *a, **k: {
        "bravo-ig-dm": {"name": "bravo-ig-dm",
                        "script": "scripts/integrations/ig_dm_daemon.py",
                        "args": None, "interp": "pythonw.exe"}})
    entries = fw.manifest()
    assert entries[0]["script"].endswith("ig_dm_daemon.py")
    assert not entries[0]["unrunnable"]


# ---------------------------------------------------------------- siblings ---
# Added 2026-09-02. PM2 was retired on 08-27 and this watchdog replaced it only
# for Business-Empire-Agent, so Atlas's and Maven's Telegram bridges had NO
# supervisor at all and were simply dead — while the Command Center's worker
# board rendered them "Down — stopped reporting", which reads like a heartbeat
# problem rather than "nothing is running this".

def test_two_daemons_sharing_a_script_name_are_told_apart():
    """Bravo's bridge and Maven's are BOTH telegram_agent.js, in different
    repos. On the first run after Maven was adopted the watchdog reported it UP
    while no such process existed — it was matching Bravo's. A supervisor that
    reads one daemon's process as another's never starts the dead one."""
    bravo = {"name": "bravo-telegram", "script": "telegram_agent.js",
             "args": [], "interp": "node"}
    maven = {"name": "maven-telegram",
             "script": r"C:\Users\User\CMO-Agent\telegram_agent.js",
             "args": [], "interp": "node"}
    b_id, m_id = fw._identity(bravo), fw._identity(maven)
    assert b_id != m_id, "a basename cannot separate two repos' telegram_agent.js"

    bravo_cmdline = "node telegram_agent.js"
    assert fw._row_runs(bravo_cmdline, b_id) is True
    assert fw._row_runs(bravo_cmdline, m_id) is False, (
        "Bravo's process must not satisfy Maven's identity")


# ------------------------------------------------- ownership arbitration ---
# 2026-09-03. The test above only ever asserted ONE direction. The other
# direction was true the whole time and nobody had asked: Bravo's basename
# ident 'telegram_agent.js' DOES match Maven's absolute command line, so
# pids_for("telegram_agent.js") returned Maven's PID and a Stop or Restart on
# bravo-telegram issued `taskkill /PID <maven> /T /F` against another agent's
# bridge. Only bravo-telegram went into fleet_disabled.json, so the next pass
# revived Maven and nothing in any log tied the outage to the click.
#
# Verified live before and after the fix, against the real process table:
#   bravo-telegram  pids without arbitration [18404, 40180] -> with [18404]
#   maven-telegram  pids [40180] either way
MAVEN_CMDLINE = r"node c:\users\user\cmo-agent\telegram_agent.js"
BRAVO_CMDLINE = "node telegram_agent.js"
BRAVO_ID = "telegram_agent.js"
MAVEN_ID = "c:/users/user/cmo-agent/telegram_agent.js"


def test_the_basename_fallback_really_does_match_the_siblings_process():
    """The premise. If this ever stops being true the fix below is dead code
    and the test that guards it would pass for the wrong reason."""
    assert fw._row_runs(MAVEN_CMDLINE, BRAVO_ID) is True


def test_a_sibling_full_path_claim_outranks_our_basename_match():
    """Maven's process is Maven's, however well it matches our basename."""
    assert fw._claimed_elsewhere(MAVEN_CMDLINE, BRAVO_ID, [MAVEN_ID]) is True


def test_our_own_process_is_never_claimed_away():
    """Bravo's relative command line is matched by nobody else, so it stays
    ours — the fix must not make a live daemon read as someone else's."""
    assert fw._claimed_elsewhere(BRAVO_CMDLINE, BRAVO_ID, [MAVEN_ID]) is False
    assert fw._row_runs(BRAVO_CMDLINE, BRAVO_ID) is True


def test_an_exact_claim_of_our_own_outranks_everything():
    """A daemon whose ident IS the full path keeps its process even when some
    other entry also names it."""
    assert fw._claimed_elsewhere(MAVEN_CMDLINE, MAVEN_ID, [BRAVO_ID, MAVEN_ID]) is False


def test_arbitration_is_not_the_absolute_ident_shortcut():
    """Why the fix is arbitration and not 'make every ident absolute'.

    This repo's own command lines are RELATIVE (`node telegram_agent.js`). An
    absolute ident matches neither spelling, so every local daemon would read
    DOWN and the watchdog would start a duplicate of the entire fleet — the
    failure _identity's docstring already records once.
    """
    absolute_bravo = "c:/users/user/business-empire-agent/telegram_agent.js"
    assert fw._row_runs(BRAVO_CMDLINE, absolute_bravo) is False


def test_row_runs_exact_refuses_the_basename_fallback():
    assert fw._row_runs_exact(MAVEN_CMDLINE, MAVEN_ID) is True
    assert fw._row_runs_exact(MAVEN_CMDLINE, BRAVO_ID) is False
    assert fw._row_runs_exact("", MAVEN_ID) is False
    assert fw._row_runs_exact(MAVEN_CMDLINE, "") is False


def test_other_idents_excludes_the_app_itself():
    apps = [{"name": "bravo-telegram", "script": "telegram_agent.js",
             "args": [], "interp": "node"},
            {"name": "maven-telegram",
             "script": r"C:\Users\User\CMO-Agent\telegram_agent.js",
             "args": [], "interp": "node"}]
    others = fw._other_idents("bravo-telegram", apps)
    assert others == [MAVEN_ID]
    assert BRAVO_ID not in others, "an app must never arbitrate against itself"


def test_stop_arbitrates_before_it_kills():
    """Source-level, because the kill is a taskkill: the arbitration must
    happen BEFORE pids_for feeds a /T /F, not after."""
    src = (REPO_ROOT / "scripts" / "ops" / "fleet_watchdog.py").read_text(encoding="utf-8")
    body = src[src.index("def stop(app: dict)"):]
    body = body[: body.index("\ndef ", 1)]
    # Anchor on the CALL, not the word: stop()'s comments say "taskkill" too,
    # and slicing at prose silently cut the assertion's search window down to
    # nothing — a test that passes on an empty haystack proves nothing.
    kill_at = body.index('"taskkill"')
    before_the_kill = body[:kill_at]
    assert "_other_idents(" in before_the_kill, (
        "stop() must resolve the other daemons' identities before killing")
    assert "pids_for(ident, other_idents=others)" in before_the_kill, (
        "the kill list must be the ARBITRATED one")


def test_a_full_path_identity_survives_windows_backslashes():
    """The ident is stored slash-normalised; Windows reports command lines with
    backslashes. Before both sides were normalised, atlas-telegram read DOWN
    with its own PID plainly visible in the process table."""
    app = {"name": "atlas-telegram",
           "script": r"C:\Users\User\APPS\CFO-Agent\telegram_app\bot.py",
           "args": [], "interp": "python.exe"}
    ident = fw._identity(app)
    cmdline = r"c:\users\user\appdata\local\programs\python\python312\python.exe c:\users\user\apps\cfo-agent\telegram_app\bot.py"
    assert fw._row_runs(cmdline, ident) is True


def test_an_interpreter_path_is_still_never_the_identity():
    """The absolute-path branch must not fire for `pythonw -m module`. When it
    did, claude-bridge and claude-bridge-ping — both alive — read DOWN, which
    would have started a duplicate of each."""
    app = {"name": "claude-bridge",
           "script": r"C:\repo\.venv\Scripts\pythonw.exe",
           "args": ["-m", "bravo_cli.bridge_chat_server"], "interp": ""}
    assert fw._identity(app) == "bravo_cli.bridge_chat_server"


def test_a_sibling_without_its_repo_is_unrunnable_not_invisible(monkeypatch, tmp_path):
    """Silence would put it back in the state this feature exists to end: no
    process, and nothing saying so."""
    monkeypatch.setattr(fw, "SIBLING_APPS",
                        {"ghost-agent": (tmp_path / "nope", "ghost-agent")})
    rows = fw._sibling_manifest()
    assert len(rows) == 1
    assert rows[0]["name"] == "ghost-agent"
    assert rows[0]["unrunnable"], "a missing sibling must be reported, not dropped"


# --------------------------------------------------------------- disabled ---

def test_an_operator_stop_must_stick(monkeypatch, tmp_path):
    """A `disable` that silently reverses within five minutes is worse than a
    daemon being down, because it is invisible. bravo-ig-dm sends Instagram DMs;
    an unwanted restart is an outward effect."""
    disabled = tmp_path / "fleet_disabled.json"
    disabled.write_text(json.dumps(["bravo-ig-dm"]), encoding="utf-8")
    monkeypatch.setattr(fw, "DISABLED", disabled)
    assert "bravo-ig-dm" in fw.disabled_names()


# -------------------------------------------------- parity check behaviour ---

def _parity():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import machine_parity
    return machine_parity


def test_parity_does_not_invoke_pm2_when_no_daemon_is_alive(monkeypatch):
    """Calling pm2 against a blocked pipe SPAWNS an orphan daemon; 23 accumulated
    that way, several from health checks. A health check that worsens what it
    measures is not a health check."""
    mp = _parity()
    calls: list[list[str]] = []
    real_run = mp.subprocess.run

    def spy(cmd, *a, **k):
        if isinstance(cmd, list) and cmd and cmd[0] == "pm2":
            calls.append(cmd)
        return real_run(cmd, *a, **k)

    monkeypatch.setattr(mp, "_pm2_daemon_alive", lambda: False)
    monkeypatch.setattr(mp.subprocess, "run", spy)
    mp.check_tls_keylog()
    assert calls == [], f"pm2 was invoked with no daemon alive: {calls}"


def test_daemon_detector_does_not_match_its_own_invocation(monkeypatch):
    """The first version substring-searched the whole process table, so any
    command that merely MENTIONED the daemon path — a grep, a filter, the
    diagnostic asking the question — matched. It returned True with zero daemons
    running, the guard fell through, and it leaked the daemon it existed to
    prevent. A detector that matches its own invocation is measuring itself."""
    mp = _parity()
    fake_table = (
        "commandline\n"
        r'wmic process where "commandline like \'%pm2\lib\daemon.js%\'" get name' "\n"
        "powershell -command get-process | where { $_.commandline -like '*pm2\\lib\\daemon.js*' }\n"
    )

    class R:
        stdout = fake_table
    monkeypatch.setattr(mp.subprocess, "run", lambda *a, **k: R())
    assert mp._pm2_daemon_alive() is False, (
        "matched a QUERY about the daemon rather than the daemon itself")


def test_daemon_detector_still_finds_a_real_daemon(monkeypatch):
    """Break the test before trusting it: the exclusion must not suppress a
    genuine daemon line."""
    mp = _parity()

    class R:
        stdout = ("commandline\n"
                  r'"c:\program files\nodejs\node.exe" c:\users\user\appdata\roaming\npm\node_modules\pm2\lib\daemon.js'
                  "\n")
    monkeypatch.setattr(mp.subprocess, "run", lambda *a, **k: R())
    assert mp._pm2_daemon_alive() is True


def test_parity_liveness_has_exactly_one_definition():
    """machine_parity must ASK fleet_watchdog rather than carry a second copy.

    They agreed on the day they were written, which is how this class hides —
    the fifth instance in this subsystem after two claim mechanisms, two
    coverage implementations, two ownership maps and two identity lists. The
    latent divergence was real: the watchdog honours an operator `disable` and
    the private copy did not, so a deliberate stop would have read as a parity
    FAILURE and trained the operator to ignore the check.
    """
    src = (REPO_ROOT / "scripts" / "machine_parity.py").read_text(encoding="utf-8")
    assert "from ops import fleet_watchdog" in src
    assert "fleet_watchdog.status()" in src


# ------------------------------------------------- unreadable process table ---
# Added 2026-08-28 after the SECOND incident that day. `_process_table()`
# returned "" on any failure, and `status()` tested `ident in table`, which is
# False for every daemon against an empty string. An unreadable table therefore
# read as "the entire fleet is dead" — and this watchdog's response to a dead
# fleet is to start the fleet, every five minutes from Task Scheduler.
#
# Found running side by side: four bravo-scheduler instances (started 21:26,
# 23:56, 00:01, 00:10) and duplicate event-routers, so every cron in the empire
# executed up to 4x — four concurrent inbound-email sweeps racing one mailbox,
# eight email_engine processes live at once, each classifying the same mail and
# each marking it \Seen. It also self-amplifies: duplicates raise load, load
# slows the table read, a slow read times out, and a timeout starts more
# duplicates.


@pytest.fixture
def restore_table():
    original = fw._process_table
    yield
    fw._process_table = original


def test_unreadable_table_raises_rather_than_reporting_down(restore_table):
    """If we cannot prove a daemon is down, we must not start one."""
    fw._process_table = lambda: None
    with pytest.raises(fw.ProcessTableUnreadable):
        fw.status()


def test_empty_table_raises_too(restore_table):
    """The original bug's exact shape. `table is None` alone lets "" through,
    so the guard has to be falsy-based, not None-based."""
    fw._process_table = lambda: ""
    with pytest.raises(fw.ProcessTableUnreadable):
        fw.status()


def test_valid_table_still_resolves_liveness(restore_table):
    fw._process_table = lambda: ("pythonw.exe c:/repo/scripts/scheduler.py\n"
                                 "node c:/repo/telegram_agent.js")
    running = {r["name"] for r in fw.status() if r["running"]}
    assert "bravo-scheduler" in running
    assert "bravo-telegram" in running


def test_daemon_absent_from_a_readable_table_is_down(restore_table):
    """Fail-closed must not become fail-useless: a genuinely absent daemon still
    has to report down, or the watchdog would never start anything again."""
    fw._process_table = lambda: "node c:/repo/telegram_agent.js"
    down = {r["name"] for r in fw.status() if not r["running"] and not r["disabled"]}
    assert "bravo-scheduler" in down


# ------------------------------------------------- liveness is not mention ---
# Added 2026-08-29 after the mirror-image incident. `status()` tested
# `ident in table` — a substring search across the WHOLE process table — so any
# command line that merely NAMED a daemon's script proved it alive. Observed
# live: bravo-scheduler was killed, `fleet_watchdog up` answered "nothing to
# start — everything up or disabled", and the scheduler stayed dead. The false
# evidence was this session's own diagnostic shell, whose command line quoted
# the string "scheduler.py".
#
# The two failure directions are not symmetric and both are represented below:
#   false NEGATIVE (says down while up)  -> starts a duplicate. Catastrophic;
#                                           this is the 4x-scheduler incident.
#   false POSITIVE (says up while down)  -> never restarts. This bug.
# So every case that a REAL daemon row must still satisfy is asserted too.

@pytest.mark.parametrize("cmdline,why", [
    ("/usr/bin/bash -c \"grep -n scheduler.py scripts/scheduler.py\"",
     "a shell whose argument quotes the path"),
    ("c:/python312/python.exe -c \"print('scripts/scheduler.py')\"",
     "inline code that mentions the path"),
    ("c:/python312/python.exe -m pyflakes scripts/scheduler.py",
     "a linter RUN AGAINST the script"),
    ("c:/python312/python.exe scripts/tail_scheduler.py",
     "a different script whose name merely ends with the identity"),
])
def test_mentioning_a_daemon_is_not_running_it(restore_table, cmdline, why):
    fw._process_table = lambda: f"|4242|{cmdline}\n|1|c:/repo/.venv/scripts/python.exe -m pytest"
    running = {r["name"] for r in fw.status() if r["running"]}
    assert "bravo-scheduler" not in running, f"{why} counted as the daemon running"


@pytest.mark.parametrize("cmdline", [
    "|900|c:/repo/.venv/scripts/pythonw.exe scripts/scheduler.py",
    '|900|"c:/users/user/appdata/local/programs/python/python312/pythonw.exe" scripts/scheduler.py',
    "|900|pythonw.exe c:/repo/scripts/scheduler.py",
])
def test_the_real_daemon_row_still_reads_as_running(restore_table, cmdline):
    """Recall must not regress: a false negative starts a SECOND scheduler."""
    fw._process_table = lambda: cmdline
    running = {r["name"] for r in fw.status() if r["running"]}
    assert "bravo-scheduler" in running


def test_module_launched_daemons_still_resolve(restore_table):
    """`pythonw -m bravo_cli.bridge_chat_server` has no script path at all —
    the identity is the -m module, and it must survive the same tightening."""
    fw._process_table = lambda: ('|901|"c:/repo/.venv/scripts/pythonw.exe" '
                                 '-m bravo_cli.bridge_chat_server')
    running = {r["name"] for r in fw.status() if r["running"]}
    assert "claude-bridge" in running
    assert "claude-bridge-ping" not in running, "sibling -m daemon must not alias"


def test_a_multiline_command_line_stays_one_process(restore_table):
    """A shell invoked with a heredoc carries newlines INSIDE its command line.
    Split naively, each fragment becomes a fake process — and a fragment that
    happens to start with the daemon's path is indistinguishable from the real
    row. Continuation lines must stay attached to the row that opened them."""
    fw._process_table = lambda: (
        "|55|/usr/bin/bash -c \"python - <<PY\n"
        "scripts/scheduler.py\n"
        "PY\"\n"
        "|56|c:/repo/.venv/scripts/python.exe -m pytest")
    assert len(fw._table_rows(fw._process_table())) == 2
    assert "bravo-scheduler" not in {r["name"] for r in fw.status() if r["running"]}


def test_real_process_table_can_see_python_processes():
    """Guards a near-miss. psutil is 5x faster than wmic and was tried as the
    source; on this machine it returns an EMPTY cmdline for 163 of 579
    processes, including every detached pythonw daemon this file supervises. It
    reported four running daemons as DOWN, which would have started a duplicate
    of each — the very duplication this module now guards against, caused by the
    fix for it. Any future swap of the source must still see live processes."""
    table = fw._process_table()
    if table is None:
        pytest.skip("process table unreadable in this environment")
    assert "python" in table, "process-table source cannot see python processes"


# -------------------------------------------------------------- run lock ---

def test_run_lock_is_exclusive(tmp_path, monkeypatch):
    """Two overlapping passes each seeing a daemon down, and each starting one,
    is the other half of how four schedulers came to exist. The Task Scheduler
    fires this every 5 minutes; a pass can take longer than that."""
    monkeypatch.setattr(fw, "RUN_LOCK", tmp_path / "wd.lock")
    assert fw._acquire_run_lock() is True
    assert fw._acquire_run_lock() is False, "second concurrent pass must be refused"
    fw._release_run_lock()
    assert fw._acquire_run_lock() is True, "lock must be reusable after release"
    fw._release_run_lock()


def test_stale_lock_is_reclaimed(tmp_path, monkeypatch):
    """A pass killed mid-run must not disable supervision forever.

    Ages the lock file rather than setting the threshold to 0: a lock written
    microseconds ago is legitimately NOT older than zero seconds, so that
    version tested a degenerate boundary instead of the real condition (a lock
    left behind by a process that died some time ago).
    """
    import os as _os
    lock = tmp_path / "wd.lock"
    monkeypatch.setattr(fw, "RUN_LOCK", lock)
    lock.write_text("99999")
    stale = time.time() - (fw.LOCK_STALE_SEC + 60)
    _os.utime(lock, (stale, stale))
    assert fw._acquire_run_lock() is True, "a stale lock must be reclaimable"
    fw._release_run_lock()


def test_fresh_lock_is_not_reclaimed(tmp_path, monkeypatch):
    """The other half: a lock held by a pass that is genuinely still running
    must be respected, or the staleness escape hatch defeats the lock.

    The holder must be a REAL live pid (2026-09-02). This wrote 99999 — a pid
    that does not exist — and passed only because the lock was age-only: it was
    asserting "recent" while its docstring claimed "still running", and the two
    stopped being the same thing the moment liveness was checked. A fixture
    that cannot express the behaviour it names is not testing it.
    """
    import os as _os
    lock = tmp_path / "wd.lock"
    monkeypatch.setattr(fw, "RUN_LOCK", lock)
    lock.write_text(str(_os.getppid()))  # the shell that launched pytest
    assert fw._acquire_run_lock() is False, "a live holder's lock must be honoured"


def test_fresh_lock_whose_holder_died_is_reclaimed(tmp_path, monkeypatch):
    """A pass killed mid-run must not stop supervision until the age fence
    expires. At a 5-minute cadence and LOCK_STALE_SEC of 600 that is two
    skipped passes, and any daemon that dies inside the window stays dead.

    Verified live on the sibling case: the Instagram poller sat logging
    "another poll holds the lock" every 20s against a holder that had been gone
    the whole time.
    """
    lock = tmp_path / "wd.lock"
    monkeypatch.setattr(fw, "RUN_LOCK", lock)
    lock.write_text("999999")  # never existed in this boot
    assert fw._acquire_run_lock() is True, "a dead holder must not hold the fleet"
    fw._release_run_lock()


def test_an_unreadable_holder_falls_back_to_the_age_fence(tmp_path, monkeypatch):
    """Garbage in the lock must not read as 'dead'. Failing open here would
    let two passes start the fleet at once, which is how four schedulers came
    to exist."""
    lock = tmp_path / "wd.lock"
    monkeypatch.setattr(fw, "RUN_LOCK", lock)
    lock.write_text("not-a-pid")
    assert fw._acquire_run_lock() is False, "an unreadable holder is not a dead one"


# ------------------------------------------------ one definition of state ---
# Added after a self-review found that fixing the pm2 probes had created FIVE
# hand-rolled predicates for "is this daemon a problem?" — in harness_eval,
# cron_health_check, dashboard_email_queue_monitor, local_bridge and
# machine_parity — and they disagreed. Some treated an operator-disabled daemon
# as an outage; some folded an unrunnable manifest entry into "down", which pins
# an alert permanently red. This subsystem has form: see
# test_parity_liveness_has_exactly_one_definition above, whose docstring calls
# the two-definitions problem "the fifth instance in this subsystem".


@pytest.mark.parametrize("row,expected", [
    ({"disabled": True, "running": False, "unrunnable": ""}, "disabled"),
    ({"disabled": True, "running": True, "unrunnable": ""}, "disabled"),
    ({"disabled": False, "running": True, "unrunnable": ""}, "running"),
    ({"disabled": False, "running": False, "unrunnable": "no script"}, "unrunnable"),
    ({"disabled": False, "running": False, "unrunnable": ""}, "down"),
])
def test_classify_covers_every_state(row, expected):
    assert fw.classify(row) == expected


def test_disabled_outranks_running():
    """An operator stop is the operator's decision even if the process lingers;
    reporting it as healthy would hide a stop that did not take effect."""
    assert fw.classify({"disabled": True, "running": True}) == "disabled"


def test_down_names_excludes_disabled_and_unrunnable():
    """Only a genuine outage is worth paging on. Including the other two is what
    trains an operator to ignore the alert."""
    rows = [
        {"name": "a", "running": True, "disabled": False, "unrunnable": ""},
        {"name": "b", "running": False, "disabled": True, "unrunnable": ""},
        {"name": "c", "running": False, "disabled": False, "unrunnable": "no script"},
        {"name": "d", "running": False, "disabled": False, "unrunnable": ""},
    ]
    assert fw.down_names(rows) == ["d"]


def test_consumers_do_not_reimplement_the_predicate():
    """Every consumer must ASK fleet_watchdog rather than re-derive state from
    the raw flags. A second copy is how the five disagreed in the first place."""
    consumers = [
        REPO_ROOT / "scripts" / "harness_eval.py",
        REPO_ROOT / "scripts" / "core" / "cron_health_check.py",
        REPO_ROOT / "scripts" / "dashboard_email_queue_monitor.py",
        REPO_ROOT / "bravo_cli" / "local_bridge.py",
    ]
    for path in consumers:
        src = path.read_text(encoding="utf-8")
        assert "fleet_watchdog import classify" in src, (
            f"{path.name} must use fleet_watchdog.classify, not its own predicate")


def test_process_table_works_when_imported_not_just_as_main():
    """The self-check must identify THIS PROCESS, not this FILE.

    The first version verified the table by looking for "fleet_watchdog.py" in
    it. That string is only present when this module is the __main__ script —
    but every real consumer IMPORTS it (harness_eval, cron_health_check,
    local_bridge), so for them the running command line is harness_eval.py and
    the check rejected a perfectly good table. Combined with fail-closed, that
    turned every consumer's gate red on healthy infrastructure.

    This test runs in pytest, so the process is NOT fleet_watchdog.py — exactly
    the condition that broke it.
    """
    table = fw._process_table()
    assert table is not None, (
        "process table rejected when called from an importer — the self-check "
        "is keyed on the file rather than the process")
    assert f"|{os.getpid()}|" in table, "self-check token must identify this PID"


# --------------------------------------------------- session-0 supervision ---

def test_session_id_is_detectable_on_windows():
    """The guard is only real if the session can actually be read."""
    sid = fw._windows_session_id()
    if os.name != "nt":
        pytest.skip("windows-only")
    assert sid is not None, "cannot determine session — the session-0 guard is inert"
    assert sid >= 0


def test_supervision_refuses_to_run_from_session_zero(monkeypatch, capsys):
    """A session-0 supervisor sees the user-session fleet as ABSENT and starts a
    duplicate of every daemon. That is how four schedulers came to exist: the
    "PM2 Resurrect" task was LogonType=S4U, so it supervised from session 0.

    Fourth recurrence of this class on this machine, and the first time the
    launcher itself refuses.
    """
    monkeypatch.setattr(fw, "_windows_session_id", lambda: 0)
    monkeypatch.setattr(sys, "argv", ["fleet_watchdog.py", "up"])
    rc = fw.main()
    assert rc == 1
    assert "session 0" in capsys.readouterr().err.lower()


def test_supervision_allowed_from_a_user_session(monkeypatch):
    """Break the test before trusting it: the guard must not block session 1."""
    monkeypatch.setattr(fw, "_windows_session_id", lambda: 1)
    monkeypatch.setattr(fw, "_acquire_run_lock", lambda: False)
    monkeypatch.setattr(sys, "argv", ["fleet_watchdog.py", "up"])
    assert fw.main() == 0, "a user-session pass must be allowed through the guard"


# ------------------------------------------- a crash is not a silent event ---
# Added 2026-08-29. `start()` passed stdout=DEVNULL and stderr=DEVNULL. PM2 used
# to capture those streams and PM2 is no longer the supervisor, so a daemon that
# died on boot produced nothing anywhere: the watchdog started it, it exited,
# and the next pass started it again — forever, with `status` reading "0 down"
# in between because the timing hid it.

def test_a_started_daemon_gets_its_output_captured(tmp_path, monkeypatch):
    monkeypatch.setattr(fw, "DAEMON_LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(fw, "LOG", tmp_path / "fleet.log")
    captured = {}

    class _P:
        def __init__(self, *a, **kw):
            captured.update(kw)

    monkeypatch.setattr(fw.subprocess, "Popen", _P)
    ok, _ = fw.start({"name": "probe", "interp": "python.exe", "script": "s.py",
                      "args": [], "cwd": str(tmp_path), "unrunnable": ""})
    assert ok
    assert captured["stdout"] is not fw.subprocess.DEVNULL, "output still discarded"
    assert captured["stderr"] == fw.subprocess.STDOUT, "stderr must join stdout"
    assert (tmp_path / "logs" / "daemon-probe.log").exists()


def test_an_unwritable_log_does_not_block_the_start(tmp_path, monkeypatch):
    """Never trade a running daemon for a log file."""
    monkeypatch.setattr(fw, "DAEMON_LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(fw, "LOG", tmp_path / "fleet.log")
    monkeypatch.setattr(fw, "_daemon_log", lambda name: None)
    started = {}
    monkeypatch.setattr(fw.subprocess, "Popen",
                        lambda *a, **kw: started.update(kw) or object())
    ok, _ = fw.start({"name": "probe", "interp": "python.exe", "script": "s.py",
                      "args": [], "cwd": str(tmp_path), "unrunnable": ""})
    assert ok
    assert started["stdout"] is fw.subprocess.DEVNULL


def test_the_daemon_log_is_bounded(tmp_path, monkeypatch):
    """A raw handle handed to a detached child has no logging handler behind it,
    so nothing else can rotate this file."""
    monkeypatch.setattr(fw, "DAEMON_LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(fw, "DAEMON_LOG_MAX_BYTES", 500)
    (tmp_path / "logs").mkdir()
    big = tmp_path / "logs" / "daemon-probe.log"
    big.write_text("x" * 5000, encoding="utf-8")
    fh = fw._daemon_log("probe")
    assert fh is not None
    fh.close()
    assert big.stat().st_size < 500, "oversized daemon log was not rolled"
    assert (tmp_path / "logs" / "daemon-probe.log.1").exists(), "first traceback was lost"


def test_a_crash_loop_is_counted_not_just_restarted(tmp_path, monkeypatch):
    """The watchdog already recorded every start; nothing read them back, so a
    daemon dying every five minutes looked exactly like one that had been up all
    day."""
    import json as _json
    from datetime import datetime, timedelta, timezone as _tz
    monkeypatch.setattr(fw, "LOG", tmp_path / "fleet.log")
    now = datetime.now(_tz.utc)
    lines = [_json.dumps({"ts": (now - timedelta(minutes=m)).isoformat(),
                          "msg": "started probe: python s.py"})
             for m in (1, 6, 11)]
    lines.append(_json.dumps({"ts": (now - timedelta(hours=9)).isoformat(),
                              "msg": "started probe: python s.py"}))
    (tmp_path / "fleet.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert fw.recent_starts("probe") == 3, "starts outside the window must not count"
    assert fw.recent_starts("other") == 0


def test_a_healthy_daemon_start_carries_no_crash_loop_note(tmp_path, monkeypatch):
    monkeypatch.setattr(fw, "DAEMON_LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(fw, "LOG", tmp_path / "fleet.log")
    monkeypatch.setattr(fw.subprocess, "Popen", lambda *a, **kw: object())
    _, msg = fw.start({"name": "probe", "interp": "python.exe", "script": "s.py",
                       "args": [], "cwd": str(tmp_path), "unrunnable": ""})
    assert "CRASH LOOP" not in msg
