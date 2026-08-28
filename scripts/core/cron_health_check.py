"""cron_health_check.py — meta-monitoring for the Automations tab.

Runs hourly via SEED_JOBS entry "Bravo — Hourly Cron Health Check".
Scans `cron_jobs` (and `tenant_cron_jobs`) and ships a single consolidated
Telegram alert to CC so a broken cron doesn't sit dead for a week (which is
exactly how the MRR sync gap went unnoticed until 2026-05-22).

FAILURE IS A SHAPE, NOT A PREFIX (2026-08-21). Until this rewrite the scan was
`last_result.upper().startswith(("ERROR", "FAILED"))` on `is_active = True`
rows only. That left three blind spots wide enough to drive the fleet through:

  1. A job that reports a JSON summary carrying its own error count —
     `{"errors": 3, "sent": 0}` — never starts with ERROR, so it was invisible.
     The IG closer, the event-bus drain and the review harvester all report
     this way; every one of them could fail forever and read green.
  2. A job that stops running entirely is not "failing" — it has NO new
     last_result at all. The row keeps whatever succeeded last, so a scheduler
     that died, a bridge that went offline, or a machine that stopped booting
     shows the fleet as perfectly healthy. Eight SunBiz crons sat "enabled and
     dead" for fifteen days under the old check without a single alert.
  3. `is_active = False` was excluded BY CONSTRUCTION, so a job someone
     disarmed "just for now" could never surface again. Disarming is how a
     job dies quietly; the watchdog has to be the thing that remembers.

So: three verdicts now, not one.
  FAILING  — the result SHAPE says it failed (prefix, JSON error counts,
             `ok: false`, `status: error`, or a `failures: N>0` in plain text).
  STALE    — no run in >= STALE_MISSED_FIRES multiples of the row's own cron
             schedule. Computed from the schedule itself, so a */5 job and a
             quarterly job get proportionate patience.
  DISARMED — SEED_JOBS declares the job should be active and the live row is
             not. Reported in its own bucket, never mixed with crashes: an
             operator toggle is a decision to re-examine, not an incident.

Two reasons this is the *meta* cron, not just another business cron:
  1. It guards the OTHER crons. A silent break in any of the 14+ active
     business automations would be invisible without this; CC only catches
     them by happening to look at the dashboard.
  2. It self-monitors: if this script itself fails, the FAILED row in
     cron_jobs surfaces in the dashboard's red-border treatment — so the
     watchdog watches itself.

Flags:
  --alert       actually send the Telegram alert (default in production cron)
  --json        machine-readable output (default for dry-run)
  --dry-run     scan + print, but suppress the Telegram send
  --no-tenant   skip the tenant_cron_jobs sweep (empire cron_jobs only)

Exit code:
  0 = scan succeeded (regardless of whether bad crons were found)
  1 = scan itself errored (DB unreachable etc.)

Author: Bravo · 2026-05-22 · shape-based detection 2026-08-21
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from lib.secret_loader import bootstrap  # noqa: E402
bootstrap()

# Windows CA-bundle fix (2026-07-28) — see lib/tls_trust.py. Without it this
# watchdog died with CERTIFICATE_VERIFY_FAILED before it could read cron_jobs,
# so the meta-cron that exists to surface broken crons was itself broken and
# silent — exactly the failure mode it was built to prevent.
from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

from supabase_tool import get_client, load_env  # noqa: E402

# Single source of truth for "this failure is the harness scoring itself".
# Guarded import: this watchdog must still run and alert if harness_eval is
# mid-edit or missing — degrading to "report everything" is the safe direction
# for a watchdog, so the fallback never suppresses anything.
try:
    from harness_eval import is_self_scored_failure as _is_self_scored_failure  # noqa: E402
except Exception as _exc:  # noqa: BLE001
    print(f"[cron_health_check] WARNING: harness_eval import failed ({type(_exc).__name__}: {_exc}); "
          "self-scored suppression DISABLED — the nightly eval's own row may alert.",
          file=sys.stderr)

    def _is_self_scored_failure(job: dict) -> bool:  # type: ignore[misc]  # noqa: ARG001
        return False


# How many consecutive missed fires before a silent job counts as dead. Scaled
# by the job's OWN schedule, so a */5 sweep is judged in minutes and a quarterly
# drill in months. 4 is deliberately forgiving: a scheduler restart or a laptop
# lid costs one or two fires, and a watchdog that cries at the first miss gets
# muted, which is the only failure mode worse than not having one.
STALE_MISSED_FIRES = int(os.environ.get("CRON_STALE_MISSED_FIRES", "4"))

# Absolute floor under the staleness window. Without it a `* * * * *` job would
# be "dead" after four minutes and the hourly watchdog would page CC every time
# the scheduler paused to breathe.
MIN_STALE_GRACE_SEC = int(os.environ.get("CRON_MIN_STALE_GRACE_SEC", "1800"))

# Keys whose non-zero value means the run reported its own failures. Read off
# the shapes actually stored in cron_jobs.last_result today — the IG closer's
# {"errors":0,...}, the event-bus drain's {"replayed":0,"failed":0,...}, the
# review harvester's {"drained":0}. Guessing this list would have been the
# Anti-Slop #7 defect; these came from the live rows.
_FAILURE_COUNT_KEYS = (
    "errors", "error", "error_count", "errors_count",
    "failures", "failure", "failure_count", "failures_count",
    "failed", "failed_count", "exceptions", "dead_lettered",
)

# `status`/`state` values that mean the run did not succeed.
_FAILURE_STATUS_VALUES = {"error", "errored", "failed", "failure", "fatal", "crash", "crashed"}

# Plain-text counters: "failed: 3", "errors = 12". Anchored on a word boundary
# and requiring the separator so "no failures" or "0 failed" prose can't trip it,
# and so the very common healthy shape "synced: 157 · failed: 0" reads as 0.
_TEXT_COUNT_RE = re.compile(
    r"\b(errors?|failures?|failed)\s*[:=]\s*(\d+)\b", re.IGNORECASE)


def _coerce_count(value) -> int | None:
    """How many failures does this JSON value represent? None = not a counter.

    `{"errors": 2}` is 2. `{"errors": []}` is 0 and `{"errors": ["boom"]}` is 1 —
    a list of errors is a count of errors. `{"error": "timeout"}` is 1, because a
    populated error string is a failure even though it carries no number, while
    `{"error": null}` and `{"error": ""}` are 0.
    """
    if value is None or value is False:
        return 0
    if value is True:
        return 1
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, (list, tuple, dict)):
        return len(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return 0
        if s.isdigit():
            return int(s)
        return 0 if s.lower() in ("none", "null", "0", "false", "ok") else 1
    return None


def _scan_json_for_failure(obj, depth: int = 0) -> str | None:
    """Walk a decoded JSON summary for self-reported failure. Returns the reason
    string, or None if the payload looks clean.

    Recurses a bounded 3 levels because handlers wrap their counts
    (`{"summary": {"errors": 2}}`). Unbounded recursion on attacker-shaped data
    is how a watchdog becomes the outage.
    """
    if depth > 3:
        return None
    if isinstance(obj, list):
        for item in obj:
            hit = _scan_json_for_failure(item, depth + 1)
            if hit:
                return hit
        return None
    if not isinstance(obj, dict):
        return None

    for key, value in obj.items():
        k = str(key).strip().lower()
        if k == "ok" and value is False:
            return "reported ok=false"
        if k in ("status", "state", "result") and isinstance(value, str):
            if value.strip().lower() in _FAILURE_STATUS_VALUES:
                return f"reported {k}={value.strip()}"
        if k in _FAILURE_COUNT_KEYS:
            count = _coerce_count(value)
            if count and count > 0:
                return f"reported {k}={count if not isinstance(value, str) else value[:60]}"

    for value in obj.values():
        if isinstance(value, (dict, list)):
            hit = _scan_json_for_failure(value, depth + 1)
            if hit:
                return hit
    return None


def classify_last_result(last_result: str | None) -> tuple[bool, str]:
    """(is_failure, reason) from the SHAPE of a stored last_result.

    The whole point of the 2026-08-21 rewrite. Three detectors, cheapest first:

      1. The legacy ERROR/FAILED prefix — still the most common shape, since
         scheduler.run_script stamps it on a non-zero exit.
      2. A JSON summary that reports its own errors/failures/ok=false.
      3. A plain-text counter, "failed: 3".

    An UNPARSEABLE result is NOT a failure. Several jobs store the last stdout
    line of pretty-printed JSON, which is a lone "}" — inferring failure from
    that would page CC about three healthy jobs every hour, and a watchdog that
    is usually wrong is a watchdog that gets ignored. Those rows are surfaced
    separately as `opaque` (visible, never alerting) and are still fully covered
    by the staleness check, which does not care what the text says.

    ACCEPTS A PRE-DECODED dict/list, not just a string (2026-08-21, caught by the
    live delivery probe and not by reading the code). The Turso compat layer
    auto-decodes JSON-looking TEXT columns, so `last_result` arrives here as a
    real dict for exactly the rows this function exists to catch. Stringifying it
    gives Python repr — `{'errors': 3}` with single quotes — which json.loads
    rejects and the text regex does not match, so the JSON detector was dead
    against every live row while passing its unit tests on hand-written strings.
    Handle the decoded object FIRST; the string path is now the fallback.
    """
    if isinstance(last_result, (dict, list)):
        hit = _scan_json_for_failure(last_result)
        if hit:
            return True, f"{hit} — {json.dumps(last_result, default=str)[:160]}"
        return False, ""

    text = str(last_result or "").strip()
    if not text:
        return False, ""

    upper = text.upper()
    if upper.startswith("ERROR") or upper.startswith("FAILED"):
        return True, text[:200]

    # JSON summary — the shape the old prefix check was blind to.
    if text[:1] in "{[":
        try:
            decoded = json.loads(text)
        except (ValueError, TypeError):
            decoded = None
        if decoded is not None:
            hit = _scan_json_for_failure(decoded)
            if hit:
                return True, f"{hit} — {text[:160]}"

    for _label, digits in _TEXT_COUNT_RE.findall(text):
        try:
            if int(digits) > 0:
                return True, text[:200]
        except ValueError:
            continue
    return False, ""


def _is_opaque(last_result: str | None) -> bool:
    """A stored result that cannot carry a verdict either way.

    script_run keeps only the LAST stdout line, so a handler that pretty-prints
    JSON stores "}". Not a failure — but not evidence of health either, so it is
    reported (never alerted) to keep the blind spot visible instead of letting it
    read as a green tick.
    """
    text = str(last_result or "").strip()
    return text in ("}", "]", "})", "}]")


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def schedule_interval_seconds(schedule: str, samples: int = 6) -> float | None:
    """Nominal seconds between fires of `schedule`. None if unparseable.

    Derived by asking the fleet's own cron parser for the next few fire times
    and taking the LARGEST gap, rather than hardcoding a table of intervals.
    The max (not the mean) is what keeps "0 10 * * MON-FRI" from being called
    dead every Sunday: its biggest legitimate gap is the 3-day weekend, so that
    is the gap staleness must be measured against.
    """
    try:
        from schedule_helpers import next_local_cron_run  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — parser unreachable → no staleness verdict
        return None
    try:
        cursor = next_local_cron_run(schedule)
        if cursor is None:
            return None
        gaps: list[float] = []
        for _ in range(samples):
            nxt = next_local_cron_run(schedule, after=cursor)
            if nxt is None:
                break
            gaps.append((nxt - cursor).total_seconds())
            cursor = nxt
        return max(gaps) if gaps else None
    except Exception:  # noqa: BLE001
        return None


def staleness(schedule: str, last_run_at, created_at=None,
              now: datetime | None = None) -> tuple[bool, str]:
    """(is_stale, reason) — has this job missed too many of its own fires?

    Falls back to `created_at` when the job has NEVER run, so a row that was
    armed and then ignored by every scheduler tick is caught. Without that
    fallback the single worst state — enabled, scheduled, never once executed —
    would be the one state the watchdog could not see.
    """
    now = now or datetime.now(timezone.utc)
    interval = schedule_interval_seconds(schedule)
    if not interval or interval <= 0:
        return False, ""

    baseline = _parse_ts(last_run_at)
    never_ran = baseline is None
    if never_ran:
        baseline = _parse_ts(created_at)
    if baseline is None:
        return False, ""

    elapsed = (now - baseline).total_seconds()
    if elapsed <= 0:
        return False, ""
    window = max(interval * STALE_MISSED_FIRES, MIN_STALE_GRACE_SEC)
    if elapsed < window:
        return False, ""

    missed = int(elapsed // interval)
    days = elapsed / 86400
    verb = "never ran since being created" if never_ran else "no run"
    return True, (f"{verb} for {days:.1f}d — schedule '{schedule}' expects one "
                  f"every {_human_interval(interval)} (~{missed} missed)")


def _human_interval(seconds: float) -> str:
    if seconds < 3600:
        return f"{seconds / 60:.0f}min"
    if seconds < 86400:
        return f"{seconds / 3600:.0f}h"
    return f"{seconds / 86400:.0f}d"


def _seed_expectations() -> dict[str, bool]:
    """{normalized job name: should_be_active} from SEED_JOBS.

    Guarded exactly like the harness_eval import above: a watchdog must still
    run when a neighbour module is mid-edit. An empty map degrades to "report no
    disarmed jobs", which loses a signal but never invents one.
    """
    try:
        from cron_engine import SEED_JOBS, _normalize_dash  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(f"[cron_health_check] WARNING: cron_engine import failed "
              f"({type(exc).__name__}: {exc}); disarmed-job detection DISABLED.",
              file=sys.stderr)
        return {}
    return {_normalize_dash(str(j.get("name") or "")).casefold(): bool(j.get("is_active"))
            for j in SEED_JOBS}


def _norm_name(name: str) -> str:
    try:
        from cron_engine import _normalize_dash  # noqa: PLC0415
        return _normalize_dash(str(name or "")).casefold()
    except Exception:  # noqa: BLE001
        return str(name or "").casefold()


def find_bad_crons(include_tenant: bool = True) -> dict[str, list[dict]]:
    """Scan every automation row and bucket it by verdict.

    Returns {"failing": [...], "stale": [...], "disarmed": [...], "opaque": [...]}.
    Each finding carries name / last_result / last_run_at / detail / source.

    NOTE the signature change (2026-08-21): this used to return a bare list of
    failures. It returns buckets now because "crashed", "stopped running" and
    "somebody turned it off" need different reactions from CC, and flattening
    them into one list is what let the disarmed ones hide.
    """
    db = get_client(load_env())
    now = datetime.now(timezone.utc)
    expectations = _seed_expectations()

    findings: dict[str, list[dict]] = {
        "failing": [], "stale": [], "disarmed": [], "opaque": [],
    }

    # -- empire cron_jobs ----------------------------------------------------
    # Deliberately NOT filtered on is_active. The old query's `.eq("is_active",
    # True)` is precisely why a disarmed-but-expected job could never surface.
    rows = db.table("cron_jobs").select(
        "id,name,is_active,schedule,last_result,last_run_at,created_at").execute()
    for row in rows.data or []:
        name = str(row.get("name") or "")
        active = bool(row.get("is_active"))
        last_result = row.get("last_result")

        if not active:
            if expectations.get(_norm_name(name)) is True:
                findings["disarmed"].append({
                    "name": name, "source": "cron_jobs",
                    "last_result": str(last_result or "")[:200],
                    "last_run_at": row.get("last_run_at"),
                    "detail": "SEED_JOBS expects this active; the live row is disabled",
                })
            continue

        # Same suppression harness_eval.check_cron_health already applied — the
        # nightly eval scoring ITSELF 12/14 is not a broken cron, it is the eval
        # reporting a fleet gap that has usually been fixed by the time this
        # runs. Without this the watchdog paged CC hourly (12:02, 12:30, 13:30,
        # 14:02 on 2026-08-13) about run ffb0b9a0e90d, a result already stale.
        # Imported, never re-implemented: two copies of this rule drifting apart
        # is exactly how the alert and the eval ended up disagreeing.
        self_scored = _is_self_scored_failure(row)

        is_fail, reason = classify_last_result(last_result)
        if is_fail and not self_scored:
            findings["failing"].append({
                "name": name, "source": "cron_jobs",
                "last_result": str(last_result or "").strip()[:200],
                "last_run_at": row.get("last_run_at"),
                "detail": reason,
            })
        elif _is_opaque(last_result):
            findings["opaque"].append({
                "name": name, "source": "cron_jobs",
                "last_result": str(last_result or "").strip()[:200],
                "last_run_at": row.get("last_run_at"),
                "detail": "last_result is a truncated JSON tail — verdict unknowable",
            })

        stale, stale_reason = staleness(str(row.get("schedule") or ""),
                                        row.get("last_run_at"),
                                        row.get("created_at"), now)
        if stale:
            findings["stale"].append({
                "name": name, "source": "cron_jobs",
                "last_result": str(last_result or "").strip()[:200],
                "last_run_at": row.get("last_run_at"),
                "detail": stale_reason,
            })

    if include_tenant:
        findings = _scan_tenant_crons(db, findings, now)
    findings = _scan_daemon_backed(findings)
    findings = _scan_bridge_pairings(db, findings)
    return findings


# Tenants whose cron rows belong in CC'S OWN Telegram digest. OASIS only:
# Atlas's four rows live under the OASIS tenant (Atlas is CC's personal CFO),
# so they stay covered; SunBiz and any future client tenant are excluded — the
# founder's phone is not the client's monitoring channel.
BRAVO_GOVERNED_TENANTS: frozenset[str] = frozenset({"ef8d389e"})

# Which machines are SUPPOSED to hold an unrevoked pairing, per tenant prefix.
# Any other live pairing is an executor that can claim jobs — and a machine
# running stale bridge code poisons rows with errors for repos it does not
# have. That exact failure took three forms in one week: the Mac (revoked
# 08-22 07:13, RE-PAIRED ITSELF at 11:15 the same day), and the VPS paired to
# the wrong tenant for 11 days. Revocation alone is a lock a machine with
# re-pair credentials can pick, so the watchdog PAGES on any unexpected live
# pairing with the response in the message.
EXPECTED_PAIRINGS: dict[str, tuple[str, ...]] = {
    # PAIRING legitimacy, not execution rights. The Mac became a sanctioned
    # device on 2026-08-23 (CC ran the handover and moved credentials to it),
    # so its pairing stops paging him — but the dashboard's poll gate
    # (EXPECTED_EXECUTOR_BY_TENANT_PREFIX) still serves OASIS cron jobs to
    # CCPC alone. A device may be trusted to exist without being trusted to
    # execute; conflating those two lists is how the Mac poisoned rows for a
    # week.
    "ef8d389e": ("CCPC (Windows)", "192.168.11.27 (Mac)"),
    "aa04fa1f": ("srv1723601 (Linux)",),      # SunBiz: the VPS only
}


def _scan_bridge_pairings(db, findings: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Flag any live pairing that is not on the expected-machines list."""
    try:
        rows = (db.table("bridge_pairings")
                .select("id,label,tenant_id,last_seen_at,revoked_at").execute()).data or []
    except Exception as exc:  # noqa: BLE001
        print(f"[cron_health_check] WARNING: bridge_pairings unreadable "
              f"({type(exc).__name__}); pairing detection DISABLED.", file=sys.stderr)
        return findings
    for r in rows:
        if r.get("revoked_at"):
            continue
        prefix = str(r.get("tenant_id") or "")[:8]
        expected = EXPECTED_PAIRINGS.get(prefix)
        if expected is None:
            continue  # tenants we don't govern (other products)
        if str(r.get("label") or "") not in expected:
            findings["failing"].append({
                "name": f"bridge pairing: {r.get('label')}",
                "source": "bridge_pairings",
                "last_result": f"unexpected LIVE pairing on tenant {prefix}*, "
                               f"last_seen {str(r.get('last_seen_at'))[:16]}",
                "last_run_at": r.get("last_seen_at"),
                "detail": ("an unexpected machine can claim this tenant's cron jobs "
                           "and poison rows. Revoke it in bridge_pairings (set "
                           "revoked_at) or via the dashboard; the durable fix is "
                           "updating that machine's bridge code"),
            })
    return findings


def _scan_daemon_backed(findings: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """A daemon-backed automation whose PM2 process is not online is FAILING.

    The Instagram setter's cron row is deliberately disarmed forever — the PM2
    process `bravo-ig-dm` owns execution, and arming the row makes the daemon
    refuse to boot. So the row-based scan above can never see the setter die.
    PM2 auto-restarts a crash, but a STOPPED process (pm2 stop, a failed
    restart, a machine that booted without resurrection) stays down silently —
    and this watchdog is the only thing positioned to say so.

    Seeds declare the link via `daemon_backed: "<pm2-name>"`. Read from the
    seed, not hardcoded, so the next daemon-backed automation is covered by
    adding one key. Guarded like every other neighbour import: a broken seed
    module or missing pm2 degrades to "no daemon findings", never a crash —
    but it SAYS it degraded, because a silently-disabled check is how this
    watchdog spent months claiming health it could not see.
    """
    try:
        from cron_engine import SEED_JOBS  # noqa: PLC0415
        daemon_jobs = [(str(j.get("name") or ""), str(j["daemon_backed"]))
                       for j in SEED_JOBS if j.get("daemon_backed")]
    except Exception as exc:  # noqa: BLE001
        print(f"[cron_health_check] WARNING: seed import failed "
              f"({type(exc).__name__}); daemon-backed detection DISABLED.",
              file=sys.stderr)
        return findings
    if not daemon_jobs:
        return findings
    # NEVER invoke pm2 here. This used to shell `pm2 jlist` every hour. On a
    # machine where pm2's named pipe returns EPERM that call (a) always fails,
    # so this check reported every daemon-backed job as DOWN and paged CC with
    # an ERROR every hour, and (b) SPAWNS AN ORPHAN PM2 GOD DAEMON per run.
    # 132 orphans had accumulated by 2026-08-28 across this and three sibling
    # probes. The hourly ERROR Telegram CC received on 2026-08-28 00:08 was
    # this exact call failing.
    #
    # fleet_watchdog.status() answers the same question from the OS process
    # table, and is the supervisor of record since e7d0a50f.
    try:
        _scripts = Path(__file__).resolve().parents[1]
        if str(_scripts) not in sys.path:
            sys.path.insert(0, str(_scripts))
        from ops.fleet_watchdog import status as fleet_status
        rows = {r.get("name"): r for r in fleet_status()}
    except Exception as exc:  # noqa: BLE001
        print(f"[cron_health_check] WARNING: fleet status unavailable "
              f"({type(exc).__name__}); daemon-backed detection DISABLED.",
              file=sys.stderr)
        return findings
    for job_name, pm2_name in daemon_jobs:
        row = rows.get(pm2_name)
        if row is None:
            state = "NOT IN FLEET MANIFEST"
        elif row.get("disabled"):
            continue  # operator stopped it deliberately — not a failure to page on
        elif row.get("running"):
            continue
        elif row.get("unrunnable"):
            state = f"UNRUNNABLE ({row['unrunnable']})"
        else:
            state = "not running"
        findings["failing"].append({
            "name": job_name, "source": "daemon",
            "last_result": f"daemon {pm2_name!r}: {state}",
            "last_run_at": None,
            "detail": (f"daemon-backed automation is DOWN — its work stops "
                       f"silently while the row correctly shows disarmed. "
                       f"Revive with: python scripts/ops/fleet_watchdog.py up"),
        })
    return findings


def _scan_tenant_crons(db, findings: dict[str, list[dict]],
                       now: datetime) -> dict[str, list[dict]]:
    """Same three verdicts against `tenant_cron_jobs`.

    Added 2026-08-21. The empire table was the only thing this watchdog had ever
    looked at, so every per-tenant automation — the eight SunBiz jobs, Atlas's
    four — was unmonitored by construction. They died on 2026-08-06 and nothing
    said a word for fifteen days.

    Different column names (`enabled`, `last_run_status`, `last_run_error`,
    `last_run_output`), so this cannot share the loop above; it shares the
    CLASSIFIERS instead, which is where the logic that matters lives.

    Best-effort: a schema change here must not take down the empire sweep, which
    is the part CC depends on hourly.
    """
    try:
        rows = db.table("tenant_cron_jobs").select(
            "id,tenant_id,agent_key,name,enabled,schedule,last_run_at,"
            "last_run_status,last_run_error,last_run_output,created_at").execute()
    except Exception as exc:  # noqa: BLE001
        print(f"[cron_health_check] WARNING: tenant_cron_jobs scan skipped "
              f"({type(exc).__name__}: {exc})", file=sys.stderr)
        return findings

    for row in rows.data or []:
        # CC'S SCOPE RULING (2026-08-22): Bravo's Telegram digest covers OASIS
        # and CC's personal automations ONLY. Client-tenant rows (SunBiz et al.)
        # paged CC about helios/solara jobs he neither owns nor operates —
        # "I have my personal automations; I don't want to be reminded of
        # client automations." Client tenants have their own watchdog: the
        # dashboard's /api/cron/health-check (every 15 min) pages the
        # sunbiz-ops lane, and the client's own dashboard shows its rows.
        # Bravo covering them here was double-coverage that leaked client
        # noise to the founder's phone.
        if str(row.get("tenant_id") or "")[:8] not in BRAVO_GOVERNED_TENANTS:
            continue
        if not bool(row.get("enabled")):
            continue  # no SEED_JOBS equivalent for tenant rows — nothing to expect
        agent = str(row.get("agent_key") or "?")
        name = f"[{agent}] {row.get('name') or ''}".strip()
        status = str(row.get("last_run_status") or "").strip().lower()
        err = str(row.get("last_run_error") or "").strip()
        output = row.get("last_run_output")

        reason = ""
        if status in _FAILURE_STATUS_VALUES:
            reason = f"last_run_status={status}" + (f": {err[:140]}" if err else "")
        elif err:
            reason = f"last_run_error: {err[:160]}"
        else:
            is_fail, out_reason = classify_last_result(output)
            if is_fail:
                reason = out_reason
        if reason:
            findings["failing"].append({
                "name": name, "source": "tenant_cron_jobs",
                "last_result": (err or str(output or ""))[:200],
                "last_run_at": row.get("last_run_at"),
                "detail": reason,
            })

        stale, stale_reason = staleness(str(row.get("schedule") or ""),
                                        row.get("last_run_at"),
                                        row.get("created_at"), now)
        if stale:
            findings["stale"].append({
                "name": name, "source": "tenant_cron_jobs",
                "last_result": (err or str(output or ""))[:200],
                "last_run_at": row.get("last_run_at"),
                "detail": stale_reason,
            })
    return findings


def _as_buckets(findings) -> dict[str, list[dict]]:
    """Accept either the new bucket dict or the legacy bare list of failures.

    find_bad_crons() changed shape in the 2026-08-21 rewrite; telegram_alert is
    called by tests (and possibly by an out-of-tree caller) with the old list.
    Coercing here keeps one alert-composition path instead of two that drift.
    """
    if isinstance(findings, dict):
        return {k: list(findings.get(k) or []) for k in ("failing", "stale", "disarmed", "opaque")}
    return {"failing": list(findings or []), "stale": [], "disarmed": [], "opaque": []}


def alert_dedup_key(buckets: dict[str, list[dict]]) -> str:
    """Identity of the CONDITION, not the rendered text.

    Key on WHICH jobs are in trouble, not on the message. The message embeds
    result snippets carrying counts and tracebacks, so any drift in that snippet
    minted a fresh identity and reset the backoff — which is how this watchdog
    paged CC at 08:35, 09:00 and 10:01 for one unchanged condition (2026-08-03).
    Same set of failing jobs → same key → the 1h→2h→4h→8h→24h ladder engages.

    The failing-only prefix is byte-identical to the pre-2026-08-21 key so a
    backoff ladder already in flight is NOT reset by this rewrite — a stuck alert
    mid-escalation must not win a free re-fire just because the code changed.
    Stale and disarmed jobs append their own segment, so a job going quiet is a
    new condition and pages immediately rather than inheriting someone's window.
    """
    key = "cron_failing:" + "|".join(sorted(str(b["name"]) for b in buckets["failing"]))
    extra = ["stale=" + ",".join(sorted(str(b["name"]) for b in buckets["stale"]))] \
        if buckets["stale"] else []
    if buckets["disarmed"]:
        extra.append("disarmed=" + ",".join(sorted(str(b["name"]) for b in buckets["disarmed"])))
    return key + (";" + ";".join(extra) if extra else "")


_SECTIONS_STATE = PROJECT_ROOT / "state" / "cron_watch_sections.json"


def _bucket_fingerprint(items: list[dict]) -> str:
    return ",".join(sorted(str(b["name"]) for b in items))


def _load_section_state() -> dict:
    try:
        return json.loads(_SECTIONS_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_section_state(buckets: dict[str, list[dict]]) -> None:
    """Record what was DELIVERED, so the next digest can collapse what CC has
    already seen. Called only after notify reports ok — a suppressed or failed
    send must not mark a section as seen, or the full detail would never reach
    him at all."""
    try:
        _SECTIONS_STATE.parent.mkdir(parents=True, exist_ok=True)
        _SECTIONS_STATE.write_text(json.dumps({
            "stale": _bucket_fingerprint(buckets.get("stale") or []),
            "disarmed": _bucket_fingerprint(buckets.get("disarmed") or []),
        }, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"[cron_health_check] WARNING: could not persist section state: {exc}",
              file=sys.stderr)


def compose_alert(buckets: dict[str, list[dict]]) -> str:
    """The text CC reads on his phone. Three sections, worst first.

    FAILING always renders in full — it is the actionable bucket. STALE and
    DISARMED are STANDING CONDITIONS: when their membership has not changed
    since the last DELIVERED digest, they collapse to a one-line count instead
    of re-listing eight jobs CC has already read. During the 2026-08-22 repair
    session the failing set changed hourly (each fix minted a new dedup key,
    correctly), and every page re-rendered the same 8 dead SunBiz crons and 4
    disarmed rows in full — the news was buried in the reprint. Alert on
    change; summarize the unchanged."""
    lines: list[str] = []
    fail, stale, disarmed = buckets["failing"], buckets["stale"], buckets["disarmed"]
    seen = _load_section_state()
    stale_unchanged = _bucket_fingerprint(stale) == seen.get("stale") and bool(stale)
    disarmed_unchanged = (_bucket_fingerprint(disarmed) == seen.get("disarmed")
                          and bool(disarmed))

    if fail:
        lines.append(f"🚨 {len(fail)} cron(s) failing:")
        for b in fail[:8]:
            lines.append(f"• {b['name']}")
            snippet = str(b.get("detail") or b.get("last_result") or "")[:120]
            lines.append(f"  {snippet}".replace("\n", " "))
        if len(fail) > 8:
            lines.append(f"... and {len(fail) - 8} more failing.")
    if stale:
        if lines:
            lines.append("")
        if stale_unchanged:
            # Even collapsed, say WHOSE they are — "8 stale" with no owner reads
            # as eight new emergencies; "[solara]×4 [helios]×2" reads as the one
            # known outage it actually is. Tags come from the names themselves.
            by_tag: dict[str, int] = {}
            for b in stale:
                m = re.match(r"\[([^\]]+)\]", str(b["name"]))
                by_tag[m.group(1) if m else "empire"] = \
                    by_tag.get(m.group(1) if m else "empire", 0) + 1
            tag_summary = " ".join(f"[{t}]×{n}" for t, n in sorted(by_tag.items()))
            lines.append(f"🕳 {len(stale)} stale cron(s) — unchanged since the last "
                         f"report ({tag_summary}). Full list: "
                         f"python scripts/core/cron_health_check.py --json --dry-run")
        else:
            lines.append(f"🕳 {len(stale)} cron(s) stopped running:")
            for b in stale[:8]:
                lines.append(f"• {b['name']}")
                lines.append(f"  {str(b.get('detail') or '')[:120]}".replace("\n", " "))
            if len(stale) > 8:
                lines.append(f"... and {len(stale) - 8} more stale.")
    if disarmed:
        if lines:
            lines.append("")
        if disarmed_unchanged:
            lines.append(f"⏸ {len(disarmed)} disarmed-but-expected cron(s) — unchanged, "
                         f"details suppressed.")
        else:
            lines.append(f"⏸ {len(disarmed)} cron(s) disarmed but expected active:")
            for b in disarmed[:8]:
                lines.append(f"• {b['name']}")
            if len(disarmed) > 8:
                lines.append(f"... and {len(disarmed) - 8} more disarmed.")
    return "\n".join(lines)


def _deliverable(text: str, buckets: dict[str, list[dict]]) -> str:
    """Guarantee the alert survives notify()'s ownership filter.

    notify() DROPS (does not reroute) any body matching _NOT_BRAVO_DOMAIN_RE —
    TPS / TextTorrent / phone-lookup vocabulary that belongs to APEX. That rule
    is about the SUBJECT of an alert, and it is correct. But a cron-failure alert
    is Bravo's by definition, and a tenant job's error snippet can easily quote
    one of those words — which would silently drop the whole page and then mark
    this watchdog red for a delivery that was refused, not failed.

    So: if the composed body would trip the filter, fall back to names only. The
    filter's own regex is IMPORTED, never re-implemented, so it cannot drift away
    from the rule it is protecting against.
    """
    try:
        import notify as _nf  # noqa: PLC0415
        pattern = getattr(_nf, "_NOT_BRAVO_DOMAIN_RE", None)
    except Exception:  # noqa: BLE001
        return text
    if pattern is None or not pattern.search(text):
        return text

    names = [b["name"] for k in ("failing", "stale", "disarmed") for b in buckets[k]]
    stripped = ("🚨 Cron trouble (details withheld — a result snippet matched the "
                "APEX-domain filter and would have been dropped):\n"
                + "\n".join(f"• {n}" for n in names[:12])
                + "\n\nRun: python scripts/core/cron_health_check.py --json --dry-run")
    print("[cron_health_check] alert body tripped notify's not-Bravo-domain filter; "
          "sending names-only form so the page still lands.", file=sys.stderr)
    return stripped


def telegram_alert(bad) -> tuple[bool, str]:
    """Ship a consolidated failure alert through the same notify() path the
    rest of the fleet uses. Returns (sent, detail).

    Accepts the bucket dict from find_bad_crons(), or a bare list of failures
    (legacy shape).

    The old path read TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID straight off
    os.environ and built its own urllib send. But under the PYTHONW scheduler
    those creds live in .env.agents (loaded by secret_loader), NOT the process
    env, and the real chat id is TELEGRAM_ALLOWED_USERS — so the watchdog
    always returned 'telegram_not_configured' and CC never saw a single failure
    alert (the watchdog was itself the silently-broken cron). notify() loads via
    secret_loader and resolves the chat id.

    Tracebacks contain <module> and would break parse_mode=HTML. That escaping
    moved INTO notify() on 2026-08-04 so every caller gets it — escaping here as
    well would double-encode and show CC a literal "&lt;module&gt;"."""
    buckets = _as_buckets(bad)
    text = _deliverable(compose_alert(buckets), buckets)
    dedup_key = alert_dedup_key(buckets)
    try:
        import notify as _nf  # type: ignore
        # A SUPPRESSED alert is not a failed one. notify()'s bare bool conflates
        # them, and reading False as failure made this watchdog exit 1 and turn
        # itself into a failing cron — so CC got "cron failures detected but
        # alert delivery failed" from an alert that had worked exactly as
        # designed, and the watchdog then reported its own red row on the next
        # tick as a brand-new condition (2026-08-03).
        _, reason = _nf.notify_result(text, category="system", silent=False,
                                      force=True, dedup_key=dedup_key)
        aware = reason in _nf.DELIVERED_REASONS
        if aware:
            # Only a DELIVERED digest marks its stale/disarmed sections as seen.
            # A suppressed or failed send must not — or the collapsed one-liner
            # would replace detail CC never actually received.
            save_section_state(buckets)
        return aware, reason if reason != "failed" else "notify_failed"
    except Exception as exc:  # noqa: BLE001
        return False, f"telegram_error:{type(exc).__name__}:{str(exc)[:80]}"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--alert", action="store_true",
                   help="Send Telegram alert if bad crons found (default in prod)")
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.add_argument("--dry-run", action="store_true",
                   help="Scan + print, suppress Telegram send")
    p.add_argument("--no-tenant", action="store_true",
                   help="Skip the tenant_cron_jobs sweep (empire cron_jobs only)")
    args = p.parse_args()

    try:
        buckets = find_bad_crons(include_tenant=not args.no_tenant)
    except Exception as exc:  # noqa: BLE001
        msg = f"ERROR: scan failed: {type(exc).__name__}: {exc}"
        print(msg, file=sys.stderr)
        return 1

    # `opaque` is diagnostics, never a page: it means "this row cannot tell us
    # anything", not "this row is broken". Only the three real verdicts alert.
    alertable = buckets["failing"] + buckets["stale"] + buckets["disarmed"]

    sent = False
    send_detail = "not_attempted"
    if alertable and args.alert and not args.dry_run:
        sent, send_detail = telegram_alert(buckets)

    summary = {
        "bad_count": len(alertable),
        "failing_count": len(buckets["failing"]),
        "stale_count": len(buckets["stale"]),
        "disarmed_count": len(buckets["disarmed"]),
        "opaque_count": len(buckets["opaque"]),
        "failing": buckets["failing"],
        "stale": buckets["stale"],
        "disarmed": buckets["disarmed"],
        "opaque": buckets["opaque"],
        # Kept so any dashboard/consumer reading the old field still works.
        "bad": buckets["failing"],
        "alert_sent": sent,
        "alert_detail": send_detail,
    }

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    elif not alertable:
        # The success line the scheduler stamps into last_result. Keep the exact
        # "ok: all crons healthy" prefix — it is what the fleet's routine-result
        # matching and CC's own eye both key on.
        extra = f"  ({len(buckets['opaque'])} opaque)" if buckets["opaque"] else ""
        print(f"ok: all crons healthy{extra}")
    else:
        parts = []
        if buckets["failing"]:
            parts.append(f"{len(buckets['failing'])} failing")
        if buckets["stale"]:
            parts.append(f"{len(buckets['stale'])} stale")
        if buckets["disarmed"]:
            parts.append(f"{len(buckets['disarmed'])} disarmed")
        print(f"WARN: {', '.join(parts)}")
        for label, key in (("FAILING", "failing"), ("STALE", "stale"),
                           ("DISARMED", "disarmed"), ("opaque", "opaque")):
            for b in buckets[key]:
                print(f"  [{label}] {b['name']}: {str(b.get('detail') or b.get('last_result'))[:120]}")
        if args.alert and not args.dry_run:
            print(f"  telegram_alert: {send_detail}")

    # If we found failures and TRIED to alert but the send didn't land, the
    # watchdog itself must go RED (nonzero exit → cron_jobs.last_result starts
    # with ERROR). Otherwise the meta-cron shows green while CC gets no alert —
    # the exact silent-failure this guard exists to prevent.
    if alertable and args.alert and not args.dry_run and not sent:
        print(f"ERROR: cron failures detected but alert delivery failed "
              f"({send_detail})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
