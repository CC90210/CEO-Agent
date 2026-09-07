"""application_fields.py — read a merchant funding application with NO model.

CC's instruction, 2026-09-03: "A lot of these processes are easy, and I thought
we could really build Python scripts for most of this that are free and not
dependent on CLI."

He is right about this one. A merchant application is a FORM. Once
doc_text.py has the text, most of the fields are a label followed by a value on
the same line or the next one, plus a handful of formats (EIN, SSN, phone,
email, money, dates) that are unambiguous on sight. That does not need a
language model, it needs a parser — and a parser cannot hit a usage limit.

WHAT THIS IS FOR. This is the FLOOR of the tier ladder, not the ceiling. A model
still reads messy layouts better, so the daemon tries the Claude CLI first and
the free OpenCode model second. This tier exists so that when both are
unavailable the rep gets a part-filled application to correct instead of a red
error and a manual re-key. Partial beats blocked.

WHAT IT DELIBERATELY WILL NOT DO:
  - Guess. A label it does not recognise yields no field, never an inference.
    A wrong value silently filed into a funding application is worse than a
    blank one, because nobody re-checks a filled field.
  - Locate a signature. That needs pixels, not text; `_signature.present` is
    always false here and the daemon flags the extraction as degraded so the
    operator knows to place the signature by hand.

Every field carries provenance in the report, so a reviewer can see WHICH line
produced a value.
"""
from __future__ import annotations

import re
from typing import Any, Optional

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
    "VA", "WA", "WV", "WI", "WY", "DC", "PR",
}

ENTITY_TYPES = {
    "llc": "llc", "l.l.c": "llc", "limited liability": "llc",
    "s-corp": "s_corp", "s corp": "s_corp", "scorp": "s_corp", "subchapter s": "s_corp",
    "c-corp": "c_corp", "c corp": "c_corp", "ccorp": "c_corp", "corporation": "c_corp",
    "inc": "c_corp", "incorporated": "c_corp",
    "sole prop": "sole_proprietor", "sole-prop": "sole_proprietor", "proprietor": "sole_proprietor",
    "partnership": "partnership", "lp": "partnership", "llp": "partnership",
}

# ── value-shape patterns ────────────────────────────────────────────────────
RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
RE_PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.\-]?)?\(?([2-9]\d{2})\)?[\s.\-]?(\d{3})[\s.\-]?(\d{4})(?!\d)")
RE_EIN = re.compile(r"(?<!\d)(\d{2})[\-\s]?(\d{7})(?!\d)")
RE_SSN = re.compile(r"(?<!\d)(\d{3})[\-\s](\d{2})[\-\s](\d{4})(?!\d)")
RE_MONEY = re.compile(r"\$?\s*([0-9][0-9,]{2,})(?:\.(\d{2}))?")
RE_PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
RE_DATE = re.compile(
    r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\b"
    r"|\b(\d{4})-(\d{2})-(\d{2})\b"
    r"|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE,
)
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

# ── label synonyms → field ──────────────────────────────────────────────────
# Ordered longest-first at match time so "business legal name" beats "business".
LABELS: dict[str, tuple[str, ...]] = {
    "business_legal_name": (
        "legal business name", "business legal name", "legal name of business", "legal entity name",
        "company legal name", "registered business name", "business name", "company name",
        "legal name", "merchant name", "applicant business",
    ),
    "dba": ("dba", "d/b/a", "doing business as", "trade name", "dba name"),
    "business_address": (
        "business address", "company address", "physical address", "business street address",
        "street address", "corporate address", "location address",
    ),
    "business_state": ("state of incorporation", "state incorporated", "business state", "state"),
    "tax_id_ein": ("federal tax id", "tax id", "tax i.d", "ein", "employer identification", "fein", "federal id"),
    "business_start_date": (
        "date business started", "business start date", "date established", "inception date",
        "start date", "established", "date of incorporation", "in business since",
    ),
    "entity_type": ("entity type", "type of entity", "business type", "legal structure", "organization type"),
    "industry": ("industry", "type of business", "business category", "sic", "naics"),
    "product_service_description": ("products/services", "product or service", "description of business", "nature of business"),
    "contact_name": ("contact name", "primary contact", "contact person", "point of contact"),
    "email": ("email", "e-mail", "email address"),
    "phone": ("business phone", "company phone", "work phone", "office phone", "telephone", "phone"),
    "owner_full_name": (
        "owner name", "owner full name", "principal name", "guarantor name", "owner 1",
        "owner/officer", "first owner", "applicant name", "full name",
    ),
    "owner_ssn": ("owner ssn", "ssn", "social security", "social security number"),
    "owner_dob": ("owner dob", "date of birth", "dob", "birth date"),
    "owner_cell": ("owner cell", "cell phone", "mobile", "cell", "mobile phone", "home phone"),
    "owner_ownership_pct": ("ownership %", "ownership percentage", "% ownership", "ownership", "owned"),
    "owner_home_address": ("home address", "owner address", "residential address", "owner home address"),
    "partner_full_name": ("owner 2", "second owner", "partner name", "co-owner", "additional owner"),
    "partner_ssn": ("owner 2 ssn", "partner ssn"),
    "partner_dob": ("owner 2 dob", "partner dob"),
    "partner_cell": ("owner 2 cell", "partner cell"),
    "partner_ownership_pct": ("owner 2 ownership", "partner ownership"),
    "partner_home_address": ("owner 2 address", "partner address", "partner home address"),
    "monthly_revenue": (
        "average monthly revenue", "monthly revenue", "gross monthly sales", "monthly sales",
        "average monthly sales", "monthly gross", "avg monthly deposits", "monthly deposits",
    ),
    "requested_amount": (
        "amount requested", "requested amount", "funding amount", "amount of funding",
        "loan amount", "advance amount", "capital needed", "how much", "funding requested",
    ),
}

MONEY_FIELDS = {"monthly_revenue", "requested_amount"}
PCT_FIELDS = {"owner_ownership_pct", "partner_ownership_pct"}
DATE_FIELDS = {"business_start_date", "owner_dob", "partner_dob"}
PHONE_FIELDS = {"phone", "owner_cell", "partner_cell"}

# Flattened, longest label first — so a line with "business legal name" is not
# claimed by the shorter "business name".
_LABEL_INDEX: list[tuple[str, str]] = sorted(
    ((lab, fld) for fld, labs in LABELS.items() for lab in labs),
    key=lambda t: -len(t[0]),
)

_SEP = r"[:\-–—]|\s{2,}|\t"


def _norm_date(m: re.Match) -> Optional[str]:
    g = m.groups()
    try:
        if g[0]:  # M/D/Y
            mo, d, y = int(g[0]), int(g[1]), int(g[2])
            if y < 100:
                y += 2000 if y < 50 else 1900
            if mo > 12 and d <= 12:  # D/M/Y written by a non-US form
                mo, d = d, mo
            return f"{y:04d}-{mo:02d}-{d:02d}"
        if g[3]:  # ISO
            return f"{int(g[3]):04d}-{int(g[4]):02d}-{int(g[5]):02d}"
        if g[6]:  # Mon D, YYYY
            return f"{int(g[8]):04d}-{_MONTHS[g[6][:3].lower()]:02d}-{int(g[7]):02d}"
    except (ValueError, KeyError):
        return None
    return None


def _coerce(field: str, value: str) -> Optional[Any]:
    """Turn a raw captured string into the schema's type, or None if it isn't one."""
    v = value.strip().strip(".,;").strip()
    if not v or v.lower() in {"n/a", "na", "none", "-", "--", "x", "tbd"}:
        return None

    if field in MONEY_FIELDS:
        m = RE_MONEY.search(v)
        if not m:
            return None
        whole = m.group(1).replace(",", "")
        try:
            return float(f"{whole}.{m.group(2)}") if m.group(2) else float(whole)
        except ValueError:
            return None

    if field in PCT_FIELDS:
        m = RE_PCT.search(v) or re.search(r"(?<!\d)(\d{1,3}(?:\.\d+)?)(?!\d)", v)
        if not m:
            return None
        try:
            pct = float(m.group(1))
        except ValueError:
            return None
        return pct if 0 < pct <= 100 else None

    if field in DATE_FIELDS:
        m = RE_DATE.search(v)
        return _norm_date(m) if m else None

    if field == "tax_id_ein":
        m = RE_EIN.search(v)
        return f"{m.group(1)}-{m.group(2)}" if m else None

    if field in {"owner_ssn", "partner_ssn"}:
        m = RE_SSN.search(v)
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None

    if field == "email":
        m = RE_EMAIL.search(v)
        return m.group(0).lower() if m else None

    if field in PHONE_FIELDS:
        m = RE_PHONE.search(v)
        return f"({m.group(1)}) {m.group(2)}-{m.group(3)}" if m else None

    if field == "business_state":
        up = v.upper()
        m = re.search(r"\b([A-Z]{2})\b", up)
        if m and m.group(1) in US_STATES:
            return m.group(1)
        return None

    if field == "entity_type":
        low = v.lower()
        for needle, canon in ENTITY_TYPES.items():
            if needle in low:
                return canon
        return "other" if low else None

    # Free text. Reject a value that is obviously another label (an empty form
    # field followed immediately by the next question).
    if len(v) > 200:
        v = v[:200].rstrip()
    if any(v.lower().startswith(lab) for lab, _ in _LABEL_INDEX[:40]):
        return None
    return v or None


def _label_at(line_lower: str) -> Optional[tuple[str, str]]:
    """(field, label) when this line opens with a known label."""
    for label, field in _LABEL_INDEX:
        if line_lower.startswith(label):
            rest = line_lower[len(label):]
            # Must be followed by a separator or end-of-line, else "state" would
            # claim "statement of the business".
            if not rest or re.match(rf"^\s*(?:{_SEP})", rest) or rest[0] in " \t":
                return field, label
    return None


def extract_fields(text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parse application text. Returns (fields, report).

    `fields` uses the same keys as the model prompt in extraction_consumer.py, so
    a caller can hand it to the apply callback unchanged.
    """
    fields: dict[str, Any] = {}
    provenance: dict[str, str] = {}
    lines = [ln.rstrip() for ln in (text or "").splitlines()]

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        hit = _label_at(line.lower())
        if not hit:
            continue
        field, label = hit
        if field in fields:
            continue  # first occurrence wins; forms repeat labels in footers

        after = line[len(label):]
        after = re.sub(rf"^\s*(?:{_SEP})\s*", "", after, count=1).strip()

        value = _coerce(field, after) if after else None
        if value is None:
            # Value on the following line — the common layout for boxed forms.
            for nxt in lines[i + 1:i + 3]:
                cand = nxt.strip()
                if not cand or _label_at(cand.lower()):
                    continue
                value = _coerce(field, cand)
                if value is not None:
                    provenance[field] = f"line {i + 2}: {cand[:60]}"
                    break
        else:
            provenance[field] = f"line {i + 1}: {line[:60]}"

        if value is not None:
            fields[field] = value

    # Shape-only sweep for the unambiguous formats the form may not have
    # labelled at all. Only fills a field still missing.
    if "email" not in fields:
        m = RE_EMAIL.search(text or "")
        if m:
            fields["email"] = m.group(0).lower()
            provenance["email"] = "unlabelled email in document body"
    if "tax_id_ein" not in fields:
        m = RE_EIN.search(text or "")
        if m and m.group(1) != "00":
            fields["tax_id_ein"] = f"{m.group(1)}-{m.group(2)}"
            provenance["tax_id_ein"] = "unlabelled EIN-shaped number"
    if "phone" not in fields:
        m = RE_PHONE.search(text or "")
        if m:
            fields["phone"] = f"({m.group(1)}) {m.group(2)}-{m.group(3)}"
            provenance["phone"] = "unlabelled phone in document body"

    # A text parse cannot locate handwriting. Say so explicitly rather than
    # omitting the key, so the apply callback keeps its expected shape.
    fields["_signature"] = {"present": False, "page": None, "bbox": None}

    filled = [k for k in fields if k != "_signature"]
    report = {
        "method": "deterministic_regex",
        "fields_found": len(filled),
        "fields_possible": len(LABELS),
        "coverage": round(len(filled) / len(LABELS), 3),
        "found": sorted(filled),
        # Provenance is for a human reviewer. SSNs are excluded from it on
        # purpose — the value goes in the record, the source line does not go
        # in a log.
        "provenance": {k: v for k, v in provenance.items() if not k.endswith("_ssn")},
        "signature_detected": False,
    }
    return fields, report


# Fields that make an extraction worth applying at all. Below this the result is
# noise a rep would have to delete, so the daemon treats it as a miss.
CORE_FIELDS = ("business_legal_name", "dba", "email", "phone", "tax_id_ein",
               "owner_full_name", "requested_amount", "monthly_revenue", "business_address")
MIN_CORE_HITS = 3


def is_useful(fields: dict[str, Any]) -> bool:
    """True when the parse found enough for a rep to work from."""
    return sum(1 for f in CORE_FIELDS if fields.get(f) not in (None, "", [])) >= MIN_CORE_HITS
