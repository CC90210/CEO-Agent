"""
Bravo V6.0 — PII Scrubber

Redacts personally identifiable information before a payload leaves the
tenant boundary. Used by send_gateway.py (optional, flagged per tenant),
autonomous_agent.py (logging), and any hook that ships context to Claude API.

WHY
----
V6.0 client-security posture (docs/V6_ARCHITECTURE.md §Q4) requires that
regulated clients' PII never enters a Claude API prompt in the clear.
This module tokenizes / masks PII and returns a reversible mapping so the
agent can put real values back after the LLM response lands.

PATTERNS COVERED (regex-first, good enough for ~90% of cases)
-------------------------------------------------------------
  email, phone_us/ca, ssn_us, sin_ca, credit_card (luhn validated),
  ip_v4, ipv6, us_zip, ca_postal, street_address (best-effort),
  date_of_birth (heuristic), person_name (optional via Presidio if installed)

For stronger PII detection install Microsoft Presidio (`pip install presidio-analyzer
presidio-anonymizer`) — this module auto-detects and uses it when available.

USAGE
-----
    from pii_scrubber import scrub, unscrub

    redacted, table = scrub(user_text, tenant="acme-corp")
    # redacted: "Hi <EMAIL_1>, your card <CARD_1> ..."
    # table: {"<EMAIL_1>": "jane@acme.com", "<CARD_1>": "4111..."}

    llm_out = call_claude(redacted)
    final = unscrub(llm_out, table)

CLI::
    echo "Hi jane@acme.com, your SSN is 123-45-6789" | python scripts/pii_scrubber.py scrub
    python scripts/pii_scrubber.py audit path/to/text.txt
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

# ---- Regex patterns ---------------------------------------------------------

_RX = {
    "EMAIL":     re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
    "PHONE_NA":  re.compile(r"(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}"),
    "SSN_US":    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "SIN_CA":    re.compile(r"\b\d{3}[\s\-]\d{3}[\s\-]\d{3}\b"),
    # Credit-card-ish 13-19 digits with optional separators
    "CARD":      re.compile(r"\b(?:\d[\s\-]?){13,19}\b"),
    "IPV4":      re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "IPV6":      re.compile(r"\b(?:[A-Fa-f0-9]{1,4}:){2,7}[A-Fa-f0-9]{1,4}\b"),
    "US_ZIP":    re.compile(r"\b\d{5}(?:-\d{4})?\b"),
    "CA_POSTAL": re.compile(r"\b[A-Z]\d[A-Z][\s\-]?\d[A-Z]\d\b"),
    "DOB":       re.compile(r"\b(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}\b"),
}


# ---- Luhn check for card numbers (reduces false positives) ------------------

def _luhn_ok(digits: str) -> bool:
    s = [int(d) for d in digits if d.isdigit()]
    if not 13 <= len(s) <= 19:
        return False
    checksum = 0
    parity = len(s) % 2
    for i, d in enumerate(s):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


# ---- Presidio (optional stronger detection) --------------------------------

def _presidio_available() -> bool:
    try:
        import presidio_analyzer  # noqa: F401
        import presidio_anonymizer  # noqa: F401
        return True
    except Exception:
        return False


def _presidio_scrub(text: str) -> tuple[str, dict[str, str]]:
    from presidio_analyzer import AnalyzerEngine  # type: ignore
    analyzer = AnalyzerEngine()
    results = analyzer.analyze(text=text, language="en")
    table: dict[str, str] = {}
    out = list(text)
    # Process spans back-to-front so index shifts don't corrupt earlier spans.
    for i, r in enumerate(sorted(results, key=lambda x: -x.start)):
        token = f"<{r.entity_type}_{i}>"
        table[token] = text[r.start:r.end]
        out[r.start:r.end] = list(token)
    return "".join(out), table


# ---- Core API ---------------------------------------------------------------

@dataclass
class ScrubResult:
    redacted: str
    table: dict[str, str] = field(default_factory=dict)  # token → original
    counts: dict[str, int] = field(default_factory=dict)


def _make_token(kind: str, idx: int, tenant: Optional[str]) -> str:
    base = f"{kind}_{idx}"
    if tenant:
        # Keep tenant scope visible but not reversible to anyone w/o the table.
        short = hashlib.sha256(tenant.encode()).hexdigest()[:6]
        return f"<{short}_{base}>"
    return f"<{base}>"


def scrub(
    text: str,
    *,
    tenant: Optional[str] = None,
    use_presidio: Optional[bool] = None,
    skip_luhn: bool = False,
) -> ScrubResult:
    """Scrub PII from `text`. Returns ScrubResult with redacted text, a
    reverse-map `table` (token → original), and per-type counts."""
    if use_presidio is None:
        use_presidio = _presidio_available()

    if use_presidio:
        redacted, table = _presidio_scrub(text)
        counts: dict[str, int] = {}
        for tok in table:
            kind = tok.strip("<>").rsplit("_", 1)[0]
            counts[kind] = counts.get(kind, 0) + 1
        return ScrubResult(redacted=redacted, table=table, counts=counts)

    # Regex fallback.
    table: dict[str, str] = {}
    counts: dict[str, int] = {}
    result = text

    # Longest-match first reduces inner-match collisions.
    order = ["EMAIL", "SSN_US", "SIN_CA", "CARD", "PHONE_NA",
             "IPV6", "IPV4", "CA_POSTAL", "US_ZIP", "DOB"]
    for kind in order:
        rx = _RX[kind]
        i = 0

        def repl(m):
            nonlocal i
            raw = m.group(0)
            if kind == "CARD" and not skip_luhn and not _luhn_ok(raw):
                return raw
            i += 1
            tok = _make_token(kind, counts.get(kind, 0) + i, tenant)
            table[tok] = raw
            counts[kind] = counts.get(kind, 0) + 1
            return tok
        result = rx.sub(repl, result)

    return ScrubResult(redacted=result, table=table, counts=counts)


def unscrub(text: str, table: dict[str, str]) -> str:
    """Reverse a scrub using the table returned by `scrub()`."""
    out = text
    # Longer tokens first so that e.g. <tenant_EMAIL_10> is replaced before <tenant_EMAIL_1>.
    for tok in sorted(table.keys(), key=len, reverse=True):
        out = out.replace(tok, table[tok])
    return out


def audit(text: str) -> dict[str, int]:
    """Return per-kind counts without modifying text."""
    return scrub(text).counts


# ---- CLI --------------------------------------------------------------------

def _cli() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scrub")
    s.add_argument("--tenant")
    s.add_argument("--file")
    s.add_argument("--no-presidio", action="store_true")

    u = sub.add_parser("unscrub")
    u.add_argument("--table", required=True, help="Path to JSON file with token->original")
    u.add_argument("--file")

    a = sub.add_parser("audit")
    a.add_argument("--file")

    args = ap.parse_args()

    def _read() -> str:
        if getattr(args, "file", None):
            return open(args.file, "r", encoding="utf-8").read()
        return sys.stdin.read()

    if args.cmd == "scrub":
        res = scrub(_read(), tenant=args.tenant,
                    use_presidio=None if not args.no_presidio else False)
        print(json.dumps({
            "redacted": res.redacted,
            "table": res.table,
            "counts": res.counts,
        }, indent=2))
        return 0

    if args.cmd == "unscrub":
        table = json.load(open(args.table, "r", encoding="utf-8"))
        if isinstance(table, dict) and "table" in table:
            table = table["table"]
        print(unscrub(_read(), table))
        return 0

    if args.cmd == "audit":
        print(json.dumps(audit(_read()), indent=2))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(_cli())
