"""Daily Bravo Brief — AI-narrated morning summary to CC's Telegram.

Phase 5c of the OASIS HQ redesign. Two layers:

  1. Data layer: scripts/snapshots/briefing_snapshot.py already aggregates
     MRR / pipeline / follow-ups / client health into a single JSON blob.
     We read state/snapshots/latest_briefing.json (regenerate if stale).

  2. Narration layer: hand the JSON to the LOCAL claude CLI (CC's Claude Code
     SUBSCRIPTION / OAuth — never the metered ANTHROPIC_API_KEY, per the
     CLI-only rule) with a tight prompt → a 5-bullet brief in CC's voice.
     If narration is unavailable (no CLI, expired token, timeout) we fall
     back to a deterministic brief built straight from the snapshot — always
     accurate, never the old empty "—" message. Revenue/MRR is intentionally
     omitted from Bravo's brief: that's Atlas's (CFO) job.

  3. Delivery: notify.notify(message, category="system", force=True) ships
     it to CC's Telegram. Same path daemon crash alerts use, so we know
     it's wired and CC sees it.

CLI:
  python scripts/daily_brief.py                # generate + send
  python scripts/daily_brief.py --dry-run      # generate + print, no send
  python scripts/daily_brief.py --regenerate   # force re-aggregate the snapshot first

Cron: register as a cron_jobs SEED entry at 06:00 daily.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402
from lib.claude_cli import run_claude_cli  # noqa: E402

# Windows console defaults to cp1252; the brief includes 🌅 + bullet
# glyphs. Reconfigure to UTF-8 so --dry-run prints don't UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SNAPSHOT_PATH = PROJECT_ROOT / "state" / "snapshots" / "latest_briefing.json"

# Narration runs through the LOCAL claude CLI on CC's subscription OAuth
# (see _narrate_via_cli) — NEVER the metered ANTHROPIC_API_KEY. The old path
# POSTed to api.anthropic.com with an x-api-key header, which (a) 400'd on the
# model id and (b) violated CC's iron "CLI-only, no API keys in automations"
# rule — so every brief fell through to the fallback and read "AI narration
# unavailable". Set BRAVO_BRIEF_NARRATE=0 to skip narration and ship the
# deterministic brief directly (fully offline, zero AI dependency).
NARRATION_MODEL_CLI = "sonnet"          # CLI alias — always resolves
# Kept comfortably below the scheduler's outer run_script timeout for
# daily_brief (150s) so the inner narration bails to the deterministic brief
# BEFORE the scheduler kills the whole process. Observed narration ~22s.
CLI_NARRATION_TIMEOUT_SEC = 60
SNAPSHOT_STALENESS_SEC = 5 * 60  # 5 min — was 24h, but CC's revenue events
# (subscription_start / cancel logged manually) change throughout the day. A
# 24h-old snapshot caused the 2026-05-18 15:15 brief to report MRR $3,322 / 12d
# left when the primary $2,951 retainer had been cancelled at 15:20 just before
# the brief fired — snapshot was 11 min old and pre-cancel. 5 min cap means
# the brief regenerates from fresh CLIs on any non-trivial wait, while still
# avoiding regeneration cost on rapid-fire manual re-runs.

SYSTEM_PROMPT = """You are Bravo — CC's CEO/COO/CTO in one. Each morning you turn the last 24h of empire data into a 5-bullet operational brief CC can read in 30 seconds before his day starts.

Scope: pipeline, follow-ups, execution, client health, and system/ops. Revenue and MRR are Atlas's job (CFO) — do NOT report MRR or revenue figures. If money is relevant to a bullet, point to Atlas rather than quoting a number.

Style:
  - Five bullets. Five exactly. Never more.
  - Each bullet leads with the metric or fact, then the why-it-matters in <12 words.
  - No greetings, no sign-off, no "hope this helps".
  - Use CC's voice: direct, no corporate hedging, no "as an AI" disclaimers.
  - Numbers stay precise.
  - If something's broken or stuck, lead with it — bad news first.

Bullet shape: "<METRIC> — <one short clause of why>."
Example: "1 qualified lead (score 70) — ready to move, follow-up overdue."

Output the bullets only, one per line, prefixed with `• `. Nothing else."""


def _read_snapshot(regenerate: bool) -> dict | None:
    """Read the latest briefing snapshot. Regenerate if missing or stale."""
    if regenerate or not SNAPSHOT_PATH.exists():
        _regenerate_snapshot()
    elif _is_stale(SNAPSHOT_PATH):
        _regenerate_snapshot()

    if not SNAPSHOT_PATH.exists():
        return None
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _is_stale(path: Path) -> bool:
    try:
        age = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
        return age > SNAPSHOT_STALENESS_SEC
    except OSError:
        return True


def _regenerate_snapshot() -> None:
    # Phase 9.4 — windowless flag prevents the briefing snapshot
    # subprocess from flashing a console every 06:00.
    try:
        subprocess.run(
            [sys.executable, "scripts/snapshots/briefing_snapshot.py"],
            cwd=str(PROJECT_ROOT),
            timeout=60,
            capture_output=True,
            text=True,
            creationflags=WINDOWLESS_FLAGS,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        sys.stderr.write(f"[daily_brief] snapshot regen failed: {e}\n")


def _narrate_via_cli(snapshot: dict) -> str | None:
    """Hand the operational snapshot to the LOCAL claude CLI → 5-bullet brief.

    Routes through lib.claude_cli.run_claude_cli (CC's Claude Code SUBSCRIPTION
    OAuth, never the metered API key). Returns None on any failure; caller falls
    back to the deterministic brief, so a missing CLI / expired token / timeout
    degrades to accurate numbers rather than the old "AI narration unavailable"
    dead-end."""
    # Strip revenue/cash (Atlas's domain) + noisy fields before narrating.
    cleaned = {k: v for k, v in snapshot.items()
               if k not in ("snapshot_type", "ts", "revenue")}
    if isinstance(cleaned.get("briefing"), dict):
        cleaned["briefing"] = {k: v for k, v in cleaned["briefing"].items()
                               if k not in ("mrr", "cash")}
    user_prompt = (
        f"Today is {snapshot.get('date', 'today')}. Operational empire state "
        f"(revenue omitted — that's Atlas's brief):\n\n"
        f"{json.dumps(cleaned, indent=2, default=str)[:6000]}\n\n"
        f"Write CC's 5-bullet operational brief."
    )
    text = run_claude_cli(
        user_prompt, system=SYSTEM_PROMPT,
        model=NARRATION_MODEL_CLI, timeout=CLI_NARRATION_TIMEOUT_SEC,
    )
    if not text:
        return None
    # notify() ships with parse_mode=HTML and has NO plain-text fallback, so a
    # stray <, >, or & in the model's prose ("score > 70", "A & B") would make
    # Telegram reject the whole message → CC gets nothing. Escape the three
    # HTML-special chars; they render as literal glyphs.
    return html.escape(text, quote=False)


def _count_stage(pipe: dict, stage: str) -> int:
    """Count for one pipeline stage, tolerant of both snapshot shapes:
    {stage: {count: N}} (raw lead_engine) and {stage: N} (aggregated)."""
    v = pipe.get(stage)
    if isinstance(v, dict):
        return int(v.get("count") or 0)
    if isinstance(v, (int, float)):
        return int(v)
    return 0


_PIPELINE_STAGES = ("new", "contacted", "qualified", "proposal", "won", "lost")
_ACTIVE_STAGES = ("new", "contacted", "qualified", "proposal")


def _is_failed_block(v) -> bool:
    """briefing_snapshot._call marks a failed/unparseable sub-engine call with
    an _error or _raw key. Treat those as 'no data' — never as zero/green. A
    silent 0 is a worse lie than an honest 'unavailable'."""
    return isinstance(v, dict) and ("_error" in v or "_raw" in v)


def _render_brief(snapshot: dict) -> str:
    """Deterministic operational brief — always accurate, no AI, no API key.

    Reads the ACTUAL snapshot schema (the old fallback read keys that never
    existed → every field '—'). A DEGRADED sub-engine renders '⚠️ unavailable',
    never a false zero/green. MRR/cash omitted — revenue is Atlas's (CFO) job.
    Output is HTML-escaped for Telegram's parse_mode=HTML."""
    date = snapshot.get("date", "today")
    brief = snapshot.get("briefing") if isinstance(snapshot.get("briefing"), dict) else {}
    lines = [f"🌅 Bravo brief · {date}", ""]

    # --- Pipeline: prefer the raw lead_engine block (authoritative), then the
    #     ceo_dashboard aggregate; 'unavailable' if BOTH are degraded ---
    raw_pipe = snapshot.get("pipeline")
    brief_pipe = brief.get("pipeline") if isinstance(brief.get("pipeline"), dict) else {}
    by_stage = None
    if isinstance(raw_pipe, dict) and raw_pipe and not _is_failed_block(raw_pipe):
        by_stage = {s: _count_stage(raw_pipe, s) for s in _PIPELINE_STAGES}
    elif isinstance(brief_pipe.get("by_stage"), dict) and brief_pipe["by_stage"]:
        by_stage = {s: int(brief_pipe["by_stage"].get(s) or 0) for s in _PIPELINE_STAGES}

    if by_stage is None:
        lines.append("🎯 Pipeline — ⚠️ unavailable (snapshot degraded)")
    else:
        active = sum(int(by_stage.get(s) or 0) for s in _ACTIVE_STAGES)
        qualified = int(by_stage.get("qualified") or 0)
        stage_bits = " · ".join(
            f"{int(by_stage.get(s) or 0)} {label}"
            for s, label in (("new", "new"), ("contacted", "contacted"),
                             ("qualified", "qualified"), ("won", "won"))
            if int(by_stage.get(s) or 0)
        )
        lines.append(f"🎯 Pipeline — {active} active")
        if stage_bits:
            lines.append(f"   {stage_bits}")
        if qualified:
            lines.append(f"   → {qualified} qualified lead{'s' if qualified != 1 else ''} ready to move")

    # --- Follow-ups due: a list = real data; anything else = unavailable ---
    followups = snapshot.get("followups_due")
    lines.append("")
    if isinstance(followups, list):
        lines.append(f"📞 Follow-ups due: {len(followups)}")
        for lead in followups[:5]:
            if not isinstance(lead, dict):
                continue
            name = lead.get("name") or "—"
            company = lead.get("company") or ""
            score = lead.get("score")
            tail = f" · {company}" if company else ""
            if score is not None:
                tail += f" (score {score})"
            lines.append(f"   • {name}{tail}")
    else:
        lines.append("📞 Follow-ups due: ⚠️ unavailable")

    # --- Client health: honour the '0 monitored' truth-note; degraded = unavailable
    ch_raw = brief.get("client_health")
    alerts = snapshot.get("client_health_alerts")
    ch = ch_raw if isinstance(ch_raw, dict) else None
    lines.append("")
    if ch is None or _is_failed_block(ch_raw) or _is_failed_block(alerts):
        lines.append("🩺 Client health: ⚠️ unavailable")
    else:
        monitored = ch.get("monitored")
        at_risk = ch.get("at_risk")
        if at_risk is None and isinstance(alerts, dict):
            at_risk = len(alerts.get("at_risk_clients") or [])
        if monitored == 0:
            lines.append("🩺 Client health: ⚠️ 0 clients monitored")
            lines.append("   CRM gap — paying subscribers aren't tagged status='client'.")
        elif at_risk:
            lines.append(f"🩺 Client health: ⚠️ {at_risk} at risk")
        else:
            lines.append("🩺 Client health: ✅ all green")

    # --- footer: prove the brief ran + how fresh the data is ---
    ts = snapshot.get("ts") or ""
    hhmm = ts[11:16] if len(ts) >= 16 else ts
    lines.append("")
    lines.append(f"⏱ snapshot {hhmm} UTC" if hhmm else "⏱ snapshot generated")
    return html.escape("\n".join(lines), quote=False)


def build_brief(regenerate: bool = False) -> str:
    snapshot = _read_snapshot(regenerate)
    if not snapshot:
        return "Daily brief: snapshot unreadable. Run `python scripts/snapshots/briefing_snapshot.py` manually."

    deterministic = _render_brief(snapshot)
    # Narration is best-effort polish ON TOP of the deterministic brief. If the
    # CLI is missing, the token's expired, or it times out, CC still gets the
    # accurate deterministic brief — never the old empty "—" message.
    # BRAVO_BRIEF_NARRATE=0 skips narration entirely (pure deterministic).
    if os.environ.get("BRAVO_BRIEF_NARRATE", "1").strip() != "0":
        narrated = _narrate_via_cli(snapshot)
        if narrated:
            date_str = snapshot.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            return f"🌅 Bravo brief · {date_str}\n\n{narrated}"
    return deterministic


def send_brief(message: str) -> bool:
    """Ship to Telegram. force=True bypasses the category block list so
    the morning brief always lands even if 'system' is muted."""
    try:
        from notify import notify  # type: ignore
        return notify(message, category="system", silent=False, force=True)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[daily_brief] notify failed: {e}\n")
        return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Daily Bravo brief — Telegram delivery")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the brief instead of sending to Telegram")
    p.add_argument("--regenerate", action="store_true",
                   help="Force regenerate the briefing snapshot before narrating")
    args = p.parse_args(argv)

    brief = build_brief(regenerate=args.regenerate)
    if args.dry_run:
        print(brief)
        return 0

    ok = send_brief(brief)
    print(brief)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
