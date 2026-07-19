"""enrich_sheet_inplace.py — enrich CC's live 'Leads - Sheet31' in place.

Reads each lead (Business Name=B, Business Address=C, Owner Name=F) and finds a
REAL published phone, secondary phone, and email via the Cloak stealth browser
(research_fetch --force-tier cloak) over a search engine + the company's own site;
Haiku extracts only data that LITERALLY appears on the fetched pages. Writes back
to columns I=Phone, J=Email, K=Phone 2, L=Confidence, M=Source on the SAME row.

Parallel (thread pool) for throughput; resumable via tmp/sheet_enrich.json; the
main thread serializes the per-row sheet writes so there is no write race.
Never fabricates — a confident blank is correct. SSN/home address are never read.

Usage:
    python scripts/enrich_sheet_inplace.py --workers 6              # all leads
    python scripts/enrich_sheet_inplace.py --workers 6 --limit 8    # smoke test
    python scripts/enrich_sheet_inplace.py --workers 6 --resume     # continue
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
sys.path.insert(0, str(ROOT / "scripts"))

SHEET_ID = "1OJBuXsqzhWfOCQP6Kzsvjoa-nzgXPndVWCVg5N5IuXY"
TAB = "Leads - Sheet31"
CKPT = ROOT / "tmp" / "sheet_enrich.json"
RESEARCH = ROOT / "scripts" / "research_fetch.py"
GTOOL = ROOT / "scripts" / "integrations" / "google_tool.py"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)

PROMPT = """You are enriching ONE business lead for a phone/email dialer. From the FETCHED CONTENT below, find the REAL published phone(s) and email for THIS specific company.

Business: {business}
Address: {address}
Owner / contact: {owner}

Return STRICT JSON ONLY:
{{"business_match": true|false, "phone": string|null, "phone2": string|null, "email": string|null, "official_url": string|null, "source_url": string|null, "confidence": "high"|"medium"|"low", "note": string}}

Hard rules:
- Use ONLY data that LITERALLY appears in the content below. NEVER invent or guess a number/email from an area code or pattern. Absent => null.
- business_match=true ONLY if the content clearly matches THIS company (name AND the city/state of the address). A same-name business elsewhere => business_match=false, all null.
- phone = main line; phone2 = a distinct secondary line if present (else null). Format digits/dashes.
- email = a real published address (prefer the owner/a person over info@, but info@/contact@ is fine).
- official_url = the company's own website if identifiable (else null). source_url = where the phone/email was read.
- confidence "high" only when name+location clearly match and the data is on a labelled contact source.
"""


def _render(url: str, timeout: int = 170) -> str:
    try:
        r = subprocess.run([sys.executable, str(RESEARCH), url, "--json", "--force-tier", "cloak"],
                           capture_output=True, text=True, timeout=timeout, creationflags=NOWIN)
        d = json.loads(r.stdout or "{}")
        return (d.get("text") or "") if d.get("ok") else ""
    except Exception:  # noqa: BLE001
        return ""


def _gtool(cmd: list[str]) -> int:
    return subprocess.run([sys.executable, str(GTOOL), *cmd, "--json"],
                          capture_output=True, text=True, timeout=120, creationflags=NOWIN).returncode


def _safe(v) -> str:
    s = str(v if v is not None else "")
    s = s.replace("&", "and").replace('"', "").replace("|", "/")
    s = re.sub(r"[<>^%!`\r\n]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if s and s[0] in "=+-@":
        s = " " + s
    return s[:200]


def _us_phone(v) -> str:
    d = re.sub(r"\D", "", str(v or ""))
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return f"{d[:3]}-{d[3:6]}-{d[6:]}" if len(d) == 10 else ""


def _valid_email(v) -> str:
    """Real address only — rejects obfuscation placeholders like
    '[email protected]' (Cloudflare/WordPress, no real @) and bare domains."""
    s = _safe(v)
    return s if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", s, re.I) else ""


def _ask(business, address, owner, blob) -> dict | None:
    from lib.claude_cli import run_claude_cli
    prompt = PROMPT.format(
        business=business, address=address or "(unknown)",
        owner=owner or "(unknown)") + "\n\nFETCHED CONTENT\n===============\n" + blob[:14000]
    text = run_claude_cli(prompt, model="haiku", timeout=90)
    if text is None:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def enrich_one(business, address, owner) -> dict:
    q = " ".join(x for x in [business, address, "phone"] if x)
    serp = _render(f"https://www.bing.com/search?q={quote_plus(q)}")
    if len(serp) < 400:
        serp = _render(f"https://lite.duckduckgo.com/lite/?q={quote_plus((business + ' ' + (owner or '') + ' contact').strip())}")
    if not serp:
        return {"business_match": False, "note": "no SERP content"}
    ext = _ask(business, address, owner, serp) or {}
    if ext.get("business_match") and ext.get("official_url") and not (ext.get("phone") and ext.get("email")):
        site = _render(ext["official_url"])
        if site:
            e2 = _ask(business, address, owner, serp[:3500] + "\n\n[OFFICIAL SITE]\n" + site)
            if e2 and e2.get("business_match"):
                for k in ("phone", "phone2", "email", "source_url"):
                    ext[k] = ext.get(k) or e2.get(k)
                ext["confidence"] = e2.get("confidence") or ext.get("confidence")
    return ext


def enrich_one_deep(business, address, owner) -> dict:
    """Thorough pass for the blanks: base SERP+site, then the company's
    contact/about pages (where emails live) + directory listings."""
    res = enrich_one(business, address, owner)
    if res.get("business_match") and res.get("phone") and res.get("email"):
        return res
    blobs: list[str] = []
    url = (res.get("official_url") or "").rstrip("/")
    if url:
        for path in ("/contact", "/contact-us", "/about", "/about-us"):
            t = _render(url + path)
            if t:
                blobs.append(f"[{url + path}]\n{t[:3500]}")
            if len(blobs) >= 2:
                break
    if not res.get("phone") or not url:
        q = " ".join(x for x in [business, address] if x)
        for dom in ("yellowpages.com", "manta.com", "bbb.org"):
            t = _render(f"https://www.bing.com/search?q={quote_plus(q + ' ' + dom)}")
            if t:
                blobs.append(f"[directory {dom}]\n{t[:2500]}")
            if len(blobs) >= 4:
                break
    if blobs:
        e2 = _ask(business, address, owner, "\n\n".join(blobs))
        if e2 and e2.get("business_match"):
            for k in ("phone", "phone2", "email", "source_url", "official_url"):
                res[k] = res.get(k) or e2.get(k)
            res["business_match"] = True
            res["confidence"] = res.get("confidence") or e2.get("confidence")
    return res


def read_leads() -> list[dict]:
    r = subprocess.run([sys.executable, str(GTOOL), "sheets", "read", SHEET_ID,
                        "--range", f"{TAB}!B2:F2042", "--json"],
                       capture_output=True, text=True, timeout=120, creationflags=NOWIN)
    d = json.loads(r.stdout or "{}")
    vals = d.get("values") or (d.get("data") or {}).get("values") or []
    leads = []
    for i, row in enumerate(vals):
        row = (list(row) + [""] * 5)[:5]   # B,C,D,E,F
        business = (row[0] or "").strip()
        if not business:
            continue
        leads.append({"row": i + 2, "business": business,
                      "address": (row[1] or "").strip(), "owner": (row[4] or "").strip()})
    return leads


def write_row(row: int, res: dict) -> None:
    phone = _us_phone(res.get("phone")) if res.get("business_match") else ""
    phone2 = _us_phone(res.get("phone2")) if res.get("business_match") else ""
    email = _valid_email(res.get("email")) if res.get("business_match") else ""
    conf = _safe(res.get("confidence") or "") if res.get("business_match") else ""
    src = _safe(res.get("source_url") or "") if res.get("business_match") else ""
    vals = [[phone, email, phone2, conf, src]]
    _gtool(["sheets", "write", SHEET_ID, "--range", f"{TAB}!I{row}:M{row}", "--json-values", json.dumps(vals)])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--deep", action="store_true", help="thorough multi-source pass")
    ap.add_argument("--retry-blanks", action="store_true",
                    help="re-attempt only rows that came back with no phone AND no email")
    args = ap.parse_args()

    done: dict[str, dict] = {}
    if args.resume and CKPT.exists():
        done = json.loads(CKPT.read_text(encoding="utf-8")).get("done", {})
    leads = read_leads()
    if args.retry_blanks:
        # only rows already attempted that came back with NOTHING
        def is_blank(ld):
            d = done.get(str(ld["row"]))
            return d is not None and not d.get("phone") and not d.get("email")
        todo = [ld for ld in leads if is_blank(ld)]
    else:
        todo = [ld for ld in leads if str(ld["row"]) not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"leads={len(leads)} already_done={len(done)} to_enrich={len(todo)} workers={args.workers}")

    lock = threading.Lock()
    counters = {"n": 0, "phone": 0, "email": 0}

    enrich = enrich_one_deep if args.deep else enrich_one

    def task(ld):
        try:
            res = enrich(ld["business"], ld["address"], ld["owner"])
        except Exception as exc:  # noqa: BLE001
            res = {"business_match": False, "note": f"error {str(exc)[:60]}"}
        return ld, res

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(task, ld) for ld in todo]
        for fut in as_completed(futs):
            ld, res = fut.result()
            write_row(ld["row"], res)               # serial write from main thread
            ph = _us_phone(res.get("phone")) if res.get("business_match") else ""
            em = res.get("email") if res.get("business_match") else ""
            done[str(ld["row"])] = {"business": ld["business"], "phone": ph, "email": em or "",
                                    "conf": res.get("confidence"), "note": res.get("note")}
            with lock:
                counters["n"] += 1
                counters["phone"] += bool(ph)
                counters["email"] += bool(em)
                n = counters["n"]
            if n % 10 == 0:
                CKPT.write_text(json.dumps({"done": done}, indent=2), encoding="utf-8")
            print(f"[{n}/{len(todo)}] row{ld['row']} {ld['business'][:26]:<26} ph={ph or '-':<14} em={(em or '-')[:24]:<24}")

    CKPT.write_text(json.dumps({"done": done}, indent=2), encoding="utf-8")
    print(f"\n=== DONE === enriched={counters['n']} phone={counters['phone']} email={counters['email']}")
    print(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
