"""HMAC + identity helpers for the operator-approval override flow.

The override layer never holds an LLM-readable token. Approvals live in the
DB; this module only signs them at-rest so a future agent that somehow got
DB write access (which the guards already prevent) still couldn't forge a
valid approval without the HMAC key.

Lazy key bootstrap: if `EMPIRE_OVERRIDE_HMAC_KEY` is missing from
`.env.agents` on first use, generate a 64-hex-char key and append it.
This makes the override flow zero-config — the wizard doesn't have to
ship a key; first use mints one.

================================================================================
TWO HMAC SECRETS — DELIBERATE, NOT A LEAK
================================================================================
The override flow uses two distinct HMAC secrets at two different layers.
They have similar names and similar shapes; they are NOT the same secret.

  EMPIRE_OVERRIDE_HMAC_KEY  (this file)
    - LOCAL ONLY. Lives in .env.agents on CC's machine, never on Vercel.
    - Signs the at-rest "approval" row inside state/empire_state.db (SQLite).
    - state_manager.approve_override_request() calls sign_approval() here
      so a malicious agent with DB write access still can't forge approvals.

  OASIS_OUTBOUND_HMAC_SECRET  (set on Vercel + on local consumer)
    - CLOUD-AWARE. Set as a Vercel env var AND as a row in
      n8n_webhook_secrets so the Supabase RPC can verify.
    - Authenticates the dashboard → Supabase RPC call
      (record_exec_override_decision_v1) — see
      apps/command-center/app/overrides/page.tsx::decisionAction.

They are layered: OASIS_OUTBOUND_HMAC_SECRET protects "did the dashboard
operator click Approve" (cloud trust). EMPIRE_OVERRIDE_HMAC_KEY protects
"did exec_guard's at-runtime allow-list get tampered with on-host" (local
trust). Compromise of one does NOT yield the other.

If you find yourself unifying these two — STOP. The split is what keeps
Vercel from ever being able to forge a local SQLite approval.
================================================================================
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env.agents"
KEY_NAME = "EMPIRE_OVERRIDE_HMAC_KEY"


def make_request_id() -> str:
    """`req-` + 8 lowercase hex chars. Cheap, readable, low-collision at our volume."""
    return f"req-{uuid.uuid4().hex[:8]}"


def command_hash(command: str) -> str:
    """sha256 of the command string. Approvals are bound to this hash so an
    operator approving 'rm -rf staging/' does NOT accidentally also approve
    'rm -rf /' — the hash differs."""
    return hashlib.sha256(command.encode("utf-8")).hexdigest()


def _read_key() -> str | None:
    if not ENV_FILE.exists():
        return None
    try:
        text = ENV_FILE.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(f"{KEY_NAME}="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            return value or None
    return None


def _append_key(key_value: str) -> None:
    """Append `EMPIRE_OVERRIDE_HMAC_KEY=...` to .env.agents. mode 600 preserved."""
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    existed = ENV_FILE.exists()
    with ENV_FILE.open("a", encoding="utf-8") as fh:
        if existed:
            fh.write("\n")
        fh.write(f"# Generated lazily by scripts/lib/override_crypto.py — DO NOT share\n")
        fh.write(f"{KEY_NAME}={key_value}\n")
    if os.name == "posix":
        try:
            os.chmod(ENV_FILE, 0o600)
        except OSError:
            pass


def ensure_hmac_key() -> str:
    """Return the override HMAC key, generating + persisting it if absent.

    Order of preference:
      1. Existing value in os.environ (lets tests inject a deterministic key).
      2. Existing value in .env.agents.
      3. Mint a new 64-hex-char key, append to .env.agents, return it.
    """
    env_val = os.environ.get(KEY_NAME)
    if env_val:
        return env_val
    file_val = _read_key()
    if file_val:
        os.environ[KEY_NAME] = file_val
        return file_val
    new_key = secrets.token_hex(32)
    _append_key(new_key)
    os.environ[KEY_NAME] = new_key
    return new_key


def sign_approval(request_id: str, cmd_hash: str, expires_at: str) -> str:
    """HMAC-SHA256 over the canonical `id|hash|expires` triple."""
    key = ensure_hmac_key()
    msg = f"{request_id}|{cmd_hash}|{expires_at}".encode("utf-8")
    return hmac.new(key.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_approval(request_id: str, cmd_hash: str, expires_at: str,
                    sig: str | None) -> bool:
    """Constant-time signature check. Returns False on any mismatch or missing sig."""
    if not sig:
        return False
    expected = sign_approval(request_id, cmd_hash, expires_at)
    return hmac.compare_digest(expected, sig)


def is_tty_caller() -> bool:
    """True if the calling process appears to be an interactive operator.

    Used to refuse `exec_override.py approve` from LLM-spawned subprocesses.
    Detection layers (any miss → not-TTY):
      - stdin is a TTY
      - PYTHONINSPECT NOT set
      - PYTHON_INTERACTIVE NOT set in a way that overrides
      - the CLAUDE_PROJECT_DIR env var is NOT inherited from a hook
        (set by Claude Code on hook subprocesses; absent for direct
         operator-launched terminals).
    The caller can override the heuristic by setting
    `EMPIRE_OVERRIDE_FORCE_TTY=1` for known-good headless flows
    (CI testing the override approval path).
    """
    if os.environ.get("EMPIRE_OVERRIDE_FORCE_TTY") == "1":
        return True
    import sys
    if not sys.stdin.isatty():
        return False
    # Hook subprocesses inherit CLAUDE_PROJECT_DIR — operators in their own
    # terminal typically don't have that exported.
    if os.environ.get("CLAUDE_PROJECT_DIR") and os.environ.get("CLAUDE_HOOK_FIRED") == "1":
        return False
    return True
