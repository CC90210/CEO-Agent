"""Daily Bravo Brief — AI-narrated morning summary to CC's Telegram.

Phase 5c of the OASIS HQ redesign. Two layers:

  1. Data layer: scripts/snapshots/briefing_snapshot.py already aggregates
     MRR / pipeline / follow-ups / client health into a single JSON blob.
     We read state/snapshots/latest_briefing.json (regenerate if stale).

  2. Narration layer: hand the JSON to Claude with a tight prompt — return
     a 5-bullet brief in CC's voice. No fluff, no "I hope this finds you
     well", no recommendations Claude wasn't asked for.

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
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

# Windows console defaults to cp1252; the brief includes 🌅 + bullet
# glyphs. Reconfigure to UTF-8 so --dry-run prints don't UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SNAPSHOT_PATH = PROJECT_ROOT / "state" / "snapshots" / "latest_briefing.json"
ANTHROPIC_VERSION = "2023-06-01"
NARRATION_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 600
SNAPSHOT_STALENESS_SEC = 24 * 60 * 60  # 24h

SYSTEM_PROMPT = """You are Bravo, CC's lead architect. Each morning you turn last 24h's empire data into a 5-bullet brief CC can read in 30 seconds before he starts his day.

Style:
  - Five bullets. Five exactly. Never more.
  - Each bullet leads with the metric or fact, then the why-it-matters in <12 words.
  - No greetings, no sign-off, no "hope this helps".
  - Use CC's voice: direct, no corporate hedging, no "as an AI" disclaimers.
  - Numbers stay precise (don't round $4,237 to $4K).
  - If something's broken or stuck, lead with it — bad news first.

Bullet shape: "<METRIC> — <one short clause of why>."
Example: "MRR $2,840 — flat vs yesterday, still $2,160 from the May goal."

Output the bullets only, one per line, prefixed with `• `. Nothing else."""


def _load_env() -> dict[str, str]:
    from lib.secret_loader import load_env  # noqa: E402
    return load_env()


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


def _narrate(snapshot: dict, env: dict[str, str]) -> str | None:
    """Hand the snapshot to Claude → 5-bullet brief. Returns None on any
    failure (caller decides whether to fall back to a dumb summary)."""
    api_key = (env.get("BRAVO_ANTHROPIC_API_KEY")
               or env.get("ANTHROPIC_API_KEY")
               or os.environ.get("BRAVO_ANTHROPIC_API_KEY", "")).strip()
    if not api_key:
        sys.stderr.write("[daily_brief] BRAVO_ANTHROPIC_API_KEY missing\n")
        return None

    # Strip noisy fields before sending to Claude. The snapshot has full
    # error blobs from sub-engine failures; those waste tokens.
    cleaned = {
        k: v for k, v in snapshot.items()
        if k not in ("snapshot_type", "ts")
    }
    user_prompt = (
        f"Today is {snapshot.get('date', 'today')}. "
        f"Here's the aggregate empire state from the last 24h:\n\n"
        f"{json.dumps(cleaned, indent=2, default=str)[:6000]}\n\n"
        f"Write CC's 5-bullet brief."
    )

    body = json.dumps({
        "model": NARRATION_MODEL,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[daily_brief] anthropic call failed: {e}\n")
        return None

    blocks = payload.get("content") or []
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
    return text or None


def _dumb_fallback(snapshot: dict) -> str:
    """Pre-AI fallback. If Claude is unreachable, at least ship the numbers
    so CC knows the brief tried to fire."""
    rev = (snapshot.get("revenue") or {}).get("mrr") or {}
    pipe = snapshot.get("pipeline") or {}
    followups = snapshot.get("followups_due") or {}
    alerts = snapshot.get("client_health_alerts") or {}

    def _scalar(d, *keys, default="—"):
        v = d
        for k in keys:
            if not isinstance(v, dict):
                return default
            v = v.get(k)
            if v is None:
                return default
        return v

    return (
        f"📊 Daily brief ({snapshot.get('date', 'today')}) — AI narration unavailable\n\n"
        f"• MRR: {_scalar(rev, 'net_mrr_cad', default=_scalar(rev, 'net_mrr_usd'))}\n"
        f"• Pipeline total: {_scalar(pipe, 'total')}\n"
        f"• Follow-ups due: {_scalar(followups, 'total')}\n"
        f"• Client health alerts: {_scalar(alerts, 'total')}\n"
        f"• Snapshot ts: {snapshot.get('ts')}"
    )


def build_brief(regenerate: bool = False) -> str:
    env = _load_env()
    snapshot = _read_snapshot(regenerate)
    if not snapshot:
        return "Daily brief: snapshot unreadable. Run `python scripts/snapshots/briefing_snapshot.py` manually."

    narrated = _narrate(snapshot, env)
    if narrated:
        date_str = snapshot.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        return f"🌅 Bravo brief · {date_str}\n\n{narrated}"
    return _dumb_fallback(snapshot)


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
