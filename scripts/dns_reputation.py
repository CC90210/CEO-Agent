"""DNS reputation checks for the outbound sender domain.

This is intentionally a periodic doctor tool, not a per-send gate. DNS lookups
are too slow and too network-dependent to sit inside send_gateway.send().
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any


COMMON_DKIM_SELECTORS = [
    "google",
    "default",
    "selector1",
    "selector2",
    "k1",
    "mail",
]


def _run_nslookup(name: str, record_type: str) -> dict[str, Any]:
    if shutil.which("nslookup") is None:
        return {
            "ok": False,
            "records": [],
            "error": "nslookup not available on PATH",
        }
    try:
        proc = subprocess.run(
            ["nslookup", "-type=" + record_type, name],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "records": [], "error": str(exc)}

    combined = "\n".join(
        part for part in [proc.stdout.strip(), proc.stderr.strip()] if part
    )
    records: list[str] = []
    for line in combined.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        lower = cleaned.lower()
        if lower.startswith("text ="):
            records.append(cleaned.split("=", 1)[1].strip().strip('"'))
        elif "nameserver =" in lower:
            records.append(cleaned.split("=", 1)[1].strip())
        elif "mail exchanger =" in lower:
            records.append(cleaned.split("=", 1)[1].strip())
    return {
        "ok": proc.returncode == 0,
        "records": records,
        "raw": combined[:4000],
        "error": None if proc.returncode == 0 else combined[:500] or f"nslookup exit {proc.returncode}",
    }


def _first_txt(name: str) -> dict[str, Any]:
    lookup = _run_nslookup(name, "TXT")
    return {
        "name": name,
        "present": bool(lookup.get("records")),
        "records": lookup.get("records") or [],
        "error": lookup.get("error"),
    }


def check_sender_reputation(domain: str) -> dict[str, Any]:
    domain = (domain or "").strip().lower()
    if not domain:
        return {
            "domain": "",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "error": "domain required",
            "spf": {"present": False, "records": [], "error": "domain required"},
            "dmarc": {"present": False, "records": [], "error": "domain required"},
            "dkim": {"present": False, "selectors_checked": [], "records": {}, "error": "domain required"},
        }

    spf_lookup = _first_txt(domain)
    spf_records = [r for r in spf_lookup["records"] if r.lower().startswith("v=spf1")]

    dmarc_lookup = _first_txt(f"_dmarc.{domain}")
    dmarc_records = [r for r in dmarc_lookup["records"] if r.lower().startswith("v=dmarc1")]

    dkim_records: dict[str, list[str]] = {}
    dkim_errors: list[str] = []
    for selector in COMMON_DKIM_SELECTORS:
        lookup = _first_txt(f"{selector}._domainkey.{domain}")
        records = [
            r for r in lookup["records"]
            if "v=dkim1" in r.lower() or "k=rsa" in r.lower() or "p=" in r.lower()
        ]
        if records:
            dkim_records[selector] = records
        elif lookup.get("error"):
            dkim_errors.append(f"{selector}: {lookup['error']}")

    mx_lookup = _run_nslookup(domain, "MX")

    return {
        "domain": domain,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "spf": {
            "present": bool(spf_records),
            "records": spf_records,
            "error": spf_lookup.get("error") if not spf_records else None,
        },
        "dmarc": {
            "present": bool(dmarc_records),
            "records": dmarc_records,
            "error": dmarc_lookup.get("error") if not dmarc_records else None,
        },
        "dkim": {
            "present": bool(dkim_records),
            "selectors_checked": COMMON_DKIM_SELECTORS,
            "records": dkim_records,
            "error": None if dkim_records else "; ".join(dkim_errors[:3]) or "No common DKIM selectors resolved",
        },
        "mx": {
            "present": bool(mx_lookup.get("records")),
            "records": mx_lookup.get("records") or [],
            "error": mx_lookup.get("error"),
        },
        "summary": {
            "spf_present": bool(spf_records),
            "dmarc_present": bool(dmarc_records),
            "dkim_present": bool(dkim_records),
        },
    }


def format_reputation_report(report: dict[str, Any]) -> str:
    lines = [
        f"DNS reputation report for {report.get('domain') or '(unknown domain)'}",
        f"Checked at: {report.get('checked_at')}",
        f"SPF: {'present' if report.get('spf', {}).get('present') else 'missing'}",
    ]
    spf_records = report.get("spf", {}).get("records") or []
    if spf_records:
        lines.append(f"  {spf_records[0]}")
    elif report.get("spf", {}).get("error"):
        lines.append(f"  Error: {report['spf']['error']}")

    lines.append(f"DKIM: {'present' if report.get('dkim', {}).get('present') else 'missing'}")
    dkim_records = report.get("dkim", {}).get("records") or {}
    if dkim_records:
        for selector, records in dkim_records.items():
            lines.append(f"  {selector}: {records[0]}")
    elif report.get("dkim", {}).get("error"):
        lines.append(f"  Error: {report['dkim']['error']}")

    lines.append(f"DMARC: {'present' if report.get('dmarc', {}).get('present') else 'missing'}")
    dmarc_records = report.get("dmarc", {}).get("records") or []
    if dmarc_records:
        lines.append(f"  {dmarc_records[0]}")
    elif report.get("dmarc", {}).get("error"):
        lines.append(f"  Error: {report['dmarc']['error']}")

    mx_records = report.get("mx", {}).get("records") or []
    lines.append(f"MX: {'present' if report.get('mx', {}).get('present') else 'missing'}")
    if mx_records:
        lines.append(f"  {mx_records[0]}")
    elif report.get("mx", {}).get("error"):
        lines.append(f"  Error: {report['mx']['error']}")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Check SPF/DKIM/DMARC for a sender domain")
    parser.add_argument("domain")
    parser.add_argument("--json", dest="output_json", action="store_true")
    args = parser.parse_args()

    report = check_sender_reputation(args.domain)
    if args.output_json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(format_reputation_report(report))
