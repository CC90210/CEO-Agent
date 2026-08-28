"""PreToolUse hook — refuses an edit to a path a PEER AGENT currently holds.

Why this hook exists
--------------------
Bravo (CC) and APEX (Adon) edit the same OASIS repos from two machines. A
coordination protocol has existed in prose since 2026-06 — claim before you
touch a shared file — and it was measured on 2026-08-27 to have prevented
nothing: 226 of 1,596 files in oasis-command-center touched by both sides, and
117 cross-side edits of the SAME file inside 48h across 65 files, several under
30 minutes apart.

The cause was structural, not behavioural. Every other safety rule in this
repo is a hook — secret_guard, exec_guard, state_guard, subprocess_guard — and
every one of them held. Coordination was the only safety-critical protocol
enforced purely by documentation, and it decayed to zero, because an
unenforced protocol always does.

What it does NOT do
-------------------
It does not gate autonomy. It has exactly one denial condition: a live lease
held by a DIFFERENT agent covering this exact path. Your own leases never
block you, unclaimed paths never block you, and files outside a known repo
never block you. The only thing made impossible is two agents silently
reverting each other.

Failure behaviour — deliberately NOT fail-closed
------------------------------------------------
This is a collision gate, not a safety gate. secret_guard fails closed because
leaking a key is worse than a blocked command; here, failing closed on a Turso
hiccup would halt all editing on both machines, which is a far worse outcome
than the collision it prevents. So it FAILS DEGRADED: every successful lookup
mirrors live peer leases to state/coord_claims_mirror.json, and an outage falls
back to that mirror with its staleness stated in the log. It never silently
allows with no data at all — a fallback is always logged.

The mirror doubles as a cache (COORD_GUARD_CACHE_TTL_SEC, default 30s) so the
common case costs no network round-trip on every keystroke-level edit.

Modes (env var `EMPIRE_HOOK_COORD_GUARD`):
  enforce → exit 2 to block, naming the peer, their task, branch and machine
  report  → log a would-be block, allow  (SHIP HERE FIRST — burn in, confirm it
            would have fired on a real overlap, then flip)
  off     → pass through
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# scripts/ on the path so `import lib.*` and `import integrations.*` resolve.
# Mirrors the secret_guard.py fix — an earlier generation of these hooks pointed
# one .parent too far and failed OPEN silently, never enforcing or logging.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.hook_runtime import (  # noqa: E402
    PROJECT_ROOT,
    log_jsonl,
    mode_from_env,
    read_hook_input,
    state_log_path,
)

LOG_PATH = state_log_path("coord_guard")
MIRROR_PATH = PROJECT_ROOT / "state" / "coord_claims_mirror.json"
CACHE_TTL_SEC = int(os.environ.get("COORD_GUARD_CACHE_TTL_SEC", "30"))

EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")

REASON_TEMPLATE = """\
COORD GUARD — blocked: {peer} holds a live lease on this file.

  file    {repo}/{rel}
  peer    {peer}  (on machine {machine})
  task    {task}
  branch  {branch}
  expires {expires}

Two agents editing one file is not a merge conflict — it is one agent silently
reverting the other. That has happened 117 times across 65 files in the last 90
days, which is why this gate exists.

Your options, in order of preference:
  1. Work on something else until the lease expires or is released.
  2. Ask {peer} to release it:
       python scripts/integrations/coord_claim.py status --repo {repo} --all-agents
  3. If you have agreed a handoff with {peer}, they release and you acquire:
       python scripts/integrations/coord_claim.py acquire --repo {repo} \\
           --paths "{rel}" --task "<your task>"
"""


def _load_mirror() -> dict:
    try:
        return json.loads(MIRROR_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_mirror(claims: list[dict]) -> None:
    try:
        MIRROR_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = MIRROR_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"fetched_at": time.time(), "claims": claims},
                                  default=str), encoding="utf-8")
        tmp.replace(MIRROR_PATH)
    except Exception:  # noqa: BLE001
        pass


def _from_mirror(mirror: dict, repo: str, me: str) -> list[dict]:
    """Peer claims from the mirror that are STILL LIVE.

    Expiry must be re-evaluated against the clock NOW, not against the moment
    the mirror was written. Without this, a Turso outage pins the last-known
    lease set in place and an expired lease keeps blocking edits for the whole
    duration of the outage — which contradicts the TTL guarantee that a crashed
    agent cannot wedge a repo. (Codex adversarial review, 2026-08-27.)

    An unparseable or missing expiry is treated as NOT live: a corrupt row
    should free a path, never hold one hostage.
    """
    from datetime import datetime, timezone  # noqa: PLC0415
    now = datetime.now(timezone.utc)
    out = []
    for c in mirror.get("claims") or []:
        if c.get("repo") != repo or c.get("agent") == me:
            continue
        if (c.get("status") or "held") != "held":
            continue
        raw = c.get("expires_at")
        if not raw:
            continue
        try:
            txt = str(raw).strip()
            if txt.endswith(("Z", "z")):
                txt = txt[:-1] + "+00:00"
            exp = datetime.fromisoformat(txt)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            continue
        if exp > now:
            out.append(c)
    return out


def _peer_claims(repo: str, me: str) -> tuple[list[dict], str]:
    """(claims, source) where source is 'live' | 'cache' | 'stale-cache:<age>s'.

    Never raises — a coordination outage must not stop CC or Adon from working.
    """
    mirror = _load_mirror()
    age = time.time() - float(mirror.get("fetched_at") or 0)
    if mirror.get("claims") is not None and age < CACHE_TTL_SEC:
        return _from_mirror(mirror, repo, me), "cache"
    try:
        from integrations import coord_claim  # noqa: PLC0415 - lazy: keeps the
        # no-op path (most edits) off the Turso import entirely.
        # Mirror ALL live leases (ours included) — the nudge needs to know what
        # we hold, and a peer-only mirror made every own-lease look unclaimed.
        claims = coord_claim.live_claims()
        _save_mirror(claims)
        return [c for c in claims
                if c.get("repo") == repo and c.get("agent") != me], "live"
    except Exception as e:  # noqa: BLE001
        if mirror.get("claims") is None:
            return [], f"unavailable-no-cache ({type(e).__name__})"
        return (_from_mirror(mirror, repo, me),
                f"stale-cache:{int(age)}s ({type(e).__name__})")


def _nudge_if_contested(repo: str, rel: str, me: str) -> None:
    """Editing a MEASURED-CONTESTED path while holding no lease is the state that
    produced every collision in the record — neither agent claimed, so there was
    nothing for a peer to conflict with. Blocking here would be wrong (the peer
    is not actually in the file), but silence is what let the habit die. So:
    warn, never block, and only on the surfaces the data says are contested.
    """
    try:
        from lib import ownership  # noqa: PLC0415
        if not ownership.is_contested(repo, rel):
            return
        from lib import repo_paths  # noqa: PLC0415
        # Own leases come from the same mirror the peer check used — no second
        # round trip just to decide whether to print a hint.
        mine = [c for c in (_load_mirror().get("claims") or [])
                if c.get("repo") == repo and c.get("agent") == me
                and repo_paths.overlaps(c.get("path_glob", ""), rel)]
        if mine:
            return
    except Exception:  # noqa: BLE001
        return  # a nudge is never worth failing an edit over
    log_jsonl(LOG_PATH, {"decision": "unclaimed-contested", "repo": repo, "path": rel})
    sys.stderr.write(
        f"[coord_guard] {repo}/{rel} is a CONTESTED surface (both agents edit it) "
        f"and you hold no lease. Claim it so your peer can see you:\n"
        f"  python scripts/integrations/coord_claim.py acquire --repo {repo} "
        f'--paths "{rel}" --task "<what you are doing>"\n')


def main() -> int:
    mode = mode_from_env("EMPIRE_HOOK_COORD_GUARD", default="report")
    if mode == "off":
        return 0

    payload = read_hook_input()
    if not payload:
        return 0

    tool_name = payload.get("tool_name")
    if tool_name not in EDIT_TOOLS:
        return 0
    target = (payload.get("tool_input") or {}).get("file_path")
    if not target:
        return 0

    try:
        # repo_paths is stdlib + `git` only. Importing coord_claim here instead
        # pulled in db_turso, which connects at import time — measured 4-5s on
        # EVERY edit, cache hit or not. A guard that slow gets switched off.
        from lib import repo_paths  # noqa: PLC0415
        resolved = repo_paths.resolve(target)
        # overlaps(), not covers(): the edited file is a literal path here, so
        # covers() would suffice for it — but the HELD claim may be a glob and
        # both sides must use one predicate or the guard and the CLI disagree
        # about what conflicts (Codex P1, 2026-08-27).
        covers = repo_paths.overlaps
        me = os.environ.get("COORD_AGENT_KEY", "bravo").strip().lower()
    except Exception as e:  # noqa: BLE001
        # Import/resolve failure must not block editing. Log loudly and allow —
        # a silent pass here is the exact anti-pattern this file argues against.
        log_jsonl(LOG_PATH, {"decision": "allowed-guard-error",
                             "path": target, "error": f"{type(e).__name__}: {e}"})
        return 0

    if resolved is None:
        return 0  # not inside any git repo — nothing to coordinate on
    repo, rel = resolved

    claims, source = _peer_claims(repo, me)
    hit = next((c for c in claims if covers(c.get("path_glob", ""), rel)), None)

    if hit is None:
        if source.startswith(("stale-cache", "unavailable")):
            log_jsonl(LOG_PATH, {"decision": "allowed-degraded", "repo": repo,
                                 "path": rel, "source": source})
            # SAY IT ON STDERR, not just in the log. APEX raised this as its §4.2
            # on 2026-08-27 and it reproduced here: with an unreachable DB AND a
            # corrupt mirror, the guard returned zero peer claims — indistinguishable
            # from "nobody holds anything" — and the only thing the operator saw
            # was a routine contested-surface nudge. The log was honest; the
            # channel a human reads was not. Absence of data must never present
            # as absence of a problem.
            blind = source.startswith("unavailable")
            sys.stderr.write(
                f"[coord_guard] {'BLIND' if blind else 'DEGRADED'} — "
                f"{'could not read ANY lease data' if blind else 'using stale cached leases'} "
                f"({source}). This edit to {repo}/{rel} was ALLOWED WITHOUT A CHECK. "
                f"A peer may be in this file. Verify before you rely on it:\n"
                f"  python scripts/integrations/coord_claim.py status --repo {repo} --all-agents\n")
        _nudge_if_contested(repo, rel, me)
        return 0

    record = {
        "tool": tool_name, "repo": repo, "path": rel, "source": source,
        "peer": hit.get("agent"), "peer_task": hit.get("task"),
        "peer_branch": hit.get("branch"), "peer_machine": hit.get("machine"),
    }

    if mode == "enforce":
        log_jsonl(LOG_PATH, {"decision": "blocked", **record})
        sys.stderr.write(REASON_TEMPLATE.format(
            peer=(hit.get("agent") or "peer").upper(), repo=repo, rel=rel,
            machine=hit.get("machine") or "?", task=hit.get("task") or "?",
            branch=hit.get("branch") or "(none)",
            expires=hit.get("expires_at") or "?") + "\n")
        return 2

    log_jsonl(LOG_PATH, {"decision": "would-block", **record})
    sys.stderr.write(
        f"[coord_guard report-mode] would block {repo}/{rel} — "
        f"{(hit.get('agent') or 'peer').upper()} holds it "
        f"(task: {hit.get('task')}). Set EMPIRE_HOOK_COORD_GUARD=enforce to enforce.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
