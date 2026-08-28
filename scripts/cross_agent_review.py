# bridge_mutating: true
#
# Deliberate. `scan` and `show` are read-only, but `review` posts an ack/blocked
# row the peer acts on, and a wrong verdict published under Bravo's name is an
# outward effect. Over-confirming a read costs a tap; an unapproved verdict costs
# the peer's trust in the channel.
"""cross_agent_review — Bravo reviews APEX's PRs on surfaces Bravo owns.

WHY THIS EXISTS
---------------
We have three review layers and they are not the same thing:

  CodeRabbit  — reads the diff. Finds the null deref, the N+1, the missing guard.
  Vercel / CI — proves it builds and deploys.
  THIS        — CONTEXT review. The constraint that is not in the diff.

A bot finds the null deref. Only the surface owner knows the field is nullable
because a client's import in July depended on it, or that the "unused" branch is
load-bearing for a tenant nobody has migrated yet. That knowledge does not live
in the code and cannot be inferred from it — it lives in whichever agent owns
the surface. `review_harvest.py` already closes the CodeRabbit loop for Bravo's
own PRs; this closes the loop the bots structurally cannot.

It is also the enforcement half of the contract's two-step verification: a
change to a surface the ownership map assigns to the other agent needs that
agent's `ack` before merge. Until now that rule lived in prose, which is exactly
the shape that decayed to zero the last time.

WHAT IT DOES NOT DO
-------------------
It does not merge, push, or edit the peer's branch. It reads, forms a verdict,
and publishes it to the channel the peer already polls. The peer decides what to
do with it. Agents coordinate; humans direct.

  python scripts/cross_agent_review.py scan                 # peer PRs on my surfaces
  python scripts/cross_agent_review.py review --pr OWNER/REPO#341
  python scripts/cross_agent_review.py show --pr OWNER/REPO#341   # recorded verdicts
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import ownership  # noqa: E402

import review_harvest as rh  # noqa: E402  — reuse its authenticated gh() and PR plumbing

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERDICT_LOG = PROJECT_ROOT / "state" / "cross_agent_reviews.jsonl"
# Git identities that mean "the peer", from the ownership map rather than a
# second hardcoded list that would drift from it.
def _self_identities() -> set[str]:
    """Bravo's own git identities, from the ownership map."""
    meta = (ownership.load().get("agents") or {}).get("bravo") or {}
    return set(meta.get("git_identities") or []) | {"bravo"}


def _peer_identities() -> set[str]:
    agents = ownership.load().get("agents") or {}
    out: set[str] = set()
    for key, meta in agents.items():
        if key == "bravo":
            continue
        out.update(meta.get("git_identities") or [])
        out.add(key)
    return out


def _pr_files(repo: str, number: int) -> list[str]:
    code, out, _ = rh.gh(["api", f"repos/{repo}/pulls/{number}/files",
                          "--paginate", "-q", ".[].filename"])
    return [ln.strip() for ln in out.splitlines() if ln.strip()] if code == 0 else []


def pr_commit_authors(repo: str, number: int) -> set[str]:
    """Commit author NAMES on a PR — the only trustworthy peer signal.

    The GitHub `author` field is useless here: both agents push under the same
    account, so every PR in this repo reports `CC90210`. The commit author name
    is what actually differs (`APEX (Adon)`, `Adon Bousseau`, `CC90210`, `CC`),
    and those are exactly the `git_identities` the ownership map already lists —
    so this reuses the map rather than growing a second list that would drift.

    Getting this wrong is not cosmetic: matching on a branch-name heuristic
    would let Bravo review its OWN pull request as if it were the peer's, and
    publish a verdict on its own work under the peer-review channel.
    """
    code, out, _ = rh.gh(["api", f"repos/{repo}/pulls/{number}/commits",
                          "--paginate", "-q", ".[].commit.author.name"])
    return {ln.strip() for ln in out.splitlines() if ln.strip()} if code == 0 else set()


def _pr_meta(repo: str, number: int) -> dict:
    code, out, _ = rh.gh(["api", f"repos/{repo}/pulls/{number}",
                          "-q", "{title:.title,author:.user.login,branch:.head.ref,state:.state,draft:.draft}"])
    if code != 0:
        return {}
    try:
        return json.loads(out)
    except Exception:  # noqa: BLE001
        return {}


def classify(repo_slug: str, files: list[str]) -> dict:
    """Split a PR's files by whose surface they land on."""
    buckets: dict[str, list[str]] = {"bravo": [], "apex": [], "shared": [], "other": []}
    for f in files:
        owner = ownership.owner(repo_slug, f) or "shared"
        buckets.setdefault(owner if owner in buckets else "other", []).append(f)
    return buckets


def needs_my_review(buckets: dict) -> bool:
    """Bravo reviews what lands on Bravo's surface or on contested ground.
    A PR entirely inside APEX's own surface is APEX's call — ownership is a
    default, not a fence, and reviewing everything would make the ack meaningless."""
    return bool(buckets.get("bravo") or buckets.get("shared"))


def _record(entry: dict) -> None:
    VERDICT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(VERDICT_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")


def _load_records() -> list[dict]:
    try:
        return [json.loads(ln) for ln in
                VERDICT_LOG.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception:  # noqa: BLE001
        return []


def scan(repo: str) -> list[dict]:
    """Open peer PRs that touch a surface Bravo owns or that is contested."""
    peers = _peer_identities()
    slug = repo.split("/")[-1].lower()
    found = []
    for number in rh.open_prs(repo):
        meta = _pr_meta(repo, number)
        if not meta or meta.get("state") != "open":
            continue
        authors = pr_commit_authors(repo, number)
        # Peer iff EVERY commit author is a peer identity. A PR with a Bravo
        # commit on it is at least partly Bravo's own work, and reviewing your
        # own change as the peer's is a false verdict published under the
        # peer-review channel.
        # Read Bravo's identities from the SAME map as the peer's. A second
        # hardcoded list here would be the fourth instance of this drift class
        # in this subsystem, and the one that fails silently: add a new Bravo
        # git identity to the map, forget this copy, and Bravo starts reviewing
        # its own pull requests as the peer's.
        mine = _self_identities()
        if not authors or (authors & mine) or not (authors & peers):
            continue
        files = _pr_files(repo, number)
        if not files:
            continue
        buckets = classify(slug, files)
        if not needs_my_review(buckets):
            continue
        found.append({"repo": repo, "number": number, "title": meta.get("title"),
                      "author": ", ".join(sorted(authors)), "branch": meta.get("branch"),
                      "draft": meta.get("draft"), "buckets": buckets,
                      "files": files})
    return found


REVIEW_PROMPT = """You are Bravo, CC's engineering agent. You are reviewing a pull \
request written by APEX, Adon's agent, on a surface YOU own or that both agents \
contest.

This is CONTEXT REVIEW, not code review. CodeRabbit already read the diff for \
correctness and CI already proved it builds. Your job is the part a bot \
structurally cannot do: the constraint that is not visible in the diff.

Ask specifically:
- Does this change something whose current shape is deliberate for a reason not \
stated in the code? A prior incident, a client dependency, a migration nobody \
finished?
- Does it duplicate something that already exists elsewhere in the fleet?
- Does it break an assumption a DIFFERENT system makes about this surface?
- Does it silently change a contract (a column, a status value, a file path, an \
env var) that another agent or service reads?

Be specific and short. If you have no context-level objection, say so plainly — \
a reflexive nitpick makes the ack worthless. Do NOT restate what the diff does.

REPO: {repo}   PR #{number}: {title}
BRANCH: {branch}   AUTHOR: {author}

Files on Bravo's surface:
{bravo_files}

Files on contested/shared surface:
{shared_files}

DIFF (truncated):
{diff}

Respond in exactly this shape:
VERDICT: ack | blocked
SUMMARY: one sentence
FINDINGS:
- each finding on its own line, with the file it concerns. Empty if none.
"""


def _diff(repo: str, number: int, limit: int = 24000) -> str:
    code, out, _ = rh.gh(["api", f"repos/{repo}/pulls/{number}",
                          "-H", "Accept: application/vnd.github.v3.diff"], timeout=120)
    if code != 0:
        return "(diff unavailable)"
    return out[:limit] + ("\n...(truncated)" if len(out) > limit else "")


def review(repo: str, number: int, *, post: bool = True, dry: bool = False) -> dict:
    slug = repo.split("/")[-1].lower()
    meta = _pr_meta(repo, number)
    files = _pr_files(repo, number)
    if not files:
        return {"error": f"no files on {repo}#{number} (or gh call failed)"}
    buckets = classify(slug, files)

    if not needs_my_review(buckets):
        return {"skipped": "PR does not touch a Bravo-owned or contested surface",
                "buckets": buckets}

    prompt = REVIEW_PROMPT.format(
        repo=repo, number=number, title=meta.get("title", "?"),
        branch=meta.get("branch", "?"), author=meta.get("author", "?"),
        bravo_files="\n".join(f"  {f}" for f in buckets["bravo"]) or "  (none)",
        shared_files="\n".join(f"  {f}" for f in buckets["shared"]) or "  (none)",
        diff=_diff(repo, number))

    if dry:
        return {"prompt_chars": len(prompt), "buckets": buckets, "dry": True}

    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from lib import claude_cli  # noqa: PLC0415
    res = claude_cli.run_claude_cli(prompt, timeout=600)
    text = (res or {}).get("text") if isinstance(res, dict) else (res or "")
    if not text:
        # Fail LOUD. A review that silently produced nothing must never be
        # recorded as an ack — that is a rubber stamp wearing a verdict's face.
        return {"error": "model returned no text; NOT posting a verdict"}

    verdict = "blocked" if "\nVERDICT: blocked" in f"\n{text}" else "ack"
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(), "repo": repo, "pr": number,
        "title": meta.get("title"), "author": meta.get("author"),
        "verdict": verdict, "review": text,
        "surfaces": {k: v for k, v in buckets.items() if v},
    }
    _record(entry)

    if post:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))
        import agent_activity  # noqa: PLC0415
        summary = next((ln.split(":", 1)[1].strip() for ln in text.splitlines()
                        if ln.upper().startswith("SUMMARY:")), text[:200])
        try:
            agent_activity.post(
                verdict,
                f"Review of {repo}#{number} — {meta.get('title','')[:70]}",
                files=(buckets["bravo"] + buckets["shared"])[:8],
                branch=meta.get("branch"),
                detail=f"Bravo context-review verdict: {verdict.upper()}. {summary} "
                       f"Full findings on the PR. Surfaces reviewed: "
                       f"bravo={len(buckets['bravo'])}, shared={len(buckets['shared'])}.")
            entry["posted"] = True
        except ValueError as e:
            # The escalation lint can legitimately refuse a verdict whose text
            # reads like a failure report. Surface it rather than dropping it.
            entry["posted"] = False
            entry["post_error"] = str(e)[:300]
    return entry


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("scan", help="open peer PRs touching my surfaces")
    ps.add_argument("--repo", default="CC90210/oasis-command-center")
    ps.add_argument("--json", action="store_true")

    pr = sub.add_parser("review", help="context-review a peer PR and publish the verdict")
    pr.add_argument("--pr", required=True, help="OWNER/REPO#NUMBER")
    pr.add_argument("--no-post", action="store_true", help="review without publishing")
    pr.add_argument("--dry-run", action="store_true")
    pr.add_argument("--json", action="store_true")

    pw = sub.add_parser("show", help="verdicts recorded so far")
    pw.add_argument("--pr")
    pw.add_argument("--json", action="store_true")

    a = p.parse_args()

    if a.cmd == "scan":
        found = scan(a.repo)
        if a.json:
            print(json.dumps(found, indent=2, default=str))
        elif not found:
            print("no open peer PRs on Bravo-owned or contested surfaces")
        else:
            print(f"{len(found)} peer PR(s) awaiting Bravo review:")
            for f in found:
                b, s = len(f["buckets"]["bravo"]), len(f["buckets"]["shared"])
                print(f"  #{f['number']:<5} {(f['title'] or '')[:56]}")
                print(f"         by {f['author']} · bravo-surface {b} · shared {s}"
                      f"{' · DRAFT' if f.get('draft') else ''}")
        return 0

    if a.cmd == "review":
        try:
            repo, num = a.pr.split("#")
            number = int(num)
        except Exception:  # noqa: BLE001
            print("--pr must look like OWNER/REPO#341", file=sys.stderr)
            return 2
        res = review(repo, number, post=not a.no_post, dry=a.dry_run)
        if a.json:
            print(json.dumps(res, indent=2, default=str))
            return 1 if res.get("error") else 0
        if res.get("error"):
            print(f"ERROR: {res['error']}", file=sys.stderr)
            return 1
        if res.get("skipped"):
            print(f"skipped — {res['skipped']}")
            return 0
        if res.get("dry"):
            print(f"dry run — prompt {res['prompt_chars']} chars, surfaces {res['buckets']}")
            return 0
        print(f"VERDICT: {res['verdict'].upper()}"
              f"{'  (published)' if res.get('posted') else '  (NOT published)'}")
        if res.get("post_error"):
            print(f"  post refused: {res['post_error']}", file=sys.stderr)
        print()
        print(res["review"])
        return 3 if res["verdict"] == "blocked" else 0

    if a.cmd == "show":
        recs = _load_records()
        if a.pr:
            recs = [r for r in recs if f"{r['repo']}#{r['pr']}" == a.pr]
        if a.json:
            print(json.dumps(recs, indent=2, default=str))
        elif not recs:
            print("(no verdicts recorded)")
        else:
            for r in recs[-20:]:
                print(f"  {r['ts'][:19]}  {r['verdict'].upper():8} {r['repo']}#{r['pr']}"
                      f"  {(r.get('title') or '')[:48]}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
