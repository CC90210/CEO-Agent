"""V6 BUILD 4 — operator-approval override regression suite.

Multi-step lifecycle tests:
  block -> auto-creates request -> operator approves -> single-use -> consumed

The exec_guard hook is invoked as a subprocess for each step (matches the
production path), and the state-DB transitions are inspected directly via
state_manager helpers.

Each test uses a UNIQUE command string so the request-row state from one
test never leaks into another — `command_hash` keys are per-test.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
# Post-2026-05 reorg: guards + override CLI live under scripts/state/.
EXEC_GUARD = SCRIPTS / "state" / "exec_guard.py"
EXEC_OVERRIDE = SCRIPTS / "state" / "exec_override.py"
SECRET_GUARD = SCRIPTS / "state" / "secret_guard.py"
STATE_GUARD = SCRIPTS / "state" / "state_guard.py"

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "state"))
import state_manager  # type: ignore[import-not-found]  # noqa: E402 — sys.path.insert above


# ── Helpers ──────────────────────────────────────────────────────────────


_TRACKED_CMDS: list[str] = []


def _unique_cmd(base: str) -> str:
    """Tag a command with a unique suffix so each test gets its own DB row.

    Tracks every generated command into _TRACKED_CMDS so the autouse
    fixture can expire the matching exec_overrides rows on teardown —
    keeps the dashboard's pending-count badge from accumulating test
    artifacts (CC found 284 stale pendings on 2026-05-22, almost all
    from this suite's historical runs).
    """
    tag = uuid.uuid4().hex[:8]
    cmd = f"{base}  # test-{tag}"
    _TRACKED_CMDS.append(cmd)
    return cmd


def _bash(cmd: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def _subprocess_env(extras: dict[str, str]) -> dict[str, str]:
    """Build the env dict every subprocess in this suite needs.

    Adds scripts/ + scripts/state/ to PYTHONPATH so the guard / override
    scripts can `from lib.hook_runtime import ...` and `import state_manager`
    when launched as standalone subprocesses (their import discovery is
    sys.path-driven; with no PYTHONPATH they crash on the first import
    and the test mis-reads rc=1 as a logic failure).
    """
    pp_parts = [str(SCRIPTS), str(SCRIPTS / "state")]
    if existing := os.environ.get("PYTHONPATH"):
        pp_parts.append(existing)
    return {
        **os.environ,
        **extras,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": os.pathsep.join(pp_parts),
    }


def _run_guard(guard_path: Path, payload: dict, env_overrides: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(guard_path)],
        input=json.dumps(payload),
        capture_output=True, text=True,
        env=_subprocess_env(env_overrides), timeout=15,
    )


def _approve(req_id: str, reason: str = "test") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(EXEC_OVERRIDE), "approve", req_id, "--reason", reason],
        capture_output=True, text=True,
        env=_subprocess_env({"EMPIRE_OVERRIDE_FORCE_TTY": "1"}), timeout=15,
    )


def _extract_request_id(stderr: str) -> str | None:
    m = re.search(r"req-[0-9a-f]{8}", stderr)
    return m.group(0) if m else None


# ── Test pollution cleanup ──────────────────────────────────────────────
# Every test in this suite spawns exec_guard against a unique command
# string, which creates a real row in exec_overrides (the same table
# the dashboard reads). Without cleanup, the dashboard's "pending count"
# badge accumulates a stale row per test per CI run — CC saw 284 stale
# pendings on 2026-05-22, almost all from this suite's historical runs.
#
# _unique_cmd already appends to _TRACKED_CMDS. This autouse fixture
# walks that list after each test and marks the matching exec_overrides
# rows as 'expired' so the dashboard never sees them as pending input.

import pytest


@pytest.fixture(autouse=True)
def _cleanup_exec_overrides():
    """Mark every row this test created as 'expired' on teardown so the
    dashboard never sees test artifacts as 'pending'."""
    before = len(_TRACKED_CMDS)
    yield
    new_cmds = _TRACKED_CMDS[before:]
    if not new_cmds:
        return
    try:
        # state_manager has a known shape for this. Import here so a
        # missing import doesn't fail the test itself.
        import hashlib
        from datetime import datetime, timezone
        import supabase_tool  # type: ignore  # noqa: E402
        db = supabase_tool.get_client(supabase_tool.load_env())
        now_iso = datetime.now(timezone.utc).isoformat()
        for cmd in new_cmds:
            h = hashlib.sha256(cmd.encode("utf-8")).hexdigest()
            db.table("exec_overrides").update({
                "status": "expired", "updated_at": now_iso,
            }).eq("command_hash", h).eq("status", "pending").execute()
    except Exception:
        # Teardown cleanup is best-effort — never fail a test for it.
        pass


# ── Lifecycle tests ─────────────────────────────────────────────────────


def test_01_block_auto_creates_override_request() -> None:
    cmd = _unique_cmd("git push --force origin main")
    p = _run_guard(EXEC_GUARD, _bash(cmd), {"EMPIRE_HOOK_EXEC_GUARD": "enforce"})
    assert p.returncode == 2, "expected block on hard-blocklist hit"
    req_id = _extract_request_id(p.stderr)
    assert req_id is not None, "block stderr must surface a request_id"
    assert "Override request:" in p.stderr
    assert f"approve {req_id}" in p.stderr
    # Verify the row exists, status pending, hash matches
    appr = state_manager.find_fresh_approval(cmd)
    assert appr is None, "no approval yet — find_fresh_approval must return None"


def test_02_approve_then_retry_allows_and_consumes() -> None:
    cmd = _unique_cmd("git push --force origin main")
    p = _run_guard(EXEC_GUARD, _bash(cmd), {"EMPIRE_HOOK_EXEC_GUARD": "enforce"})
    req_id = _extract_request_id(p.stderr)
    assert req_id

    a = _approve(req_id)
    assert a.returncode == 0, f"approve failed: {a.stderr}"

    # Retry — should be allowed
    p = _run_guard(EXEC_GUARD, _bash(cmd), {"EMPIRE_HOOK_EXEC_GUARD": "enforce"})
    assert p.returncode == 0, "retry after approval must allow"
    assert "allowed via approved override" in p.stderr
    assert req_id in p.stderr


def test_03_single_use_enforced_second_run_blocks_again() -> None:
    cmd = _unique_cmd("git push --force origin main")
    p = _run_guard(EXEC_GUARD, _bash(cmd), {"EMPIRE_HOOK_EXEC_GUARD": "enforce"})
    req_id = _extract_request_id(p.stderr)
    _approve(req_id)
    # First retry — allowed
    _run_guard(EXEC_GUARD, _bash(cmd), {"EMPIRE_HOOK_EXEC_GUARD": "enforce"})
    # Second retry — single-use means a NEW request, NOT another free pass
    p = _run_guard(EXEC_GUARD, _bash(cmd), {"EMPIRE_HOOK_EXEC_GUARD": "enforce"})
    assert p.returncode == 2, "single-use violated — second retry must block again"
    new_req = _extract_request_id(p.stderr)
    assert new_req is not None
    assert new_req != req_id, "expected a fresh request_id on the second block"


def test_04_hash_binding_approval_does_not_cross_commands() -> None:
    cmd_a = _unique_cmd("git push --force origin main")
    cmd_b = _unique_cmd("git push --force origin main")  # different unique tag → different hash
    pa = _run_guard(EXEC_GUARD, _bash(cmd_a), {"EMPIRE_HOOK_EXEC_GUARD": "enforce"})
    req_a = _extract_request_id(pa.stderr)
    _approve(req_a)
    # cmd_b has a different sha256 — the approval must NOT cover it
    pb = _run_guard(EXEC_GUARD, _bash(cmd_b), {"EMPIRE_HOOK_EXEC_GUARD": "enforce"})
    assert pb.returncode == 2, "hash-binding violated — cmd_b must still block"
    req_b = _extract_request_id(pb.stderr)
    assert req_b and req_b != req_a


def test_05_expired_approval_blocks() -> None:
    """Approve, then time-fast-forward by mutating expires_at, then verify block."""
    cmd = _unique_cmd("git push --force origin main")
    p = _run_guard(EXEC_GUARD, _bash(cmd), {"EMPIRE_HOOK_EXEC_GUARD": "enforce"})
    req_id = _extract_request_id(p.stderr)
    _approve(req_id)
    # Time-travel: mutate expires_at to the past via direct DB access (test-only)
    import sqlite3
    db = sqlite3.connect(str(REPO_ROOT / "state" / "empire_state.db"))
    db.execute("UPDATE override_request SET expires_at='1970-01-01T00:00:00+00:00' WHERE id=?",
               (req_id,))
    db.commit()
    db.close()
    # The approval is now expired. find_fresh_approval should ignore it.
    p = _run_guard(EXEC_GUARD, _bash(cmd), {"EMPIRE_HOOK_EXEC_GUARD": "enforce"})
    assert p.returncode == 2, "expired approval must NOT allow"


def test_06_approve_refuses_from_non_tty() -> None:
    """LLM-spawned subprocesses must not be able to approve their own requests."""
    cmd = _unique_cmd("git push --force origin main")
    p = _run_guard(EXEC_GUARD, _bash(cmd), {"EMPIRE_HOOK_EXEC_GUARD": "enforce",
                                            "EMPIRE_OVERRIDE_FORCE_TTY": "1"})
    req_id = _extract_request_id(p.stderr)
    # Now try to approve WITHOUT FORCE_TTY, with hook-context env vars set
    env = {**os.environ,
           "PYTHONIOENCODING": "utf-8",
           "CLAUDE_PROJECT_DIR": str(REPO_ROOT),
           "CLAUDE_HOOK_FIRED": "1"}
    env.pop("EMPIRE_OVERRIDE_FORCE_TTY", None)
    p = subprocess.run(
        [sys.executable, str(EXEC_OVERRIDE), "approve", req_id],
        input="",  # not-a-tty
        capture_output=True, text=True, env=env, timeout=15,
    )
    assert p.returncode == 2, "non-TTY approve must be refused"
    assert "REFUSED" in p.stderr


def test_07_approval_does_not_apply_to_secret_guard() -> None:
    """Even if an override exists for a `cat .env.agents` command, secret_guard
    still blocks. The override layer is exec_guard-only by design — credentials
    are never LLM-readable, period."""
    cmd = _unique_cmd("cat .env.agents")
    # Manually create an "approval" in the state DB for this command, as if
    # someone tried to game the system. secret_guard does NOT consult override.
    state_manager.create_override_request(cmd, layer="manual-test-poke")
    # Pull the row, mutate to approved+signed
    rows = state_manager.list_override_requests(limit=200, since_hours=1)
    target = next(r for r in rows if r["command"] == cmd[:2000])
    state_manager.approve_override_request(target["id"], approved_by="test")
    # Now try secret_guard — must still block, override layer is irrelevant
    p = _run_guard(SECRET_GUARD, _bash(cmd), {"EMPIRE_HOOK_SECRET_GUARD": "enforce"})
    assert p.returncode == 2, "secret_guard must NOT honor override approvals"


def test_08_approval_does_not_apply_to_state_guard() -> None:
    """Same isolation for state_guard — DB-mirror writes stay protected even
    if exec_override has an approved row matching the command."""
    cmd = _unique_cmd("echo poison > memory/SESSION_LOG.md")
    state_manager.create_override_request(cmd, layer="manual-test-poke")
    rows = state_manager.list_override_requests(limit=200, since_hours=1)
    target = next(r for r in rows if r["command"] == cmd[:2000])
    state_manager.approve_override_request(target["id"], approved_by="test")
    p = _run_guard(STATE_GUARD, _bash(cmd), {"EMPIRE_HOOK_STATE_GUARD": "enforce"})
    assert p.returncode == 2, "state_guard must NOT honor override approvals"


def test_09_hmac_tamper_invalidates_approval() -> None:
    """If something flipped the hmac_sig column, find_fresh_approval must
    refuse to honor the row."""
    cmd = _unique_cmd("git push --force origin main")
    p = _run_guard(EXEC_GUARD, _bash(cmd), {"EMPIRE_HOOK_EXEC_GUARD": "enforce"})
    req_id = _extract_request_id(p.stderr)
    _approve(req_id)
    # Tamper: corrupt the HMAC sig
    import sqlite3
    db = sqlite3.connect(str(REPO_ROOT / "state" / "empire_state.db"))
    db.execute("UPDATE override_request SET hmac_sig='deadbeef' WHERE id=?", (req_id,))
    db.commit()
    db.close()
    appr = state_manager.find_fresh_approval(cmd)
    assert appr is None, "tampered HMAC sig must invalidate the approval"
    # Retry exec_guard — must block (no valid approval visible)
    p = _run_guard(EXEC_GUARD, _bash(cmd), {"EMPIRE_HOOK_EXEC_GUARD": "enforce"})
    assert p.returncode == 2


def test_10_idempotent_request_creation_dedupes_per_command() -> None:
    """If a block fires twice for the same command before approval, we should
    NOT spam two pending requests. The second create returns the first row."""
    cmd = _unique_cmd("git push --force origin main")
    p1 = _run_guard(EXEC_GUARD, _bash(cmd), {"EMPIRE_HOOK_EXEC_GUARD": "enforce"})
    p2 = _run_guard(EXEC_GUARD, _bash(cmd), {"EMPIRE_HOOK_EXEC_GUARD": "enforce"})
    req1 = _extract_request_id(p1.stderr)
    req2 = _extract_request_id(p2.stderr)
    assert req1 == req2, "duplicate blocks within TTL must reuse the same request_id"


def test_11_deny_closes_request_and_blocks_subsequent_runs() -> None:
    cmd = _unique_cmd("git push --force origin main")
    p = _run_guard(EXEC_GUARD, _bash(cmd), {"EMPIRE_HOOK_EXEC_GUARD": "enforce"})
    req_id = _extract_request_id(p.stderr)
    # Operator denies (with FORCE_TTY for the test path)
    env = {**os.environ, "EMPIRE_OVERRIDE_FORCE_TTY": "1", "PYTHONIOENCODING": "utf-8"}
    d = subprocess.run([sys.executable, str(EXEC_OVERRIDE), "deny", req_id,
                        "--reason", "test denial"],
                       capture_output=True, text=True, env=env, timeout=15)
    assert d.returncode == 0
    # After denial, retry must still block; the denied request is NOT a free pass
    p = _run_guard(EXEC_GUARD, _bash(cmd), {"EMPIRE_HOOK_EXEC_GUARD": "enforce"})
    assert p.returncode == 2


def test_12_cli_list_shows_recent_requests() -> None:
    """`exec_override.py list` returns the rows we've been creating."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run([sys.executable, str(EXEC_OVERRIDE), "list",
                        "--limit", "20", "--json"],
                       capture_output=True, text=True, env=env, timeout=15)
    assert p.returncode == 0
    rows = json.loads(p.stdout)
    assert isinstance(rows, list)
    # We've created plenty of rows in earlier tests
    assert len(rows) >= 5
    for r in rows:
        assert "id" in r and r["id"].startswith("req-")
        assert "status" in r
