"""refine.py — evidence-gated harness refinement (V7.6.0).

THE GAP THIS FILLS. `memory/PROPOSED_CHANGES.md` has specified the right schema
since 2026-05-21 — File / Section / Current / Proposed / Reason / Evidence /
Risk / Rollback / Status — and has been empty the entire time, because nothing
in the repo ever wrote to it. The design was accepted; the executor was never
built. Meanwhile `harness_eval.py` has accumulated 200+ scored runs and
`task_outcomes.py` 40+ verdicts that NOTHING reads. Measurement with no reader,
proposals with no writer.

This is the write path, and it closes both loops: a refinement is gated on a
measurement, so the telemetry finally decides something.

WHAT "EVIDENCE" MEANS HERE. Imported from PrimeIntellect-ai/prime-agent's
Continual Harness (MIT — formats and mechanics studied, no code copied), with
its weakest link deliberately inverted. In prime-agent, `refinement.ts:783-790`
sets `evidence: proposal.rationale` — the proposing model's own paragraph — and
every proposal carries an `expectedOutcome` field that is stored and never
executed. They store the expected outcome. We run it.

Evidence here is a COMMAND, and a refinement survives only if that command's
recorded output CHANGED. No delta => the change did nothing measurable => it is
reverted automatically and marked REJECTED. This is CLAUDE.md Rule 2 ("Proof:
the verification command + its actual output") made mechanical.

SAFETY. Auto-apply is an explicit ALLOWLIST (memory/*.md, skills/*/SKILL.md),
never a denylist: a path that matches nothing is HELD for CC. A new sensitive
directory is therefore protected the day it is created, without anyone
remembering to add it. Entry points, PERSONAL.md, brain/ and scripts/state/ can
never auto-apply — Rule 4 (lockstep) and Rule 10 (never silently rewrite shared
substrate).

FLEET-PORTABLE. This file is deployed verbatim into Maven (`~/CMO-Agent`) and
Atlas (`~/APPS/CFO-Agent`); only `CAPABILITY_META["owner"]` differs per agent.
Every path is derived from PROJECT_ROOT, `state/` is created on demand, and the
allowlist is expressed in repo-relative terms that hold in any agent repo. What
is NOT portable is the choice of evidence command: Bravo has `harness_eval.py`
and `task_outcomes.py`, the siblings do not, so each agent's SKILL.md documents
the evidence commands that actually exist there (`capability_query.py resolve`
is the one every agent has). Never hardcode an evidence command here.

CLI:
  python scripts/core/refine.py propose --kind memory --file memory/PATTERNS.md \\
      --current "<exact existing text>" --proposed "<replacement>" \\
      --evidence-cmd "python scripts/harness_eval.py --json" --evidence-key score \\
      --reason "why this helps"
  python scripts/core/refine.py list [--status PENDING] [--json]
  python scripts/core/refine.py show <id> [--json]
  python scripts/core/refine.py apply <id> [--approve] [--json]
  python scripts/core/refine.py revert <id> [--json]
  python scripts/core/refine.py ledger [--limit N] [--json]

Exit codes: 0 success, 1 refused/failed, 2 bad usage.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shlex
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CAPABILITY_META = {
    "category": "governance.self_improvement",
    "lifecycle": "active",
    "risk": "local_write",
    "triggers": [
        "propose a change to my own rules",
        "refine the harness with evidence",
        "queue a proposed change for CC",
        "roll back a harness refinement",
        "show the refinement ledger",
    ],
    "owner": "bravo",
    "project": "empire",
    "bridge": {
        "visible": True,
        "confirm": True,
        "subcommands": {
            "list": {"key": "refine_list", "visible": True, "confirm": False},
            "show": {"key": "refine_show", "visible": True, "confirm": False},
            "ledger": {"key": "refine_ledger", "visible": True, "confirm": False},
            # propose/apply/revert/cancel run an operator-supplied shell command
            # as the evidence gate. That must never be reachable from the chat
            # bridge: inbound Telegram content is untrusted data, and a visible
            # subcommand taking a free-text command is a remote-execution path.
            # See CLAUDE.md § Untrusted Content Discipline.
            "propose": {"key": "refine_propose", "visible": False, "confirm": True},
            "apply": {"key": "refine_apply", "visible": False, "confirm": True},
            "revert": {"key": "refine_revert", "visible": False, "confirm": True},
            "cancel": {"key": "refine_cancel", "visible": False, "confirm": True},
        },
    },
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "state"
DB_PATH = STATE_DIR / "empire_state.db"
MIRROR = PROJECT_ROOT / "memory" / "PROPOSED_CHANGES.md"

KINDS = ("prompt_note", "memory", "skill", "subagent")
STATUSES = ("PENDING", "HELD", "APPLIED", "REJECTED", "REVERTED", "WITHDRAWN")

# --- The auto-apply allowlist. Fail-closed: anything not matched here is HELD.
# Deliberately an allowlist and not a denylist — see module docstring.
#
# Expressed as (parent_parts, filename_glob) rather than a path glob, because
# fnmatch's `*` matches `/`: `fnmatch("memory/../CLAUDE.md", "memory/*.md")` is
# True, and so is `memory/a/b/deep.md`. A path-glob allowlist is therefore not a
# boundary at all — verified live 2026-08-08, `memory/../CLAUDE.md` classified as
# auto-appliable. Segment-exact matching plus resolving the path before
# classification is what actually closes it. Same lesson as
# pattern_security_boundary_needs_a_parser_not_a_regex: a security boundary needs
# a parser, not a pattern.
AUTO_APPLY_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("memory",), "*.md"),          # memory/<name>.md, no deeper
    (("skills", "*"), "SKILL.md"),  # skills/<one-segment>/SKILL.md
)

# Carve-outs INSIDE the allowlist, matched case-insensitively so a differently
# cased spelling cannot slip past a deny rule. SESSION_LOG is machine-generated
# between AUTO-GENERATED markers and state_guard blocks hand-edits;
# PROPOSED_CHANGES is this tool's own mirror and editing it through the tool
# would be circular.
NEVER_AUTO = (
    "memory/session_log.md",
    "memory/proposed_changes.md",
    "skills/_archive/*",
)

# Gate defaults adopted verbatim from prime-agent's autonomous-gate config.
GATE_TIMEOUT_S = 300
GATE_OUTPUT_CAP = 6000
# Hard read cap. Distinct from GATE_OUTPUT_CAP (what we *store*): this is what we
# are willing to pull into memory at all, and the child is killed past it.
GATE_READ_CAP = 256 * 1024

_IS_WIN = sys.platform.startswith("win")


# --------------------------------------------------------------------------
# storage
# --------------------------------------------------------------------------
def _connect() -> sqlite3.Connection | None:
    try:
        # Create state/ on demand: this file is deployed verbatim into sibling
        # agents (Maven, Atlas) and Atlas had no state/ directory at all.
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), timeout=5.0, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS refinements (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               session_id TEXT,
               kind TEXT NOT NULL,
               target_file TEXT NOT NULL,
               anchor TEXT NOT NULL,
               proposed TEXT NOT NULL,
               reason TEXT,
               evidence_cmd TEXT NOT NULL,
               evidence_key TEXT,
               evidence_before TEXT,
               evidence_after TEXT,
               status TEXT NOT NULL DEFAULT 'PENDING',
               requires_operator INTEGER NOT NULL DEFAULT 1,
               enabled INTEGER NOT NULL DEFAULT 1,
               sha_before TEXT,
               sha_after TEXT,
               detail TEXT,
               created_at TEXT DEFAULT (datetime('now')),
               applied_at TEXT
           )"""
    )


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _read(path: Path) -> str:
    """Read WITHOUT newline translation, so bytes round-trip through a revert.

    `Path.read_text()`/`write_text()` default to newline=None: reading collapses
    CRLF to LF and writing expands LF back to os.linesep. On Windows that means
    reverting an LF-stored file silently rewrites EVERY line ending to CRLF — the
    text is restored, the bytes are not. Found 2026-08-08 by porting to Maven,
    whose memory/PATTERNS.md is LF; Bravo's is already CRLF so it round-tripped
    by luck and the byte-hash checks passed. `git diff` showed nothing because git
    normalizes, so the corruption was invisible on both sides.
    See pattern_eol_normalize_checksum_gates.
    """
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        return fh.read()


def _write(path: Path, text: str) -> None:
    """Write verbatim — no newline translation. Pairs with `_read`."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _session_id() -> str:
    return os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("EMPIRE_SESSION_ID") or "local"


# --------------------------------------------------------------------------
# evidence
# --------------------------------------------------------------------------
def _run(argv: list[str], timeout: int = GATE_TIMEOUT_S) -> tuple[int, str, bool]:
    """Run a command with a HARD byte cap on captured output.

    Returns (exit_code, output, truncated). Streams and kills the child once the
    cap is passed rather than buffering everything: an evidence command is
    operator-supplied, and `capture_output=True` would let a noisy one allocate
    unbounded memory twice per propose and again per apply — a self-inflicted DoS
    through the gate (Codex adversarial audit, 2026-08-08).
    """
    kwargs: dict = {}
    if _IS_WIN:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **kwargs,
        )
    except (OSError, ValueError) as e:
        return 127, f"<could not execute: {e}>", False

    chunks: list[bytes] = []
    size = 0
    truncated = False
    try:
        assert proc.stdout is not None
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            room = GATE_READ_CAP - size
            if room <= 0:
                truncated = True
                break
            chunks.append(chunk[:room])
            size += min(len(chunk), room)
            if len(chunk) > room:
                truncated = True
                break
        if truncated:
            proc.kill()
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return 124, f"<timeout after {timeout}s>", truncated
    except OSError as e:
        proc.kill()
        proc.wait()
        return 127, f"<read failed: {e}>", truncated
    finally:
        if proc.stdout is not None:
            proc.stdout.close()

    out = b"".join(chunks).decode("utf-8", errors="replace")
    return code, out, truncated


def _dig(obj, dotted: str):
    """Walk a dotted path through nested dicts/lists. Returns None if absent."""
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                return None
            cur = cur[part]
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def run_evidence(cmd: str, key: str | None) -> dict:
    """Execute an evidence command and reduce it to a comparable value.

    Returns {"exit", "output" (capped), "value", "digest"}. `value` is what the
    gate actually compares: a JSON sub-key when --evidence-key is given, else
    the whole output. Reducing to a key is what makes commands with volatile
    envelopes (timestamps, run ids) usable as evidence at all.
    """
    try:
        argv = shlex.split(cmd, posix=True)
    except ValueError as e:
        return {"exit": 2, "output": f"<unparseable command: {e}>", "value": None, "digest": None}
    if not argv:
        return {"exit": 2, "output": "<empty command>", "value": None, "digest": None}

    code, out, truncated = _run(argv)
    if key:
        try:
            picked = _dig(json.loads(out), key)
        except (json.JSONDecodeError, ValueError):
            picked = None
        value = "<key-missing>" if picked is None else json.dumps(picked, sort_keys=True)
    else:
        # Bound what the digest hashes, not just what we store. An unkeyed
        # command on a large output would otherwise hash megabytes per run.
        value = out[:GATE_OUTPUT_CAP]
    return {
        "exit": code,
        "output": out[:GATE_OUTPUT_CAP],
        "value": value,
        "truncated": truncated,
        "digest": _sha(f"{code}\x00{value}"),
    }


# NOTE — prime-agent detects a no-op with a git working-tree fingerprint
# (`git status --porcelain` + `git diff --binary HEAD`). That does NOT port here:
# `.gitignore:44` untracks `memory/PATTERNS.md`, and memory/ holds most of the
# auto-apply allowlist, so a git-based snapshot is blind to exactly the files
# this tool is allowed to edit. Verified 2026-08-07: an edit to PATTERNS.md left
# the tree fingerprint byte-identical. We compare content hashes of the target
# file instead — exact, cheap, and indifferent to whether git tracks it.
#
# It also means git is NOT a rollback path for memory refinements: the inverse
# stored in the ledger is the only way back. That is why the prior text is
# persisted at apply time rather than synthesized at rollback time.


# --------------------------------------------------------------------------
# policy
# --------------------------------------------------------------------------
def _resolve(rel_path: str) -> Path | None:
    """Resolve inside the repo. Refuses traversal outside PROJECT_ROOT.

    `.resolve()` also collapses `..` and follows symlinks, which is why
    classification must run on the OUTPUT of this, never on the caller's string.
    """
    try:
        p = (PROJECT_ROOT / rel_path).resolve()
    except (OSError, ValueError):
        return None
    try:
        p.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return None
    return p


def canonical_rel(rel_path: str) -> str | None:
    """The repo-relative POSIX path after resolving `..` and symlinks."""
    p = _resolve(rel_path)
    if p is None:
        return None
    return p.relative_to(PROJECT_ROOT.resolve()).as_posix()


def _segments_match(parts: tuple[str, ...], pattern: tuple[str, ...]) -> bool:
    """Segment-exact comparison; a pattern segment of '*' matches one segment."""
    if len(parts) != len(pattern):
        return False
    return all(pat == "*" or pat == part for part, pat in zip(parts, pattern))


def classify_target(rel_path: str) -> tuple[bool, str]:
    """Return (requires_operator, reason). Fail-closed: unmatched => operator.

    Classifies the RESOLVED path, so `memory/../CLAUDE.md` is judged as
    `CLAUDE.md` and a symlink is judged as its target. Allow rules match
    case-sensitively (so `MEMORY/x.md` falls through to held) and deny rules
    case-insensitively (so `memory/Session_Log.md` is still denied) — both
    directions err toward holding.
    """
    rel = canonical_rel(rel_path)
    if rel is None:
        return True, f"'{rel_path}' does not resolve inside the repo — refused"

    lowered = rel.lower()
    for pat in NEVER_AUTO:
        if fnmatch.fnmatch(lowered, pat):
            return True, f"'{rel}' is carved out of the allowlist ({pat}) — operator only"

    parts = tuple(rel.split("/"))
    for parent, name_glob in AUTO_APPLY_RULES:
        if (
            len(parts) == len(parent) + 1
            and _segments_match(parts[:-1], parent)
            and fnmatch.fnmatchcase(parts[-1], name_glob)
        ):
            shown = "/".join((*parent, name_glob))
            return False, f"'{rel}' matches auto-apply allowlist ({shown})"

    shown = [f"{'/'.join(p)}/{n}" for p, n in AUTO_APPLY_RULES]
    return True, (
        f"'{rel}' matches no auto-apply rule {shown} — held for CC "
        "(allowlist is fail-closed by design)"
    )


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def propose(
    kind: str,
    rel_path: str,
    current: str,
    proposed: str,
    evidence_cmd: str,
    evidence_key: str | None,
    reason: str | None,
) -> dict:
    if kind not in KINDS:
        return {"ok": False, "error": f"kind must be one of {KINDS}"}
    if current == proposed:
        return {"ok": False, "error": "--current and --proposed are identical; nothing to refine"}

    target = _resolve(rel_path)
    if target is None:
        return {"ok": False, "error": f"{rel_path} resolves outside the repo"}
    if not target.exists():
        return {"ok": False, "error": f"{rel_path} does not exist"}

    body = _read(target)
    hits = body.count(current)
    if hits == 0:
        return {"ok": False, "error": "--current text not found in the target file (must match exactly)"}
    if hits > 1:
        return {"ok": False, "error": f"--current matches {hits} times; make it unique so the edit is unambiguous"}

    # Volatility pre-check: run the evidence command TWICE. If two back-to-back
    # runs already disagree, the command cannot prove anything — every future
    # refinement would "show a delta" and the gate would pass everything. This
    # is what catches harness_eval's per-run `timestamp`/`run_id` envelope.
    first = run_evidence(evidence_cmd, evidence_key)
    if first["digest"] is None:
        return {"ok": False, "error": f"evidence command could not run: {first['output'][:300]}"}
    second = run_evidence(evidence_cmd, evidence_key)
    if first["digest"] != second["digest"]:
        return {
            "ok": False,
            "error": (
                "evidence command is volatile — two back-to-back runs differ, so it "
                "can never prove a refinement did anything. Narrow it with "
                "--evidence-key (e.g. --evidence-key score) and retry."
            ),
        }

    requires_operator, why = classify_target(rel_path)
    conn = _connect()
    if conn is None:
        return {"ok": False, "error": "db unavailable"}
    try:
        _ensure_table(conn)
        cur = conn.execute(
            """INSERT INTO refinements
               (session_id, kind, target_file, anchor, proposed, reason, evidence_cmd,
                evidence_key, evidence_before, status, requires_operator, sha_before, detail)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                _session_id(), kind, rel_path, current, proposed, reason, evidence_cmd,
                evidence_key, json.dumps(first), "HELD" if requires_operator else "PENDING",
                1 if requires_operator else 0, _sha(body), why,
            ),
        )
        rid = cur.lastrowid
    except sqlite3.Error as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()

    render_mirror()
    return {
        "ok": True,
        "id": rid,
        "status": "HELD" if requires_operator else "PENDING",
        "requires_operator": requires_operator,
        "policy": why,
        "evidence_before": first["value"][:200] if first["value"] else None,
    }


def _get(rid: int) -> sqlite3.Row | None:
    conn = _connect()
    if conn is None:
        return None
    try:
        _ensure_table(conn)
        return conn.execute("SELECT * FROM refinements WHERE id = ?", (rid,)).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _update(rid: int, **fields) -> None:
    if not fields:
        return
    conn = _connect()
    if conn is None:
        return
    try:
        _ensure_table(conn)
        sets = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE refinements SET {sets} WHERE id = ?", (*fields.values(), rid))
    except sqlite3.Error:
        pass
    finally:
        conn.close()


def gate_verdict(before: dict, after: dict, key: str | None) -> str | None:
    """THE GATE. Returns a rejection reason, or None to accept.

    Pure and side-effect free so it can be tested directly — extracted from
    `apply_refinement` on 2026-08-08 because the single most important decision
    in this tool was only reachable through a live file edit, and the "proof" I
    first wrote reimplemented the rules instead of exercising them. A gate
    verified by a copy of itself is not verified.

    Two questions, in order: did a measurement actually happen, and did the
    measured VALUE move?

    Compares `value`, never `digest`. The digest folds in the exit code, so an
    edit that only flipped the exit code would read as a delta while the measured
    number sat still (Codex adversarial audit, 2026-08-08).

    Exit codes are judged by whether the command carries a result channel:
      * keyed   — the exit code is a RESULT, not a failure. `harness_eval --json`
        exits 1 whenever the harness is imperfect; it is 9/10 today. Demanding
        exit 0 would reject the very evidence command the skill documents. The
        key being present is the proof a measurement happened.
      * unkeyed — the output IS the value, so a crash changes it and mimics a
        delta. Here exit 0 after the edit is required.
    124 (timeout) and 127 (could not execute) mean no measurement happened.
    """
    measured_before = before.get("value")
    measured_after = after.get("value")

    if after.get("exit") in (124, 127):
        return f"evidence command could not produce a measurement (exit {after.get('exit')})"
    if measured_after == "<key-missing>":
        return f"evidence key '{key}' vanished after the edit — nothing to compare"
    if not key and after.get("exit") != 0:
        return (
            f"unkeyed evidence command failed after the edit (exit {after.get('exit')}) — "
            "it changed because it broke, which is not an improvement"
        )
    if measured_after == measured_before:
        return f"no measured effect — evidence unchanged ({str(measured_after)[:120]})"
    return None


def apply_refinement(rid: int, approve: bool = False) -> dict:
    row = _get(rid)
    if row is None:
        return {"ok": False, "error": f"refinement {rid} not found"}
    if row["status"] not in ("PENDING", "HELD"):
        return {"ok": False, "error": f"refinement {rid} is {row['status']}, not applicable"}
    if not row["enabled"]:
        return {"ok": False, "error": f"refinement {rid} is disabled"}
    if row["requires_operator"] and not approve:
        return {
            "ok": False,
            "held": True,
            "error": f"refinement {rid} requires CC's approval: {row['detail']}. Re-run with --approve.",
        }

    target = _resolve(row["target_file"])
    if target is None or not target.exists():
        return {"ok": False, "error": f"{row['target_file']} missing"}

    before_body = _read(target)
    hits = before_body.count(row["anchor"])
    if hits != 1:
        return {
            "ok": False,
            "error": f"anchor matches {hits} times now (file drifted since propose) — re-propose against current text",
        }

    after_body = before_body.replace(row["anchor"], row["proposed"], 1)

    # No-op detector, on content rather than on git (see note above).
    if _sha(after_body) == _sha(before_body):
        _update(rid, status="REJECTED", detail="no-op edit — file content unchanged by the replacement")
        render_mirror()
        return {"ok": False, "id": rid, "status": "REJECTED", "reason": "no-op edit (content unchanged)"}

    _write(target, after_body)

    after = run_evidence(row["evidence_cmd"], row["evidence_key"])
    try:
        before = json.loads(row["evidence_before"] or "{}")
    except (json.JSONDecodeError, ValueError):
        before = {}

    reject = gate_verdict(before, after, row["evidence_key"])
    if reject:
        _write(target, before_body)
        _update(
            rid,
            status="REJECTED",
            evidence_after=json.dumps(after),
            detail=f"{reject}; auto-reverted",
        )
        render_mirror()
        return {
            "ok": False,
            "id": rid,
            "status": "REJECTED",
            "reason": reject,
            "evidence_value": str(after["value"])[:200],
            "evidence_exit": after["exit"],
            "reverted_clean": _read(target) == before_body,
        }

    _update(
        rid,
        status="APPLIED",
        evidence_after=json.dumps(after),
        sha_after=_sha(after_body),
        applied_at=datetime.now(timezone.utc).isoformat(),
        detail=f"applied — evidence moved {str(before.get('value'))[:60]} -> {str(after['value'])[:60]}",
    )
    render_mirror()
    return {
        "ok": True,
        "id": rid,
        "status": "APPLIED",
        "evidence_before": str(before.get("value"))[:200],
        "evidence_after": str(after["value"])[:200],
    }


def revert(rid: int) -> dict:
    row = _get(rid)
    if row is None:
        return {"ok": False, "error": f"refinement {rid} not found"}
    if row["status"] != "APPLIED":
        return {"ok": False, "error": f"refinement {rid} is {row['status']}; only APPLIED can be reverted"}

    target = _resolve(row["target_file"])
    if target is None or not target.exists():
        return {"ok": False, "error": f"{row['target_file']} missing"}

    body = _read(target)
    if row["sha_after"] and _sha(body) != row["sha_after"]:
        return {
            "ok": False,
            "error": (
                f"{row['target_file']} changed since this refinement was applied — refusing to "
                "auto-revert over someone else's edit. Revert by hand or re-propose."
            ),
        }
    if body.count(row["proposed"]) != 1:
        return {"ok": False, "error": "proposed text is not uniquely present; cannot revert deterministically"}

    restored = body.replace(row["proposed"], row["anchor"], 1)
    _write(target, restored)
    ok = _sha(restored) == (row["sha_before"] or _sha(restored))
    _update(rid, status="REVERTED", detail=f"reverted (byte-exact restore: {ok})")
    render_mirror()
    return {"ok": True, "id": rid, "status": "REVERTED", "byte_exact": ok}


def cancel(rid: int, reason: str | None) -> dict:
    """Withdraw a queued proposal. Distinct from REJECTED, which means the gate
    measured no effect — conflating the two would lose why it didn't ship."""
    row = _get(rid)
    if row is None:
        return {"ok": False, "error": f"refinement {rid} not found"}
    if row["status"] not in ("PENDING", "HELD"):
        return {"ok": False, "error": f"refinement {rid} is {row['status']}; only queued proposals can be withdrawn"}
    _update(rid, status="WITHDRAWN", detail=f"withdrawn: {reason or 'no reason given'}")
    render_mirror()
    return {"ok": True, "id": rid, "status": "WITHDRAWN"}


def listing(status: str | None, limit: int = 50) -> list[dict]:
    conn = _connect()
    if conn is None:
        return []
    try:
        _ensure_table(conn)
        if status:
            rows = conn.execute(
                "SELECT * FROM refinements WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status.upper(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM refinements ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


# --------------------------------------------------------------------------
# human-readable mirror — PROPOSED_CHANGES.md finally gets its writer
# --------------------------------------------------------------------------
def _section_bounds(lines: list[str], heading: str) -> tuple[int, int] | None:
    """Body span under `heading`, ending at the next '## ' or horizontal rule."""
    start = None
    for i, ln in enumerate(lines):
        if ln.strip() == heading:
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start, len(lines)):
        s = lines[j].strip()
        if s.startswith("## ") or s == "---":
            end = j
            break
    return start, end


def _ev_value(blob: str | None, cap: int = 80) -> str | None:
    """Pull the comparable value out of a stored evidence blob, flattened to one
    line so it renders inside a markdown bullet."""
    if not blob:
        return None
    try:
        val = json.loads(blob).get("value")
    except (json.JSONDecodeError, ValueError, AttributeError):
        return None
    if val is None:
        return None
    return " ".join(str(val).split())[:cap] or "(empty)"


def _oneline(text: str | None, cap: int = 300) -> str | None:
    """Collapse whitespace so a value can't break out of a markdown bullet."""
    if not text:
        return None
    return " ".join(str(text).split())[:cap] or None


def _render_rows(rows: list[dict]) -> list[str]:
    if not rows:
        return ["", "*None.*", ""]
    out: list[str] = [""]
    for r in rows:
        out.append(f"### #{r['id']} — `{r['target_file']}` · {r['kind']} · **{r['status']}**")
        out.append("")
        out.append(f"- **File:** `{r['target_file']}`")
        out.append(f"- **Reason:** {_oneline(r.get('reason')) or '—'}")
        out.append(f"- **Evidence:** `{_oneline(r['evidence_cmd'])}`" + (f" (key: `{r['evidence_key']}`)" if r.get("evidence_key") else ""))
        ev_b = _ev_value(r.get("evidence_before"))
        ev_a = _ev_value(r.get("evidence_after"))
        out.append(f"- **Measured:** before `{ev_b or '—'}` → after `{ev_a or '(not measured)'}`")
        # Three distinct cases, and conflating them misreports history: APPLIED is
        # the only state with something to undo, REVERTED was applied and already
        # undone, and everything else never touched the file.
        if r["status"] == "APPLIED":
            out.append(f"- **Rollback:** `python scripts/core/refine.py revert {r['id']}`")
        elif r["status"] == "REVERTED":
            out.append("- **Rollback:** already reverted — the file is back to its prior text")
        else:
            out.append("- **Rollback:** n/a — never applied (nothing to undo)")
        # detail can carry a multi-line evidence value; a raw newline here breaks
        # out of the bullet list and mangles every following entry.
        out.append(f"- **Status:** {r['status']} — {_oneline(r.get('detail')) or ''}")
        out.append(f"- **Created:** {r.get('created_at')} (session `{r.get('session_id')}`)")
        out.append("")
    return out


def render_mirror() -> bool:
    """Rewrite the two managed sections of PROPOSED_CHANGES.md from the DB."""
    if not MIRROR.exists():
        return False
    rows = listing(None, limit=200)
    active = [r for r in rows if r["status"] in ("PENDING", "HELD")]
    history = [r for r in rows if r["status"] in ("APPLIED", "REJECTED", "REVERTED", "WITHDRAWN")]

    lines = _read(MIRROR).split("\n")
    for heading, body in (
        ("## Applied History", _render_rows(history)),   # bottom-up so indices stay valid
        ("## Active Proposals", _render_rows(active)),
    ):
        span = _section_bounds(lines, heading)
        if span is None:
            continue
        lines[span[0]:span[1]] = body
    _write(MIRROR, "\n".join(lines))
    return True


# --------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Evidence-gated harness refinement")
    sub = ap.add_subparsers(dest="cmd")

    pp = sub.add_parser("propose", help="queue a refinement, measured against a command")
    pp.add_argument("--kind", required=True, choices=KINDS)
    pp.add_argument("--file", required=True, help="repo-relative path")
    pp.add_argument("--current", required=True, help="exact existing text (must be unique in the file)")
    pp.add_argument("--proposed", required=True)
    pp.add_argument("--evidence-cmd", required=True, help="command whose output must CHANGE for this to stick")
    pp.add_argument("--evidence-key", default=None, help="dotted JSON path to compare (e.g. score)")
    pp.add_argument("--reason", default=None)
    pp.add_argument("--json", action="store_true")

    pl = sub.add_parser("list", help="queued and historical refinements")
    pl.add_argument("--status", default=None, choices=[s.lower() for s in STATUSES] + list(STATUSES))
    pl.add_argument("--limit", type=int, default=50)
    pl.add_argument("--json", action="store_true")

    ps = sub.add_parser("show", help="one refinement in full")
    ps.add_argument("id", type=int)
    ps.add_argument("--json", action="store_true")

    pa = sub.add_parser("apply", help="apply, then prove it changed something")
    pa.add_argument("id", type=int)
    pa.add_argument("--approve", action="store_true", help="CC's approval for an operator-gated target")
    pa.add_argument("--json", action="store_true")

    pr = sub.add_parser("revert", help="restore the stored prior text")
    pr.add_argument("id", type=int)
    pr.add_argument("--json", action="store_true")

    pc = sub.add_parser("cancel", help="withdraw a queued proposal")
    pc.add_argument("id", type=int)
    pc.add_argument("--reason", default=None)
    pc.add_argument("--json", action="store_true")

    pg = sub.add_parser("ledger", help="full history, newest first")
    pg.add_argument("--limit", type=int, default=50)
    pg.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 2

    if args.cmd == "propose":
        out = propose(args.kind, args.file, args.current, args.proposed,
                      args.evidence_cmd, args.evidence_key, args.reason)
    elif args.cmd == "apply":
        out = apply_refinement(args.id, args.approve)
    elif args.cmd == "revert":
        out = revert(args.id)
    elif args.cmd == "cancel":
        out = cancel(args.id, args.reason)
    elif args.cmd == "show":
        row = _get(args.id)
        out = dict(row) if row else {"ok": False, "error": f"refinement {args.id} not found"}
    else:  # list | ledger
        rows = listing(getattr(args, "status", None), args.limit)
        if args.json:
            print(json.dumps(rows, indent=2))
            return 0
        if not rows:
            print("No refinements recorded.")
            return 0
        for r in rows:
            flag = "OPERATOR" if r["requires_operator"] else "auto"
            print(f"#{r['id']:<4} {r['status']:<9} {flag:<8} {r['kind']:<11} {r['target_file']}")
            print(f"       evidence: {r['evidence_cmd']}" + (f"  [{r['evidence_key']}]" if r["evidence_key"] else ""))
            if r.get("detail"):
                print(f"       {r['detail']}")
        return 0

    if getattr(args, "json", False):
        print(json.dumps(out, indent=2, default=str))
    else:
        for k, v in out.items():
            print(f"{k}: {v}")
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
