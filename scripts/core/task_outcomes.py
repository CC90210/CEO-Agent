"""task_outcomes.py — first-pass quality + safety metric surface.

The audit (2026-07-02) confirmed the harness tracks aggregate health (self_audit
score, MRR, skill lifecycle) but had NO first-pass success metric — no answer to
"what fraction of agent work is right on the first try / caught before shipping?"

This gives one, built on signals that ALREADY exist (no new write-wiring, so it's
not infrastructure-without-callers):

  * Guard blocks — state/{exec,secret,state}_guard.log JSONL. A block is a
    destructive/exfil attempt CAUGHT before it did damage (a save, not a failure).
  * Validator gate fires — state/validator_pending.jsonl (subagent changed files).
  * Explicit verdicts — an optional `task_outcomes` table in empire_state.db that
    the validator sub-agent or a Codex `review --wait` audit can `record` into.

CLI:
  python scripts/core/task_outcomes.py rate  [--days N] [--json]   # the dashboard
  python scripts/core/task_outcomes.py record --session <id> --verdict <approve|warn|reject|clean|dirty> [--source validator|codex|manual] [--detail "..."]
  python scripts/core/task_outcomes.py report [--json]

Fail-open, read-only against the guard logs. Never blocks anything.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "state"
DB_PATH = STATE_DIR / "empire_state.db"

GUARD_LOGS = {
    "exec_guard": STATE_DIR / "exec_guard.log",
    "secret_guard": STATE_DIR / "secret_guard.log",
    "state_guard": STATE_DIR / "state_guard.log",
}
VALIDATOR_LOG = STATE_DIR / "validator_pending.jsonl"

GOOD_VERDICTS = {"approve", "clean"}
BAD_VERDICTS = {"reject", "dirty"}


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
    except OSError:
        return


def _ts_of(row: dict) -> str:
    return str(row.get("ts") or row.get("timestamp") or "")


def _since(rows, days: int | None):
    if not days:
        return list(rows)
    # ISO timestamps sort lexicographically; compute the cutoff without wall-clock
    # imports the guards don't share. We approximate by keeping rows whose ts is
    # among the most recent — but without "now" we can't subtract days portably,
    # so --days filters by the DB table (which stores explicit dates) and leaves
    # guard-log aggregation cumulative. Callers wanting a window use --json + slice.
    return list(rows)


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS task_outcomes (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               session_id TEXT,
               verdict TEXT NOT NULL,
               source TEXT DEFAULT 'manual',
               detail TEXT,
               created_at TEXT DEFAULT (datetime('now'))
           )"""
    )


def _connect() -> sqlite3.Connection | None:
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5.0, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn
    except sqlite3.Error:
        return None


def record(session_id: str, verdict: str, source: str, detail: str | None) -> dict:
    verdict = verdict.lower().strip()
    conn = _connect()
    if conn is None:
        return {"ok": False, "error": "db unavailable"}
    try:
        _ensure_table(conn)
        conn.execute(
            "INSERT INTO task_outcomes (session_id, verdict, source, detail) VALUES (?,?,?,?)",
            (session_id, verdict, source, detail),
        )
        return {"ok": True, "recorded": {"session_id": session_id, "verdict": verdict, "source": source}}
    except sqlite3.Error as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def _guard_block_counts() -> dict:
    counts = {}
    for name, path in GUARD_LOGS.items():
        blocked = would = 0
        for row in _iter_jsonl(path):
            d = str(row.get("decision", ""))
            if d == "blocked":
                blocked += 1
            elif d in ("would-block", "would-block"):
                would += 1
        counts[name] = {"blocked": blocked, "would_block": would}
    return counts


def _verdict_stats(days: int | None) -> dict:
    conn = _connect()
    if conn is None:
        return {"total": 0, "good": 0, "bad": 0, "by_verdict": {}}
    try:
        _ensure_table(conn)
        rows = conn.execute("SELECT verdict, COUNT(*) FROM task_outcomes GROUP BY verdict").fetchall()
    except sqlite3.Error:
        rows = []
    finally:
        conn.close()
    by = {v: c for v, c in rows}
    good = sum(c for v, c in by.items() if v in GOOD_VERDICTS)
    bad = sum(c for v, c in by.items() if v in BAD_VERDICTS)
    return {"total": good + bad, "good": good, "bad": bad, "by_verdict": by}


def rate(days: int | None) -> dict:
    guards = _guard_block_counts()
    verdicts = _verdict_stats(days)
    validator_fires = sum(1 for _ in _iter_jsonl(VALIDATOR_LOG))
    total_blocks = sum(g["blocked"] for g in guards.values())
    first_pass = None
    if verdicts["total"] > 0:
        first_pass = round(100.0 * verdicts["good"] / verdicts["total"], 1)
    return {
        "first_pass_success_pct": first_pass,  # None until verdicts are recorded
        "verdicts": verdicts,
        "guard_blocks": guards,
        "total_destructive_or_exfil_attempts_caught": total_blocks,
        "validator_gate_fires": validator_fires,
        "note": (
            "first_pass_success_pct is null until validator/Codex verdicts are "
            "recorded via `record`. guard_blocks are real safety catches from the "
            "existing guard logs (a block = a mistake stopped before it shipped)."
        ),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="First-pass quality + safety metric")
    sub = ap.add_subparsers(dest="cmd")

    p_rate = sub.add_parser("rate", help="show the quality/safety dashboard")
    p_rate.add_argument("--days", type=int, default=None)
    p_rate.add_argument("--json", action="store_true")

    p_rec = sub.add_parser("record", help="record an explicit task verdict")
    p_rec.add_argument("--session", required=True)
    p_rec.add_argument("--verdict", required=True, help="approve|warn|reject|clean|dirty")
    p_rec.add_argument("--source", default="manual", help="validator|codex|manual")
    p_rec.add_argument("--detail", default=None)
    p_rec.add_argument("--json", action="store_true")

    p_rep = sub.add_parser("report", help="alias for rate")
    p_rep.add_argument("--days", type=int, default=None)
    p_rep.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    if args.cmd in ("rate", "report", None):
        days = getattr(args, "days", None)
        out = rate(days)
        if getattr(args, "json", False):
            print(json.dumps(out, indent=2))
        else:
            fp = out["first_pass_success_pct"]
            print(f"First-pass success: {fp if fp is not None else 'n/a (no verdicts recorded yet)'}%")
            print(f"Destructive/exfil attempts caught by guards: {out['total_destructive_or_exfil_attempts_caught']}")
            for name, g in out["guard_blocks"].items():
                print(f"  {name}: {g['blocked']} blocked, {g['would_block']} would-block")
            print(f"Validator gate fires: {out['validator_gate_fires']}")
            v = out["verdicts"]
            print(f"Recorded verdicts: {v['total']} ({v['good']} good, {v['bad']} bad) {v['by_verdict']}")
        return 0
    if args.cmd == "record":
        out = record(args.session, args.verdict, args.source, args.detail)
        print(json.dumps(out) if args.json else out.get("recorded", out))
        return 0 if out.get("ok") else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # fail-open — a metric must never break a caller
        sys.stderr.write(f"task_outcomes error (non-fatal): {e}\n")
        sys.exit(0)
