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
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402
from lib.json_ledger import load_ledger, save_ledger  # noqa: E402
from review_harvest import canonical_repo, gh, harvest_pr  # noqa: E402

# notify_error was USED at the escalation site below but never imported — a
# NameError that would have fired at the exact moment the loop tried to tell CC
# something was wrong, and only then. Same shape as the missing `Optional` in
# notify.py (2026-07-30). Import what you call; a test now imports this module
# and asserts both names are bound.
try:
    from notify import notify, notify_error
except ImportError:  # pragma: no cover
    def notify(*_a, **_kw):
        return False

    def notify_error(*_a, **_kw):
        return False

QUEUE_PATH = PROJECT_ROOT / "tmp" / "review_harvest_queue.json"

# How many times a PR whose fix did not land may be retried before the loop
# gives up and escalates. Bounded on purpose: unbounded retry is what produced
# the 2026-07-30 overnight alert storm, and dropping it silently is the bug that
# replaced it. At the */15 cadence this is ~45 minutes of trying before CC hears
# about it once.
RETRY_LIMIT = int(os.environ.get("REVIEW_LOOP_RETRY_LIMIT", "3") or "3")

# Statuses meaning the fixer is DONE with a finding, whether or not it succeeded.
# Anything review_fix can emit that is not here is treated as retryable.
#
#   fixed / skipped / no-op  — resolved, or deliberately not ours to touch
#   would-fix                — dry-run output; nothing was attempted
#   escalated                — operator-owned. Already Telegrammed, and left out
#                              of the harvest seen-ledger, so a manual
#                              `review_harvest.py --pr` still surfaces it.
#                              Retrying every 15 min would only re-spam.
#
# Retryable (failed / reverted / committed-not-pushed) means NOTHING reached the
# branch. Draining those loses the review permanently, because the only thing
# that enqueues a PR is inbound review mail.
#
# MODULE SCOPE ON PURPOSE. This lived inside the loop body, so the test that was
# supposed to pin it declared its own copy and asserted against that — it would
# have passed while the real set drifted underneath. Same useless-guard shape as
# the anti-slop drift test earlier the same day. A constant a test cannot import
# is a constant no test protects.
TERMINAL_STATUSES = frozenset({"fixed", "skipped", "no-op", "escalated", "would-fix"})
# One PR per pass. The fixer spawns a full Claude session per finding; draining
# ten PRs in one tick would run for an hour and overlap the next cron fire.
MAX_PRS_PER_PASS = 1
MAX_FIXES_PER_PR = 3


def load_queue() -> dict:
    return load_ledger(QUEUE_PATH)


def save_queue(q: dict) -> None:
    # No cap: the queue is drained, not accumulated, and its values are dicts
    # rather than sortable timestamps.
    save_ledger(QUEUE_PATH, q, indent=2)


def pr_for_branch(repo: str, branch: str) -> Optional[int]:
    """Open PR whose HEAD is `branch`, or None.

    A "Run failed:" notification names the workflow and the branch but never a
    PR. This is the bridge from one to the other.
    """
    rc, out, _ = gh(["pr", "list", "--repo", canonical_repo(repo),
                     "--head", branch, "--state", "open",
                     "--json", "number", "--limit", "1"])
    if rc != 0 or not out:
        return None
    try:
        data = json.loads(out)
        return int(data[0]["number"]) if data else None
    except (ValueError, KeyError, IndexError, TypeError):
        return None


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


SEED_MAX_AGE_DAYS = 14


def _is_recent(updated_at: Optional[str], days: int) -> bool:
    """Was this PR touched recently enough to be worth auto-fixing?

    THE BOUND THE EMAIL PATH HAD IMPLICITLY. Mail only ever queued a PR that had
    just generated a notification, so recency came free. Polling has no such
    limit, and the first real run queued 22 PRs — including ones untouched since
    2026-07-20, several of them APEX's branches.

    review_fix EDITS AND PUSHES to the PR branch. Doing that to a branch dead for
    five weeks is wasted work at best and an unwelcome surprise on a peer's
    abandoned branch at worst. An unbounded poll is not more thorough than the
    email path; it is indiscriminate, which is a different thing.

    Pure on purpose: the timestamp arrives with the PR listing, so this is a
    date comparison a test can drive without touching the network.
    """
    if not updated_at:
        return False                      # cannot date it -> do not touch it
    try:
        ts = datetime.fromisoformat(updated_at.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).days <= days


def seed_from_open_prs(dry_run: bool = False, max_age_days: int = SEED_MAX_AGE_DAYS) -> int:
    """Queue every open PR that has UNRESOLVED review findings, without email.

    WHY: the queue was fed only by notification mail. That made the whole loop
    depend on a message arriving, being unread, and being classified — and the
    live evidence was a cron with 2098 runs, 0 failures, and `{"drained": 0}`
    every time, while 20+ peer PRs sat open with CodeRabbit findings on them. A
    healthy-looking loop doing nothing, because its only trigger never fired.

    Email stays as the fast path — it reacts in minutes. This is the floor: it
    asks GitHub directly, so a push with no mail (a forward that never arrived,
    a filtered notification, a peer pushing while the mailbox is quiet) is still
    picked up on the next pass.

    Entries match the shape email_engine._enqueue_review_harvest writes, keyed
    repo#pr, so the two producers cannot create competing formats for one queue.
    """
    import review_harvest as rh  # noqa: PLC0415

    queue = load_queue()
    added = 0
    skipped_stale = 0
    for repo in rh.TRACKED_REPOS if hasattr(rh, "TRACKED_REPOS") else []:
        for pr in rh.open_prs_detailed(repo):
            number = pr["number"]
            key = f"{repo}#{number}"
            if key in queue:
                continue                     # already queued by mail or a prior pass
            if not _is_recent(pr.get("updatedAt"), max_age_days):
                skipped_stale += 1           # dead branch — not ours to auto-edit
                continue
            res = rh.harvest_pr(repo, number)
            if not res or not res.get("findings"):
                continue
            if dry_run:
                print(f"  DRY seed {key} ({len(res['findings'])} unresolved)")
                added += 1
                continue
            queue[key] = {
                "repo": repo, "pr": number, "branch": pr.get("headRefName"),
                "kinds": sorted({f.get("kind", "review") for f in res["findings"]}),
                "message_ids": [], "count": len(res["findings"]),
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "source": "seed-open",       # distinguishes a poll from a mail ping
            }
            added += 1
    if added and not dry_run:
        save_queue(queue)
    if skipped_stale:
        # Never silent. A poll that quietly drops candidates reads as "nothing
        # to do", which is the exact failure this whole function exists to fix.
        print(f"  seed: skipped {skipped_stale} PR(s) not updated in "
              f"{max_age_days}d")
    return added


def main() -> None:
    ap = argparse.ArgumentParser(description="Drain the automated-review queue")
    ap.add_argument("--once", action="store_true", help="one drain pass")
    ap.add_argument("--status", action="store_true", help="show the queue, change nothing")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--seed-max-age-days", type=int, default=SEED_MAX_AGE_DAYS,
                    help="only seed PRs updated within this many days")
    ap.add_argument("--seed-open", action="store_true",
                    help="seed the queue from OPEN PRs with unresolved findings, "
                         "instead of waiting for a notification email")
    args = ap.parse_args()

    if args.seed_open:
        seed_from_open_prs(dry_run=args.dry_run, max_age_days=args.seed_max_age_days)

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

    # Resolve branch-only entries (workflow-failure mail carries no PR number)
    # to a PR before scheduling. Without this they were skipped by the `if
    # v.get("pr")` filter below AND never removed — a queue entry that could
    # never drain, accumulating one row per red CI run forever.
    resolved_any = False
    for key, entry in list(queue.items()):
        if entry.get("pr"):
            continue
        if not entry.get("branch"):
            # Neither a PR nor a branch — nothing here is addressable. This
            # shape comes from run_failed mail enqueued before the branch was
            # captured; keeping it means one dead row per red CI run, forever.
            queue.pop(key, None)
            resolved_any = True
            if not args.json:
                print(f"  dropped {key} — no PR and no branch to resolve")
            continue
        pr = pr_for_branch(entry["repo"], entry["branch"])
        if pr:
            entry["pr"] = pr
            resolved_any = True
            log_line = f"resolved {entry['repo']}@{entry['branch']} -> #{pr}"
        else:
            # No open PR for that branch (a push straight to a branch, or the PR
            # was merged/closed). Nothing this loop can act on.
            queue.pop(key, None)
            resolved_any = True
            log_line = (f"dropped {entry['repo']}@{entry['branch']} — "
                        f"no open PR for that branch")
        if not args.json:
            print(f"  {log_line}")
    if resolved_any and not args.dry_run:
        save_queue(queue)

    # Oldest-first: a PR that has been waiting should not starve behind a chatty
    # one that keeps re-enqueuing.
    entries = sorted((v for v in queue.values() if v.get("pr")),
                     key=lambda v: v.get("last_seen") or "")
    if not entries:
        print(json.dumps({"drained": 0}) if args.json else "review queue empty")
        return

    report, drained, blocked_out, kept = [], [], [], []
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

        # A BLOCKED PR needs a human, not a retry. review_fix exits 0 with
        # blocked=true for branch mismatch / protected branch / missing local
        # checkout — conditions that will be equally true in 15 minutes.
        # Draining is the whole point: the alternative is what CC actually got
        # on 2026-07-29, an identical alert every hour through the night.
        # Escalated once, below.
        if result.get("blocked") and not args.dry_run:
            for k in key_candidates:
                queue.pop(k, None)
            drained.append(f"{repo}#{pr}")
            blocked_out.append(
                f"{repo}#{pr}: {result.get('reason')} — {result.get('detail', '')[:140]}")
            continue
        # Drain only when the pass reached a TERMINAL state for every finding.
        #
        # Draining on any clean exit (2026-07-30, fixing the overnight storm)
        # over-corrected: review_fix exits 0 while reporting per-finding
        # `failed` / `reverted` / `committed-not-pushed` inside results. Nothing
        # landed on the branch in those cases, and the ONLY thing that enqueues
        # a PR is inbound review mail (email_engine._enqueue_review_harvest) —
        # there is no independent sweep of open PRs. So a drained-but-unfixed PR
        # was never looked at again until a NEW review comment happened to
        # arrive. Leaving the seen-ledger untouched does not save it: no reader
        # goes looking. (Found by Codex; the claim held once I traced the only
        # enqueue path.)
        #
        statuses = [r.get("status") for r in (result.get("results") or [])]
        retryable = [s for s in statuses if s not in TERMINAL_STATUSES]

        if not args.dry_run and not result.get("error"):
            if not retryable:
                for k in key_candidates:
                    queue.pop(k, None)
                drained.append(f"{repo}#{pr}")
            else:
                # Bounded retry, then give up LOUDLY. An unbounded retry is how
                # the original storm happened; a silent drop is what we just
                # fixed. Neither is acceptable, so: count, retry, escalate once.
                entry = queue.get(key_candidates[0]) or {}
                attempts = int(entry.get("fix_attempts") or 0) + 1
                if attempts >= RETRY_LIMIT:
                    for k in key_candidates:
                        queue.pop(k, None)
                    drained.append(f"{repo}#{pr}")
                    blocked_out.append(
                        f"{repo}#{pr}: gave up after {attempts} attempts — "
                        f"unresolved: {', '.join(sorted(set(retryable)))}")
                    notify_error(
                        "Review Loop",
                        f"{repo}#{pr}: {attempts} attempts, still unresolved "
                        f"({', '.join(sorted(set(retryable)))}). Needs you.",
                        stage=f"giveup:{repo}#{pr}",
                    )
                else:
                    for k in key_candidates:
                        if k in queue:
                            queue[k]["fix_attempts"] = attempts
                    kept.append(f"{repo}#{pr} ({attempts}/{RETRY_LIMIT}: "
                                f"{', '.join(sorted(set(retryable)))})")

    if not args.dry_run:
        save_queue(queue)

    if args.json:
        # SINGLE LINE, deliberately. scheduler.run_script_action stores only the
        # LAST stdout line in cron_jobs.last_result, so pretty-printed JSON makes
        # last_result literally "}" — which is what "Event Bus Offline Drain -> }"
        # in the PM2 log has been showing all along. Compact output means the
        # dashboard and the health check see a real result, not a brace.
        summary = {
            "drained": drained,
            # Surfaced so a PR being retried is VISIBLE rather than looking
            # identical to one that succeeded. A silent retry and a silent drop
            # read the same from outside.
            "kept": kept,
            "remaining": len(queue),
            "fixed": sum(1 for r in report
                         for x in (r.get("results") or []) if x["status"] == "fixed"),
            "escalated": sum(1 for r in report
                             for x in (r.get("results") or []) if x["status"] == "escalated"),
            "errors": [f"{r['repo']}#{r['pr']}: {r['error'][:80]}"
                       for r in report if r.get("error")],
            "at": datetime.now(timezone.utc).isoformat(),
            "report": report,
        }
        print(json.dumps(summary, separators=(",", ":")))
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
        for k in kept:
            print(f"  retrying: {k}")
        print(f"\ndrained {len(drained)}, kept {len(kept)}, {len(queue)} still queued")

    # review_fix already Telegrams per-PR on a successful fix; only speak here
    # when the LOOP itself failed, so CC isn't double-pinged.
    errored = [r for r in report if r.get("error")]
    if errored and not args.dry_run:
        notify("Review loop errors:\n" + "\n".join(
            f"  {r['repo']}#{r['pr']}: {r['error'][:120]}" for r in errored),
            category="system", silent=True, force=True)

    # Blocked PRs: ONE actionable message naming the fix, then the queue is
    # empty so it cannot repeat. dedup_key pins the alert to the blocking
    # CONDITION rather than the message text, so re-blocking on the same reason
    # within the window stays quiet even though the PR was re-queued by a new
    # CodeRabbit email.
    if blocked_out and not args.dry_run:
        notify("Review loop — needs you (no retry will help):\n"
               + "\n".join(f"  {b}" for b in blocked_out),
               category="system", silent=True, force=True,
               dedup_key="review_loop_blocked:" + "|".join(sorted(
                   b.split(" — ")[0] for b in blocked_out)))


if __name__ == "__main__":
    main()
