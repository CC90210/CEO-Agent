#!/usr/bin/env python3
"""system_health — the Loud-Failures probe (V7 EPIC 7).

Surfaces SILENT failures BEFORE someone trips over them. The 2026-06-06 audit found four
bugs live for days/weeks because subprocess + DEVNULL + bare-except = invisible failure
(retriever_postedit path drift, event_router stale PM2 path, wizard wrong path). This probe
is the standing regression check for that whole class.

Probes (each → green / yellow / red; red fails --strict):
  1. cron-scripts   — every SEED_JOBS action_config.script exists on disk AND py-compiles
  2. hook-targets   — every command in .claude/settings.local.json hooks points at a real file
  3. mcp-wrappers   — every MCP server in MCP_CONFIG_PATHS references a wrapper that exists
  4. pm2-paths      — no PM2 daemon for THIS repo has a stale/missing pm_exec_path (the
                      CEO-Agent → Business-Empire-Agent rename class); online daemons noted
  5. path-drift     — no `scripts/<x>.py` reference in scripts/ + hooks + bravo_cli fails to resolve
  6. subprocess-raw — count production subprocess.run/Popen OUTSIDE lib/ + tests (yellow if > 0)
  7. silent-except  — count `except …: pass|return None` without a breadcrumb (yellow if > threshold)

Usage:
  python scripts/system_health.py [--json] [--strict] [--notify]

  --strict  exit 1 on any red. For humans and CI — NOT for the cron.
  --notify  Telegram on any red, deduped on WHICH checks are red.

WHY THE CRON DOES NOT USE --strict (2026-08-03): a weekly probe that exits 1 on a
finding is read by the scheduler as a BROKEN CRON, and cron_health_check then
re-pages "1 cron(s) failing" every hour for as long as the condition holds. The
finding was real; the delivery turned it into a metronome. Per EXECUTION_RULES
§ 19, a blocking condition exits 0 and reports — so the cron runs `--json --notify`
and the probe raises its own alarm, once, with backoff.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
try:
    from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402
except Exception:
    WINDOWLESS_FLAGS = 0

RED, YELLOW, GREEN = "red", "yellow", "green"
SKIP_DIRS = {"_archive", "node_modules", ".venv", "tmp", "__pycache__", "tests"}
# Example / placeholder path tokens — a reference containing one of these is a docstring
# sample or brace-glob, not a real dependency (e.g. scheduler.py's `"script": "scripts/foo.py"`
# cron example, or `scripts/state/{secret,exec,state}_guard.py` brace notation).
EXAMPLE_TOKENS = ("foo", "bar", "baz", "example", "placeholder", "your", "dummy", "sample", "<", "{", "}")


def _is_example(ref: str) -> bool:
    low = ref.lower()
    return any(tok in low for tok in EXAMPLE_TOKENS)


def _pm2(args):
    """Run pm2 cross-platform (Windows pm2 is a .cmd shim → needs shell)."""
    if os.name == "nt":
        return subprocess.run("pm2 " + " ".join(args), shell=True, capture_output=True,
                              text=True, timeout=15, creationflags=WINDOWLESS_FLAGS)
    return subprocess.run(["pm2", *args], capture_output=True, text=True, timeout=15)  # noqa: SUBPROCESS (POSIX branch; creationflags is Windows-only)


def _result(name, status, detail, items=None):
    return {"check": name, "status": status, "detail": detail, "items": items or []}


def _py_files(*roots):
    for root in roots:
        base = PROJECT_ROOT / root
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            yield p


# ── 1. cron scripts exist + parse ──────────────────────────────────────────
def check_cron_scripts():
    cron = PROJECT_ROOT / "scripts" / "core" / "cron_engine.py"
    if not cron.exists():
        return _result("cron-scripts", YELLOW, "cron_engine.py not found")
    refs = re.findall(r'"script"\s*:\s*"([^"]+)"', cron.read_text(encoding="utf-8"))
    missing, unparsable = [], []
    for rel in sorted(set(refs)):
        f = PROJECT_ROOT / rel
        if not f.exists():
            missing.append(rel)
        elif f.suffix == ".py":
            try:
                compile(f.read_text(encoding="utf-8"), str(f), "exec")
            except SyntaxError:
                unparsable.append(rel)
    if missing or unparsable:
        return _result("cron-scripts", RED,
                       f"{len(missing)} missing, {len(unparsable)} unparsable of {len(set(refs))} cron scripts",
                       missing + [f"{u} (syntax)" for u in unparsable])
    return _result("cron-scripts", GREEN, f"all {len(set(refs))} SEED_JOBS scripts exist + parse")


# ── 2. hook targets exist ───────────────────────────────────────────────────
def check_hook_targets():
    settings = PROJECT_ROOT / ".claude" / "settings.local.json"
    if not settings.exists():
        return _result("hook-targets", YELLOW, "settings.local.json not found")
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except Exception as e:
        return _result("hook-targets", RED, f"settings.local.json unparsable: {e}")
    missing = []
    for event, entries in (data.get("hooks") or {}).items():
        for entry in entries:
            for hk in entry.get("hooks", []):
                cmd = hk.get("command", "")
                for m in re.findall(r'([A-Za-z]:[\\/][^\s"]+\.py|scripts[\\/][^\s"]+\.py)', cmd):
                    fp = Path(m) if Path(m).is_absolute() else PROJECT_ROOT / m
                    if not fp.exists():
                        missing.append(f"{event}: {m}")
    if missing:
        return _result("hook-targets", RED, f"{len(missing)} hook target(s) missing", missing)
    return _result("hook-targets", GREEN, "all hook command targets resolve")


# ── 3. MCP wrappers exist ───────────────────────────────────────────────────
def check_mcp_wrappers():
    audit = PROJECT_ROOT / "scripts" / "audit_mcp_secrets.py"
    if not audit.exists():
        return _result("mcp-wrappers", YELLOW, "audit_mcp_secrets.py not found")
    # Resolve MCP_CONFIG_PATHS by importing the module's constant (no secret values touched).
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_amcp", audit)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        paths = [Path(p) for p in getattr(mod, "MCP_CONFIG_PATHS", [])]
    except Exception as e:
        return _result("mcp-wrappers", YELLOW, f"could not load MCP_CONFIG_PATHS: {str(e)[:80]}")
    present = [p for p in paths if p.exists()]
    missing_wrappers = []
    for cfg in present:
        try:
            blob = cfg.read_text(encoding="utf-8")
        except Exception:
            continue
        # find wrapper .cmd / .py / .mjs script references; verify any repo-relative ones exist
        for m in re.findall(r'scripts[\\/][^\s"]+\.(?:py|cmd|mjs|sh)', blob):
            if _is_example(m):
                continue  # brace-glob / placeholder, not a literal path
            fp = PROJECT_ROOT / m.replace("\\", "/")
            if not fp.exists():
                missing_wrappers.append(f"{cfg.name}: {m}")
    if missing_wrappers:
        return _result("mcp-wrappers", RED, f"{len(missing_wrappers)} MCP wrapper(s) missing", missing_wrappers)
    return _result("mcp-wrappers", GREEN, f"{len(present)}/{len(paths)} MCP configs present; referenced wrappers resolve")


# ── 4. PM2 path audit ───────────────────────────────────────────────────────
def check_pm2_paths():
    try:
        r = _pm2(["jlist"])
        procs = json.loads(r.stdout or "[]")
    except Exception as e:
        return _result("pm2-paths", YELLOW, f"pm2 unavailable / jlist failed: {str(e)[:80]}")
    stale, online = [], 0
    root_name = PROJECT_ROOT.name  # "Business-Empire-Agent"
    for p in procs:
        exec_path = (p.get("pm2_env", {}) or {}).get("pm_exec_path", "") or ""
        status = (p.get("pm2_env", {}) or {}).get("status", "")
        if status == "online":
            online += 1
        # flag daemons that belong to THIS repo (by old or new name) but point at a dead path
        looks_ours = "CEO-Agent" in exec_path or root_name in exec_path
        if looks_ours and exec_path and not Path(exec_path).exists():
            stale.append(f"{p.get('name')}: {exec_path}")
        elif "CEO-Agent" in exec_path and root_name not in exec_path:
            stale.append(f"{p.get('name')}: stale repo name → {exec_path}")
    if stale:
        return _result("pm2-paths", RED, f"{len(stale)} stale/dead PM2 path(s) ({online} online)", stale)
    return _result("pm2-paths", GREEN, f"{len(procs)} daemons, {online} online; no stale paths for this repo")


# ── 5. path-drift detector ──────────────────────────────────────────────────
# Catches BOTH reference shapes that caused the V6→V7 incidents:
#   (a) string literal           "scripts/core/memory_retriever.py"
#   (b) segmented Path build      REPO_ROOT / "scripts" / "state" / "state_manager.py"
# (b) is the incident-#1/#3 class — a hardcoded internal script path behind an .exists()
# guard that silently became always-False after the file moved into a subpackage.
_LITERAL_RE = re.compile(r'["\'](scripts/[A-Za-z0-9_./-]+\.py)["\']')
_SEGMENT_RE = re.compile(r'["\']scripts["\']\s*(?:/\s*["\'][A-Za-z0-9_.-]+["\']\s*)+')
_SEG_TOKEN = re.compile(r'["\']([A-Za-z0-9_.-]+)["\']')


# Line-scoped opt-out. Some references are deliberately unresolvable HERE because
# they name a sibling repo's filename — agent_genome.py's DEFAULTS are candidate
# lists ("the gene is expressed if ANY candidate exists"), so Bravo carries
# scripts/bravo_sleep.py while a sibling carries scripts/agent_sleep.py. Creating
# the file to satisfy the checker would be inventing a dependency. The marker is
# per-LINE, not per-file, so a genuine drift elsewhere in the same file still reds.
_DRIFT_OK = "path-drift-ok"


def _drift_refs(text):
    """Yield every repo-relative scripts/*.py path referenced in source (both shapes)."""
    for m in _LITERAL_RE.findall(text):
        yield m
    for chunk in _SEGMENT_RE.findall(text):
        segs = _SEG_TOKEN.findall(chunk)  # ['scripts', 'state', 'state_manager.py']
        if segs and segs[-1].endswith(".py"):
            yield "/".join(segs)


def _suppressed_refs(text):
    """Refs the file explicitly marks as deliberate, scoped to THIS file.

    Scanned separately from _drift_refs so the detector keeps scanning the whole
    blob — a segmented Path build wrapped across lines must still be caught, which
    a line-by-line detector would silently stop seeing.
    """
    out = set()
    for line in text.splitlines():
        if _DRIFT_OK not in line:
            continue
        out.update(_drift_refs(line))
    return out


def check_path_drift():
    drift = []
    for f in _py_files("scripts", "bravo_cli"):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        allowed = _suppressed_refs(text) if _DRIFT_OK in text else set()
        for ref in _drift_refs(text):
            if _is_example(ref):
                continue  # docstring sample (scripts/foo.py etc.), not a real dependency
            if ref in allowed:
                continue  # deliberate cross-repo candidate, marked at the call site
            if not (PROJECT_ROOT / ref).exists():
                drift.append(f"{f.relative_to(PROJECT_ROOT)} → {ref}")
    drift = sorted(set(drift))
    if drift:
        return _result("path-drift", RED, f"{len(drift)} unresolved scripts/*.py reference(s)", drift[:20])
    return _result("path-drift", GREEN, "every scripts/*.py reference in code resolves (literal + segmented)")


# ── 6. raw subprocess sweep (informational) ─────────────────────────────────
def check_subprocess_raw():
    raw = []
    pat = re.compile(r"\bsubprocess\.(?:run|Popen|call|check_output)\(")
    for f in _py_files("scripts"):
        rel = str(f.relative_to(PROJECT_ROOT))
        if "lib/subprocess_helpers" in rel.replace("\\", "/") or "/lib/" in rel.replace("\\", "/"):
            continue
        try:
            n = len(pat.findall(f.read_text(encoding="utf-8", errors="ignore")))
        except Exception:
            n = 0
        if n:
            raw.append((rel, n))
    total = sum(n for _, n in raw)
    status = YELLOW if total > 0 else GREEN
    return _result("subprocess-raw", status,
                   f"{total} raw subprocess call(s) across {len(raw)} files (prefer lib/subprocess_helpers)",
                   [f"{r}: {n}" for r, n in sorted(raw, key=lambda x: -x[1])[:12]])


# ── 7. silent-except sweep (informational) ──────────────────────────────────
def check_silent_except():
    swallow = re.compile(r"except[^\n:]*:\s*\n\s*(?:pass|return\s+None)\b")
    hits = []
    for f in _py_files("scripts"):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        n = len(swallow.findall(text))
        if n:
            hits.append((str(f.relative_to(PROJECT_ROOT)), n))
    total = sum(n for _, n in hits)
    status = YELLOW if total > 25 else GREEN
    return _result("silent-except", status,
                   f"{total} bare swallow(s) (except→pass/return None) across {len(hits)} files; add breadcrumbs to the worst",
                   [f"{r}: {n}" for r, n in sorted(hits, key=lambda x: -x[1])[:12]])


CHECKS = [check_cron_scripts, check_hook_targets, check_mcp_wrappers, check_pm2_paths,
          check_path_drift, check_subprocess_raw, check_silent_except]


def run():
    results = []
    for c in CHECKS:
        try:
            results.append(c())
        except Exception as e:
            results.append(_result(c.__name__, YELLOW, f"probe error: {type(e).__name__}: {str(e)[:100]}"))
    reds = [r for r in results if r["status"] == RED]
    yellows = [r for r in results if r["status"] == YELLOW]
    return {"reds": len(reds), "yellows": len(yellows), "checks": results}


def red_dedup_key(rep) -> str:
    """Identity for repeat-suppression: WHICH checks are red, not how they read.

    The detail strings carry counts and file lists that drift between runs, so
    keying on the rendered message defeats dedup entirely — the other half of how
    an alert storm happens (FLEET_ALERT_DISCIPLINE, dedup property #2).
    """
    names = sorted(r["check"] for r in rep["checks"] if r["status"] == RED)
    return f"system_health_red:{'|'.join(names)}"


def notify_reds(rep) -> bool:
    """Raise the alarm the cron used to raise by dying. Loud on failure."""
    reds = [r for r in rep["checks"] if r["status"] == RED]
    if not reds:
        return False
    lines = [f"🔴 system_health: {len(reds)} red"]
    for r in reds:
        lines.append(f"• {r['check']}: {r['detail']}")
        for it in r["items"][:5]:
            lines.append(f"   - {it}")
    try:
        import notify as _nf  # type: ignore
        # Suppressed != failed. Treating a deduped alert as a delivery failure
        # would make this probe exit 1 and present as a broken cron — the exact
        # thing dropping --strict was for. cron_health_check learned this the
        # hard way the same day.
        _, reason = _nf.notify_result("\n".join(lines), category="system",
                                      force=True, dedup_key=red_dedup_key(rep))
        return reason in _nf.DELIVERED_REASONS
    except Exception as exc:  # noqa: BLE001 — never silent: the probe IS the alarm
        print(f"[system_health] notify failed: {type(exc).__name__}: {str(exc)[:200]}",
              file=sys.stderr)
        return False


def main():
    ap = argparse.ArgumentParser(description="system_health — loud-failures probe")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any check is red (humans + CI; NOT the cron)")
    ap.add_argument("--notify", action="store_true",
                    help="Telegram on any red, deduped on which checks are red")
    a = ap.parse_args()
    rep = run()

    # If the probe owns the alarm, a FAILED alarm is itself a broken-cron
    # condition and must exit non-zero — otherwise dropping --strict trades a
    # noisy true alert for a silent one, which is the worse bug. EXECUTION_RULES
    # § 19 meta-rule: the failure shape to fear is "everything looked fine
    # because the mechanism that would have reported the problem was broken".
    # cron_health_check.py:166 draws the same line for the same reason.
    alert_failed = False
    if a.notify:
        alert_failed = bool(rep["reds"]) and not notify_reds(rep)

    if a.json:
        # ONE compact line, deliberately — scheduler.py stores out[-1][:200] as
        # last_result, so pretty JSON ends in a lone bracket and the watchdog
        # classifies the run as OPAQUE ("verdict unknowable"). Same fix as the
        # Instagram poller; do not "improve" this back to indent=2.
        print(json.dumps(rep, separators=(",", ":")))
    if alert_failed:
        print("ERROR: red checks found but the Telegram alert did not send — "
              "the probe's only reporting path is down.", file=sys.stderr)
        return 1
    if a.json:
        return 1 if (a.strict and rep["reds"]) else 0
    mark = {RED: "🔴", YELLOW: "⚠ ", GREEN: "✓ "}
    print(f"=== system_health: {rep['reds']} red, {rep['yellows']} yellow ===")
    for r in rep["checks"]:
        print(f"  {mark[r['status']]} {r['check']:<16} {r['detail']}")
        for it in r["items"][:8]:
            print(f"        - {it}")
    return 1 if (a.strict and rep["reds"]) else 0


if __name__ == "__main__":
    sys.exit(main())
