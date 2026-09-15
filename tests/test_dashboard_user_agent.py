"""Every HTTP request to the OASIS dashboard must carry a User-Agent.

Cloudflare sits in front of oasisai.work with Browser Integrity Check ON. BIC
bans Python's default urllib User-Agent ("Python-urllib/3.x") by signature and
answers 403 with the body "error code: 1010" BEFORE the request reaches
Next.js. Nothing of ours runs, so a correct HMAC does not help and the route's
own logs stay empty.

That is not hypothetical. It took the application-drop feature down twice:
2026-08-31 (2 drops, unnoticed) and 2026-09-15 (5 drops in 14 minutes), and it
was silently dropping outbound send write-backs at the same time. Both were
mislabelled `dashboard_rejected_signature_403`, which sent the investigation
after a shared secret that was never wrong.

So the rule is mechanical, not a convention to remember: build dashboard
requests with scripts/lib/dashboard_http.dashboard_request(), which forces the
User-Agent on unconditionally. This test fails the build on a raw
urllib.request.Request whose URL comes from the dashboard, and proves itself by
scanning a planted violation.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCAN_ROOT = REPO / "scripts"

# Any of these in a URL expression means "this request goes to the dashboard".
DASHBOARD_MARKERS = (
    "_dashboard_base",
    "OASIS_DASHBOARD_URL",
    "PUBLIC_APP_URL",
    "DEFAULT_DASHBOARD_URL",
    "oasisai.work",
    "/api/internal/",
    "/api/outbound/",
)

# The seam itself is allowed to build the Request - that is its whole job.
EXEMPT_FILES = {"lib/dashboard_http.py"}


def _is_urllib_request_call(node: ast.AST) -> bool:
    """Match urllib.request.Request(...) and a bare Request(...) alias."""
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    if isinstance(f, ast.Attribute) and f.attr == "Request":
        return True
    return isinstance(f, ast.Name) and f.id == "Request"


def _url_expr_sources(call: ast.Call, tree: ast.AST, src: str) -> list[str]:
    """Source text of everything that could define this call's URL.

    The URL argument - positional OR the `url=` keyword - plus, when that
    argument is a bare name, every assignment to that name anywhere in the file.

    Both halves are load-bearing. Without name resolution, a
    `url = f"{base}/api/outbound/log"` two lines above the call reads as an
    opaque variable, which is exactly the shape outbound_log_post.py had while
    it was silently failing in production. Without the keyword form,
    `Request(url=dashboard_url)` walks straight past the guard (Codex review,
    2026-09-15).
    """
    first = None
    if call.args:
        first = call.args[0]
    else:
        for kw in call.keywords:
            if kw.arg == "url":
                first = kw.value
                break
    if first is None:
        return []
    out = [ast.get_source_segment(src, first) or ""]
    if isinstance(first, ast.Name):
        target = first.id
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == target for t in node.targets
            ):
                out.append(ast.get_source_segment(src, node.value) or "")
    return out


def _violations() -> list[str]:
    found: list[str] = []
    for path in sorted(SCAN_ROOT.rglob("*.py")):
        rel = path.relative_to(SCAN_ROOT).as_posix()
        if rel in EXEMPT_FILES or "__pycache__" in rel:
            continue
        src = path.read_text(encoding="utf-8", errors="replace")
        if "urllib" not in src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue  # a .bak or a partially-written file is not this test's job
        for node in ast.walk(tree):
            if not _is_urllib_request_call(node):
                continue
            blob = " ".join(_url_expr_sources(node, tree, src))
            if any(marker in blob for marker in DASHBOARD_MARKERS):
                found.append(f"{rel}:{node.lineno}")
    return found


def test_no_raw_urllib_request_to_the_dashboard():
    bad = _violations()
    assert not bad, (
        "These build a urllib Request to the dashboard directly, so it ships the "
        "default Python-urllib User-Agent that Cloudflare bans with 403 "
        '"error code: 1010" before Next.js sees it. Use '
        "lib.dashboard_http.dashboard_request() instead:\n  " + "\n  ".join(bad)
    )


def test_the_scan_actually_fires(tmp_path, monkeypatch):
    """Plant a violation and prove the scanner catches it.

    A guard nobody has seen fail is a guard nobody knows works. This writes a
    file with the exact shape of the 2026-09-15 bug - a dashboard URL built into
    a local variable, then handed to a raw urllib Request - and asserts the scan
    reports it. If this test ever passes while the one above cannot fail, the
    scanner has silently stopped scanning.
    """
    planted = tmp_path / "planted_violation.py"
    planted.write_text(
        textwrap.dedent(
            '''
            import urllib.request

            def post(base_url, body):
                url = f"{base_url}/api/internal/apply-extraction"
                req = urllib.request.Request(url, data=body, method="POST")
                return urllib.request.urlopen(req)

            def post_by_keyword(base_url, body):
                # Same bug, written the other way round. A guard that only reads
                # positional arguments waves this straight through.
                dashboard_url = f"{base_url}/api/outbound/log"
                req = urllib.request.Request(url=dashboard_url, data=body)
                return urllib.request.urlopen(req)
            '''
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    import sys

    monkeypatch.setattr(sys.modules[__name__], "SCAN_ROOT", tmp_path)
    bad = _violations()
    planted = [b for b in bad if "planted_violation.py" in b]
    assert planted, (
        "The planted violation was NOT detected - the scanner is no longer "
        "catching the bug it exists to catch."
    )
    assert len(planted) == 2, (
        "Both invocation forms must be caught - positional AND url= keyword. "
        f"Only found: {planted}"
    )


def test_the_seam_forces_the_user_agent():
    """The contract the rest of this file relies on, asserted directly."""
    import sys

    sys.path.insert(0, str(SCAN_ROOT))
    from lib.dashboard_http import OASIS_UA, classify_edge_block, dashboard_request

    # Forgot a UA entirely.
    r = dashboard_request("https://oasisai.work/api/internal/x", data=b"{}")
    assert r.get_header("User-agent") == OASIS_UA
    assert "urllib" not in OASIS_UA.lower()

    # Tried to set the banned default by hand, in any casing.
    r = dashboard_request(
        "https://oasisai.work/api/internal/x",
        data=b"{}",
        headers={"user-agent": "Python-urllib/3.12"},
    )
    assert r.get_header("User-agent") == OASIS_UA

    # The deliberate override, and the fact that it stays deliberate: omitting
    # it must still force our own UA, so the canary cannot become the way the
    # banned default creeps back in.
    from lib.dashboard_http import BANNED_PROBE_UA

    r = dashboard_request("https://oasisai.work/api/internal/x", data=b"{}",
                          user_agent=BANNED_PROBE_UA)
    assert r.get_header("User-agent") == BANNED_PROBE_UA
    r = dashboard_request("https://oasisai.work/api/internal/x", data=b"{}")
    assert r.get_header("User-agent") == OASIS_UA
    assert "urllib" in BANNED_PROBE_UA.lower(), "the probe must use the UA Cloudflare bans"

    # An edge denial is HTML from Cloudflare; ours is JSON. They must not be
    # confused, because they call for opposite actions.
    assert classify_edge_block(403, "error code: 1010") == "cloudflare_1010"
    assert classify_edge_block(403, '{"ok":false,"error":"bad_signature"}') is None
    assert classify_edge_block(401, '{"ok":false,"error":"bad_signature"}') is None


def test_a_busy_edge_is_not_a_banned_one():
    """A throttle must stay retryable; only a policy ban may go terminal.

    Conflating them loses a finished extraction over a thirty-second Cloudflare
    hiccup, because the caller marks a `blocked:` reason permanently failed.
    """
    import sys

    sys.path.insert(0, str(SCAN_ROOT))
    from lib.dashboard_http import classify_edge_block, edge_block_is_transient

    for status in (429, 503):
        reason = classify_edge_block(status, "<html>Cloudflare: please try again</html>")
        assert reason == f"edge_transient_{status}", reason
        assert edge_block_is_transient(reason), f"{status} must stay retryable"

    ban = classify_edge_block(403, "error code: 1010")
    assert not edge_block_is_transient(ban), "a 1010 ban must NOT be retried forever"

    # Our own rate limiter answering 429 in JSON is the dashboard, not the edge.
    assert classify_edge_block(429, '{"ok":false,"error":"rate_limited"}') is None
