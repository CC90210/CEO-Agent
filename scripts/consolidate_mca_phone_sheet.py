"""Consolidate CC's 2026-06-24 MCA lead phone sheet.

Reads the linked raw tab with phone1..phone5 plus context fields, uses the
existing Sheet1 one-number export as a supporting hint, and writes:

- raw tab K:L => best_phone_1, best_phone_2
- Sheet1 A:H  => clean dialer view with one/two phones plus context

The original raw phone columns are never overwritten.

Runs read-only by default. Pass ``--apply`` to write after reviewing the
computed totals/sample; sheet and tab targets are CLI-configurable.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CAPABILITY_META = {
    "category": "client.data_operations",
    "lifecycle": "one_off",
    "risk": "external_write",
    "triggers": ["consolidate mca phone sheet", "clean sunbiz phone leads", "build mca dialer sheet"],
    "owner": "bravo",
    "project": "sunbiz",
    "bridge": {"visible": False},
}

try:
    import phonenumbers  # type: ignore
except ImportError:  # pragma: no cover - local one-off script fallback
    phonenumbers = None

ROOT = Path(__file__).resolve().parent.parent
GTOOL = ROOT / "scripts" / "integrations" / "google_tool.py"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)

SHEET_ID = "1iSejOylhx7cMqd-GbEcdjLPPsKMShK0C9T4lMNhQ5bI"
RAW_TAB = "1750 MCA apps for admin@sunbizfunding.com MCA Apps 06-24-2026 (1)"
OUTPUT_TAB = "Sheet1"
RAW_RANGE = f"'{RAW_TAB}'!A1:J1753"
OUTPUT_HINT_RANGE = f"{OUTPUT_TAB}!A1:D1753"
RAW_WRITE_RANGE = f"'{RAW_TAB}'!K1:L1753"
OUTPUT_WRITE_RANGE = f"{OUTPUT_TAB}!A1:H1753"

RAW_HEADERS = [
    "phone1",
    "phone2",
    "phone3",
    "phone4",
    "phone5",
    "firstname",
    "lastname",
    "email",
    "company",
    "revenue",
]
OUTPUT_HEADERS = [
    "phone number",
    "phone 2",
    "first name",
    "last name",
    "email",
    "company",
    "revenue",
    "selection note",
]

# CC's stated source trust order: phone1/phone3 are the top tier, then
# phone2, phone4, phone5. phone3 gets a tiny nudge because the pre-existing
# Sheet1 export often selected it where phone1 and phone3 disagreed.
SOURCE_WEIGHT = {
    "phone1": 68,
    "phone3": 70,
    "phone2": 45,
    "phone4": 30,
    "phone5": 20,
}
SOURCE_INDEX = {name: i for i, name in enumerate(RAW_HEADERS[:5])}
COMPANY_SUFFIXES = {
    "llc",
    "inc",
    "corp",
    "corporation",
    "co",
    "company",
    "ltd",
    "limited",
    "lp",
    "pllc",
    "pc",
}


@dataclass
class Candidate:
    phone: str
    sources: list[str] = field(default_factory=list)
    score: int = 0
    sheet1_hint: bool = False


def gread(range_name: str, sheet_id: str = SHEET_ID) -> list[list[Any]]:
    proc = subprocess.run(
        [
            sys.executable,
            str(GTOOL),
            "sheets",
            "read",
            sheet_id,
            "--range",
            range_name,
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        creationflags=NOWIN,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"google_tool sheets read failed for {range_name}: "
            f"{(proc.stderr or proc.stdout).strip()}"
        )
    data = json.loads(proc.stdout or "{}")
    return data.get("values") or (data.get("data") or {}).get("values") or []


def gwrite(
    range_name: str, values: list[list[Any]], sheet_id: str = SHEET_ID
) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(GTOOL),
            "sheets",
            "write",
            sheet_id,
            "--range",
            range_name,
            "--json-values",
            json.dumps(values),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        creationflags=NOWIN,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"google_tool sheets write failed for {range_name}: "
            f"{(proc.stderr or proc.stdout).strip()}"
        )


def write_chunks(
    tab: str,
    start_col: str,
    end_col: str,
    values: list[list[Any]],
    chunk_size: int = 75,
    start_row: int = 1,
    sheet_id: str = SHEET_ID,
) -> None:
    quoted = f"'{tab}'" if any(ch in tab for ch in " @()-") else tab
    for offset in range(0, len(values), chunk_size):
        chunk = values[offset : offset + chunk_size]
        start = start_row + offset
        end = start + len(chunk) - 1
        try:
            gwrite(f"{quoted}!{start_col}{start}:{end_col}{end}", chunk, sheet_id)
        except RuntimeError:
            if chunk_size == 1 or len(chunk) == 1:
                raise
            for row_offset, row in enumerate(chunk):
                row_num = start + row_offset
                gwrite(
                    f"{quoted}!{start_col}{row_num}:{end_col}{row_num}",
                    [row],
                    sheet_id,
                )


def normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return ""
    if phonenumbers is not None:
        try:
            parsed = phonenumbers.parse(digits, "US")
            if not phonenumbers.is_valid_number(parsed):
                return ""
        except Exception:
            return ""
    # NANP: area code and exchange cannot start with 0/1. Also drop obvious
    # fake repeats such as 1111111111 or 9171111111.
    if digits[0] in "01" or digits[3] in "01":
        return ""
    if len(set(digits)) <= 2:
        return ""
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"


def clean_cell(value: Any, limit: int = 220) -> str:
    text = str(value if value is not None else "")
    text = text.replace("&", "and").replace('"', "").replace("|", "/")
    text = re.sub(r"[<>^%!`\r\n]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text and text[0] in "=+-@":
        text = " " + text
    return text[:limit]


def company_key(value: Any) -> str:
    text = re.sub(r"[^a-z0-9 ]", " ", str(value or "").lower())
    parts = [p for p in text.split() if p not in COMPANY_SUFFIXES]
    return "".join(parts)


def person_key(first: Any, last: Any = "") -> str:
    return re.sub(r"[^a-z]", "", f"{first or ''} {last or ''}".lower())


def split_name(first_field: Any, last_field: Any) -> tuple[str, str]:
    first = clean_cell(first_field, 80)
    last = clean_cell(last_field, 80)
    if last:
        return first, last
    parts = first.split()
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    return first, ""


def build_sheet1_hints(rows: list[list[Any]]) -> dict[str, set[str]]:
    hints: dict[str, set[str]] = defaultdict(set)
    for row in rows[1:]:
        cells = (list(row) + [""] * 4)[:4]
        phone = normalize_phone(cells[0])
        if not phone:
            continue
        ckey = company_key(cells[3])
        pkey = person_key(cells[1], cells[2])
        if ckey:
            hints[f"company:{ckey}"].add(phone)
        if ckey and pkey:
            hints[f"company_person:{ckey}:{pkey}"].add(phone)
    return hints


def candidate_scores(row: list[Any], hint_phones: set[str]) -> tuple[list[Candidate], dict[str, int]]:
    by_phone: dict[str, Candidate] = {}
    stats = {"invalid": 0, "hint_supported": 0}
    for source, idx in SOURCE_INDEX.items():
        raw = row[idx] if idx < len(row) else ""
        phone = normalize_phone(raw)
        if not raw:
            continue
        if not phone:
            stats["invalid"] += 1
            continue
        cand = by_phone.setdefault(phone, Candidate(phone=phone))
        cand.sources.append(source)

    for cand in by_phone.values():
        cand.score = max(SOURCE_WEIGHT[src] for src in cand.sources)
        if len(cand.sources) > 1:
            cand.score += 14 * (len(cand.sources) - 1)
        if {"phone1", "phone3"}.issubset(set(cand.sources)):
            cand.score += 28
        if cand.phone in hint_phones:
            cand.sheet1_hint = True
            cand.score += 24
            stats["hint_supported"] += 1

    ordered = sorted(
        by_phone.values(),
        key=lambda c: (
            c.score,
            c.sheet1_hint,
            "phone3" in c.sources,
            "phone1" in c.sources,
            -min(SOURCE_INDEX[s] for s in c.sources),
        ),
        reverse=True,
    )
    return ordered, stats


def select_phones(row: list[Any], hints: dict[str, set[str]]) -> tuple[str, str, str, dict[str, int]]:
    first, last = split_name(row[5] if len(row) > 5 else "", row[6] if len(row) > 6 else "")
    ckey = company_key(row[8] if len(row) > 8 else "")
    pkey = person_key(first, last)
    hint_phones = set()
    if ckey:
        hint_phones |= hints.get(f"company:{ckey}", set())
        if pkey:
            hint_phones |= hints.get(f"company_person:{ckey}:{pkey}", set())

    candidates, stats = candidate_scores(row, hint_phones)
    if not candidates:
        return "", "", "no valid NANP phone in phone1-phone5", stats

    primary = candidates[0]
    secondary = ""
    secondary_note = ""
    for cand in candidates[1:]:
        # Include a backup only when it has credible support: top-tier source,
        # Sheet1 support, duplicate presence, or phone2-level trust or better.
        credible = (
            cand.sheet1_hint
            or "phone1" in cand.sources
            or "phone3" in cand.sources
            or "phone2" in cand.sources
            or len(cand.sources) > 1
        )
        if credible:
            secondary = cand.phone
            secondary_note = f"; backup from {'/'.join(cand.sources)}"
            break

    support = "/".join(primary.sources)
    note_bits = [f"primary from {support}"]
    if len(primary.sources) > 1:
        note_bits.append("duplicate-supported")
    if primary.sheet1_hint:
        note_bits.append("matches existing Sheet1 export")
    note = ", ".join(note_bits) + secondary_note
    return primary.phone, secondary, note, stats


def build_outputs(raw_rows: list[list[Any]], sheet1_rows: list[list[Any]]) -> tuple[list[list[str]], list[list[str]], dict[str, int]]:
    if not raw_rows or [h.lower() for h in raw_rows[0][:10]] != RAW_HEADERS:
        raise RuntimeError(f"unexpected raw headers: {raw_rows[0] if raw_rows else '<empty>'}")

    hints = build_sheet1_hints(sheet1_rows)
    raw_out = [["best_phone_1", "best_phone_2"]]
    clean_out = [OUTPUT_HEADERS]
    totals = Counter(
        {
            "rows": 0,
            "primary": 0,
            "secondary": 0,
            "invalid_cells": 0,
            "hint_supported": 0,
        }
    )

    for source in raw_rows[1:]:
        row = (list(source) + [""] * 10)[:10]
        first, last = split_name(row[5], row[6])
        phone1, phone2, note, stats = select_phones(row, hints)
        totals["rows"] += 1
        totals["primary"] += bool(phone1)
        totals["secondary"] += bool(phone2)
        totals["invalid_cells"] += stats["invalid"]
        totals["hint_supported"] += stats["hint_supported"]

        raw_out.append([phone1, phone2])
        clean_out.append(
            [
                phone1,
                phone2,
                clean_cell(first, 80),
                clean_cell(last, 80),
                clean_cell(row[7], 140),
                clean_cell(row[8], 160),
                clean_cell(row[9], 40),
                clean_cell(note, 260),
            ]
        )

    # Pad output to wipe stale rows from Sheet1 if Google kept old data below.
    while len(clean_out) < 1753:
        clean_out.append([""] * len(OUTPUT_HEADERS))
    while len(raw_out) < 1753:
        raw_out.append(["", ""])
    return raw_out, clean_out, dict(totals)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="write the computed output")
    mode.add_argument(
        "--dry-run", action="store_true", help="compute only; do not write (default)"
    )
    parser.add_argument("--sample", type=int, default=0, help="rows to print (requires --show-pii)")
    parser.add_argument(
        "--show-pii", action="store_true",
        help="allow sampled names, emails, and phone numbers in terminal output",
    )
    parser.add_argument("--skip-raw", action="store_true", help="do not rewrite raw tab K:L")
    parser.add_argument("--output-start-row", type=int, default=1, help="resume Sheet1 write from this 1-based row")
    parser.add_argument("--sheet-id", default=SHEET_ID, help="source/output Google Sheet id")
    parser.add_argument("--raw-tab", default=RAW_TAB, help="raw lead-data tab")
    parser.add_argument("--output-tab", default=OUTPUT_TAB, help="clean dialer output tab")
    args = parser.parse_args()
    if args.sample and not args.show_pii:
        parser.error("--sample requires --show-pii")

    raw_range = f"'{args.raw_tab}'!A1:J1753"
    output_hint_range = f"{args.output_tab}!A1:D1753"
    raw_rows = gread(raw_range, args.sheet_id)
    sheet1_rows = gread(output_hint_range, args.sheet_id)
    raw_out, clean_out, totals = build_outputs(raw_rows, sheet1_rows)

    print(json.dumps(totals, indent=2))
    print("sample:")
    for row in clean_out[1 : 1 + args.sample]:
        print(" | ".join(row[:6]))

    if not args.apply:
        print("dry_run=true writes_skipped=true")
        return 0

    if not args.skip_raw:
        write_chunks(args.raw_tab, "K", "L", raw_out, chunk_size=75, sheet_id=args.sheet_id)
    output_start = max(1, args.output_start_row)
    write_chunks(
        args.output_tab,
        "A",
        "H",
        clean_out[output_start - 1 :],
        chunk_size=10,
        start_row=output_start,
        sheet_id=args.sheet_id,
    )
    print("writes_complete=true")
    print(f"raw_range='{args.raw_tab}'!K1:L1753")
    print(f"output_range={args.output_tab}!A1:H1753")
    print(f"https://docs.google.com/spreadsheets/d/{args.sheet_id}/edit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
