"""
CloakBrowser CLI Tool — Stealth Chromium for fresh-session work against bot-protected sites.

Drop-in Playwright replacement with C++ source-level fingerprint patches. Passes Cloudflare
Turnstile, reCAPTCHA v3 (~0.9 score), DataDome, ShieldSquare, FingerprintJS, BrowserScan.

WHEN TO USE
-----------
  - Fresh-session scrape against a site that blocks raw Playwright (Cloudflare etc.)
  - Lead/competitor research where Firecrawl returns 403/429 or empty content
  - Interactive flows on protected sites where no CC login exists
  Use Browser Harness instead when you need CC's authenticated session.
  Use Firecrawl instead for simple public scrapes (cheaper, faster, structured extraction).

USAGE
-----
  python scripts/cloak_browser_tool.py scrape <url> [--screenshot path] [--headed]
  python scripts/cloak_browser_tool.py goto <url> --eval "<js>"        # one-shot JS eval
  python scripts/cloak_browser_tool.py check-stealth                    # self-test against detection sites
  python scripts/cloak_browser_tool.py binary-info                      # show installed Chromium binary
  python scripts/cloak_browser_tool.py download                         # pre-fetch the ~200MB binary
  python scripts/cloak_browser_tool.py clear-cache                      # wipe binary cache (force redownload)

Flags
  --json          Output JSON for agent consumption
  --headed        Show browser window (debug only; default headless)
  --timeout N     Page load timeout in seconds (default 30)
  --proxy URL     Override proxy (else read CLOAK_PROXY_URL from .env.agents)
  --screenshot P  Save screenshot to path (scrape command)
  --user-agent S  Override User-Agent string

Credentials (all optional, all loaded from .env.agents via secret_loader):
  CLOAK_PROXY_URL       e.g. http://user:pass@gw.brightdata.com:22225 (residential proxy for max stealth)
  CLOAK_PROXY_USERNAME  Alternative to embedding in URL
  CLOAK_PROXY_PASSWORD  Alternative to embedding in URL
  CLOAK_TIMEZONE_ID     e.g. America/Toronto (else GeoIP'd from proxy/host)
  CLOAK_LOCALE          e.g. en-US (else GeoIP'd)

For the stealth fallback ladder + decision matrix, see skills/cloak-browser/SKILL.md
and skills/web-scraping/SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    from lib.secret_loader import load_env  # type: ignore
except Exception:  # pragma: no cover
    def load_env(required=None):
        return dict(os.environ)


_RESET, _BOLD, _GREEN, _YELLOW, _CYAN, _RED, _DIM = (
    "\033[0m", "\033[1m", "\033[32m", "\033[33m", "\033[36m", "\033[31m", "\033[2m"
)


def _c(code: str, text: str, json_mode: bool) -> str:
    if json_mode or not sys.stdout.isatty():
        return text
    return f"{code}{text}{_RESET}"


def _proxy_settings(env: dict, override: str | None):
    """Build a cloakbrowser.ProxySettings or None."""
    url = override or env.get("CLOAK_PROXY_URL")
    if not url:
        return None
    try:
        from cloakbrowser import ProxySettings  # type: ignore
    except ImportError:
        return None

    user = env.get("CLOAK_PROXY_USERNAME")
    pwd = env.get("CLOAK_PROXY_PASSWORD")
    if user and pwd:
        return ProxySettings(server=url, username=user, password=pwd)
    return ProxySettings(server=url)


def _launch_kwargs(env: dict, args) -> dict:
    """Common launch kwargs: headless, proxy, timezone, locale."""
    kw: dict[str, Any] = {"headless": not args.headed}
    proxy = _proxy_settings(env, args.proxy)
    if proxy is not None:
        kw["proxy"] = proxy
    tz = env.get("CLOAK_TIMEZONE_ID")
    if tz:
        kw["timezone_id"] = tz
    locale = env.get("CLOAK_LOCALE")
    if locale:
        kw["locale"] = locale
    if args.user_agent:
        kw["user_agent"] = args.user_agent
    return kw


def _import_cloak():
    try:
        import cloakbrowser  # type: ignore
        return cloakbrowser
    except ImportError:
        print("ERROR: cloakbrowser not installed. Run: pip install cloakbrowser", file=sys.stderr)
        sys.exit(1)


def _html_to_text(html: str) -> str:
    """Best-effort HTML → text. Uses bs4 if available, else naive strip."""
    try:
        from bs4 import BeautifulSoup  # type: ignore
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
    except ImportError:
        import re
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.I)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        return "\n".join(line.strip() for line in text.splitlines() if line.strip())


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_scrape(args, env: dict) -> int:
    """Load a page through the stealth Chromium and return text + metadata."""
    jm = args.output_json
    cb = _import_cloak()
    timeout_ms = max(1000, args.timeout * 1000)

    result: dict[str, Any] = {
        "url": args.url,
        "ok": False,
        "status": None,
        "title": None,
        "final_url": None,
        "text_chars": 0,
        "html_chars": 0,
        "screenshot": None,
        "stealth_chromium": cb.CHROMIUM_VERSION,
    }

    with cb.launch(**_launch_kwargs(env, args)) as browser:
        context = browser.new_context()
        page = context.new_page()
        try:
            response = page.goto(args.url, timeout=timeout_ms, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
            html = page.content()
            text = _html_to_text(html)
            result.update({
                "ok": True,
                "status": response.status if response else None,
                "title": page.title(),
                "final_url": page.url,
                "text_chars": len(text),
                "html_chars": len(html),
            })
            if args.screenshot:
                shot = Path(args.screenshot).resolve()
                shot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(shot), full_page=True)
                result["screenshot"] = str(shot)
            if jm:
                result["text"] = text
                result["html"] = html if args.include_html else None
            else:
                print(_c(_BOLD + _CYAN, f"Scraped: {result['title'] or args.url}", jm))
                print(_c(_DIM, f"  status={result['status']}  final={result['final_url']}", jm))
                print(_c(_DIM, f"  chromium={cb.CHROMIUM_VERSION}  text={result['text_chars']} chars", jm))
                if result["screenshot"]:
                    print(_c(_DIM, f"  screenshot={result['screenshot']}", jm))
                print()
                print(text)
        except Exception as exc:
            result["error"] = str(exc)
            if not jm:
                print(_c(_RED, f"FAILED: {exc}", jm), file=sys.stderr)
        finally:
            try:
                context.close()
            except Exception:
                pass

    if jm:
        print(json.dumps(result, indent=2, default=str))
    return 0 if result["ok"] else 1


def cmd_goto(args, env: dict) -> int:
    """Navigate to URL and optionally evaluate a JS expression."""
    cb = _import_cloak()
    timeout_ms = max(1000, args.timeout * 1000)

    result: dict[str, Any] = {"url": args.url, "ok": False, "status": None, "eval_result": None}
    with cb.launch(**_launch_kwargs(env, args)) as browser:
        context = browser.new_context()
        page = context.new_page()
        try:
            response = page.goto(args.url, timeout=timeout_ms, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
            result["ok"] = True
            result["status"] = response.status if response else None
            result["title"] = page.title()
            result["final_url"] = page.url
            if args.eval_js:
                result["eval_result"] = page.evaluate(args.eval_js)
        except Exception as exc:
            result["error"] = str(exc)
        finally:
            try:
                context.close()
            except Exception:
                pass

    print(json.dumps(result, indent=2, default=str))
    return 0 if result["ok"] else 1


def cmd_check_stealth(args, env: dict) -> int:
    """Self-test against bot-detection signals. Returns 0 if all checks pass."""
    jm = args.output_json
    cb = _import_cloak()
    timeout_ms = max(1000, args.timeout * 1000)

    checks: list[dict[str, Any]] = []

    # Five canonical fingerprint signals every modern bot detector probes:
    #   1. navigator.webdriver — true means automation framework
    #   2. window.chrome — namespace must exist (real Chrome) and be non-trivial
    #   3. navigator.plugins — empty array fingerprints headless
    #   4. navigator.languages — empty fingerprints headless
    #   5. WebGL vendor — SwiftShader/Brian Paul = software renderer, classic headless tell
    eval_payload = """() => {
        const chromeOk = (typeof window.chrome !== 'undefined') &&
                         (Object.keys(window.chrome || {}).length > 0);
        return {
            webdriver: navigator.webdriver,
            chrome_namespace: chromeOk,
            chrome_keys: typeof window.chrome !== 'undefined' ? Object.keys(window.chrome).slice(0, 8) : [],
            plugins_len: navigator.plugins ? navigator.plugins.length : 0,
            languages: navigator.languages || [],
            webgl_vendor: (() => {
                try {
                    const c = document.createElement('canvas').getContext('webgl');
                    const ext = c.getExtension('WEBGL_debug_renderer_info');
                    return c.getParameter(ext.UNMASKED_VENDOR_WEBGL);
                } catch (e) { return 'unavailable'; }
            })(),
            platform: navigator.platform,
            ua: navigator.userAgent,
        };
    }"""

    with cb.launch(**_launch_kwargs(env, args)) as browser:
        context = browser.new_context()
        page = context.new_page()
        try:
            # Use example.com (not about:blank) so extension/runtime context loads.
            page.goto("https://example.com", timeout=timeout_ms, wait_until="domcontentloaded")
            sig = page.evaluate(eval_payload)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
            return 1
        finally:
            context.close()

    checks.append({"name": "navigator.webdriver hidden",   "pass": sig["webdriver"] in (None, False), "value": sig["webdriver"]})
    checks.append({"name": "window.chrome namespace populated", "pass": bool(sig["chrome_namespace"]), "value": sig["chrome_keys"]})
    checks.append({"name": "plugins populated",            "pass": sig["plugins_len"] > 0,            "value": sig["plugins_len"]})
    checks.append({"name": "languages populated",          "pass": len(sig["languages"]) > 0,         "value": sig["languages"]})
    checks.append({"name": "WebGL vendor not SwiftShader", "pass": "swift" not in str(sig["webgl_vendor"]).lower() and "brian paul" not in str(sig["webgl_vendor"]).lower(), "value": sig["webgl_vendor"]})

    passed = sum(1 for c in checks if c["pass"])
    total = len(checks)
    payload = {
        "ok": passed == total,
        "passed": passed,
        "total": total,
        "chromium": cb.CHROMIUM_VERSION,
        "user_agent": sig["ua"],
        "platform": sig["platform"],
        "proxy_in_use": bool(env.get("CLOAK_PROXY_URL") or args.proxy),
        "checks": checks,
    }

    if jm:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(_c(_BOLD + _CYAN, f"CloakBrowser stealth check — {passed}/{total} passed", jm))
        print(_c(_DIM, f"  Chromium {cb.CHROMIUM_VERSION}  proxy={'yes' if payload['proxy_in_use'] else 'no'}", jm))
        for c in checks:
            mark = _c(_GREEN, "  PASS", jm) if c["pass"] else _c(_RED, "  FAIL", jm)
            print(f"{mark}  {c['name']}  ({c['value']})")
        print()
        if payload["ok"]:
            print(_c(_GREEN + _BOLD, "All stealth checks passed.", jm))
        else:
            print(_c(_RED + _BOLD, "Some stealth checks failed — see above.", jm))
    return 0 if payload["ok"] else 1


def cmd_binary_info(args, _env: dict) -> int:
    """Show the installed CloakBrowser Chromium binary location and version."""
    jm = args.output_json
    cb = _import_cloak()
    info = cb.binary_info() if hasattr(cb, "binary_info") else {}
    payload = {"chromium_version": cb.CHROMIUM_VERSION, "binary_info": info}
    if jm:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(_c(_BOLD + _CYAN, f"CloakBrowser binary", jm))
        print(_c(_DIM, f"  chromium_version={cb.CHROMIUM_VERSION}", jm))
        for k, v in (info or {}).items():
            print(f"  {k}={v}")
    return 0


def cmd_download(args, _env: dict) -> int:
    """Pre-fetch the ~200MB stealth Chromium binary."""
    jm = args.output_json
    cb = _import_cloak()
    if not jm:
        print(_c(_BOLD + _CYAN, "Pre-fetching CloakBrowser stealth Chromium (~200MB)...", jm))
    cb.ensure_binary() if hasattr(cb, "ensure_binary") else cb.download()
    info = cb.binary_info() if hasattr(cb, "binary_info") else {}
    payload = {"ok": True, "binary_info": info}
    if jm:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(_c(_GREEN + _BOLD, "Binary ready.", jm))
        for k, v in (info or {}).items():
            print(f"  {k}={v}")
    return 0


def cmd_clear_cache(args, _env: dict) -> int:
    """Wipe the cached binary so the next launch re-downloads."""
    jm = args.output_json
    cb = _import_cloak()
    if hasattr(cb, "clear_cache"):
        cb.clear_cache()
    payload = {"ok": True, "message": "cache cleared"}
    if jm:
        print(json.dumps(payload, indent=2))
    else:
        print(_c(_GREEN, "Cache cleared.", jm))
    return 0


# ── Entry point ──────────────────────────────────────────────────────────────

def _add_common_browser_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--headed", action="store_true", help="Show browser window (default headless)")
    p.add_argument("--timeout", type=int, default=30, help="Page load timeout seconds (default 30)")
    p.add_argument("--proxy", default=None, help="Override CLOAK_PROXY_URL")
    p.add_argument("--user-agent", default=None, dest="user_agent", help="Override User-Agent")
    p.add_argument("--json", dest="output_json", action="store_true", help="Output JSON")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CloakBrowser CLI — stealth Chromium for fresh-session bot-protected scraping",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s scrape https://nowsecure.nl
  %(prog)s scrape https://example.com --screenshot tmp/shot.png --json
  %(prog)s goto https://example.com --eval "() => document.title"
  %(prog)s check-stealth
  %(prog)s download

Skill:        skills/cloak-browser/SKILL.md
Decision matrix: skills/web-scraping/SKILL.md (Firecrawl vs Cloak vs Playwright vs Harness)
        """,
    )
    sub = parser.add_subparsers(dest="command", help="Command to execute")

    p_scrape = sub.add_parser("scrape", help="Load a page → text + metadata")
    p_scrape.add_argument("url")
    p_scrape.add_argument("--screenshot", default=None, help="Save full-page screenshot")
    p_scrape.add_argument("--include-html", action="store_true", help="Include raw HTML in JSON output")
    _add_common_browser_flags(p_scrape)

    p_goto = sub.add_parser("goto", help="Navigate + optional JS eval")
    p_goto.add_argument("url")
    p_goto.add_argument("--eval", dest="eval_js", default=None, help="JS expression to evaluate")
    _add_common_browser_flags(p_goto)

    p_check = sub.add_parser("check-stealth", help="Self-test against detection signals")
    _add_common_browser_flags(p_check)

    p_info = sub.add_parser("binary-info", help="Show installed Chromium binary info")
    p_info.add_argument("--json", dest="output_json", action="store_true")

    p_dl = sub.add_parser("download", help="Pre-fetch the ~200MB binary")
    p_dl.add_argument("--json", dest="output_json", action="store_true")

    p_cc = sub.add_parser("clear-cache", help="Wipe binary cache")
    p_cc.add_argument("--json", dest="output_json", action="store_true")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    try:
        env = dict(load_env())
    except Exception:
        env = dict(os.environ)

    handlers = {
        "scrape": cmd_scrape,
        "goto": cmd_goto,
        "check-stealth": cmd_check_stealth,
        "binary-info": cmd_binary_info,
        "download": cmd_download,
        "clear-cache": cmd_clear_cache,
    }
    try:
        return handlers[args.command](args, env)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        jm = getattr(args, "output_json", False)
        if jm:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
