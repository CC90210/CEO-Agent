#!/usr/bin/env python3
"""review_loop.py — drain the review queue: harvest → fix → push → report.

The cron entry point that closes CC's loop. The inbox sweep detects a
CodeRabbit / Vercel / CI notification and writes (repo, pr) to
tmp/review_harvest_queue.json; this drains it.

  email arrives -> email_engine detects a review ping -> queue
                -> review_loop (cron) -> review_harvest (live gh state)
                -> review_fix (edit + test + push to the PR branch)
                -> Telegram summary to CC

Deliberately does NOT re-read the email. The email said "something happened on
PR #42"; everything acted on is fetched live, because a notification is a
snapshot and threads get resolved.

Usage:
    python scripts/review_loop.py --once            # drain one pass
    python scripts/review_loop.py --once --dry-run
    python scripts/review_loop.py --status
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402
from review_harvest import canonical_repo, harvest_pr  # noqa: E402

try:
    from notify import notify
except ImportError:  # pragma: no cover
    def notify(*_a, **_kw):
        return False

QUEUE_PATH = PROJECT_ROOT / "tmp" / "review_harvest_queue.json"
# One PR per pass. The fixer spawns a full Claude session per finding; draining
# ten PRs in one tick would run for an hour and overlap the next cron fire.
MAX_PRS_PER_PASS = 1
MAX_FIXES_PER_PR = 3


def load_queue() -> dict:
    try:
        if QUEUE_PATH.exists():
            d = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return d
    except Exception:  # noqa: BLE001
        pass
    return {}


def save_queue(q: dict) -> None:
    try:
        QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = QUEUE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(q, indent=2), encoding="utf-8")
        os.replace(tmp, QUEUE_PATH)
    except Exception as exc:  # noqa: BLE001
        print(f"[review_loop] could not persist queue: {exc}", file=sys.stderr)


def run_fixer(repo: str, pr: int, dry_run: bool) -> dict:
    venv = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if not venv.exists():
        venv = PROJECT_ROOT / ".venv" / "bin" / "python"
    cmd = [str(venv) if venv.exists() else sys.executable,
           str(PROJECT_ROOT / "scripts" / "review_fix.py"),
           "--pr", f"{repo}#{pr}", "--max", str(MAX_FIXES_PER_PR), "--json"]
    if dry_run:
        cmd.append("--dry-run")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=3600, cwd=str(PROJECT_ROOT),
                           creationflags=WINDOWLESS_FLAGS)
    except subprocess.TimeoutExpired:
        return {"error": "review_fix timed out (3600s)"}
    if r.returncode != 0:
        return {"error": (r.stderr or r.stdout or "non-zero exit").strip()[:400]}
    try:
        return json.loads(r.stdout or "{}")
    except Exception:  # noqa: BLE001
        return {"error": f"unparseable review_fix output: {(r.stdout or '')[:200]}"}


def main() -> None:
    ap = argparse.ArgumentParser(description="Drain the automated-review queue")
    ap.add_argument("--once", action="store_true", help="one drain pass")
    ap.add_argument("--status", action="store_true", help="show the queue, change nothing")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    queue = load_queue()

    if args.status or not args.once:
        if args.json:
            print(json.dumps({"queued": queue}, indent=2))
        elif not queue:
            print("review queue empty")
        else:
            print(f"{len(queue)} PR(s) queued:")
            for k, v in sorted(queue.items(),
                               key=lambda kv: kv[1].get("last_seen") or "", reverse=True):
                print(f"  {k:<44} {v.get('count', 0)} ping(s)  "
                      f"{', '.join(v.get('kinds') or [])}  last {v.get('last_seen', '')[:19]}")
        return

    # Oldest-first: a PR that has been waiting should not starve behind a chatty
    # one that keeps re-enqueuing.
    entries = sorted((v for v in queue.values() if v.get("pr")),
                     key=lambda v: v.get("last_seen") or "")
    if not entries:
        print(json.dumps({"drained": 0}) if args.json else "review queue empty")
        return

    report, drained = [], []
    for entry in entries[:MAX_PRS_PER_PASS]:
        repo = canonical_repo(entry["repo"])
        pr = int(entry["pr"])
        key_candidates = [k for k, v in queue.items()
                          if canonical_repo(v.get("repo", "")) == repo
                          and v.get("pr") == pr]

        h = harvest_pr(repo, pr)
        if h.get("error"):
            err = h["error"]
            report.append({"repo": repo, "pr": pr, "error": err})
            # Distinguish GONE from TRANSIENT (Codex P1, 2026-07-29).
            #
            # The first version popped the entry on ANY harvest error, so one
            # `gh` auth blip, API timeout or rate-limit permanently erased the
            # PR from the queue — and the queue is the only record. Only a PR
            # that genuinely no longer exists gets dropped immediately.
            gone = any(s in err.lower() for s in
                       ("not found", "404", "could not resolve to a pullrequest"))
            if gone:
                for k in key_candidates:
                    queue.pop(k, None)
            else:
                # Transient: keep it, count the attempt, and give up only after
                # a sustained failure so a genuinely poisoned entry can't wedge
                # the loop forever.
                for k in key_candidates:
                    entry_ref = queue.get(k)
                    if not entry_ref:
                        continue
                    entry_ref["harvest_failures"] = int(
                        entry_ref.get("harvest_failures", 0)) + 1
                    entry_ref["last_error"] = err[:200]
                    if entry_ref["harvest_failures"] >= 10:
                        queue.pop(k, None)
                        notify(f"Review loop: giving up on {repo}#{pr} after 10 "
                               f"failed harvests — {err[:140]}",
                               category="system", silent=True, force=True)
            continue

        if not h["findings"]:
            report.append({"repo": repo, "pr": pr, "status": "nothing unresolved"})
            for k in key_candidates:
                queue.pop(k, None)
            drained.append(f"{repo}#{pr}")
            continue

        result = run_fixer(repo, pr, args.dry_run)
        report.append({"repo": repo, "pr": pr, **result})
        # Drain on a clean run even if every finding merely escalated: review_fix
        # has already Telegrammed CC about the escalations, and re-notifying
        # every 15 minutes would be spam. The finding is NOT lost — escalated
        # threads are deliberately left out of the harvest's seen-ledger, so
        # `review_harvest.py --pr ...` still surfaces them until they are
        # genuinely resolved.
        if not args.dry_run and not result.get("error"):
            for k in key_candidates:
                queue.pop(k, None)
            drained.append(f"{repo}#{pr}")

    if not args.dry_run:
        save_queue(queue)

    if args.json:
        print(json.dumps({"drained": drained, "remaining": len(queue),
                          "at": datetime.now(timezone.utc).isoformat(),
                          "report": report}, indent=2))
    else:
        for r in report:
            print(f"\n{r['repo']}#{r['pr']}")
            if r.get("error"):
                print(f"  ERROR: {r['error'][:200]}")
                continue
            if r.get("status"):
                print(f"  {r['status']}")
            for item in r.get("results", []):
                print(f"  [{item['status']:<20}] {item.get('path') or '(PR)'}")
        print(f"\ndrained {len(drained)}, {len(queue)} still queued")

    # review_fix already Telegrams per-PR on a successful fix; only speak here
    # when the LOOP itself failed, so CC isn't double-pinged.
    errored = [r for r in report if r.get("error")]
    if errored and not args.dry_run:
        notify("Review loop errors:\n" + "\n".join(
            f"  {r['repo']}#{r['pr']}: {r['error'][:120]}" for r in errored),
            category="system", silent=True, force=True)


if __name__ == "__main__":
    main()
