"""harness_eval.py — deterministic eval suite for the Bravo agent harness.

The training-practices extrapolation (2026-07-09): frontier models are trained
against VERIFIABLE REWARD — every capability claim is backed by an eval that
either passes or fails. This is that discipline applied to the harness itself.
Any runtime (Claude Code, Gemini CLI, Antigravity, Codex, OpenCode, ZCode)
runs ONE command and gets the same objective score of the substrate it is
about to trust: routing truth, entry-point lockstep, guard posture, live
automation health, model-call path.

Run it at session start on an unfamiliar machine, after any substrate change,
or whenever an agent "feels" mis-wired. A failing check names the exact gap.

CLI:
  python scripts/harness_eval.py               # table + score
  python scripts/harness_eval.py --json        # machine-readable
  python scripts/harness_eval.py --with-model  # + live claude-CLI probe (~5-20s)

Exit code: 0 = all checks pass, 1 = any failure (cron-able; nonzero → red).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    from _subprocess_helpers import WINDOWLESS_FLAGS  # type: ignore
except Exception:
    WINDOWLESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)

ENTRY_POINTS = ["CLAUDE.md", "GEMINI.md", "ANTIGRAVITY.md", "AGENTS.md", "OPENCODE.md", "ZCODE.md"]
LOCKSTEP_MARKER = "CRM motion (2026-07-09): INBOUND-first"
REQUIRED_PM2 = {"bravo-scheduler", "bravo-telegram", "claude-bridge", "event-router", "bravo-coord"}


def _run(cmd: list[str], timeout: int = 60, env_extra: dict | None = None) -> tuple[int, str, str]:
    import os
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    if env_extra:
        env.update(env_extra)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=str(PROJECT_ROOT), encoding="utf-8", errors="replace",
                           creationflags=WINDOWLESS_FLAGS, env=env)
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception as e:  # noqa: BLE001
        return -1, "", str(e)


def _read(rel: str) -> str:
    try:
        return (PROJECT_ROOT / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ── checks: each returns (ok: bool, detail: str) ────────────────────────────

def check_entry_point_lockstep():
    missing = [f for f in ENTRY_POINTS if LOCKSTEP_MARKER not in _read(f)]
    if missing:
        return False, f"lockstep line missing from: {', '.join(missing)}"
    drifted = []
    for f in ENTRY_POINTS:
        mirror = PROJECT_ROOT / ".gemini" / "rules" / f
        if mirror.exists() and mirror.read_bytes() != (PROJECT_ROOT / f).read_bytes():
            drifted.append(f)
    if drifted:
        return False, f".gemini/rules mirrors differ from roots: {', '.join(drifted)}"
    return True, "6 entry points carry the lockstep line; mirrors byte-identical"


def check_capability_graph():
    raw = _read("brain/CAPABILITY_GRAPH.json")
    if not raw:
        return False, "brain/CAPABILITY_GRAPH.json missing/unreadable"
    try:
        g = json.loads(raw)
    except json.JSONDecodeError as e:
        return False, f"graph JSON invalid: {e}"
    on_disk = sum(1 for d in (PROJECT_ROOT / "skills").iterdir()
                  if d.is_dir() and d.name not in ("_archive", "in-progress")
                  and (d / "SKILL.md").exists())
    in_graph = g.get("totals", {}).get("skills")
    drift = g.get("drift", [])
    if in_graph != on_disk:
        return False, f"graph says {in_graph} skills, disk has {on_disk} — rerun build_capability_graph.py"
    if drift:
        return False, f"{len(drift)} drift entries: {drift[:3]}"
    return True, f"{on_disk} skills disk==graph, 0 drift"


def check_wtus_descriptions():
    wtus = _read("brain/WHEN_TO_USE_SKILLS.md")
    if not wtus:
        return False, "brain/WHEN_TO_USE_SKILLS.md missing"
    blind = re.findall(r"^## (.+)\n- \*\*Use when:\*\* [>|]?\s*$", wtus, re.MULTILINE)
    if blind:
        return False, f"routing-blind skills (empty/'>' descriptions): {blind[:6]}"
    return True, "no routing-blind skill descriptions"


def _uses_metered_api(rel: str) -> bool:
    """True only if api.anthropic.com appears on a CODE line — comments
    documenting the retired path (e.g. daily_brief's fix note) don't count."""
    for line in _read(rel).splitlines():
        stripped = line.strip()
        if "api.anthropic.com" in stripped and not stripped.startswith(("#", "//", "*", ">")):
            return True
    return False


def check_atlas_boundary():
    problems = []
    er = _read("brain/EXECUTION_RULES.md")
    if "ATLAS-OWNED" not in er:
        problems.append("EXECUTION_RULES.md lost the ATLAS-OWNED MRR row")
    ar = _read("brain/AGENT_ROUTER.md")
    if "ATLAS-OWNED" not in ar:
        problems.append("AGENT_ROUTER.md lost the ATLAS-OWNED MRR routing")
    brief = _read("scripts/daily_brief.py")
    if "net_mrr_cad" in brief or _uses_metered_api("scripts/daily_brief.py"):
        problems.append("daily_brief.py regressed (old keys or API endpoint)")
    return (False, "; ".join(problems)) if problems else (True, "routers + brief hold the Atlas boundary")


def check_no_dead_api_key_in_active():
    # The cron-wired model-calling automations must be on the CLI path.
    active = ["scripts/daily_brief.py", "scripts/bravo_sleep.py", "scripts/auto_score_leads.py"]
    bad = [f for f in active if _uses_metered_api(f)]
    if bad:
        return False, f"active automations still on the metered API: {bad}"
    ok_import = [f for f in active if "claude_cli" in _read(f)]
    if len(ok_import) != len(active):
        return False, f"missing lib.claude_cli import in: {sorted(set(active) - set(ok_import))}"
    return True, "all 3 cron-wired model callers route via lib/claude_cli"


def check_brief_renders():
    rc, out, err = _run([sys.executable, "scripts/daily_brief.py", "--dry-run"],
                        timeout=90, env_extra={"BRAVO_BRIEF_NARRATE": "0"})
    if rc != 0:
        return False, f"daily_brief --dry-run exit {rc}: {err[:120]}"
    if "AI narration unavailable" in out or "MRR" in out:
        return False, "brief contains a banned marker (MRR / narration-unavailable)"
    if "Pipeline" not in out or ": —" in out:
        return False, f"brief looks degraded: {out[:160]!r}"
    return True, "deterministic brief renders with real data, no MRR"


def check_tenant_scoping():
    src = _read("scripts/lead_engine.py")
    if "OASIS_TENANT_ID" not in src:
        return False, "lead_engine.py lost OASIS_TENANT_ID"
    if src.count('eq("tenant_id", OASIS_TENANT_ID)') < 2:
        return False, "pipeline/followups reads no longer tenant-scoped"
    if '"tenant_id": getattr(args, "tenant", None) or OASIS_TENANT_ID' not in src \
            and '"tenant_id": OASIS_TENANT_ID' not in src:
        return False, "insert paths no longer tenant-stamped"
    return True, "reads scoped + writes stamped to OASIS_TENANT_ID"


_REQUIRED_GUARDS = {"EMPIRE_HOOK_SECRET_GUARD", "EMPIRE_HOOK_EXEC_GUARD", "EMPIRE_HOOK_STATE_GUARD"}


def check_guards_enforce():
    # Merge parsed modes across both settings files (env can be split), then
    # require every expected guard present AND == enforce. An empty/malformed
    # parse must FAIL — a substring match alone was a false-pass (Codex 2026-07-09).
    modes: dict[str, str] = {}
    seen_files = []
    for candidate in (".claude/settings.json", ".claude/settings.local.json"):
        raw = _read(candidate)
        if raw:
            found = dict(re.findall(r'"(EMPIRE_HOOK_\w+)"\s*:\s*"(\w+)"', raw))
            if found:
                modes.update(found)
                seen_files.append(candidate)
    missing = _REQUIRED_GUARDS - set(modes)
    if missing:
        return False, f"guard modes not found/parseable: {sorted(missing)}"
    lax = {k: modes[k] for k in _REQUIRED_GUARDS if modes[k] != "enforce"}
    if lax:
        return False, f"guards not in enforce: {lax}"
    return True, f"{len(_REQUIRED_GUARDS)} required guards enforce ({', '.join(seen_files)})"


def check_cron_health():
    rc, out, _ = _run([sys.executable, "scripts/core/cron_engine.py", "--json", "list"], timeout=60)
    if rc != 0 or not out.strip():
        return False, "cron_engine list failed (Supabase unreachable?)"
    try:
        jobs = json.loads(out)
    except json.JSONDecodeError:
        return False, "cron_engine returned non-JSON"
    bad = [j["name"] for j in jobs if j.get("is_active")
           and str(j.get("last_result") or "").upper().startswith(("ERROR", "FAILED"))]
    mrr_on = [j["name"] for j in jobs if j.get("is_active") and j.get("name") == "Weekly MRR Report"]
    if bad:
        return False, f"active crons in ERROR: {bad}"
    if mrr_on:
        return False, "Weekly MRR Report is active — violates the Atlas boundary"
    return True, f"{sum(1 for j in jobs if j.get('is_active'))} active crons, none in ERROR, no Bravo MRR digest"


def check_pm2_fleet():
    pm2 = shutil.which("pm2") or shutil.which("pm2.cmd")
    if not pm2:
        return False, "pm2 not on PATH"
    rc, out, err = _run([pm2, "jlist"], timeout=30)
    if rc != 0:
        return False, f"pm2 jlist failed: {err[:80]}"
    try:
        procs = json.loads(out[out.index("["):])
    except (ValueError, json.JSONDecodeError):
        return False, "pm2 jlist returned unparseable output"
    online = {p["name"] for p in procs if p.get("pm2_env", {}).get("status") == "online"}
    down = REQUIRED_PM2 - online
    if down:
        return False, f"required PM2 processes not online: {sorted(down)}"
    return True, f"{len(REQUIRED_PM2)} required processes online ({len(online)} total)"


def check_model_call_path():
    from lib.claude_cli import run_claude_cli  # noqa: E402
    text = run_claude_cli("Reply with exactly one word: ready", model="haiku", timeout=90)
    if text and "ready" in text.lower():
        return True, "local claude CLI answered on subscription OAuth"
    return False, f"claude CLI probe failed (got {text!r})"


CHECKS = [
    ("entry-point lockstep (6 runtimes + mirrors)", check_entry_point_lockstep, False),
    ("capability graph fresh (skills disk==graph, 0 drift)", check_capability_graph, False),
    ("skill routing not blind (WTUS descriptions)", check_wtus_descriptions, False),
    ("Atlas boundary held (routers + brief)", check_atlas_boundary, False),
    ("no dead API key in active automations", check_no_dead_api_key_in_active, False),
    ("daily brief renders real data", check_brief_renders, False),
    ("CRM tenant scoping intact", check_tenant_scoping, False),
    ("safety guards in enforce", check_guards_enforce, False),
    ("cron table healthy (no ERROR, no MRR digest)", check_cron_health, False),
    ("PM2 fleet online", check_pm2_fleet, False),
    ("model-call path live (claude CLI probe)", check_model_call_path, True),  # --with-model only
]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Deterministic harness eval — run from ANY runtime")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--with-model", action="store_true",
                   help="include the live claude-CLI probe (~5-20s, spends one subscription call)")
    args = p.parse_args(argv)

    results = []
    for name, fn, model_only in CHECKS:
        if model_only and not args.with_model:
            continue
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"check crashed: {type(e).__name__}: {e}"
        results.append({"check": name, "ok": ok, "detail": detail})

    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    if args.json:
        print(json.dumps({"score": f"{passed}/{total}", "pass": passed == total,
                          "results": results}, indent=2))
    else:
        print(f"HARNESS EVAL — {passed}/{total} checks pass\n")
        for r in results:
            mark = "✅" if r["ok"] else "❌"
            print(f"  {mark} {r['check']}")
            print(f"      {r['detail']}")
        print()
        print("ALL GREEN — harness is turnkey for any runtime." if passed == total
              else "FAILURES above name the exact gap. Fix, then re-run.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
