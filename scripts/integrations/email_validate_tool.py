"""email_validate_tool.py — free, zero-key email validation via Disify.

Checks format / DNS / disposable-domain status for an email address using the
Disify public API (https://www.disify.com — no signup, no key; Free-Tier Radar
row `disify-email-validate`, adopted V7.1.0). Primary use: lead-list hygiene
before outreach — flag disposable/undeliverable addresses so they never reach
send_gateway. NOT wired into send_gateway itself (chokepoint changes are a
separate operator-approved task).

USAGE
-----
    python scripts/integrations/email_validate_tool.py check <email> [--json]
    python scripts/integrations/email_validate_tool.py batch <file> [--json]   # one email per line, max 200

EXIT CODES
----------
    0 — API answered (verdict is in the output, including disposable=true)
    1 — bad invocation (missing/unreadable file, no emails)
    2 — validation unavailable (network/API failure after retries)

NOTES
-----
- No credentials required, so `lib.secret_loader` is deliberately NOT invoked:
  loading every empire secret into a zero-key tool violates least-privilege
  (RULE 3) for no gain. If Disify ever adds a keyed tier, migrate to the
  standard `from lib.secret_loader import load_env` pattern.
- Disify 403-blocks default urllib/curl User-Agents; a browser UA is required
  (verified live 2026-07-17). This is a public no-auth API — the header is a
  compatibility requirement, not an auth bypass.
- Windows TLS: `truststore` (OS cert store) is injected when available, per the
  2026-07-17 Supabase CA-bundle lesson.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

try:  # Windows console defaults to cp1252 — same guard harness_eval.py uses
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

try:  # Windows: prefer the OS trust store (certifi bundles miss corporate/OS roots)
    import truststore  # noqa: E402

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001
    pass

from lib.retry import retry, RetryConfig  # noqa: E402

DISIFY_BASE = "https://www.disify.com/api/email"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BATCH_LIMIT = 200
BATCH_DELAY_SEC = 0.35  # be polite to a free no-auth service


def _ping_health(status: str, error: str | None = None) -> None:
    """Best-effort Command Center green-dot update. Never raises."""
    try:
        from integration_health import ping  # noqa: E402

        ping("disify", status=status, error=error)
    except Exception:  # noqa: BLE001
        pass


@retry(RetryConfig(max_retries=3, base_delay=0.5))
def _fetch(email: str) -> dict:
    url = f"{DISIFY_BASE}/{urllib.parse.quote(email)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def _check_one(email: str) -> dict:
    """Return {email, ok, format, dns, disposable, ...} — ok=False means API unreachable."""
    try:
        data = _fetch(email)
    except Exception as e:  # noqa: BLE001
        return {"email": email, "ok": False, "error": f"{type(e).__name__}: {e}"}
    data["email"] = email
    data["ok"] = True
    return data


def _human_line(r: dict) -> str:
    if not r.get("ok"):
        return f"  ?  {r['email']}  — validation unavailable ({r.get('error', '')[:80]})"
    flags = []
    if not r.get("format"):
        flags.append("BAD-FORMAT")
    if r.get("disposable"):
        flags.append("DISPOSABLE")
    if r.get("format") and not r.get("dns"):
        flags.append("NO-DNS")
    verdict = ", ".join(flags) if flags else "clean"
    return f"  {'✗' if flags else '✓'}  {r['email']}  — {verdict}"


def cmd_check(args: argparse.Namespace) -> int:
    result = _check_one(args.email)
    _ping_health("healthy" if result["ok"] else "degraded",
                 None if result["ok"] else result.get("error"))
    if args.output_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(_human_line(result))
    return 0 if result["ok"] else 2


def cmd_batch(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1
    emails = [ln.strip() for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines()
              if ln.strip() and not ln.strip().startswith("#")]
    if not emails:
        print("error: no emails in file", file=sys.stderr)
        return 1
    if len(emails) > BATCH_LIMIT:
        print(f"note: truncating to first {BATCH_LIMIT} of {len(emails)} emails", file=sys.stderr)
        emails = emails[:BATCH_LIMIT]
    results = []
    for i, email in enumerate(emails):
        results.append(_check_one(email))
        if i < len(emails) - 1:
            time.sleep(BATCH_DELAY_SEC)
    reached = sum(1 for r in results if r["ok"])
    _ping_health("healthy" if reached else "degraded",
                 None if reached else "all lookups failed")
    if args.output_json:
        print(json.dumps({"total": len(results), "reachable": reached,
                          "flagged": sum(1 for r in results if r.get("ok") and
                                         (r.get("disposable") or not r.get("format"))),
                          "results": results}, indent=2, default=str))
    else:
        for r in results:
            print(_human_line(r))
        print(f"\n{len(results)} checked, {reached} answered, "
              f"{sum(1 for r in results if r.get('ok') and (r.get('disposable') or not r.get('format')))} flagged")
    return 0 if reached else 2


def main() -> int:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--json", dest="output_json", action="store_true",
                        help="machine-readable output")
    p = argparse.ArgumentParser(description="Free email validation via Disify (no key needed)")
    sub = p.add_subparsers(dest="command")
    pc = sub.add_parser("check", parents=[parent], help="Validate one email address")
    pc.add_argument("email")
    pb = sub.add_parser("batch", parents=[parent], help="Validate a file of emails (one per line)")
    pb.add_argument("file")
    args = p.parse_args()
    if args.command == "check":
        return cmd_check(args)
    if args.command == "batch":
        return cmd_batch(args)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
