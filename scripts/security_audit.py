"""Empire-wide security audit. Seven independent scans, one report.

Usage:
    python scripts/security_audit.py scan        # all 7 scans
    python scripts/security_audit.py secrets     # only the secret scan
    python scripts/security_audit.py injection   # only SQL/shell injection
    python scripts/security_audit.py perms       # only the secret_loader audit
    python scripts/security_audit.py evals       # only eval/exec scan
    python scripts/security_audit.py traversal   # only path-traversal scan
    python scripts/security_audit.py deps        # only dep vuln scan
    python scripts/security_audit.py guards      # only guard-mode posture

All produce a single-document JSON when invoked with --json.

The scans:
  1. Secret scan       — high-confidence regexes for API keys, tokens, passwords
  2. SQL injection     — raw query paths in supabase_tool / direct exec_sql calls
  3. Permission audit  — scripts still bypassing lib.secret_loader for .env reads
  4. Eval/exec scan    — unsafe `eval()`, `exec()`, `os.system()` with dynamic input
  5. Path traversal    — file reads/writes that interpolate user input
  6. Dependency audit  — `pip audit` if installed
  7. Guard modes       — production posture of EMPIRE_HOOK_* env vars

This script READS the codebase but never mutates it. It is safe to run in CI.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

EXCLUDE_DIRS = {
    "_archive", "__pycache__", "node_modules", ".venv", "venv",
    "in-progress", "state", "tmp", "media",
}
EXCLUDE_FILES = {
    ".env.agents", ".env.example", ".env.agents.template",
}


def _iter_py(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        if p.name in EXCLUDE_FILES:
            continue
        yield p


def _ok(name: str, detail: str = "") -> dict[str, Any]:
    return {"name": name, "status": "pass", "detail": detail, "findings": []}


def _warn(name: str, detail: str, findings: list[Any] | None = None) -> dict[str, Any]:
    return {"name": name, "status": "warn", "detail": detail, "findings": findings or []}


def _fail(name: str, detail: str, findings: list[Any] | None = None) -> dict[str, Any]:
    return {"name": name, "status": "fail", "detail": detail, "findings": findings or []}


# ── 1. Secret scan ─────────────────────────────────────────────────────

_SECRET_PATTERNS = [
    # OpenAI / Anthropic / Stripe / GitHub / generic high-entropy
    (re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"), "openai_or_anthropic_key"),
    (re.compile(r"sk_live_[a-zA-Z0-9]{20,}"), "stripe_live_key"),
    (re.compile(r"sk_test_[a-zA-Z0-9]{20,}"), "stripe_test_key"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36,}"), "github_personal_token"),
    (re.compile(r"gho_[a-zA-Z0-9]{36,}"), "github_oauth_token"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{35}"), "google_api_key"),
    (re.compile(r"eyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+"), "jwt_token"),
    (re.compile(r"xox[bpoa]-[a-zA-Z0-9\-]{10,}"), "slack_token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "aws_access_key"),
]


def scan_secrets() -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    for path in _iter_py(PROJECT_ROOT):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pat, label in _SECRET_PATTERNS:
            for m in pat.finditer(text):
                # Exclude obvious test fixtures
                snippet = text[max(0, m.start() - 20): m.end() + 20]
                if any(marker in snippet.lower() for marker in
                       ("example", "fake", "dummy", "placeholder", "test-")):
                    continue
                line_no = text.count("\n", 0, m.start()) + 1
                hits.append({
                    "file": str(path.relative_to(PROJECT_ROOT)),
                    "line": line_no,
                    "kind": label,
                    "preview": snippet[:80],
                })
    if not hits:
        return _ok("Secret Scan", "0 secrets found in codebase")
    return _fail("Secret Scan", f"{len(hits)} suspected secrets — rotate immediately", hits[:25])


# ── 2. SQL / shell injection ───────────────────────────────────────────

_RAW_SQL_PATTERNS = [
    re.compile(r"execute\s*\(\s*f['\"]"),
    re.compile(r"executemany\s*\(\s*f['\"]"),
    re.compile(r"rpc\s*\(\s*['\"]exec_sql['\"].*\+\s*[a-zA-Z_]"),
    re.compile(r"\.sql\s*\(\s*f['\"]"),
]


def scan_injection() -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    for path in _iter_py(PROJECT_ROOT):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pat in _RAW_SQL_PATTERNS:
            for m in pat.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                line = text.splitlines()[line_no - 1] if line_no <= len(text.splitlines()) else ""
                hits.append({
                    "file": str(path.relative_to(PROJECT_ROOT)),
                    "line": line_no,
                    "snippet": line.strip()[:140],
                })
    if not hits:
        return _ok("SQL Injection", "0 f-string SQL or interpolated exec_sql calls")
    return _warn("SQL Injection",
                 f"{len(hits)} raw SQL paths — confirm parameterization", hits[:25])


# ── 3. Permission audit ────────────────────────────────────────────────

_DOTENV_PATTERNS = [
    re.compile(r"from\s+dotenv\s+import\s+load_dotenv"),
    re.compile(r"load_dotenv\s*\("),
    re.compile(r"open\s*\(\s*[^)]*\.env\.agents[^)]*\)"),
]


def scan_permissions() -> dict[str, Any]:
    hits: list[str] = []
    for path in _iter_py(PROJECT_ROOT):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # secret_loader.py itself is allowed to read .env.agents
        if path.name == "secret_loader.py":
            continue
        for pat in _DOTENV_PATTERNS:
            if pat.search(text):
                hits.append(str(path.relative_to(PROJECT_ROOT)))
                break
    if not hits:
        return _ok("Permissions", "0 scripts bypass lib.secret_loader")
    return _warn("Permissions",
                 f"{len(hits)} scripts still load .env.agents directly", hits[:30])


# ── 4. Eval / exec scan ────────────────────────────────────────────────

_EVAL_PATTERNS = [
    re.compile(r"\beval\s*\("),
    re.compile(r"\bexec\s*\("),
    re.compile(r"os\.system\s*\("),
    re.compile(r"subprocess\.(call|run|Popen)\s*\([^)]*shell\s*=\s*True"),
]


def scan_evals() -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    for path in _iter_py(PROJECT_ROOT):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pat in _EVAL_PATTERNS:
            for m in pat.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                # Skip the security audit itself + test files looking for patterns
                if path.name in ("security_audit.py", "test_security_audit.py"):
                    continue
                hits.append({
                    "file": str(path.relative_to(PROJECT_ROOT)),
                    "line": line_no,
                    "pattern": pat.pattern,
                })
    if not hits:
        return _ok("Eval/Exec Scan", "0 unsafe eval/exec/os.system calls")
    return _warn("Eval/Exec Scan",
                 f"{len(hits)} dynamic-code call sites — review for user input",
                 hits[:25])


# ── 5. Path traversal ──────────────────────────────────────────────────

_TRAVERSAL_PATTERNS = [
    re.compile(r"open\s*\(\s*request\.[a-z_]+"),
    re.compile(r"open\s*\(\s*args\.[a-z_]+"),
    re.compile(r"Path\s*\(\s*request\.[a-z_]+"),
]


def scan_traversal() -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    for path in _iter_py(PROJECT_ROOT):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pat in _TRAVERSAL_PATTERNS:
            for m in pat.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                hits.append({
                    "file": str(path.relative_to(PROJECT_ROOT)),
                    "line": line_no,
                })
    if not hits:
        return _ok("File Traversal", "0 unchecked dynamic file paths")
    return _warn("File Traversal",
                 f"{len(hits)} dynamic file paths — verify sanitization", hits[:20])


# ── 6. Dependency vuln scan ────────────────────────────────────────────

def scan_dependencies() -> dict[str, Any]:
    pip_audit = shutil.which("pip-audit") or shutil.which("pip_audit")
    if pip_audit:
        try:
            result = subprocess.run(
                [pip_audit, "-f", "json"], capture_output=True,
                text=True, timeout=60, cwd=str(PROJECT_ROOT),
            )
        except (subprocess.SubprocessError, OSError) as exc:
            return _warn("Dependencies", f"pip-audit failed: {exc}")
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                vulns = data.get("vulnerabilities", data) if isinstance(data, dict) else data
                count = len(vulns) if isinstance(vulns, list) else 0
                if count == 0:
                    return _ok("Dependencies", "pip-audit reports 0 vulnerabilities")
                return _warn("Dependencies", f"pip-audit found {count} vulnerabilities",
                             vulns[:10] if isinstance(vulns, list) else [])
            except json.JSONDecodeError:
                return _warn("Dependencies", "pip-audit output not parseable")
        return _warn("Dependencies", f"pip-audit exit {result.returncode}")
    return _warn("Dependencies", "pip-audit not installed (pip install pip-audit)")


# ── 7. Guard-mode posture ──────────────────────────────────────────────

def scan_guards() -> dict[str, Any]:
    secret = os.environ.get("EMPIRE_HOOK_SECRET_GUARD", "report").lower()
    exec_g = os.environ.get("EMPIRE_HOOK_EXEC_GUARD", "report").lower()
    state_g = os.environ.get("EMPIRE_HOOK_STATE_GUARD", "off").lower()
    posture = {"secret": secret, "exec": exec_g, "state": state_g}
    if secret == "off":
        return _fail("Guard Modes", "secret_guard=off (must be report or enforce)",
                     [posture])
    if exec_g == "off":
        return _warn("Guard Modes", "exec_guard=off — should be report or enforce",
                     [posture])
    if exec_g == "report" or state_g != "enforce":
        return _warn("Guard Modes",
                     "production should run all three guards in enforce mode",
                     [posture])
    return _ok("Guard Modes", "all three guards in enforce mode")


SCANNERS = {
    "secrets":   scan_secrets,
    "injection": scan_injection,
    "perms":     scan_permissions,
    "evals":     scan_evals,
    "traversal": scan_traversal,
    "deps":      scan_dependencies,
    "guards":    scan_guards,
}


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    if counts["fail"]:
        overall = "CRITICAL_FINDINGS"
    elif counts["warn"]:
        overall = "PASS_WITH_WARNINGS"
    else:
        overall = "CLEAN"
    return {"overall": overall, **counts, "total": len(results)}


def render_text(report: dict[str, Any]) -> str:
    glyph = {"pass": "[PASS]", "warn": "[WARN]", "fail": "[FAIL]"}
    lines = ["Empire Security Audit", "=" * 60]
    for r in report["results"]:
        lines.append(f"{r['name']:18s} {glyph.get(r['status'], '[??]')} {r['detail']}")
        for f in r.get("findings", [])[:3]:
            if isinstance(f, dict) and "file" in f:
                lines.append(f"    - {f.get('file')}:{f.get('line', '?')} "
                             f"({f.get('kind') or f.get('pattern') or f.get('snippet', '')[:60]})")
            else:
                lines.append(f"    - {f}")
    s = report["summary"]
    lines.append("=" * 60)
    lines.append(f"Overall: {s['overall']} ({s['pass']}/{s['total']} pass, "
                 f"{s['warn']} warn, {s['fail']} fail)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["scan"] + list(SCANNERS.keys()), default="scan", nargs="?")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.action == "scan":
        results = [SCANNERS[k]() for k in SCANNERS]
    else:
        results = [SCANNERS[args.action]()]
    report = {"results": results, "summary": _summarize(results)}

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render_text(report))

    return 0 if report["summary"]["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
