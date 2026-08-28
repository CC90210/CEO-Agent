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

V7.1 (patterns from GokuMohandas/Made-With-ML, MIT): checks roll up into named
SLICES (lockstep / routing / boundary / guards / live-health / model-call) so a
regression concentrated in one slice can't hide inside the aggregate score, and
every run appends {run_id, timestamp, score, slices, failed} to
state/harness_eval_history.jsonl for drift tracking across sessions.
"""
from __future__ import annotations

import argparse
import ast
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
# The germline seed's core block (stamped from PERSONAL.md by genome_sync.py).
LOCKSTEP_MARKER = "LOCKSTEP:seed_core"
REQUIRED_PM2 = {"bravo-scheduler", "bravo-telegram", "claude-bridge", "event-router", "bravo-coord"}
# This eval's own cron_jobs row (cron_engine.SEED_JOBS). check_cron_health skips
# it ONLY when it failed by scoring itself — see the note there. The marker is
# the banner this script prints, so the row's text proves the script actually
# ran and self-scored (vs. failing to launch at all).
_SELF_CRON_NAME = "Bravo — Nightly Harness Eval"
_SELF_SCORE_MARKER = "HARNESS EVAL"
SESSION_LOG_PATH = PROJECT_ROOT / "memory" / "SESSION_LOG.md"

# A daily brief that contains one of these strings has already admitted that a
# source failed. Treating it as a green live-health check is false assurance.
_DEGRADED_BRIEF_MARKERS = ("timed out", "broken", "needs a fix", "unavailable")


def _normalize_dash(s: str) -> str:
    """Fold em/en/non-breaking/minus dashes to ASCII '-' and squash whitespace.

    Defensive, NOT a bug fix: verified 2026-08-13 that the constant above and
    the live cron_jobs row are both U+2014 byte-for-byte
    (hex 427261766F20E28094...), so today they match exactly. The hazard is
    future re-registration — SEED_JOBS is edited by hand across five runtimes,
    and a job renamed with a plain '-' would silently stop matching, which
    turns the self-score suppression below off with no error anywhere. Cheap
    insurance against a failure mode that is invisible when it happens.
    """
    if not s:
        return ""
    for dash in ("—", "–", "‒", "−", "‐", "‑", "­"):
        s = s.replace(dash, "-")
    return " ".join(s.split())


def _same_cron_name(a: str, b: str) -> bool:
    """Case-insensitive, dash-normalized cron-name equality."""
    return _normalize_dash(a).casefold() == _normalize_dash(b).casefold()


def is_self_scored_failure(job: dict) -> bool:
    """True only for THIS eval's own cron row failing because it scored itself.

    Public so the alerting path (core/cron_health_check.py) applies the exact
    same rule instead of keeping a second copy that can drift — the drift is
    what pages CC hourly about a job that is actually healthy.
    """
    if not _same_cron_name(str(job.get("name") or ""), _SELF_CRON_NAME):
        return False
    return _SELF_SCORE_MARKER in str(job.get("last_result") or "").upper()


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

    # Anti-hallucination clause must be present AND byte-identical everywhere.
    # Every runtime (Claude Code, Codex CLI, OpenCode, Gemini CLI, Antigravity)
    # reads its own entry point, so a rule that drifts in one file is a rule
    # that one chassis does not have. The recurring failure it prevents: an
    # agent claiming a credential is missing, or telling CC to install a plugin
    # / paste an env var, without running capability_probe first.
    clause_lines = {}
    for f in ENTRY_POINTS:
        for line in _read(f).splitlines():
            if line.startswith("**Credentials before"):
                clause_lines.setdefault(line.strip(), []).append(f)
                break
    covered = sum(len(v) for v in clause_lines.values())
    if covered != len(ENTRY_POINTS):
        have = {f for fs in clause_lines.values() for f in fs}
        return False, ("anti-hallucination credentials clause missing from: "
                       f"{', '.join(sorted(set(ENTRY_POINTS) - have))}")
    if len(clause_lines) != 1:
        return False, (f"credentials clause has drifted into {len(clause_lines)} variants — "
                       "edit PERSONAL.md then run scripts/genome_sync.py")
    clause = next(iter(clause_lines))
    for token in ("capability_probe.py", "AVAILABLE means you are authorized"):
        if token not in clause:
            return False, f"credentials clause no longer states {token!r}"
    return True, ("6 entry points carry the lockstep line + identical "
                  "anti-hallucination clause; mirrors byte-identical")


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
    lowered = out.lower()
    degraded = next((marker for marker in _DEGRADED_BRIEF_MARKERS if marker in lowered), None)
    if degraded:
        return False, f"brief contains degraded marker {degraded!r}: {out[:160]!r}"
    if "MRR" in out:
        return False, "brief contains a banned marker (MRR / narration-unavailable)"
    if "Pipeline" not in out or ": —" in out:
        return False, f"brief looks degraded: {out[:160]!r}"
    return True, "deterministic brief renders with real data, no MRR"


def check_self_audit_mandatory_gates():
    """Require the broad self-audit's mandatory gates, not its advisory score."""
    _rc, out, err = _run(
        [sys.executable, "scripts/core/self_audit.py", "--json"], timeout=180
    )
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        return False, f"self-audit returned invalid JSON: {(err or out)[:160]}"
    failures = payload.get("mandatory_gate_failures") or []
    score = payload.get("health_score", "?")
    if not payload.get("mandatory_gate_passed"):
        detail = "; ".join(map(str, failures or ["unspecified failure"]))
        return False, f"self-audit mandatory drift: {detail}"
    return True, f"self-audit mandatory gates pass (health {score}/100)"


def check_migration_docs_classified():
    """Block unclassified Supabase claims in the brain/memory scanner scope."""
    _rc, out, err = _run(
        [sys.executable, "scripts/core/doc_sweep.py", "--term", "supabase",
         "--brain", "--memory", "--json"],
        timeout=180,
    )
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        return False, f"migration doc sweep returned invalid JSON: {(err or out)[:160]}"
    counts = payload.get("unannotated_tier_counts") or {}
    tier1 = int(counts.get("1", counts.get(1, 0)) or 0)
    tier2 = int(counts.get("2", counts.get(2, 0)) or 0)
    if tier1 or tier2:
        return False, (
            f"migration docs unclassified: {tier1} Tier-1, "
            f"{tier2} Tier-2 Supabase hit(s)"
        )
    return True, "brain/memory Tier-1 and Tier-2 Supabase references are classified"


def check_session_log_integrity():
    """Reject the archive bug's repeated YAML-frontmatter signature."""
    try:
        content = SESSION_LOG_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, f"SESSION_LOG unreadable: {exc}"
    count = len(re.findall(r"(?mi)^tags:\s*\[daily\]\s*$", content))
    if count != 1:
        return False, f"SESSION_LOG has {count} frontmatter block(s); expected exactly 1"
    return True, "SESSION_LOG has one frontmatter block"


def check_tenant_scoping():
    """Regression guard on lead_engine.py's tenant contract — NOT a fleet-wide
    tenant-isolation audit, and not a data check.

    Scope correction 2026-08-04: this greps ONE file for three substrings. It
    was labelled "CRM tenant scoping intact", which reads as a guarantee about
    the whole CRM. It is not. A live audit that day found 14 INSERT sites into
    tenant-scoped tables (inbound_classifier, send_gateway, funnel_sync,
    email_brain, contract_tool, scrape_firecrawl_leads, lead_engine) that do not
    stamp tenant_id, and 37 of 63 sampled `leads` rows with a NULL tenant_id —
    all while this check was green. A gate that overstates its coverage is worse
    than no gate: no gate keeps you cautious, a green one makes you confident.

    The label now says what it actually proves. Widening it to the other 13 call
    sites is CC's call, because making it honest AND broad turns harness_eval
    red until those sites are fixed, and harness_eval pages on non-zero exit.
    """
    src = _read("scripts/lead_engine.py")
    if "OASIS_TENANT_ID" not in src:
        return False, "lead_engine.py lost OASIS_TENANT_ID"
    if src.count('eq("tenant_id", OASIS_TENANT_ID)') < 2:
        return False, "pipeline/followups reads no longer tenant-scoped"
    if '"tenant_id": getattr(args, "tenant", None) or OASIS_TENANT_ID' not in src \
            and '"tenant_id": OASIS_TENANT_ID' not in src:
        return False, "insert paths no longer tenant-stamped"
    return True, ("lead_engine.py only — reads scoped + writes stamped"
                  + _unstamped_insert_advisory())


# Tables that carry a tenant_id column (verified live 2026-08-04).
_TENANT_SCOPED_TABLES = ("leads", "lead_interactions", "contracts")
_TENANT_WRITE_RE = re.compile(
    r'\.table\(\s*["\'](?P<t>' + "|".join(_TENANT_SCOPED_TABLES) + r')["\']\s*\)'
    r'\s*(?:\.[a-z_]+\([^\n]*\)\s*)*?\.insert\(', re.S)


def _unstamped_insert_advisory() -> str:
    """Count INSERTs into tenant-scoped tables that never stamp tenant_id.

    ADVISORY ONLY — appended to the message, never flips pass/fail. The audit
    that found this gap also found that making it blocking turns harness_eval
    red, and harness_eval pages CC on non-zero exit; whether to accept that is
    his call. But the count belongs in the output either way: a gap that lives
    only in a commit message is a gap nobody sees again.

    Never raises — an advisory that can break the check it decorates is worse
    than no advisory. But it also never makes an AFFIRMATIVE safety claim: this
    is a regex over a narrow fluent-call shape with a 16-line proximity window,
    so it can miss a payload built further away and can be fooled by an
    unrelated nearby `tenant_id`. It is good enough to say "look here", never
    good enough to say "all clear" (Codex audit 2026-08-04 — a zero from a
    heuristic reading as a guarantee is the same false-confidence bug this
    whole check was relabelled for).

    VERIFIED 2026-08-08: all 13 then-flagged sites were traced to the payload.
    5 were real gaps and are now stamped (funnel_sync, inbound_classifier x2,
    email_brain, scrape_firecrawl_leads); the rest stamp upstream of the
    16-line window or are deliberately tenantless (send_gateway legacy branch
    :906, reservations stamped at finalize :2186). The residual count is
    expected non-zero — it only re-earns attention if it GROWS.
    """
    try:
        scripts_dir = Path(__file__).resolve().parent
        candidates = 0
        for path in scripts_dir.rglob("*.py"):
            parts = path.parts
            if "_archive" in parts or "__pycache__" in parts or "tests" in parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if ".table(" not in text:
                continue
            lines = text.splitlines()
            for m in _TENANT_WRITE_RE.finditer(text):
                ln = text[:m.start()].count("\n")
                if "tenant_id" not in "\n".join(lines[ln:ln + 16]):
                    candidates += 1
        if candidates:
            return (f" | ADVISORY: {candidates} candidate unstamped tenant-table "
                    f"INSERTs (heuristic, verify before trusting)")
        return " | (no unstamped INSERT candidates matched — heuristic, not a guarantee)"
    except Exception as exc:  # noqa: BLE001
        return f" | (fleet advisory failed: {type(exc).__name__}: {str(exc)[:60]})"


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
    # Self-scored suppression lives at module level as is_self_scored_failure()
    # so core/cron_health_check.py enforces the identical rule. Rationale kept
    # here because this is where it bites:
    #
    # The deadlock (2026-07-28): a transient failure stamps
    # last_result="ERROR: script_run exit 1: HARNESS EVAL — 9/10 ..." on this
    # eval's row; the check below then sees that row, fails, and re-stamps
    # ERROR — forever, no matter how healthy the fleet actually is.
    #
    # Narrow, not blanket: only a failure whose text is this eval's own
    # scoreboard is skipped. If the row fails for any OTHER reason — script
    # path broken, timeout, interpreter missing — the text won't carry the
    # scoreboard marker and the job is still reported, so "the scheduled
    # harness cron is broken" remains detectable.
    bad = [j["name"] for j in jobs if j.get("is_active")
           and not is_self_scored_failure(j)
           and str(j.get("last_result") or "").upper().startswith(("ERROR", "FAILED"))]
    mrr_on = [j["name"] for j in jobs if j.get("is_active")
              and _same_cron_name(str(j.get("name") or ""), "Weekly MRR Report")]
    if bad:
        return False, f"active crons in ERROR: {bad}"
    if mrr_on:
        return False, "Weekly MRR Report is active — violates the Atlas boundary"
    return True, f"{sum(1 for j in jobs if j.get('is_active'))} active crons, none in ERROR, no Bravo MRR digest"


def check_pm2_fleet():
    """Is the daemon fleet actually running? Answered from the OS process table,
    never by invoking pm2.

    WHY NOT pm2 (2026-08-28): pm2's named pipe returns EPERM on this machine, so
    `pm2 jlist` failed on every run — and worse, each invocation against the
    blocked pipe SPAWNS AN ORPHAN PM2 DAEMON. 42 had accumulated, a meaningful
    share of them from this very check running nightly at 03:30. A health check
    that degrades the system it measures is worse than no health check, and it
    also conflated two different states: "supervisor unreachable" was reported
    as "fleet down" while every daemon was in fact alive.

    Supervision moved to scripts/ops/fleet_watchdog.py (Windows Task Scheduler,
    every 5 min) in e7d0a50f. Its status() reads `wmic process get CommandLine`
    and matches on the SCRIPT name rather than the interpreter — matching
    `pythonw.exe` would report every unrelated python process as a live daemon.
    Reusing it here keeps one definition of "up" for the watchdog and the gate.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "ops"))
        from ops.fleet_watchdog import status as fleet_status  # noqa: E402
    except Exception as e:  # noqa: BLE001
        return False, f"fleet_watchdog unavailable: {type(e).__name__}: {e}"

    try:
        rows = fleet_status()
    except Exception as e:  # noqa: BLE001
        return False, f"fleet status probe failed: {type(e).__name__}: {e}"

    if not rows:
        return False, "fleet manifest empty — nothing is being supervised"

    # Three states the fleet distinguishes, and this gate must too:
    #   disabled   — operator chose to stop it. Not an outage; nagging about a
    #                deliberate stop is how a gate teaches people to ignore it.
    #   unrunnable — the MANIFEST is broken (no script recorded), so the daemon
    #                cannot be started at all. A real defect, but a config one
    #                that no restart fixes, and it would otherwise pin this
    #                check red forever — the state in which gates get ignored.
    #   down       — supposed to be running, is not. The actual alarm.
    # fleet_watchdog uses the same split ("0 of 8 down" with one unrunnable).
    disabled = sorted(r["name"] for r in rows if r.get("disabled"))
    unrunnable = sorted(r["name"] for r in rows if r.get("unrunnable") and not r.get("disabled"))
    down = sorted(r["name"] for r in rows
                  if not r["running"] and not r.get("disabled") and not r.get("unrunnable"))
    up = sum(1 for r in rows if r["running"])

    if down:
        return False, f"daemons DOWN: {down}"
    notes = []
    if unrunnable:
        notes.append(f"{len(unrunnable)} unrunnable manifest entr{'y' if len(unrunnable) == 1 else 'ies'}: {unrunnable}")
    if disabled:
        notes.append(f"{len(disabled)} disabled by operator")
    suffix = f" ({'; '.join(notes)})" if notes else ""
    return True, f"{up}/{len(rows)} fleet daemons running{suffix}"


# Undefined names that are NOT bugs. Keyed (relative_path, name) so a new
# undefined name in the same file still fails — an allowlist that silences a
# whole file is how the next one hides. These three are string annotations
# (`-> "torch.nn.Module"`) on optional-ML-dependency helpers that import torch
# inside the function body; pyflakes cannot see through the quoted form.
_UNDEFINED_NAME_ALLOWLIST = {
    ("scripts/maml_onboard.py", "torch"),
    ("scripts/neural_memory.py", "torch"),
    ("scripts/tft_forecast.py", "torch"),
}


def check_fleet_compiles():
    """ast.parse every production script under scripts/, then run pyflakes'
    undefined-name analysis over the same tree. Either a SyntaxError or an
    unbound name anywhere in the fleet must fail the eval NOW, not when the
    cron that runs that script next hits it.

    WHY (2026-08-11): a session cut off mid-batch-edit left 12 scripts with
    truncated Supabase->Turso fallback edits — 10 with a SyntaxError (one of
    them a live PM2 app), 2 with a collided line that compiled but skipped the
    env-var fallback. Every existing gate stayed green because none of them
    PARSES the fleet: harness_eval reported ALL GREEN over a codebase whose
    next cron run would crash. A gate that cannot see a syntax error in the
    files it claims to cover is not a gate.

    WHY THE SECOND PASS (2026-08-28): ast.parse stops one notch short of the
    defect that actually keeps happening. a71826a7 switched inbound_classifier
    to run_smart_cli but left the import naming run_claude_cli — valid syntax,
    NameError at runtime, swallowed by a broad except, and every inbound email
    fell back to keyword classification for two days with the harness green.
    The identical class had already hit the same function in July (TypeError on
    a dead `_env` param). Four more unbound-name bugs were sitting in the fleet
    when this pass was added.

    pyproject.toml already selects ruff rule set "F", which includes F821 — the
    exact rule. Ruff is not installed and nothing invoked it, so the rule had
    never run. This uses the pyflakes already in .venv and reuses the AST the
    loop above parses, so the pass costs no extra read and no subprocess.
    """
    from pyflakes.checker import Checker
    from pyflakes.messages import UndefinedName

    root = Path(__file__).resolve().parent
    broken: list[str] = []
    undefined: list[str] = []
    scanned = 0
    for path in root.rglob("*.py"):
        parts = path.parts
        if "_archive" in parts or "__pycache__" in parts or "tests" in parts:
            continue
        scanned += 1
        rel = path.relative_to(root.parent).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as e:
            broken.append(f"{rel}:{e.lineno}")
            continue
        except (ValueError, UnicodeDecodeError) as e:
            broken.append(f"{rel}:decode({type(e).__name__})")
            continue
        try:
            messages = Checker(tree, filename=str(path)).messages
        except Exception:  # noqa: BLE001 - analysis must never break the gate
            continue
        for m in messages:
            if not isinstance(m, UndefinedName):
                continue
            name = m.message_args[0] if m.message_args else "?"
            if (rel, name) in _UNDEFINED_NAME_ALLOWLIST:
                continue
            undefined.append(f"{rel}:{m.lineno} undefined name {name!r}")

    if broken:
        return False, f"syntax errors in {len(broken)} scripts: {broken[:6]}"
    if undefined:
        return False, f"{len(undefined)} undefined names (NameError at runtime): {undefined[:6]}"
    return True, f"{scanned} production scripts parse clean, no undefined names"


def check_model_call_path():
    # Deliberately probes claude_cli DIRECTLY (not run_smart_cli): this check's
    # job is substrate TRUTH — is the subscription CLI alive right now? Routing
    # the probe through the fallback would mask a quota/auth outage with a
    # fake green. The failure text reports fallback availability so the
    # Telegram alert is actionable instead of alarming.
    from lib.claude_cli import run_claude_cli  # noqa: E402
    from lib.model_fallback import is_fallback_available  # noqa: E402
    text = run_claude_cli("Reply with exactly one word: ready", model="haiku", timeout=90)
    if text and "ready" in text.lower():
        return True, "local claude CLI answered on subscription OAuth"
    fb = "available" if is_fallback_available() else "NOT installed"
    return False, f"claude CLI probe failed (got {text!r}) — opencode fallback {fb}, automations degrade to it"


# V7.1: each check belongs to a named SLICE (pattern: Made-With-ML slice-based
# evaluation — an aggregate 10/10 can hide a regression concentrated in one
# slice; per-slice pass-rates surface it). Tuple: (name, fn, model_only, slice).
CHECKS = [
    ("entry-point lockstep (6 runtimes + mirrors)", check_entry_point_lockstep, False, "lockstep"),
    ("capability graph fresh (skills disk==graph, 0 drift)", check_capability_graph, False, "routing"),
    ("skill routing not blind (WTUS descriptions)", check_wtus_descriptions, False, "routing"),
    ("Atlas boundary held (routers + brief)", check_atlas_boundary, False, "boundary"),
    ("no dead API key in active automations", check_no_dead_api_key_in_active, False, "model-call"),
    ("daily brief renders real data", check_brief_renders, False, "live-health"),
    ("self-audit mandatory gates pass", check_self_audit_mandatory_gates, False, "live-health"),
    ("migration docs classified (brain/memory)", check_migration_docs_classified, False, "routing"),
    ("session log structure intact", check_session_log_integrity, False, "lockstep"),
    ("lead_engine tenant contract intact", check_tenant_scoping, False, "boundary"),
    ("safety guards in enforce", check_guards_enforce, False, "guards"),
    ("cron table healthy (no ERROR, no MRR digest)", check_cron_health, False, "live-health"),
    ("PM2 fleet online", check_pm2_fleet, False, "live-health"),
    ("fleet compiles (no SyntaxError anywhere)", check_fleet_compiles, False, "live-health"),
    ("model-call path live (claude CLI probe)", check_model_call_path, True, "model-call"),  # --with-model only
]

HISTORY_PATH = PROJECT_ROOT / "state" / "harness_eval_history.jsonl"


def _slice_rollup(results: list[dict]) -> dict[str, dict]:
    slices: dict[str, dict] = {}
    for r in results:
        s = slices.setdefault(r["slice"], {"passed": 0, "total": 0})
        s["total"] += 1
        if r["ok"]:
            s["passed"] += 1
    for s in slices.values():
        s["ok"] = s["passed"] == s["total"]
    return slices


def _append_history(record: dict) -> None:
    """Persist the run (pattern: Made-With-ML versioned eval records — a score
    without a persisted run_id/timestamp can't show drift). Best-effort: the
    eval must never fail because the history write did."""
    try:
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with HISTORY_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception:  # noqa: BLE001
        pass


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Deterministic harness eval — run from ANY runtime")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--with-model", action="store_true",
                   help="include the live claude-CLI probe (~5-20s, spends one subscription call)")
    args = p.parse_args(argv)

    results = []
    for name, fn, model_only, slice_name in CHECKS:
        if model_only and not args.with_model:
            continue
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"check crashed: {type(e).__name__}: {e}"
        results.append({"check": name, "ok": ok, "detail": detail, "slice": slice_name})

    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    slices = _slice_rollup(results)

    import uuid
    from datetime import datetime, timezone
    run_id = uuid.uuid4().hex[:12]
    timestamp = datetime.now(timezone.utc).isoformat()
    _append_history({"run_id": run_id, "timestamp": timestamp,
                     "score": f"{passed}/{total}", "pass": passed == total,
                     "with_model": bool(args.with_model),
                     "slices": slices,
                     "failed": [r["check"] for r in results if not r["ok"]]})

    if args.json:
        print(json.dumps({"score": f"{passed}/{total}", "pass": passed == total,
                          "run_id": run_id, "timestamp": timestamp,
                          "slices": slices, "results": results}, indent=2))
    else:
        print(f"HARNESS EVAL — {passed}/{total} checks pass  (run {run_id})\n")
        for r in results:
            mark = "✅" if r["ok"] else "❌"
            print(f"  {mark} {r['check']}")
            print(f"      {r['detail']}")
        print()
        slice_bits = ", ".join(f"{k} {v['passed']}/{v['total']}" for k, v in sorted(slices.items()))
        print(f"  slices: {slice_bits}")
        print()
        print("ALL GREEN — harness is turnkey for any runtime." if passed == total
              else "FAILURES above name the exact gap. Fix, then re-run.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
