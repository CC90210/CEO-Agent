"""One-shot Codex subscription CLI runner.

Prompts travel through stdin, runs are ephemeral, the child receives only a
small runtime allowlist (never business credentials), and failures return
``None``. This is the canonical operator-trusted second subscription when
Claude is unavailable. Untrusted text transforms must not use this runner:
Codex's read-only sandbox still permits file and shell reads.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from lib.subprocess_helpers import (
    command_without_cmd_shim,
    enriched_path,
    safe_run,
    which_cli,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VALID_SANDBOXES = {"read-only", "workspace-write"}
RUNTIME_ENV_ALLOWLIST = {
    "PATH", "Path", "PATHEXT", "SystemRoot", "SYSTEMROOT", "windir",
    "COMSPEC", "USERPROFILE", "HOME", "HOMEDRIVE", "HOMEPATH",
    "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "PROGRAMFILES",
    "PROGRAMFILES(X86)", "PROGRAMDATA", "USERNAME", "USERDOMAIN",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS", "CODEX_HOME",
    "NODE_USE_SYSTEM_CA", "SSL_CERT_FILE",
}


def _fingerprint(prompt: str) -> str:
    digest = hashlib.sha256(prompt.encode("utf-8", "replace")).hexdigest()[:12]
    return f"sha256:{digest} len={len(prompt)}"


def resolve_codex_bin() -> Optional[str]:
    override = (os.environ.get("BRAVO_CODEX_EXE") or "").strip()
    if override and Path(override).exists():
        return override
    return which_cli("codex")


def _subscription_env(codex_bin: str) -> dict[str, str]:
    """Codex login/OAuth only, with no inherited business credentials.

    A suffix blocklist is insufficient: refresh tokens, Telegram tokens, and
    service-role credentials do not end in ``_API_KEY``. Codex can invoke a
    read command even in its read-only sandbox, so the environment boundary is
    an explicit allowlist. Subscription auth is loaded from CODEX_HOME or the
    user's profile, not from a metered key.
    """
    env = {
        k: v for k, v in os.environ.items()
        if k in RUNTIME_ENV_ALLOWLIST
    }
    env.update({
        "PATH": enriched_path(codex_bin),
        "CI": "true",
        "NONINTERACTIVE": "true",
        "PAGER": "cat",
        "NO_COLOR": "1",
        "FORCE_COLOR": "0",
    })
    return env


def run_codex_cli(
    prompt: str,
    *,
    system: Optional[str] = None,
    timeout: int = 180,
    cwd: Optional[Path] = None,
    sandbox: str = "read-only",
    respect_rules: bool = False,
    operator_trusted: bool = False,
) -> Optional[str]:
    """Run Codex non-interactively and return only its final message.

    ``read-only`` prevents writes but does not remove Codex's shell/file-read
    tools. Callers must therefore establish operator trust before invoking this
    function. Operator-authenticated Telegram work uses ``workspace-write`` and
    the repository rules.
    """
    if not operator_trusted:
        sys.stderr.write(
            "[codex_cli] refused: Codex has read tools and the caller did not "
            "establish operator trust\n"
        )
        return None
    if sandbox not in VALID_SANDBOXES:
        raise ValueError(f"unsupported Codex sandbox: {sandbox}")
    codex_bin = resolve_codex_bin()
    if not codex_bin:
        sys.stderr.write("[codex_cli] Codex CLI is not installed\n")
        return None

    root = Path(cwd or PROJECT_ROOT).resolve()
    full_prompt = prompt
    if system:
        full_prompt = (
            "<system_instructions>\n"
            f"{system}\n"
            "</system_instructions>\n\n"
            "<operator_or_data_payload>\n"
            f"{prompt}\n"
            "</operator_or_data_payload>"
        )

    out_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".txt", delete=False
        ) as handle:
            out_path = handle.name

        args = [
            *command_without_cmd_shim(codex_bin),
            "exec",
            # Ignore ~/.codex/config.toml so a fallback run cannot inherit
            # user-configured MCP servers, hooks, profiles, or other ambient
            # capabilities. Login state remains available through CODEX_HOME.
            "--ignore-user-config",
            "--sandbox", sandbox,
            "--ephemeral",
            "--skip-git-repo-check",
            "--color", "never",
        ]
        if not respect_rules:
            args.append("--ignore-rules")
        args.extend([
            "-C", str(root),
            "--output-last-message", out_path,
            "-",
        ])
        try:
            proc = safe_run(
                args,
                input=full_prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=str(root),
                env=_subscription_env(codex_bin),
            )
        except subprocess.TimeoutExpired:
            sys.stderr.write(
                f"[codex_cli] timeout after {timeout}s; prompt {_fingerprint(prompt)}\n"
            )
            return None
        except OSError as exc:
            sys.stderr.write(f"[codex_cli] spawn failed: {type(exc).__name__}\n")
            return None

        if proc.returncode != 0:
            sys.stderr.write(
                f"[codex_cli] exit {proc.returncode}; prompt {_fingerprint(prompt)}\n"
            )
            return None
        try:
            result = Path(out_path).read_text(
                encoding="utf-8", errors="replace"
            ).strip()
        except OSError:
            result = ""
        if not result:
            sys.stderr.write(
                f"[codex_cli] empty final message; prompt {_fingerprint(prompt)}\n"
            )
            return None
        return result
    finally:
        if out_path:
            try:
                Path(out_path).unlink(missing_ok=True)
            except OSError:
                pass


def is_codex_available() -> bool:
    return resolve_codex_bin() is not None


def is_codex_authenticated(timeout: int = 15) -> bool:
    """Return true only when the CLI is installed and its login is usable."""
    codex_bin = resolve_codex_bin()
    if not codex_bin:
        return False
    try:
        proc = safe_run(
            [*command_without_cmd_shim(codex_bin), "login", "status"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            env=_subscription_env(codex_bin),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0
