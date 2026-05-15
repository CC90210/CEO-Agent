"""sales_angle.py — generate operator-facing sales positioning copy.

Phase 7.2 of the SunBiz CRM build (2026-05-15). Jordan's meeting:
"ultimately providing suggestions on how to sell the deal."

Pipeline:

  parsed_statements (from statement_parser)
  + debt_summary    (from debt_detector)
  + application_data (business_name, time_in_business, FICO, requested)
  + lender_preferences (optional — which lenders the operator is shopping
                       this deal to; lets the prompt mention them
                       specifically: "TruFund will care about the daily
                       MCA debits more than monthly term-loan payments")
        |
        v
  Claude (Sonnet 4.6) — coaching-style sales angle in ~150 words
        |
        v
  String (operator pastes into CRM / uses on the lender call)

CLI:
  python scripts/underwriting/sales_angle.py write \\
    --debt-summary debt.json \\
    --application app.json [--lenders trufund,bluevine]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_TIMEOUT_S = 60


def _load_env_var(name: str) -> str:
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from lib.secret_loader import load_env  # type: ignore
        return (load_env().get(name) or os.environ.get(name) or "").strip()
    except Exception:
        return os.environ.get(name, "").strip()


SALES_ANGLE_PROMPT = """You're coaching a SunBiz Funding sales rep on how to position a deal to lenders. You have three inputs: the application summary, the debt-load summary from bank statements, and (optionally) the specific lenders the operator is shopping to.

Write a ~150-word sales angle the rep can use on the lender call or paste into the shop-out email. Cover:

1. The strongest one-liner ("$X monthly revenue, Y months in biz, Z+ FICO — looking for clean first position")
2. The "why this deal" thesis — what's strong about it
3. The risk to acknowledge upfront before the lender finds it (NSF events, debt stack, etc. — never hide it; lender will pull statements anyway and trust dies if you tried to mask)
4. The recommended product fit (MCA / term loan / line of credit) based on the data
5. If specific lenders are listed, ONE sentence per lender about how to angle them

Be direct + operator-friendly. No marketing fluff. No "exciting opportunity" / "synergies." Just the deal.

INPUTS:

<application>
{application_json}
</application>

<debt_summary>
{debt_json}
</debt_summary>

<target_lenders>
{lenders}
</target_lenders>

Return ONLY the sales angle text, no JSON, no preamble, no markdown headers.
"""


def generate_sales_angle(
    application: dict,
    debt_summary: dict,
    target_lenders: list[str] | None = None,
) -> str:
    api_key = _load_env_var("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing in environment")
    try:
        import requests
    except ImportError as e:
        raise RuntimeError("requests package required") from e

    prompt = SALES_ANGLE_PROMPT.format(
        application_json=json.dumps(application, indent=2),
        debt_json=json.dumps(debt_summary, indent=2),
        lenders=", ".join(target_lenders) if target_lenders else "(none specified — give a general lender-agnostic angle)",
    )

    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": DEFAULT_MODEL,
            "max_tokens": 600,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=DEFAULT_TIMEOUT_S,
    )
    if r.status_code >= 400:
        try:
            err = r.json()
        except ValueError:
            err = r.text[:400]
        raise RuntimeError(f"Anthropic HTTP {r.status_code}: {err}")
    data = r.json()
    text = ""
    for blk in data.get("content", []):
        if blk.get("type") == "text":
            text += blk.get("text", "")
    return text.strip()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sales_angle")
    p.add_argument("--json", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    w = sub.add_parser("write", help="Generate the sales angle")
    w.add_argument("--debt-summary", required=True, help="Path to debt_summary JSON")
    w.add_argument("--application", required=True, help="Path to application JSON")
    w.add_argument("--lenders", default="", help="Comma-separated lender names")
    w.set_defaults(func=_write_from_files)

    args = p.parse_args(argv)
    try:
        result = args.func(args)
    except (FileNotFoundError, RuntimeError, json.JSONDecodeError) as e:
        if args.json:
            print(json.dumps({"ok": False, "error": str(e)}), file=sys.stderr)
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"ok": True, "result": result}))
    else:
        print(result)
    return 0


def _write_from_files(args) -> str:
    debt = json.loads(Path(args.debt_summary).read_text(encoding="utf-8"))
    app = json.loads(Path(args.application).read_text(encoding="utf-8"))
    lenders = [l.strip() for l in args.lenders.split(",") if l.strip()] if args.lenders else None
    return generate_sales_angle(app, debt, lenders)


if __name__ == "__main__":
    sys.exit(main())
