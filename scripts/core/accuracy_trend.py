"""Week-over-week accuracy of the harness, the eval suites and the review gate.

WHY THIS EXISTS
---------------
Three time-series already existed and nothing read any of them, so "is the
system getting better or worse?" could not be answered — only asserted. This
turns data already on disk into one table CC can read in ten seconds.

THE THREE FORMATS DO NOT AGREE, AND THAT IS THE WHOLE JOB
---------------------------------------------------------
* state/harness_eval_history.jsonl — `score` is the STRING "12/14", and the
  DENOMINATOR MOVED (10 -> 14 as checks were added). Comparing the raw strings,
  or even the numerators, would show a "decline" every time a check was added.
  Parsed to a ratio.
* task_outcomes.created_at — bare UTC with no offset, while the JSONL uses
  ISO+offset. Both normalised to a date before bucketing.
* evals/reports/*.json — one file per suite per run, `score` may be null for a
  suite with nothing scoreable (never treat that as zero).

WHAT IT DELIBERATELY DOES NOT CLAIM
-----------------------------------
A hallucination rate. The validator queues work in state/validator_pending.jsonl
whose schema is {changed_count, sample} — no timestamp, no verdict — so nothing
records what the validator CONCLUDED. And 70 of 93 task_outcomes rows are
`warn`, which belongs to neither the good nor the bad set. The REFUTED-per-week
number the brief asked for is not computable from existing data; this prints the
gate mix that IS real and says plainly what is missing, rather than inventing a
denominator.

CLI:
  python scripts/core/accuracy_trend.py             # last 8 weeks
  python scripts/core/accuracy_trend.py --weeks 12
  python scripts/core/accuracy_trend.py --json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HARNESS_HISTORY = PROJECT_ROOT / "state" / "harness_eval_history.jsonl"
STATE_DB = PROJECT_ROOT / "state" / "empire_state.db"
EVAL_REPORTS = PROJECT_ROOT / "evals" / "reports"


def _week(d: date) -> str:
    """ISO week label, Monday-anchored: '2026-W35'."""
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _as_date(raw: str | None) -> date | None:
    """Parse a timestamp that may or may not carry an offset."""
    if not raw:
        return None
    text = str(raw).strip().replace("Z", "+00:00")
    for parse in (datetime.fromisoformat,
                  lambda s: datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S"),
                  lambda s: datetime.strptime(s[:10], "%Y-%m-%d")):
        try:
            dt = parse(text)
            return (dt.astimezone(timezone.utc) if dt.tzinfo else dt).date()
        except (ValueError, TypeError):
            continue
    return None


def _ratio(score) -> float | None:
    """'12/14' -> 0.857. The denominator moves as checks are added, so only the
    RATIO is comparable across weeks; the numerator alone is not."""
    if isinstance(score, (int, float)):
        return float(score)
    if isinstance(score, str) and "/" in score:
        num, _, den = score.partition("/")
        try:
            d = float(den)
            return float(num) / d if d else None
        except ValueError:
            return None
    return None


def harness_by_week(weeks: int) -> dict[str, dict]:
    out: dict[str, list[float]] = defaultdict(list)
    fails: dict[str, list[str]] = defaultdict(list)
    if not HARNESS_HISTORY.is_file():
        return {}
    for line in HARNESS_HISTORY.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        d = _as_date(row.get("timestamp"))
        r = _ratio(row.get("score"))
        if d is None or r is None:
            continue
        out[_week(d)].append(r)
        for f in row.get("failed") or []:
            fails[_week(d)].append(str(f))
    keep = sorted(out)[-weeks:]
    return {w: {"runs": len(out[w]),
                "mean": sum(out[w]) / len(out[w]),
                "worst": min(out[w]),
                "top_failure": _most_common(fails.get(w, []))}
            for w in keep}


def _most_common(items: list[str]) -> str | None:
    if not items:
        return None
    counts: dict[str, int] = defaultdict(int)
    for i in items:
        counts[i] += 1
    name, n = max(counts.items(), key=lambda kv: kv[1])
    return f"{name} ({n}x)"


def gate_by_week(weeks: int) -> dict[str, dict]:
    """Review-gate verdict mix from task_outcomes."""
    if not STATE_DB.is_file():
        return {}
    try:
        con = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
        rows = con.execute("SELECT verdict, created_at FROM task_outcomes").fetchall()
        con.close()
    except sqlite3.Error:
        return {}
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for verdict, created in rows:
        d = _as_date(created)
        if d is None:
            continue
        buckets[_week(d)][str(verdict or "unknown")] += 1
    keep = sorted(buckets)[-weeks:]
    return {w: dict(buckets[w]) for w in keep}


def evals_by_week(weeks: int) -> dict[str, dict]:
    if not EVAL_REPORTS.is_dir():
        return {}
    buckets: dict[str, dict[str, float]] = defaultdict(dict)
    for f in sorted(EVAL_REPORTS.glob("*.json")):
        try:
            rep = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        d = _as_date(rep.get("date"))
        score = rep.get("score")
        if d is None or score is None:
            continue  # null score = nothing scoreable, NOT zero
        buckets[_week(d)][str(rep.get("suite") or f.stem)] = float(score)
    keep = sorted(buckets)[-weeks:]
    return {w: buckets[w] for w in keep}


def harness_trailing(windows=(5, 20, 50)) -> dict[int, dict]:
    """Trailing-window rates — what the harness scores NOW.

    WHY THIS EXISTS SEPARATELY FROM THE WEEKLY MEAN (2026-08-28): the weekly
    figure is a lagging average. On the day six substantial defects were fixed
    it read 91.3%, because it averaged 110 runs most of which were taken while
    the fleet was genuinely broken — while the trailing 20 read 95.7% and the
    last seven runs were all perfect. Reporting only the weekly number tells an
    operator the system is worse than it is, and hides the moment a fix lands.

    Both are kept. The weekly mean answers "how was this week"; the trailing
    window answers "what is true right now", and a fix should move the second
    immediately and the first only slowly.
    """
    rows = []
    if HARNESS_HISTORY.is_file():
        for line in HARNESS_HISTORY.read_text(encoding="utf-8",
                                              errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if _ratio(row.get("score")) is not None and row.get("timestamp"):
                rows.append(row)
    rows.sort(key=lambda r: r["timestamp"])
    out = {}
    for n in windows:
        w = rows[-n:]
        if not w:
            continue
        vals = [_ratio(r["score"]) for r in w]
        out[n] = {"runs": len(w),
                  "mean": sum(vals) / len(vals),
                  "perfect": sum(1 for r in w if r.get("pass"))}
    return out


def build(weeks: int) -> dict:
    return {"generated": datetime.now(timezone.utc).isoformat(),
            "weeks": weeks,
            "harness": harness_by_week(weeks),
            "harness_now": harness_trailing(),
            "gate": gate_by_week(weeks),
            "evals": evals_by_week(weeks)}


def _arrow(curr: float, prev: float | None) -> str:
    if prev is None:
        return "  "
    if curr > prev + 1e-9:
        return "up"
    if curr < prev - 1e-9:
        return "DN"
    return "= "


def render(data: dict) -> str:
    L: list[str] = []
    L.append("=" * 72)
    L.append(" ACCURACY TREND — harness · eval suites · review gate")
    L.append("=" * 72)

    now = data.get("harness_now") or {}
    if now:
        L.append("")
        L.append("HARNESS NOW (trailing windows — a fix moves these immediately)")
        for n in sorted(now):
            v = now[n]
            L.append(f"  last {n:>3} runs  {v['mean'] * 100:5.1f}%   "
                     f"perfect {v['perfect']}/{v['runs']}")

    h = data["harness"]
    L.append("")
    L.append("HARNESS BY WEEK (lagging — averages in runs from before a fix landed)")
    if not h:
        L.append("  no history yet")
    else:
        prev = None
        for w in sorted(h):
            v = h[w]
            L.append(f"  {w}  {v['mean'] * 100:5.1f}%  {_arrow(v['mean'], prev)}  "
                     f"{v['runs']:>3} runs  worst {v['worst'] * 100:5.1f}%"
                     f"   {v['top_failure'] or ''}")
            prev = v["mean"]

    e = data["evals"]
    L.append("")
    L.append("EVAL SUITES (a suite with nothing scoreable is blank, never 0%)")
    if not e:
        L.append("  no reports yet — run: python evals/run_suites.py")
    else:
        suites = sorted({s for wk in e.values() for s in wk})
        L.append("  week       " + "".join(f"{s[:11]:>13}" for s in suites))
        for w in sorted(e):
            cells = "".join(
                (f"{e[w][s] * 100:12.1f}%" if s in e[w] else f"{'—':>13}")
                for s in suites)
            L.append(f"  {w}" + cells)

    g = data["gate"]
    L.append("")
    L.append("REVIEW GATE (task_outcomes verdict mix)")
    if not g:
        L.append("  no gate verdicts recorded")
    else:
        for w in sorted(g):
            mix = "  ".join(f"{k}={v}" for k, v in sorted(g[w].items()))
            L.append(f"  {w}  {mix}")

    L.append("")
    L.append("NOT MEASURED: hallucination / REFUTED-claim rate.")
    L.append("  state/validator_pending.jsonl records {changed_count, sample} only —")
    L.append("  no timestamp and no verdict, so what the validator CONCLUDED is not")
    L.append("  stored anywhere. Reporting a rate would mean inventing a denominator.")
    L.append("=" * 72)
    return "\n".join(L)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--weeks", type=int, default=8)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    data = build(max(1, args.weeks))
    if args.json:
        print(json.dumps(data, separators=(",", ":"), default=str))
        return 0
    print(render(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
