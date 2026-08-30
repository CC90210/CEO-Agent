"""Run the eval suites and score them against evals/baselines.json.

WHY THIS EXISTS
---------------
The 2026-08-27 remediation brief said "put the existing eval suites on a cron".
There was nothing to schedule: evals/adapter.py is a CLI-less library with zero
importers, and the runner that used to drive it (tools/eval_runner.py) belonged
to a retired harness and is gone. The suites had not run since 2026-06-10 — the
accuracy of this system was, in practice, unmeasured.

WHAT IT SCORES
--------------
Each case directory holds task.md, meta.yaml and expected.json. adapter.run_case
executes the REAL code path (skill router, CASL gate, footer builder) and returns
a dict; expected.json names which field to compare and how:

    {"scorer": "exact"|"decision"|"rubric", "field": ..., "expected": ...}

`rubric` cases are NOT scoreable offline — they are a regression backlog waiting
to be wired to a deterministic check. They are counted as UNSCORED, never as
passes and never as failures. A suite of them (mistakes) reports as un-baselined
rather than as 0%.

THE PAGING CONTRACT (do not "simplify" this)
--------------------------------------------
scheduler.py ignores `notify_on` — it is dead config. A cron job pages CC only
by exiting non-zero AND printing a line beginning "ERROR:". It also stores only
the LAST stdout line as last_result, so the summary line is printed last and
kept short.

A GATE THAT IS ALWAYS RED IS IGNORED
------------------------------------
Two suites have no usable baseline: routing_nl scores 0.333 and is deliberately
red (it measures natural-language routing that is known-weak), and mistakes is
entirely rubric. Failing the job on those would make the alert meaningless
within a week, so only suites WITH a baseline can fail it. The others are
reported every run so they stay visible.

CLI:
  python evals/run_suites.py                 # all suites, write reports
  python evals/run_suites.py --suite routing # one suite
  python evals/run_suites.py --json          # one-line JSON (cron-safe)
  python evals/run_suites.py --no-write      # score without writing reports
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import date
from pathlib import Path

EVALS = Path(__file__).resolve().parent
REPO = EVALS.parent
REPORTS = EVALS / "reports"
BASELINES = EVALS / "baselines.json"

sys.path.insert(0, str(EVALS))
sys.path.insert(0, str(REPO / "scripts"))

import adapter  # noqa: E402

def discover_suites() -> list[str]:
    """Suite directories that hold at least one case.

    Directory-based, NOT adapter.DISPATCH-based. routing_nl's cases carry
    `suite: routing` in meta.yaml, so the adapter runs them fine — but keying
    discovery on DISPATCH silently skipped the whole directory, which is how a
    suite stops being measured without anyone deciding to stop measuring it.
    adapter.run_case still resolves the handler per case, so a directory with no
    wired adapter surfaces as an error rather than being quietly dropped.
    """
    out = []
    for d in sorted(EVALS.iterdir()):
        if d.is_dir() and d.name not in ("reports", "__pycache__") and _case_dirs(d.name):
            out.append(d.name)
    return out


def _case_dirs(suite: str) -> list[Path]:
    d = EVALS / suite
    if not d.is_dir():
        return []
    return sorted(c for c in d.iterdir() if c.is_dir() and (c / "expected.json").is_file())


def _score_case(case: Path) -> dict:
    """Run one case. Returns {name, scorer, status, expected, actual, error}.

    status: 'pass' | 'fail' | 'unscored' | 'error'
    """
    name = case.name
    try:
        spec = json.loads((case / "expected.json").read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"name": name, "scorer": None, "status": "error",
                "error": f"unreadable expected.json: {exc}"}

    scorer = spec.get("scorer")
    field = spec.get("field")
    expected = spec.get("expected")

    if scorer == "rubric":
        # Honest pending, never a fake pass. See module docstring.
        return {"name": name, "scorer": scorer, "status": "unscored",
                "expected": expected, "actual": None,
                "note": spec.get("note") or "needs a deterministic check"}

    try:
        result = adapter.run_case(case)
    except Exception as exc:  # noqa: BLE001
        return {"name": name, "scorer": scorer, "status": "error",
                "expected": expected, "actual": None,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()[-1500:]}

    actual = result.get(field) if isinstance(result, dict) else result
    # 'exact' and 'decision' are both equality today; kept distinct because the
    # case files distinguish them and a future scorer may not be equality.
    passed = actual == expected
    return {"name": name, "scorer": scorer,
            "status": "pass" if passed else "fail",
            "field": field, "expected": expected, "actual": actual}


def run_suite(suite: str) -> dict:
    """Score one suite. Report shape matches the 2026-06-10 reports on disk."""
    cases = _case_dirs(suite)
    results = [_score_case(c) for c in cases]
    scored = [r for r in results if r["status"] in ("pass", "fail")]
    passed = [r for r in scored if r["status"] == "pass"]
    errored = [r for r in results if r["status"] == "error"]
    return {
        "suite": suite,
        "date": date.today().isoformat(),
        "n_cases": len(results),
        "n_scored": len(scored),
        "n_pass": len(passed),
        "n_error": len(errored),
        # None, not 0.0 — a suite with nothing scoreable has no score, and
        # calling that zero would read as a total regression.
        "score": (len(passed) / len(scored)) if scored else None,
        "results": results,
    }


def _baselines() -> dict:
    try:
        return json.loads(BASELINES.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def verdict(report: dict, baselines: dict) -> dict:
    """Compare a suite to its baseline. Only a BASELINED suite can regress."""
    base = baselines.get(report["suite"])
    score = report["score"]
    if base is None or base.get("score") is None:
        return {"state": "unbaselined", "detail": "no baseline — reported, not gated"}
    if score is None:
        return {"state": "unscored", "detail": "nothing scoreable in this suite"}
    floor = float(base["score"]) - float(base.get("tolerance", 0))
    if score + 1e-9 < floor:
        return {"state": "regressed",
                "detail": f"{score:.3f} < {floor:.3f} (baseline {base['score']} "
                          f"± {base.get('tolerance', 0)})"}
    return {"state": "ok", "detail": f"{score:.3f} >= {floor:.3f}"}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--suite", help="run one suite (default: all runnable)")
    p.add_argument("--json", action="store_true", help="one-line JSON output")
    p.add_argument("--no-write", action="store_true", help="do not write report files")
    args = p.parse_args()

    available = discover_suites()
    suites = [args.suite] if args.suite else available
    unknown = [s for s in suites if s not in available]
    if unknown:
        print(f"ERROR: no cases found for suite(s): {unknown} "
              f"(available: {available})", file=sys.stderr)
        return 1

    baselines = _baselines()
    reports, verdicts = [], {}
    for suite in suites:
        rep = run_suite(suite)
        reports.append(rep)
        verdicts[suite] = verdict(rep, baselines)
        if not args.no_write:
            try:
                REPORTS.mkdir(parents=True, exist_ok=True)
                (REPORTS / f"{rep['date']}_{suite}.json").write_text(
                    json.dumps(rep, indent=2, default=str), encoding="utf-8")
            except OSError as exc:
                print(f"could not write {suite} report: {exc}", file=sys.stderr)

    regressed = [s for s, v in verdicts.items() if v["state"] == "regressed"]
    errored = [r["suite"] for r in reports if r["n_error"]]
    summary = {
        "date": date.today().isoformat(),
        "suites": {r["suite"]: {"score": r["score"], "n_pass": r["n_pass"],
                                "n_scored": r["n_scored"], "n_cases": r["n_cases"],
                                "n_error": r["n_error"],
                                "verdict": verdicts[r["suite"]]["state"]}
                   for r in reports},
        "regressed": regressed,
        "errored": errored,
    }

    if args.json:
        # ONE compact line: scheduler.py keeps only the last stdout line as
        # last_result, and pretty JSON ends in a lone brace, which the cron
        # health check then classifies as "verdict unknowable".
        print(json.dumps(summary, separators=(",", ":"), default=str))
    else:
        for r in reports:
            v = verdicts[r["suite"]]
            score = "  n/a" if r["score"] is None else f"{r['score'] * 100:5.1f}%"
            mark = {"ok": "OK", "regressed": "REGRESSED",
                    "unbaselined": "no baseline", "unscored": "unscored"}[v["state"]]
            print(f"  {r['suite']:<14} {score}  "
                  f"{r['n_pass']}/{r['n_scored']} scored of {r['n_cases']} cases"
                  f"{f', {r["n_error"]} ERROR' if r['n_error'] else ''}"
                  f"  [{mark}] {v['detail']}")

    # Paging contract: non-zero exit + an "ERROR:" line. Only baselined suites
    # can trigger it, plus any suite whose cases blew up (that is a broken
    # harness, which is worth waking someone for).
    if regressed or errored:
        parts = []
        if regressed:
            parts.append("regressed: " + ", ".join(
                f"{s} ({verdicts[s]['detail']})" for s in regressed))
        if errored:
            parts.append("errored: " + ", ".join(errored))
        print(f"ERROR: eval suites {'; '.join(parts)}")
        return 1

    ok = sum(1 for v in verdicts.values() if v["state"] == "ok")
    print(f"eval suites OK — {ok}/{len(verdicts)} baselined suites within tolerance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
