"""
research_fetch — Unified research-tier fetcher with auto-escalation + site-reputation memory.

The single entry point all research-heavy skills should call instead of choosing tiers
themselves. Escalates through tiers based on actual response + remembers which tier
worked per domain so the next call skips straight to the right one.

TIERS (escalation order, cheapest → most stealthy)
--------------------------------------------------
  1. Firecrawl     — scripts/firecrawl_tool.py scrape (cloud-side, clean markdown)
  2. CloakBrowser  — scripts/cloak_browser_tool.py scrape (stealth Chromium 146)
  3. Fail          — return ok=False with last-tier error

Escalation triggers (auto, no agent decision needed):
  - Firecrawl returns 403 / 429 / 5xx → escalate to CloakBrowser
  - Firecrawl returns text_chars < min_chars threshold → escalate (silent block)
  - Firecrawl raises (timeout, network) → escalate

SITE-REPUTATION MEMORY
----------------------
SQLite at state/site_reputation.db keyed by registered domain (e.g. www.cloudflare.com
collapses to cloudflare.com). Records:
  - last_tier_succeeded (firecrawl | cloak)
  - firecrawl_success_count / firecrawl_fail_count
  - cloak_success_count / cloak_fail_count
  - last_seen_at, first_seen_at

On fetch: start at `last_tier_succeeded` if reputation exists, else start at Firecrawl.
Saves the 200MB Chromium fire on domains where Firecrawl always works (singlekey.com,
example.com, most marketing sites). Burns straight through to Cloak on domains we
already know need it (truepeoplesearch.com, g2.com, indeed.com).

CLI USAGE
---------
    python scripts/research_fetch.py <url> [--json] [--force-tier {firecrawl,cloak}] [--min-chars N]
    python scripts/research_fetch.py reputation [domain]              # show one or all
    python scripts/research_fetch.py reputation-clear <domain>        # forget what we learned
    python scripts/research_fetch.py reputation-top [--limit N]       # most-seen domains

PROGRAMMATIC USAGE
------------------
    from research_fetch import fetch
    r = fetch("https://example.com")
    if r["ok"]:
        print(r["tier_used"], r["text"][:500])

RETURNS
-------
    {
        "ok": bool,
        "url": str,
        "final_url": str | None,
        "status": int | None,
        "title": str | None,
        "text": str,
        "text_chars": int,
        "tier_used": "firecrawl" | "cloak" | None,
        "tiers_tried": [str, ...],
        "errors": {tier: str, ...},   # only present if any tier failed
        "reputation": {"hit": bool, "start_tier": str},
    }

SAFETY
------
- Read-only fetcher. No sends, no clicks, no mutations.
- For CC-authenticated targets (Skool/Stripe/LinkedIn/Vercel dashboards) use
  Browser Harness instead — research_fetch is for fresh-session third-party reads.
- For interactive flows (forms, multi-step), call cloak_browser_tool.py goto directly.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
REPUTATION_DB = PROJECT_ROOT / "state" / "site_reputation.db"

DEFAULT_MIN_CHARS = 150  # tiny-page tolerance (example.com is ~200 chars)
TIER_TIMEOUT_SECONDS = 90

_RESET, _BOLD, _GREEN, _YELLOW, _CYAN, _RED, _DIM = (
    "\033[0m", "\033[1m", "\033[32m", "\033[33m", "\033[36m", "\033[31m", "\033[2m"
)


def _c(code: str, text: str, json_mode: bool) -> str:
    if json_mode or not sys.stdout.isatty():
        return text
    return f"{code}{text}{_RESET}"


# ── Reputation store ─────────────────────────────────────────────────────────

def _registered_domain(url: str) -> str:
    """Collapse hostname to its registered domain (e.g. www.foo.co.uk → foo.co.uk).
    Simple heuristic — strips leading www. Anything fancier needs publicsuffix2."""
    host = (urlparse(url).hostname or url).lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _db() -> sqlite3.Connection:
    REPUTATION_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(REPUTATION_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS site_reputation (
            domain TEXT PRIMARY KEY,
            last_tier_succeeded TEXT,
            firecrawl_success INTEGER NOT NULL DEFAULT 0,
            firecrawl_fail INTEGER NOT NULL DEFAULT 0,
            cloak_success INTEGER NOT NULL DEFAULT 0,
            cloak_fail INTEGER NOT NULL DEFAULT 0,
            last_seen_at TEXT NOT NULL,
            first_seen_at TEXT NOT NULL
        )
    """)
    return conn


def _reputation_lookup(domain: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT domain, last_tier_succeeded, firecrawl_success, firecrawl_fail, "
            "cloak_success, cloak_fail, last_seen_at, first_seen_at "
            "FROM site_reputation WHERE domain = ?",
            (domain,),
        ).fetchone()
    if not row:
        return None
    return {
        "domain": row[0],
        "last_tier_succeeded": row[1],
        "firecrawl_success": row[2],
        "firecrawl_fail": row[3],
        "cloak_success": row[4],
        "cloak_fail": row[5],
        "last_seen_at": row[6],
        "first_seen_at": row[7],
    }


def _reputation_record(domain: str, tier: str, succeeded: bool) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM site_reputation WHERE domain = ?", (domain,)
        ).fetchone()
        if existing:
            col_succ = f"{tier}_success"
            col_fail = f"{tier}_fail"
            if succeeded:
                conn.execute(
                    f"UPDATE site_reputation SET {col_succ} = {col_succ} + 1, "
                    f"last_tier_succeeded = ?, last_seen_at = ? WHERE domain = ?",
                    (tier, now, domain),
                )
            else:
                conn.execute(
                    f"UPDATE site_reputation SET {col_fail} = {col_fail} + 1, "
                    f"last_seen_at = ? WHERE domain = ?",
                    (now, domain),
                )
        else:
            col_succ = "firecrawl_success" if tier == "firecrawl" else "cloak_success"
            col_fail = "firecrawl_fail" if tier == "firecrawl" else "cloak_fail"
            conn.execute(
                f"INSERT INTO site_reputation (domain, last_tier_succeeded, "
                f"{col_succ}, {col_fail}, last_seen_at, first_seen_at) "
                f"VALUES (?, ?, ?, ?, ?, ?)",
                (
                    domain,
                    tier if succeeded else None,
                    1 if succeeded else 0,
                    0 if succeeded else 1,
                    now,
                    now,
                ),
            )
        conn.commit()


# ── Tier callers ─────────────────────────────────────────────────────────────

def _call_firecrawl(url: str) -> dict:
    """Invoke scripts/firecrawl_tool.py scrape <url> --json. Returns a normalized dict."""
    cmd = [sys.executable, str(SCRIPTS_DIR / "firecrawl_tool.py"), "scrape", url, "--json"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=TIER_TIMEOUT_SECONDS,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "firecrawl timeout", "status": None, "text": "", "title": None, "final_url": None}
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout or "firecrawl nonzero exit")[:300], "status": None, "text": "", "title": None, "final_url": None}
    try:
        raw = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "firecrawl returned non-json", "status": None, "text": "", "title": None, "final_url": None}
    md = raw.get("markdown") or raw.get("text") or ""
    metadata = raw.get("metadata") or {}
    status = metadata.get("statusCode") or metadata.get("status")
    title = metadata.get("title") or metadata.get("ogTitle")
    final_url = metadata.get("url") or metadata.get("sourceURL") or url
    return {
        "ok": True,
        "status": status,
        "text": md,
        "title": title,
        "final_url": final_url,
        "raw_metadata": metadata,
    }


def _call_cloak(url: str, timeout: int) -> dict:
    """Invoke scripts/cloak_browser_tool.py scrape <url> --json. Returns a normalized dict."""
    cmd = [
        sys.executable, str(SCRIPTS_DIR / "cloak_browser_tool.py"),
        "scrape", url, "--json", "--timeout", str(timeout),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout + 30,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "cloak timeout", "status": None, "text": "", "title": None, "final_url": None}
    try:
        raw = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "cloak returned non-json", "status": None, "text": "", "title": None, "final_url": None}
    return {
        "ok": bool(raw.get("ok")),
        "status": raw.get("status"),
        "text": raw.get("text", ""),
        "title": raw.get("title"),
        "final_url": raw.get("final_url"),
        "error": raw.get("error"),
    }


# ── Escalation logic ─────────────────────────────────────────────────────────

def _firecrawl_signals_block(result: dict, min_chars: int) -> bool:
    """Heuristics: should we escalate from Firecrawl to Cloak?

    Escalate when:
      - call errored (network/timeout/non-json)
      - status is 4xx (excluding 200) or 5xx → bot defense or server fault
      - text is empty (0 chars) regardless of status
      - status is missing AND text is below min_chars (likely a silent block page)
    """
    if not result.get("ok"):
        return True
    status = result.get("status")
    text = result.get("text", "")
    if isinstance(status, int):
        if status in (403, 429) or 400 <= status < 600 and status != 200:
            return True
    if not text:
        return True
    if status != 200 and len(text) < min_chars:
        return True
    return False


# ── Public API ───────────────────────────────────────────────────────────────

def fetch(
    url: str,
    *,
    force_tier: str | None = None,
    min_chars: int = DEFAULT_MIN_CHARS,
    cloak_timeout: int = 45,
    record_reputation: bool = True,
) -> dict:
    """Fetch a URL, auto-escalating through tiers until one succeeds.

    See module docstring for return shape.
    """
    domain = _registered_domain(url)
    rep = _reputation_lookup(domain)

    # Tier ordering — reputation-aware
    if force_tier in ("firecrawl", "cloak"):
        tiers = [force_tier]
    elif rep and rep["last_tier_succeeded"] == "cloak":
        tiers = ["cloak"]  # we already know this domain needs Cloak
    else:
        tiers = ["firecrawl", "cloak"]

    result: dict[str, Any] = {
        "ok": False,
        "url": url,
        "final_url": None,
        "status": None,
        "title": None,
        "text": "",
        "text_chars": 0,
        "tier_used": None,
        "tiers_tried": [],
        "errors": {},
        "reputation": {
            "hit": rep is not None,
            "start_tier": tiers[0],
            "domain": domain,
        },
    }

    for tier in tiers:
        result["tiers_tried"].append(tier)
        if tier == "firecrawl":
            r = _call_firecrawl(url)
            if r.get("ok") and not _firecrawl_signals_block(r, min_chars):
                if record_reputation:
                    _reputation_record(domain, "firecrawl", True)
                result.update({
                    "ok": True,
                    "tier_used": "firecrawl",
                    "status": r.get("status"),
                    "title": r.get("title"),
                    "final_url": r.get("final_url"),
                    "text": r.get("text", ""),
                    "text_chars": len(r.get("text", "")),
                })
                return result
            if record_reputation:
                _reputation_record(domain, "firecrawl", False)
            result["errors"]["firecrawl"] = r.get("error") or f"signals_block status={r.get('status')} chars={len(r.get('text',''))}"
        elif tier == "cloak":
            r = _call_cloak(url, cloak_timeout)
            # Soft-block tolerance: status=403 with non-trivial body is fine (G2 test 2026-05-15).
            # Accept any successful response with text; only reject empty.
            ok = bool(r.get("ok")) and len(r.get("text", "")) > 0
            if ok:
                if record_reputation:
                    _reputation_record(domain, "cloak", True)
                result.update({
                    "ok": True,
                    "tier_used": "cloak",
                    "status": r.get("status"),
                    "title": r.get("title"),
                    "final_url": r.get("final_url"),
                    "text": r.get("text", ""),
                    "text_chars": len(r.get("text", "")),
                })
                return result
            if record_reputation:
                _reputation_record(domain, "cloak", False)
            result["errors"]["cloak"] = r.get("error") or f"signals_block status={r.get('status')} chars={len(r.get('text',''))}"

    return result


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cmd_fetch(args) -> int:
    jm = args.output_json
    started = time.time()
    r = fetch(
        args.url,
        force_tier=args.force_tier,
        min_chars=args.min_chars,
        cloak_timeout=args.cloak_timeout,
    )
    r["elapsed_seconds"] = round(time.time() - started, 2)

    if jm:
        print(json.dumps(r, indent=2, default=str))
    else:
        mark = _c(_GREEN, "OK", jm) if r["ok"] else _c(_RED, "FAIL", jm)
        print(f"{mark}  {r['url']}")
        print(_c(_DIM, f"  tier_used={r['tier_used']}  tiers_tried={r['tiers_tried']}  reputation_hit={r['reputation']['hit']}", jm))
        print(_c(_DIM, f"  status={r['status']}  text_chars={r['text_chars']}  elapsed={r['elapsed_seconds']}s", jm))
        if r["title"]:
            print(_c(_DIM, f"  title={r['title'][:80]}", jm))
        if r["errors"]:
            for tier, err in r["errors"].items():
                print(_c(_YELLOW, f"  {tier}_error: {err}", jm))
        if r["text"]:
            print()
            print(r["text"][:2000])
            if r["text_chars"] > 2000:
                print(_c(_DIM, f"\n  ... ({r['text_chars'] - 2000} more chars)", jm))
    return 0 if r["ok"] else 1


def _cmd_reputation(args) -> int:
    jm = args.output_json
    if args.domain:
        domain = _registered_domain(args.domain) if "://" in args.domain or "." in args.domain else args.domain
        rep = _reputation_lookup(domain)
        if jm:
            print(json.dumps(rep or {"domain": domain, "found": False}, indent=2))
        else:
            if rep:
                print(_c(_BOLD + _CYAN, f"Reputation: {domain}", jm))
                for k, v in rep.items():
                    print(f"  {k}: {v}")
            else:
                print(_c(_DIM, f"No reputation recorded for {domain}", jm))
        return 0
    # All domains
    with _db() as conn:
        rows = conn.execute(
            "SELECT domain, last_tier_succeeded, firecrawl_success, firecrawl_fail, "
            "cloak_success, cloak_fail, last_seen_at FROM site_reputation "
            "ORDER BY last_seen_at DESC LIMIT ?",
            (args.limit,),
        ).fetchall()
    if jm:
        print(json.dumps([
            {"domain": r[0], "last_tier_succeeded": r[1], "firecrawl_success": r[2],
             "firecrawl_fail": r[3], "cloak_success": r[4], "cloak_fail": r[5],
             "last_seen_at": r[6]}
            for r in rows
        ], indent=2))
    else:
        print(_c(_BOLD + _CYAN, f"Site reputation — {len(rows)} domains", jm))
        for r in rows:
            tier = r[1] or "—"
            fc = f"FC {r[2]}/{r[2]+r[3]}"
            ck = f"CK {r[4]}/{r[4]+r[5]}"
            print(f"  {r[0]:<35} tier={tier:<9} {fc:<10} {ck:<10} last={r[6][:19]}")
    return 0


def _cmd_reputation_clear(args) -> int:
    domain = _registered_domain(args.domain) if "://" in args.domain or "." in args.domain else args.domain
    with _db() as conn:
        n = conn.execute("DELETE FROM site_reputation WHERE domain = ?", (domain,)).rowcount
        conn.commit()
    print(json.dumps({"ok": True, "domain": domain, "deleted": n}, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Unified research-tier fetcher (Firecrawl → CloakBrowser auto-escalation)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://example.com
  %(prog)s https://protected.com --json
  %(prog)s https://known-blocker.com --force-tier cloak
  %(prog)s reputation                       # all domains, most recent first
  %(prog)s reputation singlekey.com         # one domain
  %(prog)s reputation-clear truepeoplesearch.com

Skill: skills/research-fetch/SKILL.md
        """,
    )
    sub = p.add_subparsers(dest="command")

    # Default subcommand is implicit if first arg is a URL
    pf = sub.add_parser("fetch", help="Fetch a URL with auto-escalation")
    pf.add_argument("url")
    pf.add_argument("--force-tier", choices=["firecrawl", "cloak"], default=None)
    pf.add_argument("--min-chars", type=int, default=DEFAULT_MIN_CHARS)
    pf.add_argument("--cloak-timeout", type=int, default=45)
    pf.add_argument("--json", dest="output_json", action="store_true")

    pr = sub.add_parser("reputation", help="Show site reputation memory")
    pr.add_argument("domain", nargs="?", default=None)
    pr.add_argument("--limit", type=int, default=50)
    pr.add_argument("--json", dest="output_json", action="store_true")

    prc = sub.add_parser("reputation-clear", help="Forget reputation for a domain")
    prc.add_argument("domain")

    # Allow bare URL as first arg → fetch
    if len(sys.argv) >= 2 and sys.argv[1] not in {"fetch", "reputation", "reputation-clear", "-h", "--help"}:
        if sys.argv[1].startswith("http://") or sys.argv[1].startswith("https://"):
            sys.argv.insert(1, "fetch")

    args = p.parse_args()
    if not args.command:
        p.print_help()
        return 1
    if args.command == "fetch":
        return _cmd_fetch(args)
    if args.command == "reputation":
        return _cmd_reputation(args)
    if args.command == "reputation-clear":
        return _cmd_reputation_clear(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
