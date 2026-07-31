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
    python scripts/enrich_sheet_inplace.py --limit 8                # dry run
    python scripts/enrich_sheet_inplace.py --apply --workers 6      # write all leads
    python scripts/enrich_sheet_inplace.py --apply --resume         # continue writes
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import socket
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote_plus, urlsplit

CAPABILITY_META = {
    "category": "lead.data_operations",
    "lifecycle": "manual",
    "risk": "external_write",
    "triggers": ["enrich lead sheet", "find lead contact data", "update sheet enrichment"],
    "owner": "bravo",
    "project": "oasis",
    "bridge": {"visible": False},
}

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
sys.path.insert(0, str(ROOT / "scripts"))

DEFAULT_SHEET_ID = "1OJBuXsqzhWfOCQP6Kzsvjoa-nzgXPndVWCVg5N5IuXY"
DEFAULT_TAB = "Leads - Sheet31"
CKPT = ROOT / "tmp" / "sheet_enrich.json"
RESEARCH = ROOT / "scripts" / "research_fetch.py"
GTOOL = ROOT / "scripts" / "integrations" / "google_tool.py"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FETCH_HOST_ALLOWLIST = {
    "www.bing.com",
    "lite.duckduckgo.com",
    "html.duckduckgo.com",
}

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


def _is_public_http_url(url: str) -> bool:
    """Reject non-web, credentialed, local, and non-public-IP fetch targets."""
    try:
        parsed = urlsplit(str(url).strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        if parsed.username or parsed.password:
            return False
        host = parsed.hostname.rstrip(".").lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return False
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
            addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
        return bool(addresses) and all(address.is_global for address in addresses)
    except (OSError, ValueError, UnicodeError):
        return False


def _checkpoint_path(sheet_id: str, tab: str) -> Path:
    identity = hashlib.sha256(f"{sheet_id}\0{tab}".encode("utf-8")).hexdigest()[:12]
    return CKPT.with_name(f"{CKPT.stem}_{identity}{CKPT.suffix}")


def _checkpoint_payload(sheet_id: str, tab: str, done: dict[str, dict]) -> dict:
    return {"sheet_id": sheet_id, "tab": tab, "done": done}


def _render(url: str, timeout: int = 170) -> str | None:
    parsed = urlsplit(str(url).strip())
    if parsed.hostname not in FETCH_HOST_ALLOWLIST or not _is_public_http_url(url):
        return None
    try:
        r = subprocess.run([sys.executable, str(RESEARCH), url, "--json", "--force-tier", "cloak"],
                           capture_output=True, text=True, timeout=timeout, creationflags=NOWIN)
        if r.returncode != 0:
            return None
        d = json.loads(r.stdout or "{}")
        final_url = d.get("final_url") or url
        final_host = urlsplit(str(final_url)).hostname
        if final_host not in FETCH_HOST_ALLOWLIST or not _is_public_http_url(str(final_url)):
            return None
        return (d.get("text") or "") if d.get("ok") else None
    except Exception:  # noqa: BLE001
        return None


def _official_site_search_url(official_url: str, terms: str) -> str | None:
    """Turn an untrusted model URL into a query against a fixed search host."""
    if not _is_public_http_url(official_url):
        return None
    host = urlsplit(official_url).hostname
    if not host:
        return None
    return f"https://www.bing.com/search?q={quote_plus(f'site:{host} {terms}') }"


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
    if not serp or len(serp) < 400:
        fallback = _render(f"https://lite.duckduckgo.com/lite/?q={quote_plus((business + ' ' + (owner or '') + ' contact').strip())}")
        if fallback:
            serp = fallback
    if not serp:
        raise RuntimeError("search fetch returned no usable content")
    ext = _ask(business, address, owner, serp)
    if ext is None or not isinstance(ext.get("business_match"), bool):
        raise RuntimeError("model extraction returned no valid result")
    if ext.get("business_match") and ext.get("official_url") and not (ext.get("phone") and ext.get("email")):
        site_query = _official_site_search_url(
            str(ext["official_url"]), f"{business} contact phone email"
        )
        if not site_query:
            raise RuntimeError("official URL could not be converted to a safe search")
        site = _render(site_query)
        if not site:
            raise RuntimeError("supplemental search fetch returned no usable content")
        e2 = _ask(business, address, owner, serp[:3500] + "\n\n[OFFICIAL SITE]\n" + site)
        if e2 is None or not isinstance(e2.get("business_match"), bool):
            raise RuntimeError("supplemental model extraction returned no valid result")
        if e2.get("business_match"):
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
    url = str(res.get("official_url") or "").rstrip("/")
    if url:
        for terms in ("contact phone email", "about contact"):
            query_url = _official_site_search_url(url, terms)
            if not query_url:
                raise RuntimeError("official URL could not be converted to a safe search")
            t = _render(query_url)
            if not t:
                raise RuntimeError("deep supplemental search fetch returned no usable content")
            if t:
                blobs.append(f"[official-site search]\n{t[:3500]}")
            if len(blobs) >= 2:
                break
    if not res.get("phone") or not url:
        q = " ".join(x for x in [business, address] if x)
        for dom in ("yellowpages.com", "manta.com", "bbb.org"):
            t = _render(f"https://www.bing.com/search?q={quote_plus(q + ' ' + dom)}")
            if not t:
                raise RuntimeError("directory supplemental search fetch returned no usable content")
            if t:
                blobs.append(f"[directory {dom}]\n{t[:2500]}")
            if len(blobs) >= 4:
                break
    if blobs:
        e2 = _ask(business, address, owner, "\n\n".join(blobs))
        if e2 is None or not isinstance(e2.get("business_match"), bool):
            raise RuntimeError("deep model extraction returned no valid result")
        if e2.get("business_match"):
            for k in ("phone", "phone2", "email", "source_url", "official_url"):
                res[k] = res.get(k) or e2.get(k)
            res["business_match"] = True
            res["confidence"] = res.get("confidence") or e2.get("confidence")
    return res


def read_leads(sheet_id: str, tab: str) -> list[dict]:
    r = subprocess.run([sys.executable, str(GTOOL), "sheets", "read", sheet_id,
                        "--range", f"{tab}!B2:F2042", "--json"],
                       capture_output=True, text=True, timeout=120, creationflags=NOWIN)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "Google Sheets read failed").strip())
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


def write_row(row: int, res: dict, sheet_id: str, tab: str) -> int:
    phone = _us_phone(res.get("phone")) if res.get("business_match") else ""
    phone2 = _us_phone(res.get("phone2")) if res.get("business_match") else ""
    email = _valid_email(res.get("email")) if res.get("business_match") else ""
    conf = _safe(res.get("confidence") or "") if res.get("business_match") else ""
    src = _safe(res.get("source_url") or "") if res.get("business_match") else ""
    values = (("I", phone), ("J", email), ("K", phone2), ("L", conf), ("M", src))
    # Never replace an existing cell with a blank merely because one source or
    # model call failed to find that field. Only positive evidence is written.
    written = 0
    for column, value in values:
        if not value:
            continue
        rc = _gtool([
            "sheets", "write", sheet_id, "--range", f"{tab}!{column}{row}",
            "--json-values", json.dumps([[value]]),
        ])
        if rc != 0:
            raise RuntimeError(f"Google Sheets write failed for row {row} column {column}")
        written += 1
    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--deep", action="store_true", help="thorough multi-source pass")
    ap.add_argument("--retry-blanks", action="store_true",
                    help="re-attempt only rows that came back with no phone AND no email")
    ap.add_argument("--sheet-id", default=DEFAULT_SHEET_ID,
                    help="Google Sheet id (defaults to the original lead sheet)")
    ap.add_argument("--tab", default=DEFAULT_TAB,
                    help="Google Sheet tab containing the lead rows")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true",
                      help="write enrichment results and checkpoint progress")
    mode.add_argument("--dry-run", action="store_true",
                      help="compute and print results without writing (default)")
    ap.add_argument(
        "--show-pii", action="store_true",
        help="print business/contact values and the sheet URL (default output is redacted)",
    )
    args = ap.parse_args()

    ckpt = _checkpoint_path(args.sheet_id, args.tab)
    done: dict[str, dict] = {}
    if args.resume and ckpt.exists():
        payload = json.loads(ckpt.read_text(encoding="utf-8"))
        if payload.get("sheet_id") != args.sheet_id or payload.get("tab") != args.tab:
            raise RuntimeError("checkpoint target does not match --sheet-id/--tab")
        done = payload.get("done", {})
    leads = read_leads(args.sheet_id, args.tab)
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
    run_mode = "apply" if args.apply else "dry-run"
    print(f"mode={run_mode} leads={len(leads)} already_done={len(done)} "
          f"to_enrich={len(todo)} workers={args.workers}")

    # Fail-closed preflight (restores the run-level guard the SDK->CLI migration
    # removed — the old `cl = _anthropic()` raised SystemExit up front on a missing
    # key). If the subscription `claude` CLI is unavailable, ABORT before any write:
    # otherwise every enrich() returns {} -> write_row blanks columns I:M for each
    # row AND checkpoints it done, silently wiping real phone/email across the whole
    # sheet on a model outage, with no retry (the --resume default skips done rows).
    from lib.claude_cli import run_claude_cli
    if run_claude_cli("Reply with: ok", model="haiku", timeout=60) is None:
        print("ABORT: claude subscription CLI unavailable — refusing to run so rows "
              "are not blanked (run `claude setup-token`).", file=sys.stderr)
        return 1

    lock = threading.Lock()
    counters = {"n": 0, "phone": 0, "email": 0, "errors": 0}

    enrich = enrich_one_deep if args.deep else enrich_one

    def task(ld):
        try:
            res = enrich(ld["business"], ld["address"], ld["owner"])
        except Exception as exc:  # noqa: BLE001
            return ld, None, f"error {str(exc)[:120]}"
        return ld, res, None

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(task, ld) for ld in todo]
        for fut in as_completed(futs):
            ld, res, error = fut.result()
            if error is not None or not isinstance(res, dict):
                counters["errors"] += 1
                label = f" {ld['business'][:40]}" if args.show_pii else ""
                detail = (error or "invalid result") if args.show_pii else "enrichment failed"
                print(f"[ERROR] row{ld['row']}{label}: {detail}")
                continue
            if args.apply:
                write_row(ld["row"], res, args.sheet_id, args.tab)
            ph = _us_phone(res.get("phone")) if res.get("business_match") else ""
            em = res.get("email") if res.get("business_match") else ""
            if args.apply:
                done[str(ld["row"])] = {
                    "business": ld["business"], "phone": ph, "email": em or "",
                    "conf": res.get("confidence"), "note": res.get("note"),
                }
            with lock:
                counters["n"] += 1
                counters["phone"] += bool(ph)
                counters["email"] += bool(em)
                n = counters["n"]
            if args.apply and n % 10 == 0:
                ckpt.write_text(
                    json.dumps(_checkpoint_payload(args.sheet_id, args.tab, done), indent=2),
                    encoding="utf-8",
                )
            if args.show_pii:
                print(f"[{n}/{len(todo)}] row{ld['row']} {ld['business'][:26]:<26} "
                      f"ph={ph or '-':<14} em={(em or '-')[:24]:<24}")
            else:
                print(f"[{n}/{len(todo)}] row{ld['row']} "
                      f"match={bool(res.get('business_match'))} "
                      f"phone={bool(ph)} email={bool(em)}")

    if args.apply and done:
        ckpt.write_text(
            json.dumps(_checkpoint_payload(args.sheet_id, args.tab, done), indent=2),
            encoding="utf-8",
        )
    print(f"\n=== DONE ({run_mode}) === enriched={counters['n']} "
          f"phone={counters['phone']} email={counters['email']} errors={counters['errors']}")
    if args.show_pii:
        print(f"https://docs.google.com/spreadsheets/d/{args.sheet_id}/edit")
    else:
        print("target_sheet_configured=true pii_output=false")
    return 1 if counters["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
