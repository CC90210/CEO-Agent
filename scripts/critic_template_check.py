"""Regression test: every OASIS email template rendered against a synthetic
lead must pass draft_critic. Prevents critic-vs-template drift (the
2026-05-04 mistake where 67% of cold sends were blocked by critic on
template-native phrases like 'Only good things from now on').

Run before shipping any template change OR critic config change. Exits 1 if
any template fails — wire this into CI before allowing template merges.

Usage:
    python scripts/critic_template_check.py            # human report
    python scripts/critic_template_check.py --json     # machine output
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

# Synthetic lead for rendering — covers the geo-rapport path (region inference)
# and gives the critic real-looking inputs without hitting Supabase.
SAMPLE_VARS = {
    "first_name": "Jordan",
    "company": "Apex Wellness Studio",
    "region": "the Hamilton area",
}


def list_templates() -> list[dict]:
    r = subprocess.run(
        [PYTHON, "scripts/integrations/email_engine.py", "--json", "templates", "list"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8",
     creationflags=WINDOWLESS_FLAGS)
    if r.returncode != 0:
        raise RuntimeError(f"templates list failed: {r.stderr}")
    return json.loads(r.stdout)


def render_template(template_id: str, vars_: dict) -> dict:
    """Use email_engine.py templates view to get the raw HTML/text/subject,
    then format with the sample vars. The engine's --dry-run pathway also
    works but goes through gates — we want the rendered draft only.
    """
    r = subprocess.run(
        [PYTHON, "scripts/integrations/email_engine.py", "--json", "templates", "view", template_id],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8",
     creationflags=WINDOWLESS_FLAGS)
    if r.returncode != 0:
        raise RuntimeError(f"template view failed for {template_id}: {r.stderr}")
    tpl = json.loads(r.stdout)

    def fmt(s: str) -> str:
        for k, v in vars_.items():
            s = s.replace("{{" + k + "}}", v).replace("{{ " + k + " }}", v)
        return s

    return {
        "subject": fmt(tpl.get("subject", "")),
        "body_text": fmt(tpl.get("body_text") or tpl.get("body") or ""),
        "body_html": fmt(tpl.get("body_html", "")),
    }


def critique(subject: str, body: str, stage: str = "cold",
             brand: str = "oasis", intent: str = "commercial") -> dict:
    """Run draft_critic on a rendered template. Returns critic verdict."""
    cmd = [
        PYTHON, "scripts/draft_critic.py", "--json", "critique",
        "--subject", subject, "--body", body,
        "--stage", stage, "--brand", brand, "--intent", intent,
        "--recipient", SAMPLE_VARS["first_name"],
        "--company", SAMPLE_VARS["company"],
    ]
    r = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", creationflags=WINDOWLESS_FLAGS)
    if not r.stdout.strip().startswith("{"):
        return {"error": f"critic returned non-JSON: {(r.stderr or r.stdout)[:200]}"}
    return json.loads(r.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Machine output")
    parser.add_argument("--threshold", type=float, default=6.5,
                        help="Min score to pass (matches gateway gate)")
    args = parser.parse_args()

    templates = list_templates()
    results = []
    for tpl in templates:
        rendered = render_template(tpl["id"], SAMPLE_VARS)
        body = rendered["body_text"] or rendered["body_html"]
        verdict = critique(rendered["subject"], body)
        score = verdict.get("score", 0) or 0
        recommendation = verdict.get("recommendation") or verdict.get("verdict") or "unknown"
        passed = score >= args.threshold and recommendation == "ship"
        results.append({
            "template_id": tpl["id"],
            "template_name": tpl["name"],
            "subject": rendered["subject"],
            "score": score,
            "recommendation": recommendation,
            "passed": passed,
            "issues_count": len(verdict.get("issues", []) or []),
            "top_issue": (verdict.get("issues") or [{}])[0].get("issue") if verdict.get("issues") else None,
        })

    if args.json:
        print(json.dumps({"threshold": args.threshold, "results": results}, indent=2))
    else:
        print(f"Critic-Template Regression — threshold={args.threshold}")
        print()
        for r in results:
            status = "PASS" if r["passed"] else "FAIL"
            print(f"  [{status}] {r['template_name']:<22} score={r['score']:.1f}  rec={r['recommendation']}")
            if not r["passed"] and r["top_issue"]:
                print(f"          → {r['top_issue'][:120]}")
        passed = sum(1 for r in results if r["passed"])
        print()
        print(f"  {passed}/{len(results)} templates pass critic.")
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
