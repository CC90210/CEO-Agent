"""
Skill Metrics — usage tracking and promotion for auto-generated skills.

Tracks successes/failures per auto-generated skill, promotes skills that hit
the validation threshold (3 successes + >85% success rate), and reports skill
performance.

metrics.json schema (per skill, written to skills/auto-generated/<slug>/):
{
  "skill_name": str,
  "success_count": int,
  "fail_count": int,
  "total_tokens": int,
  "avg_tokens": float,
  "last_used_at": str (ISO 8601),
  "validation_score": float (0-1),
  "status": "[NEW]" | "[VALIDATED]" | "[PROMOTED]"
}

SUBCOMMANDS
-----------
    track --skill X --success bool --tokens N
        Upsert metrics.json for skill X. --success true/false. --tokens N used.

    promote --skill X
        If success_count >= 3 AND success_rate > 0.85: move skills/auto-generated/X
        to skills/X, update status to [VALIDATED], log to memory/PATTERNS.md.

    top --n 10
        List top-N skills by success_count.

    report
        Print a full performance table. --json for machine-readable output.

USAGE
-----
    python scripts/skill_metrics.py track --skill hot-reply-draft --success true --tokens 450
    python scripts/skill_metrics.py promote --skill hot-reply-draft
    python scripts/skill_metrics.py top --n 5
    python scripts/skill_metrics.py report --json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"
AUTO_SKILLS_DIR = SKILLS_DIR / "auto-generated"
MEMORY_DIR = PROJECT_ROOT / "memory"
PATTERNS_FILE = MEMORY_DIR / "PATTERNS.md"

PROMOTION_MIN_SUCCESSES = 3
PROMOTION_MIN_SUCCESS_RATE = 0.85

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ---- metrics.json helpers ----------------------------------------------------

def _metrics_path(skill_name: str) -> Path:
    """Return the metrics.json path for a given skill slug.

    Searches auto-generated first, then skills root.
    """
    auto = AUTO_SKILLS_DIR / skill_name / "metrics.json"
    if auto.parent.exists():
        return auto
    root = SKILLS_DIR / skill_name / "metrics.json"
    return root


def _load_metrics(skill_name: str) -> dict[str, Any]:
    path = _metrics_path(skill_name)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "skill_name": skill_name,
        "success_count": 0,
        "fail_count": 0,
        "total_tokens": 0,
        "avg_tokens": 0.0,
        "last_used_at": None,
        "validation_score": 0.0,
        "status": "[NEW]",
    }


def _save_metrics(skill_name: str, data: dict[str, Any]) -> Path:
    path = _metrics_path(skill_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def _success_rate(metrics: dict[str, Any]) -> float:
    total = (metrics.get("success_count") or 0) + (metrics.get("fail_count") or 0)
    if total == 0:
        return 0.0
    return (metrics.get("success_count") or 0) / total


# ---- All auto-generated skill names ------------------------------------------

def _all_auto_skill_names() -> list[str]:
    if not AUTO_SKILLS_DIR.exists():
        return []
    return sorted(
        d.name
        for d in AUTO_SKILLS_DIR.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )


# ---- TRACK -------------------------------------------------------------------

def track(
    skill_name: str,
    success: bool,
    tokens: int = 0,
    validation_score: Optional[float] = None,
) -> dict[str, Any]:
    """Upsert metrics.json for a skill. Returns updated metrics dict."""
    slug = skill_name.strip().lower().replace(" ", "-")
    metrics = _load_metrics(slug)

    if success:
        metrics["success_count"] = (metrics.get("success_count") or 0) + 1
    else:
        metrics["fail_count"] = (metrics.get("fail_count") or 0) + 1

    new_total_tokens = (metrics.get("total_tokens") or 0) + max(0, tokens)
    metrics["total_tokens"] = new_total_tokens
    total_uses = (metrics.get("success_count") or 0) + (metrics.get("fail_count") or 0)
    metrics["avg_tokens"] = round(new_total_tokens / max(1, total_uses), 1)
    metrics["last_used_at"] = datetime.now(timezone.utc).isoformat()
    metrics["skill_name"] = slug

    if validation_score is not None:
        metrics["validation_score"] = round(float(validation_score), 3)

    # Auto-update status label.
    rate = _success_rate(metrics)
    sc = metrics.get("success_count") or 0
    if metrics.get("status") == "[NEW]" and sc >= PROMOTION_MIN_SUCCESSES and rate > PROMOTION_MIN_SUCCESS_RATE:
        metrics["status"] = "[VALIDATED]"

    _save_metrics(slug, metrics)
    return metrics


def cmd_track(args: argparse.Namespace) -> int:
    success = str(args.success).lower() not in ("false", "0", "no", "n")
    tokens = max(0, args.tokens)
    try:
        metrics = track(args.skill, success=success, tokens=tokens)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: track failed: {exc}", file=sys.stderr)
        return 1

    result: dict[str, Any] = {
        "status": "tracked",
        "skill_name": metrics["skill_name"],
        "success_count": metrics["success_count"],
        "fail_count": metrics["fail_count"],
        "success_rate": round(_success_rate(metrics), 3),
        "current_status": metrics["status"],
    }
    if args.output_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        word = "SUCCESS" if success else "FAIL"
        print(
            f"Tracked [{word}] for '{metrics['skill_name']}' — "
            f"successes={metrics['success_count']} fails={metrics['fail_count']} "
            f"rate={round(_success_rate(metrics) * 100, 1)}% status={metrics['status']}"
        )
    return 0


# ---- PROMOTE -----------------------------------------------------------------

def promote(skill_name: str) -> dict[str, Any]:
    """Promote a skill from auto-generated to the main skills tree.

    Conditions: success_count >= 3 AND success_rate > 0.85.
    Steps:
      1. Load metrics — verify thresholds.
      2. Copy skills/auto-generated/<slug>/ to skills/<slug>/.
      3. Update status in SKILL.md frontmatter and metrics.json.
      4. Append a [V] entry to memory/PATTERNS.md.
    """
    slug = skill_name.strip().lower().replace(" ", "-")
    metrics = _load_metrics(slug)

    sc = metrics.get("success_count") or 0
    rate = _success_rate(metrics)
    result: dict[str, Any] = {
        "skill_name": slug,
        "success_count": sc,
        "success_rate": round(rate, 3),
        "promoted": False,
    }

    if sc < PROMOTION_MIN_SUCCESSES:
        result["reason"] = f"Not enough successes: {sc} < {PROMOTION_MIN_SUCCESSES}"
        return result
    if rate <= PROMOTION_MIN_SUCCESS_RATE:
        result["reason"] = f"Success rate too low: {rate:.1%} <= {PROMOTION_MIN_SUCCESS_RATE:.1%}"
        return result

    auto_dir = AUTO_SKILLS_DIR / slug
    main_dir = SKILLS_DIR / slug

    if not auto_dir.exists():
        result["reason"] = f"auto-generated skill folder not found: {auto_dir}"
        return result

    if main_dir.exists():
        result["reason"] = f"Destination already exists: {main_dir} — manual review needed"
        return result

    # Copy the whole folder.
    shutil.copytree(str(auto_dir), str(main_dir))

    # Update SKILL.md status line.
    skill_md = main_dir / "SKILL.md"
    if skill_md.exists():
        content = skill_md.read_text(encoding="utf-8")
        content = re.sub(r"^status:\s*'\[NEW\]'", "status: '[VALIDATED]'", content, flags=re.MULTILINE)
        content = re.sub(r"^status:\s*'\[VALIDATED\]'", "status: '[VALIDATED]'", content, flags=re.MULTILINE)
        skill_md.write_text(content, encoding="utf-8")

    # Update metrics.json in the new location.
    metrics["status"] = "[PROMOTED]"
    metrics["last_used_at"] = datetime.now(timezone.utc).isoformat()
    (main_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")

    # Also update the original auto-generated copy for traceability.
    metrics_auto = auto_dir / "metrics.json"
    metrics_auto.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")

    # Append to memory/PATTERNS.md.
    _append_pattern(slug, sc, rate)

    result["promoted"] = True
    result["destination"] = str(main_dir)
    return result


def _append_pattern(slug: str, success_count: int, rate: float) -> None:
    """Append a [V] validated-pattern entry to memory/PATTERNS.md."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n### [V] Auto-generated skill promoted: `{slug}` ({ts})\n"
        f"- **Successes:** {success_count}, **Rate:** {rate:.1%}\n"
        f"- **Source:** `skills/auto-generated/{slug}/` -> `skills/{slug}/`\n"
        f"- **Pattern:** Skill synthesizer extracted this pattern from agent_decisions "
        f"and it passed 3 tracked uses with high success rate.\n"
    )
    if PATTERNS_FILE.exists():
        current = PATTERNS_FILE.read_text(encoding="utf-8")
        PATTERNS_FILE.write_text(current.rstrip() + "\n" + entry, encoding="utf-8")
    else:
        PATTERNS_FILE.write_text(
            "# Patterns\n\nValidated patterns extracted from agent execution.\n" + entry,
            encoding="utf-8",
        )


def cmd_promote(args: argparse.Namespace) -> int:
    try:
        result = promote(args.skill)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: promote failed: {exc}", file=sys.stderr)
        return 1

    if args.output_json:
        print(json.dumps(result, indent=2, default=str))
        return 0

    if result.get("promoted"):
        print(f"Promoted '{result['skill_name']}' to {result['destination']}")
        print(f"  Success rate: {result['success_rate']:.1%} over {result['success_count']} uses")
        print("  Logged to memory/PATTERNS.md")
    else:
        print(f"Not promoted: {result.get('reason')}")
    return 0 if result.get("promoted") else 1


# ---- TOP ---------------------------------------------------------------------

def cmd_top(args: argparse.Namespace) -> int:
    names = _all_auto_skill_names()
    if not names:
        if args.output_json:
            print(json.dumps({"skills": [], "count": 0}, indent=2))
        else:
            print("No auto-generated skills found.")
        return 0

    rows: list[dict[str, Any]] = []
    for name in names:
        m = _load_metrics(name)
        rows.append({
            "skill_name": name,
            "success_count": m.get("success_count") or 0,
            "fail_count": m.get("fail_count") or 0,
            "success_rate": round(_success_rate(m), 3),
            "last_used_at": m.get("last_used_at"),
            "status": m.get("status") or "[NEW]",
        })

    rows.sort(key=lambda r: (r["success_count"], r["success_rate"]), reverse=True)
    rows = rows[: args.n]

    if args.output_json:
        print(json.dumps({"skills": rows, "count": len(rows)}, indent=2, default=str))
        return 0

    print(f"Top {len(rows)} auto-generated skills by success count:\n")
    for r in rows:
        print(
            f"  {r['skill_name']:35} "
            f"successes={r['success_count']:>3}  "
            f"fails={r['fail_count']:>3}  "
            f"rate={r['success_rate']:.0%}  "
            f"{r['status']}"
        )
    return 0


# ---- REPORT ------------------------------------------------------------------

def build_report() -> dict[str, Any]:
    names = _all_auto_skill_names()
    rows: list[dict[str, Any]] = []
    for name in names:
        m = _load_metrics(name)
        rows.append(
            {
                "skill_name": name,
                "success_count": m.get("success_count") or 0,
                "fail_count": m.get("fail_count") or 0,
                "total_uses": (m.get("success_count") or 0) + (m.get("fail_count") or 0),
                "success_rate": round(_success_rate(m), 3),
                "avg_tokens": m.get("avg_tokens") or 0.0,
                "last_used_at": m.get("last_used_at"),
                "validation_score": m.get("validation_score") or 0.0,
                "status": m.get("status") or "[NEW]",
            }
        )
    rows.sort(key=lambda r: (r["success_count"], r["success_rate"]), reverse=True)
    return {
        "total_auto_skills": len(names),
        "skills": rows,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def cmd_report(args: argparse.Namespace) -> int:
    report = build_report()

    if args.output_json:
        print(json.dumps(report, indent=2, default=str))
        return 0

    rows = report["skills"]
    print(f"Auto-generated skill report ({report['total_auto_skills']} skills)\n")
    if not rows:
        print("  No auto-generated skills found.")
        return 0

    header = f"  {'Name':35} {'Uses':>5} {'Success':>8} {'Rate':>6} {'Status'}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in rows:
        print(
            f"  {r['skill_name']:35} "
            f"{r['total_uses']:>5}  "
            f"{r['success_count']:>7}  "
            f"{r['success_rate']:>5.0%}  "
            f"{r['status']}"
        )
    return 0


# ---- CLI entry ---------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        prog="skill_metrics.py",
        description="Track usage and promote auto-generated skills.",
    )
    p.add_argument("--json", dest="output_json", action="store_true")
    sub = p.add_subparsers(dest="command")

    pt = sub.add_parser("track", help="Record a skill use outcome")
    pt.add_argument("--skill", required=True, help="Skill slug (e.g. hot-reply-draft)")
    pt.add_argument("--success", required=True, help="'true' or 'false'")
    pt.add_argument("--tokens", type=int, default=0, help="Tokens consumed in this use")
    pt.add_argument("--json", dest="output_json", action="store_true", default=argparse.SUPPRESS)

    pp = sub.add_parser("promote", help="Promote a validated skill to the main skill tree")
    pp.add_argument("--skill", required=True, help="Skill slug")
    pp.add_argument("--json", dest="output_json", action="store_true", default=argparse.SUPPRESS)

    ptop = sub.add_parser("top", help="List top skills by success count")
    ptop.add_argument("--n", type=int, default=10)
    ptop.add_argument("--json", dest="output_json", action="store_true", default=argparse.SUPPRESS)

    prep = sub.add_parser("report", help="Full performance table")
    prep.add_argument("--json", dest="output_json", action="store_true", default=argparse.SUPPRESS)

    args = p.parse_args()
    if not hasattr(args, "output_json"):
        args.output_json = False

    dispatch = {
        "track": cmd_track,
        "promote": cmd_promote,
        "top": cmd_top,
        "report": cmd_report,
    }
    fn = dispatch.get(args.command)
    if fn is None:
        p.print_help()
        sys.exit(1)
    sys.exit(fn(args))


if __name__ == "__main__":
    main()
