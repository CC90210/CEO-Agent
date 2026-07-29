#!/usr/bin/env python3
"""review_harvest.py — pull UNRESOLVED automated-review signal out of GitHub.

The closed loop CC asked for on 2026-07-29: CodeRabbit and the Vercel bot review
our PRs, they email him about it, and until now that signal died in a GitHub tab.

DESIGN PRINCIPLE — the email is a NOTIFICATION, the API is the SOURCE OF TRUTH.
We never parse review content out of email. A GitHub notification email is a
point-in-time snapshot: by the time it is read the thread may be resolved, the
line may have moved, the comment may have been edited, or a newer review may
supersede it. So the email only tells us WHICH PR to look at; everything we act
on is fetched live via `gh`.

WHAT IT COLLECTS (per PR):
  * unresolved, non-outdated review threads (CodeRabbit inline comments)
  * top-level bot reviews (CodeRabbit summaries, Vercel deployment comments)
  * failing check runs (CI, substrate-eval, Vercel build)

WHAT IT SKIPS:
  * resolved or outdated threads — acting on those re-litigates settled code
  * threads already actioned (per-thread ledger in tmp/, same idiom as
    tmp/inbound_processed_msgids.json)

REPO ALIASING: CC90210/Business-Empire-Agent and CC90210/CEO-Agent resolve to
the SAME repository. Harvesting both would double every finding, so slugs are
canonicalised before dedup.

Usage:
    python scripts/review_harvest.py --pr CC90210/CEO-Agent#42
    python scripts/review_harvest.py --repo CC90210/CEO-Agent --open --json
    python scripts/review_harvest.py --all --json          # every tracked repo
    python scripts/review_harvest.py --pr ...#42 --mark-seen
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

# Per-thread ledger. Without it a harvest run that fires every 15 minutes would
# re-surface (and re-fix) the same comment forever — the exact runaway the
# inbound-email Message-ID ledger exists to prevent.
SEEN_PATH = PROJECT_ROOT / "tmp" / "review_threads_seen.json"
SEEN_MAX = 5000

# CC90210/Business-Empire-Agent is an alias of CC90210/CEO-Agent — same repo,
# two names. Canonicalise so findings dedupe.
REPO_ALIASES = {
    "cc90210/business-empire-agent": "CC90210/CEO-Agent",
}

TRACKED_REPOS = [
    "CC90210/CEO-Agent",
    "CC90210/CMO-Agent",
    "CC90210/CFO-Agent",
    "CC90210/oasis-command-center",
]

REVIEW_BOTS = {"coderabbitai", "coderabbitai[bot]", "vercel", "vercel[bot]",
               "github-actions", "github-actions[bot]", "dependabot",
               "dependabot[bot]", "copilot-pull-request-reviewer[bot]"}

# CodeRabbit tags its own findings with these markers; they map cleanly onto our
# triage order. Order matters — first match wins.
SEVERITY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("critical", re.compile(r"\[!CAUTION\]|critical|security|vulnerab|injection|"
                            r"credential|secret|rce|data\s*loss", re.I)),
    ("high", re.compile(r"\[!WARNING\]|potential issue|bug|race|deadlock|"
                        r"unguarded|null|crash|leak|timeout", re.I)),
    ("medium", re.compile(r"\[!NOTE\]|refactor|simplif|duplicat|performance|n\+1", re.I)),
]

# Never let the auto-fixer near these. Money, credentials, the outbound
# chokepoint, and schema changes are operator-approval territory.
DANGER_PATHS = re.compile(
    r"(^|/)(database/|migrations?/|\.env|\.github/workflows/|"
    r"send_gateway\.py|secret_guard\.py|exec_guard\.py|casl_compliance\.py|"
    r"stripe_|revenue_|payment)", re.I)


# ── helpers ──────────────────────────────────────────────────────────────────

def canonical_repo(slug: str) -> str:
    return REPO_ALIASES.get(slug.strip().lower(), slug.strip())


def gh(args: list[str], timeout: int = 90) -> tuple[int, str, str]:
    """Run gh. Returns (rc, stdout, stderr) — never raises on a non-zero exit."""
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           cwd=str(PROJECT_ROOT), creationflags=WINDOWLESS_FLAGS)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", "gh CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return 124, "", f"gh timed out after {timeout}s"


def load_seen() -> dict:
    try:
        if SEEN_PATH.exists():
            d = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return d
    except Exception:  # noqa: BLE001
        pass
    return {}


def save_seen(seen: dict) -> None:
    try:
        if len(seen) > SEEN_MAX:
            seen = dict(sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:SEEN_MAX])
        SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SEEN_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(seen), encoding="utf-8")
        tmp.replace(SEEN_PATH)
    except Exception as exc:  # noqa: BLE001
        print(f"[review_harvest] could not persist seen-ledger: {exc}", file=sys.stderr)


def severity_of(body: str) -> str:
    for name, pattern in SEVERITY_PATTERNS:
        if pattern.search(body or ""):
            return name
    return "low"


def is_dangerous(path: str) -> bool:
    return bool(path and DANGER_PATHS.search(path))


# ── GraphQL: unresolved review threads ───────────────────────────────────────
#
# The REST API exposes review comments but NOT isResolved / isOutdated — those
# live only on GraphQL's reviewThreads. Without them we cannot tell a live
# finding from one that was settled weeks ago, which is the difference between a
# useful loop and a bot that keeps reopening closed arguments.

THREADS_QUERY = """
query($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      title
      isDraft
      headRefName
      baseRefName
      url
      reviewThreads(first:100) {
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          comments(first:20) {
            nodes { databaseId author { login } body createdAt url }
          }
        }
      }
    }
  }
}
"""


def fetch_threads(repo: str, number: int) -> tuple[Optional[dict], list[dict], str]:
    owner, _, name = repo.partition("/")
    rc, out, err = gh([
        "api", "graphql",
        "-f", f"query={THREADS_QUERY}",
        "-F", f"owner={owner}", "-F", f"name={name}", "-F", f"number={number}",
    ])
    if rc != 0:
        return None, [], f"graphql failed: {err[:200]}"
    try:
        pr = json.loads(out)["data"]["repository"]["pullRequest"]
    except Exception as exc:  # noqa: BLE001
        return None, [], f"unparseable graphql response: {exc}"
    if not pr:
        return None, [], f"PR {repo}#{number} not found"

    findings: list[dict] = []
    for t in (pr.get("reviewThreads") or {}).get("nodes") or []:
        # THE filter. A resolved or outdated thread is settled history.
        if t.get("isResolved") or t.get("isOutdated"):
            continue
        comments = (t.get("comments") or {}).get("nodes") or []
        if not comments:
            continue
        first = comments[0]
        author = ((first.get("author") or {}).get("login") or "").lower()
        if author not in REVIEW_BOTS:
            continue  # human threads are CC's conversation, not ours to auto-fix
        body = first.get("body") or ""
        path = t.get("path") or ""
        findings.append({
            "kind": "review_thread",
            "thread_id": t["id"],
            "repo": repo,
            "pr": number,
            "author": author,
            "path": path,
            "line": t.get("line"),
            "severity": severity_of(body),
            "dangerous": is_dangerous(path),
            "body": body,
            "url": first.get("url"),
            "created_at": first.get("createdAt"),
            "reply_count": len(comments),
        })
    return pr, findings, ""


def fetch_failing_checks(repo: str, number: int) -> list[dict]:
    rc, out, _ = gh(["pr", "checks", str(number), "--repo", repo, "--json",
                     "name,state,bucket,link"])
    if rc != 0 or not out:
        return []
    try:
        checks = json.loads(out)
    except Exception:  # noqa: BLE001
        return []
    return [{
        "kind": "failing_check",
        "thread_id": f"check:{repo}#{number}:{c.get('name')}",
        "repo": repo, "pr": number,
        "author": "github-actions",
        "path": "", "line": None,
        "severity": "high",
        "dangerous": False,
        "body": f"Check '{c.get('name')}' is {c.get('bucket')}. {c.get('link') or ''}",
        "url": c.get("link"),
        "created_at": None,
        "reply_count": 0,
    } for c in checks if (c.get("bucket") or "").lower() in ("fail", "cancel")]


def harvest_pr(repo: str, number: int, *, include_seen: bool = False) -> dict:
    repo = canonical_repo(repo)
    pr, findings, err = fetch_threads(repo, number)
    if err:
        return {"repo": repo, "pr": number, "error": err, "findings": []}
    findings += fetch_failing_checks(repo, number)

    seen = load_seen()
    fresh = [f for f in findings if include_seen or f["thread_id"] not in seen]
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    fresh.sort(key=lambda f: (order.get(f["severity"], 9), f.get("path") or ""))

    return {
        "repo": repo,
        "pr": number,
        "title": pr.get("title"),
        "url": pr.get("url"),
        "branch": pr.get("headRefName"),
        "base": pr.get("baseRefName"),
        "is_draft": pr.get("isDraft"),
        "total": len(findings),
        "already_actioned": len(findings) - len(fresh),
        "findings": fresh,
    }


def open_prs(repo: str) -> list[int]:
    rc, out, _ = gh(["pr", "list", "--repo", canonical_repo(repo), "--state", "open",
                     "--json", "number,isDraft", "--limit", "50"])
    if rc != 0 or not out:
        return []
    try:
        return [p["number"] for p in json.loads(out) if not p.get("isDraft")]
    except Exception:  # noqa: BLE001
        return []


def mark_seen(thread_ids: list[str]) -> int:
    seen = load_seen()
    now = datetime.now(timezone.utc).isoformat()
    for t in thread_ids:
        seen[t] = now
    save_seen(seen)
    return len(thread_ids)


# ── CLI ──────────────────────────────────────────────────────────────────────

def _render(results: list[dict]) -> None:
    total = 0
    for r in results:
        if r.get("error"):
            print(f"\n{r['repo']}#{r['pr']}  ERROR: {r['error']}")
            continue
        if not r["findings"]:
            continue
        total += len(r["findings"])
        print(f"\n{r['repo']}#{r['pr']} — {r.get('title', '')[:70]}")
        print(f"  branch {r.get('branch')} -> {r.get('base')}   {r.get('url')}")
        if r["already_actioned"]:
            print(f"  ({r['already_actioned']} already actioned, skipped)")
        for f in r["findings"]:
            loc = f"{f['path']}:{f['line']}" if f["path"] else "(pr-level)"
            flag = "  [OPERATOR-ONLY]" if f["dangerous"] else ""
            print(f"    [{f['severity'].upper():<8}] {loc}{flag}")
            body = " ".join((f["body"] or "").split())[:150]
            print(f"               {body}")
    print(f"\n{total} unresolved finding(s) across {len(results)} PR(s)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Harvest unresolved automated-review signal")
    ap.add_argument("--pr", help="OWNER/REPO#N")
    ap.add_argument("--repo", help="OWNER/REPO (with --open)")
    ap.add_argument("--open", action="store_true", help="all open PRs in --repo")
    ap.add_argument("--all", action="store_true", help="all open PRs in every tracked repo")
    ap.add_argument("--include-seen", action="store_true",
                    help="do not filter already-actioned threads")
    ap.add_argument("--mark-seen", action="store_true",
                    help="record the returned threads as actioned")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rc, _, err = gh(["auth", "status"], timeout=30)
    if rc != 0:
        msg = f"gh not authenticated: {err[:200]}"
        print(json.dumps({"error": msg}) if args.json else msg, file=sys.stderr)
        sys.exit(1)

    jobs: list[tuple[str, int]] = []
    if args.pr:
        m = re.match(r"^(.+?)#(\d+)$", args.pr.strip())
        if not m:
            print("--pr must look like OWNER/REPO#42", file=sys.stderr)
            sys.exit(2)
        jobs.append((m.group(1), int(m.group(2))))
    elif args.repo and args.open:
        jobs += [(args.repo, n) for n in open_prs(args.repo)]
    elif args.all:
        for repo in TRACKED_REPOS:
            jobs += [(repo, n) for n in open_prs(repo)]
    else:
        print("need --pr, or --repo with --open, or --all", file=sys.stderr)
        sys.exit(2)

    # Canonicalise + dedupe: Business-Empire-Agent and CEO-Agent are one repo.
    seen_jobs, uniq = set(), []
    for repo, number in jobs:
        key = (canonical_repo(repo).lower(), number)
        if key not in seen_jobs:
            seen_jobs.add(key)
            uniq.append((canonical_repo(repo), number))

    results = [harvest_pr(r, n, include_seen=args.include_seen) for r, n in uniq]

    if args.mark_seen:
        mark_seen([f["thread_id"] for r in results for f in r.get("findings", [])])

    if args.json:
        print(json.dumps({"harvested_at": datetime.now(timezone.utc).isoformat(),
                          "results": results}, indent=2))
    else:
        _render(results)


if __name__ == "__main__":
    main()
