"""statement_parser.py — bank statement PDF -> structured JSON via Anthropic vision.

Phase 7.2 of the SunBiz CRM build (2026-05-15) + migration 069 (2026-05-25).
2026-05-25: Known funding company registry moved from hardcoded inline list to
Supabase `known_funding_companies` table (migration 069). Loaded once per
process lifetime; falls back to _FALLBACK_KNOWN_FUNDING_COMPANIES on DB error.

Jordan's meeting:
"the AI is expected to perform automated underwriting by analyzing
bank statements to identify existing loans and debt levels."

Pipeline:

  PDF on disk OR Supabase Storage path
        |
        v
  Convert PDF -> page images (PyMuPDF / pdf2image)
        |
        v
  Anthropic vision API (Claude Sonnet 4.6, model="claude-sonnet-4-6")
  with a tight extraction prompt
        |
        v
  Structured JSON: { deposits, withdrawals, recurring_debits,
                     identified_loan_payments, nsf_events,
                     month_start_balance, month_end_balance, ... }

CLI:
  python scripts/underwriting/statement_parser.py parse --file <path> [--json]
  python scripts/underwriting/statement_parser.py parse --storage-path <key> [--json]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_PAGES = 12      # bank statements are typically 4-10 pages
DEFAULT_TIMEOUT_S = 120     # vision is slower than text


def _load_env_var(name: str) -> str:
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from lib.secret_loader import load_env  # type: ignore
        return (load_env().get(name) or os.environ.get(name) or "").strip()
    except Exception:
        return os.environ.get(name, "").strip()


# ─────────────────────────────────────────────────────────────────────
# Known funding company registry (migration 069, 2026-05-25)
# Previously hardcoded in the vision prompt; now DB-backed via the
# `known_funding_companies` Supabase table. Falls back to the constant
# below on any DB error so parse behavior is unchanged when offline.
# ─────────────────────────────────────────────────────────────────────

_FALLBACK_KNOWN_FUNDING_COMPANIES: list[dict] = [
    {"name": "BlueVine", "aliases": [], "industry_signal_keywords": [], "category": "mca"},
    {"name": "OnDeck", "aliases": ["OnDeck Capital", "ONDECK"], "industry_signal_keywords": [], "category": "mca"},
    {"name": "Kabbage", "aliases": [], "industry_signal_keywords": [], "category": "mca"},
    {"name": "Funding Circle", "aliases": [], "industry_signal_keywords": [], "category": "mca"},
    {"name": "CAN Capital", "aliases": [], "industry_signal_keywords": [], "category": "mca"},
    {"name": "Mantis Funding", "aliases": [], "industry_signal_keywords": [], "category": "mca"},
    {"name": "Rapid Capital Funding", "aliases": [], "industry_signal_keywords": [], "category": "mca"},
    {"name": "Yellowstone", "aliases": [], "industry_signal_keywords": [], "category": "mca"},
    {"name": "Forward Financing", "aliases": ["Forward Fin", "FWD FIN"], "industry_signal_keywords": [], "category": "mca"},
    {"name": "Square Capital", "aliases": [], "industry_signal_keywords": [], "category": "mca"},
    {"name": "Stripe Capital", "aliases": [], "industry_signal_keywords": [], "category": "mca"},
    {"name": "PayPal Working Capital", "aliases": [], "industry_signal_keywords": [], "category": "mca"},
]

# Module-level cache — loaded once per process lifetime.
_KNOWN_FUNDING_COMPANIES: list[dict] | None = None


def _load_known_funding_companies() -> list[dict]:
    """Return the known funding company registry from Supabase.

    Schema: known_funding_companies(name TEXT, aliases TEXT[], industry_signal_keywords TEXT[], category TEXT)
    Falls back to _FALLBACK_KNOWN_FUNDING_COMPANIES on any DB error and logs
    a warning to stderr so the caller is always unblocked.
    """
    global _KNOWN_FUNDING_COMPANIES
    if _KNOWN_FUNDING_COMPANIES is not None:
        return _KNOWN_FUNDING_COMPANIES

    try:
        from lib.secret_loader import load_env  # type: ignore
        env = load_env()
        url = (env.get("BRAVO_SUPABASE_URL") or "").strip()
        key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        if not url or not key:
            raise RuntimeError("Supabase credentials missing")
        from supabase import create_client  # type: ignore
        client = create_client(url, key)
        res = client.table("known_funding_companies").select(
            "name, aliases, industry_signal_keywords, category"
        ).execute()
        rows = list(res.data or []) if res else []
        if not rows:
            raise RuntimeError("known_funding_companies table returned no rows")
        _KNOWN_FUNDING_COMPANIES = rows
    except Exception as exc:
        import sys as _sys
        _sys.stderr.write(
            f"[statement_parser] WARNING: could not load known_funding_companies from DB "
            f"({exc}); using fallback list.\n"
        )
        _KNOWN_FUNDING_COMPANIES = _FALLBACK_KNOWN_FUNDING_COMPANIES

    return _KNOWN_FUNDING_COMPANIES


def _format_company_keywords(companies: list[dict]) -> str:
    """Format company list for injection into the vision prompt."""
    lines: list[str] = []
    for c in companies:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        aliases: list[str] = [a for a in (c.get("aliases") or []) if a]
        keywords: list[str] = [k for k in (c.get("industry_signal_keywords") or []) if k]
        parts = aliases + keywords
        if parts:
            lines.append(f"- {name} (also: {', '.join(parts)})")
        else:
            lines.append(f"- {name}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# PDF -> page images
# ─────────────────────────────────────────────────────────────────────


def _pdf_to_images(pdf_path: Path, max_pages: int = DEFAULT_MAX_PAGES) -> list[bytes]:
    """Try PyMuPDF first (fastest), fall back to pdf2image. Returns
    a list of PNG bytes, one per page."""
    pages: list[bytes] = []
    try:
        import fitz  # type: ignore  # PyMuPDF
    except ImportError:
        fitz = None  # type: ignore

    if fitz is not None:
        doc = fitz.open(str(pdf_path))
        try:
            for i, page in enumerate(doc):
                if i >= max_pages:
                    break
                # ~150 DPI keeps the text legible to the model without
                # ballooning request size.
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                pages.append(pix.tobytes("png"))
        finally:
            doc.close()
        return pages

    # Fallback: pdf2image (requires poppler installed on the system).
    try:
        from pdf2image import convert_from_path  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "Need PyMuPDF or pdf2image installed. Run: pip install pymupdf"
        ) from e
    images = convert_from_path(str(pdf_path), dpi=150)
    for i, img in enumerate(images):
        if i >= max_pages:
            break
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        pages.append(buf.getvalue())
    return pages


# ─────────────────────────────────────────────────────────────────────
# Anthropic vision call
# ─────────────────────────────────────────────────────────────────────


# Sentinel token for the company list injection point. Using a sentinel
# rather than .format() avoids KeyError if any company name/alias ever
# contains a literal { or } character (valid in some legal trade names).
_COMPANY_LIST_SENTINEL = "<<<COMPANY_LIST>>>"

_EXTRACTION_PROMPT_TEMPLATE = (
    "You're analyzing a small business bank statement on behalf of an underwriter "
    "at a funding shop. Extract a structured JSON payload describing the account activity. "
    "Be conservative — if you're unsure about a number, omit it rather than guess.\n\n"
    "Return JSON with these keys (omit keys whose value you can't determine confidently):\n\n"
    '{\n'
    '  "statement_period": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},\n'
    '  "account_holder": "<business name as it appears>",\n'
    '  "month_start_balance": <number>,\n'
    '  "month_end_balance": <number>,\n'
    '  "total_deposits": <number>,\n'
    '  "total_withdrawals": <number>,\n'
    '  "deposit_count": <int>,\n'
    '  "withdrawal_count": <int>,\n'
    '  "nsf_events": <int>,           // count of overdrafts / NSF fees\n'
    '  "overdraft_days": <int>,       // days the account was negative\n'
    '  "average_daily_balance": <number>,\n'
    '  "recurring_debits": [          // monthly subscription-style debits\n'
    '    {"vendor": "<name>", "amount": <number>, "frequency": "monthly"}\n'
    '  ],\n'
    '  "identified_loan_payments": [  // recurring debits that look like loan repay\n'
    '    {"lender_hint": "<best-guess name>", "amount": <number>, "frequency": "daily|weekly|monthly"}\n'
    '  ],\n'
    '  "notes": "<any underwriter-relevant observation in 1-2 sentences>"\n'
    '}\n\n'
    "Known MCA/loan companies (look for these in memos):\n"
    f"{_COMPANY_LIST_SENTINEL}\n\n"
    'Anything else that pattern-matches "DAILY ACH from <lender>" or '
    '"WEEKLY DEBIT <CORP>" should also land in identified_loan_payments.\n\n'
    "Return ONLY the JSON. No prose before or after.\n"
)

# Module-level cache for the rendered prompt — rebuilt only when the
# company list is first loaded (once per process lifetime).
_EXTRACTION_PROMPT: str | None = None


def _build_extraction_prompt() -> str:
    """Return the extraction prompt with the DB-backed company list injected.

    Result is cached module-level after the first call so the string
    replacement runs once per process, not once per PDF page batch.
    """
    global _EXTRACTION_PROMPT
    if _EXTRACTION_PROMPT is not None:
        return _EXTRACTION_PROMPT
    companies = _load_known_funding_companies()
    formatted = _format_company_keywords(companies)
    _EXTRACTION_PROMPT = _EXTRACTION_PROMPT_TEMPLATE.replace(_COMPANY_LIST_SENTINEL, formatted)
    return _EXTRACTION_PROMPT


def call_claude_vision(image_pngs: list[bytes], model: str = DEFAULT_MODEL) -> dict:
    """POST to Anthropic Messages API with vision. Returns the parsed
    JSON dict on success; raises RuntimeError on failure."""
    api_key = _load_env_var("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing in environment")

    try:
        import requests
    except ImportError as e:
        raise RuntimeError("requests package required") from e

    content: list[dict] = []
    for png in image_pngs:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(png).decode("ascii"),
            },
        })
    content.append({"type": "text", "text": _build_extraction_prompt()})

    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 4000,
            "messages": [{"role": "user", "content": content}],
        },
        timeout=DEFAULT_TIMEOUT_S,
    )
    if r.status_code >= 400:
        try:
            err = r.json()
        except ValueError:
            err = r.text[:600]
        raise RuntimeError(f"Anthropic HTTP {r.status_code}: {err}")
    data = r.json()
    text = ""
    for blk in data.get("content", []):
        if blk.get("type") == "text":
            text += blk.get("text", "")
    text = text.strip()
    # Strip code fences if Claude wrapped JSON in ```
    if text.startswith("```"):
        text = text.strip("`")
        # remove optional language tag like "json\n"
        if text.lower().startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract the {...} block
        s = text.find("{")
        e = text.rfind("}")
        if s != -1 and e > s:
            try:
                return json.loads(text[s : e + 1])
            except json.JSONDecodeError as inner:
                raise RuntimeError(f"vision returned non-JSON: {text[:300]}") from inner
        raise RuntimeError(f"vision returned non-JSON: {text[:300]}")


# ─────────────────────────────────────────────────────────────────────
# Top-level parse function
# ─────────────────────────────────────────────────────────────────────


def parse_statement(pdf_path: Path) -> dict:
    """Read a PDF + return structured underwriting JSON."""
    if not pdf_path.exists():
        raise FileNotFoundError(f"{pdf_path} does not exist")
    pages = _pdf_to_images(pdf_path)
    if not pages:
        raise RuntimeError(f"{pdf_path} has no extractable pages")
    return call_claude_vision(pages)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="statement_parser")
    p.add_argument("--json", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    parse = sub.add_parser("parse", help="Extract structured JSON from one PDF")
    parse.add_argument("--file", required=True, help="Path to PDF on disk")
    parse.set_defaults(func=lambda a: parse_statement(Path(a.file)))

    args = p.parse_args(argv)
    try:
        result = args.func(args)
    except (FileNotFoundError, RuntimeError) as e:
        if args.json:
            print(json.dumps({"ok": False, "error": str(e)}), file=sys.stderr)
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"ok": True, "result": result}, indent=2, default=str))
    else:
        print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
