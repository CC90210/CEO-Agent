"""lender_response_classifier.py — close the loop on lender shop-out.

Phase 6.4 of the SunBiz CRM build (2026-05-15). Lender threads created
by /api/applications/[id]/shop-out land in application_lender_threads
with status='sent' and a gmail_thread_id once the physical send fires.
This daemon polls Gmail for new messages on those threads, classifies
each via Claude (approved / declined / info_requested), and updates
the thread row so the operator sees the funding-pipeline state without
ever opening Gmail.

Architecture:

  application_lender_threads (status=sent)
        |
        v
  Daemon poll loop  -- per-thread: fetch newest message via google_tool
        |
        v
  Claude classifier  -- prompt: "is this an approval, decline, info
                                  request, or none-of-the-above?"
        |
        v
  Update row.status + last_response_summary + last_response_at

The classifier is conservative: when Claude returns low confidence,
status stays 'responded' (not approved/declined). Operators see the
ambiguity flag and can manually disambiguate. Cheaper than wrong calls
that misroute leads.

SLA-based 'no_response' transition: if a thread has been at status=sent
for longer than the lender's sla_response_days, it auto-flips to
'no_response' without consuming a classifier call. Operator decides
whether to follow up or move on.

CLI:
  python scripts/lender_response_classifier.py loop --interval 300
  python scripts/lender_response_classifier.py once
  python scripts/lender_response_classifier.py tail
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "state"
LOG_PATH = STATE_DIR / "lender_response_classifier.log"

# Look back this far when scanning Gmail threads on each poll. Older
# threads are presumed already-classified or no_response (and would
# have aged out via the SLA check anyway). Tunable.
THREAD_LOOKBACK_DAYS = 30

# Default response SLA used when the lender row has no sla_response_days
# field. Conservative ~7 business days.
DEFAULT_SLA_DAYS = 10


def _log(msg: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}\n"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass
    print(line.rstrip())


# ─────────────────────────────────────────────────────────────────────
# Supabase client + env loading — mirrors sequence_runner.py
# ─────────────────────────────────────────────────────────────────────


def _supabase():
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from lib.secret_loader import load_env  # type: ignore
    except Exception:
        return None
    try:
        env = load_env()
    except Exception:
        return None
    url = (env.get("BRAVO_SUPABASE_URL") or "").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return None
    try:
        from supabase import create_client
    except ImportError:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None


def _load_env_var(name: str) -> str:
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from lib.secret_loader import load_env  # type: ignore
        return (load_env().get(name) or os.environ.get(name) or "").strip()
    except Exception:
        return os.environ.get(name, "").strip()


# ─────────────────────────────────────────────────────────────────────
# SLA-based no_response auto-flip
# ─────────────────────────────────────────────────────────────────────


def sla_sweep(sb) -> int:
    """Find sent-but-silent threads past their SLA, mark them
    no_response. No classifier calls; cheap + safe."""
    try:
        rows = (
            sb.table("application_lender_threads")
            .select("id, lender_id, tenant_id, sent_at")
            .eq("status", "sent")
            .not_.is_("sent_at", "null")
            .execute()
        )
    except Exception as e:
        _log(f"sla_sweep: read failed: {e}")
        return 0
    if not rows.data:
        return 0

    # Batch-fetch the SLAs from lender rows (tenant_records).
    lender_ids = list({r["lender_id"] for r in rows.data})
    sla_by_lender: dict[str, int] = {}
    try:
        lenders = (
            sb.table("tenant_records")
            .select("id, data")
            .in_("id", lender_ids)
            .eq("entity_type", "lender")
            .execute()
        )
        for L in lenders.data or []:
            sla = (L.get("data") or {}).get("sla_response_days")
            if isinstance(sla, (int, float)) and sla > 0:
                sla_by_lender[L["id"]] = int(sla)
    except Exception as e:
        _log(f"sla_sweep: lender lookup failed: {e}")

    flipped = 0
    now = datetime.now(timezone.utc)
    for r in rows.data:
        sent_at_iso = r.get("sent_at")
        if not sent_at_iso:
            continue
        try:
            sent_at = datetime.fromisoformat(sent_at_iso.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        sla = sla_by_lender.get(r["lender_id"], DEFAULT_SLA_DAYS)
        if (now - sent_at) < timedelta(days=sla):
            continue
        try:
            sb.table("application_lender_threads").update({
                "status": "no_response",
                "last_error": f"SLA {sla}d exceeded; no reply from lender",
            }).eq("id", r["id"]).execute()
            flipped += 1
        except Exception as e:
            _log(f"sla_sweep: update failed row={r['id']}: {e}")
    return flipped


# ─────────────────────────────────────────────────────────────────────
# Gmail thread fetch via google_tool subprocess
# ─────────────────────────────────────────────────────────────────────


def fetch_thread_latest_body(thread_id: str) -> str | None:
    """Pull the most recent message body from a Gmail thread.
    Subprocesses out to google_tool.py to inherit the existing OAuth
    plumbing rather than wiring a second Gmail client here.

    Windows console-window suppression: when the parent daemon is run
    under pythonw.exe via PM2, pythonw doesn't have a console; but
    a child python.exe subprocess WILL allocate one unless we pass
    CREATE_NO_WINDOW. Operator sees no popups regardless.
    """
    if not thread_id:
        return None
    # Windows-only flag — on POSIX it's not defined and we just pass 0.
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "google_tool.py"),
                "gmail",
                "thread-latest",
                "--thread-id",
                thread_id,
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=creationflags,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        _log(f"gmail fetch failed thread={thread_id}: {e}")
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None
    body = data.get("body") or data.get("snippet") or ""
    return body if isinstance(body, str) else None


# ─────────────────────────────────────────────────────────────────────
# Claude classifier
# ─────────────────────────────────────────────────────────────────────


CLASSIFIER_PROMPT = """You're triaging a lender's email response to a funding-shop submission. Classify the reply into EXACTLY ONE of:

- approved        — lender offered terms (factor rate, amount, advance, etc.)
- declined        — lender passed (no offer; may say "not a fit," "credit declined," etc.)
- info_requested  — lender asked for more docs / clarification / a call before deciding
- unclear         — automated bounce, out-of-office, unrelated reply, or you genuinely can't tell

Return JSON with two keys ONLY:
  {"label": "<one of above>", "summary": "<one-sentence operator-facing summary, max 200 chars>"}

The email body is between the markers below.

<email>
{body}
</email>
"""


def classify_with_claude(body: str) -> dict:
    """Call Claude to classify the lender response. Returns
    {"label": str, "summary": str} or {"label": "unclear", ...} on
    any failure. Best-effort by design."""
    api_key = _load_env_var("ANTHROPIC_API_KEY")
    if not api_key:
        return {"label": "unclear", "summary": "ANTHROPIC_API_KEY not configured"}
    try:
        import requests
    except ImportError:
        return {"label": "unclear", "summary": "requests package not installed"}

    prompt = CLASSIFIER_PROMPT.format(body=body[:4000])
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
    except requests.RequestException as e:
        return {"label": "unclear", "summary": f"network error: {e}"}
    if r.status_code >= 400:
        return {"label": "unclear", "summary": f"Anthropic HTTP {r.status_code}"}
    try:
        data = r.json()
    except ValueError:
        return {"label": "unclear", "summary": "non-JSON response from Anthropic"}
    text = ""
    for blk in data.get("content", []):
        if blk.get("type") == "text":
            text += blk.get("text", "")
    text = text.strip()
    # Try to parse strict JSON; if Claude added prose around it, find
    # the {...} block.
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        s = text.find("{")
        e = text.rfind("}")
        if s != -1 and e > s:
            try:
                parsed = json.loads(text[s : e + 1])
            except json.JSONDecodeError:
                return {"label": "unclear", "summary": "couldn't parse classifier output"}
        else:
            return {"label": "unclear", "summary": "no JSON in classifier output"}

    label = str(parsed.get("label", "")).lower().strip()
    if label not in {"approved", "declined", "info_requested", "unclear"}:
        label = "unclear"
    summary = str(parsed.get("summary", ""))[:200]
    return {"label": label, "summary": summary}


# ─────────────────────────────────────────────────────────────────────
# Classifier tick
# ─────────────────────────────────────────────────────────────────────

# Map classifier label -> application_lender_threads.status enum value.
LABEL_TO_STATUS = {
    "approved": "approved",
    "declined": "declined",
    "info_requested": "info_requested",
    # unclear -> stay at 'responded' so the operator sees something
    # came in but decides themselves.
    "unclear": "responded",
}


def classify_tick(sb) -> int:
    """Find threads that have a Gmail thread_id, are still at status=sent,
    fetch the latest reply, classify, update status."""
    try:
        rows = (
            sb.table("application_lender_threads")
            .select("id, tenant_id, gmail_thread_id, status, sent_at")
            .eq("status", "sent")
            .not_.is_("gmail_thread_id", "null")
            .execute()
        )
    except Exception as e:
        _log(f"classify_tick: read failed: {e}")
        return 0
    if not rows.data:
        return 0

    classified = 0
    for r in rows.data:
        body = fetch_thread_latest_body(r["gmail_thread_id"])
        if not body:
            continue
        result = classify_with_claude(body)
        new_status = LABEL_TO_STATUS.get(result["label"], "responded")
        try:
            sb.table("application_lender_threads").update({
                "status": new_status,
                "last_response_at": datetime.now(timezone.utc).isoformat(),
                "last_response_summary": result["summary"],
            }).eq("id", r["id"]).execute()
            classified += 1
            _log(f"classified thread={r['id']} -> {new_status}: {result['summary']}")
        except Exception as e:
            _log(f"classify_tick: update failed row={r['id']}: {e}")
    return classified


# ─────────────────────────────────────────────────────────────────────
# Daemon
# ─────────────────────────────────────────────────────────────────────


def tick() -> tuple[int, int]:
    sb = _supabase()
    if not sb:
        _log("supabase unavailable — skipping tick")
        return 0, 0
    classified = classify_tick(sb)
    aged = sla_sweep(sb)
    return classified, aged


def loop(interval: int) -> int:
    interval = max(60, int(interval))  # never poll Gmail faster than once a minute
    _log(f"lender-response-classifier up; tick interval = {interval}s")
    while True:
        try:
            tick()
        except Exception as e:
            _log(f"tick crashed: {e}")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            _log("classifier shutting down (SIGINT)")
            return 0


def tail(count: int) -> int:
    if not LOG_PATH.exists():
        print("(no log yet)")
        return 0
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-count:]
    except OSError as e:
        print(f"read failed: {e}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Lender response classifier — Gmail label monitor")
    sub = p.add_subparsers(dest="command", required=True)

    once = sub.add_parser("once", help="Run one tick and exit")
    once.set_defaults(func=lambda _a: 0 if tick() else 0)

    lp = sub.add_parser("loop", help="Run continuously")
    lp.add_argument("--interval", type=int, default=300, help="seconds between ticks (default: 300 = 5 min)")
    lp.set_defaults(func=lambda a: loop(a.interval))

    tl = sub.add_parser("tail", help="Print the last N log lines")
    tl.add_argument("--count", type=int, default=50)
    tl.set_defaults(func=lambda a: tail(a.count))

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
