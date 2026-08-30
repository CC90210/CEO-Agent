"""opencode_cli.py — one-shot local OpenCode CLI calls (free/unlimited models).

Mirrors the claude_cli.py pattern: spawns the local `opencode run` CLI with
non-interactive flags, feeds the prompt via STDIN (never argv), and returns
the model's text or None on any failure. This is the FALLBACK layer — called
by model_fallback.py when the Claude subscription CLI is unavailable (quota /
auth / timeout).

SECURITY (V8 hardening, adversarial-review fixes 2026-08-25):
  1. NO shell anywhere. The binary is resolved to a directly-executable image
     (.exe on Windows, extensionless binary on Unix); .cmd/.ps1 npm shims are
     REJECTED because executing them requires cmd.exe, which re-opens the
     command-injection door this module exists to keep shut.
  2. The prompt goes via STDIN, never argv — same rule as claude_cli.py's V7
     fix ("callers feed untrusted data"). This also dodges the ~32K Windows
     command-line cap for long prompts.
   3. Every call runs as the restricted `bravo-oneshot` agent
      (.opencode/agents/bravo-oneshot.md — permission "*": deny) which blocks
      ALL tools — mirrors claude_cli.py's --allowedtools "" posture. Prompts
      carry untrusted lead text; a prompt-injection payload must not be able
      to invoke Bash/Edit.
  4. No secrets are read or passed beyond the inherited process environment.

Free models available through OpenCode (verified 2026-08-25):
  - opencode/big-pickle          (general reasoning, unlimited)
  - opencode/deepseek-v4-flash   (fast reasoning)
  - opencode/deepseek-v4-pro     (heavier reasoning)
  - opencode/nemotron-3.5-lightning-free  (fast classification)
  - opencode/hy3-free            (lightweight tasks)
  - opencode/mimo-v2.5-free      (lightweight tasks)

Returns the model's text, or None on ANY failure (missing CLI, timeout,
non-zero exit) so callers degrade gracefully instead of crashing.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    from _subprocess_helpers import WINDOWLESS_FLAGS  # type: ignore
except Exception:  # pragma: no cover
    WINDOWLESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Restricted text-only agent (all tools denied). Defined project-level in
# .opencode/agents/bravo-oneshot.md so it loads whenever --dir points here.
OPENCODE_AGENT = "bravo-oneshot"

# ── Tier-to-model mapping ──────────────────────────────────────────────────
# task_type → (primary, fallback). Callers pass a task_type string; the mapper
# picks the best free model for the job. "reasoning" and "closing" get the
# heaviest free model; "fast" and "classify" get a lightweight one.
TIER_MODELS: dict[str, tuple[str, str]] = {
    "reasoning":  ("opencode/big-pickle",  "opencode/deepseek-v4-flash"),
    "closing":    ("opencode/big-pickle",  "opencode/deepseek-v4-flash"),
    "fast":       ("opencode/nemotron-3.5-lightning-free", "opencode/hy3-free"),
    "classify":   ("opencode/nemotron-3.5-lightning-free", "opencode/mimo-v2.5-free"),
    "default":    ("opencode/big-pickle",  "opencode/deepseek-v4-flash"),
}

_SHIM_SUFFIXES = (".cmd", ".ps1", ".bat")


def _is_directly_executable(path: Path) -> bool:
    """True if the OS can exec this file WITHOUT a shell.

    Windows: only real PE images (.exe). Shims (.cmd/.ps1/.bat) need cmd.exe,
    which would reinterpret metacharacters — rejected by design.
    Unix: any regular file works (exec bit checked by the OS itself).
    """
    if os.name == "nt":
        return path.suffix.lower() == ".exe"
    return True


def resolve_opencode_bin() -> Optional[str]:
    """Locate the opencode CLI as a DIRECTLY EXECUTABLE binary.

    Order: BRAVO_OPENCODE_EXE override > native exe in npm global dir >
    per-OS install dirs a daemon's slim PATH misses > shutil.which
    (only if it resolves to something we can exec without a shell).
    """
    override = os.environ.get("BRAVO_OPENCODE_EXE", "").strip()
    if override:
        p = Path(override)
        if p.is_file() and _is_directly_executable(p):
            return str(p)

    home = Path.home()
    candidates: list[Path] = []
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            # Native binary shipped inside the opencode-ai npm package
            # (postinstall artifact) — executable without cmd.exe.
            candidates.append(
                Path(appdata) / "npm" / "node_modules" / "opencode-ai"
                / "bin" / "opencode.exe")
        candidates.append(home / ".local" / "bin" / "opencode.exe")
    else:
        candidates.extend(Path(d) / "opencode" for d in (
            "/opt/homebrew/bin",
            "/usr/local/bin",
            str(home / ".npm-global" / "bin"),
            str(home / ".local" / "bin"),
            str(home / ".bun" / "bin"),
        ))
    for c in candidates:
        if c.is_file():
            return str(c)

    found = shutil.which("opencode")
    if found and _is_directly_executable(Path(found)):
        return found
    return None


def model_for_task(task_type: str) -> str:
    """Return the primary free model for a given task type."""
    primary, _ = TIER_MODELS.get(task_type, TIER_MODELS["default"])
    return primary


_ANSI_RE = re.compile(
    r"[\u001b\u009b]\[[\[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]")
_BANNER_LINE_RE = re.compile(r"^[⠀█▀▄▐▌░▒▓\s]+$")
_STATUS_HEADER_RE = re.compile(r"^>\s*\w[\w.-]*\s*·\s*\S.*$")


def _clean_output(text: str) -> str:
    """Strip ANSI escapes, OpenCode banner art, and the status header line
    (`> build · <model>` that `opencode run --format default` prepends)."""
    text = _ANSI_RE.sub("", text)
    lines = text.split("\n")
    cleaned = [
        ln for ln in lines
        if not _STATUS_HEADER_RE.match(ln.strip())
        and not _BANNER_LINE_RE.match(ln.strip())
    ]
    return "\n".join(cleaned).strip()


def run_opencode_cli(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: str = "opencode/big-pickle",
    timeout: int = 120,
    cwd: Optional[Path] = None,
    task_type: str = "default",
) -> Optional[str]:
    """One-shot `opencode run` with a free model. Returns stdout text, or
    None on any failure.

    model: full provider/model string (e.g. "opencode/big-pickle").
    system: optional system prompt prepended to the user prompt (delivered
      via stdin together with the user content — never argv).
    task_type: if model is left at its default, pick a model via TIER_MODELS.
    """
    opencode_bin = resolve_opencode_bin()
    if not opencode_bin:
        sys.stderr.write(
            "[opencode_cli] no directly-executable opencode binary found "
            "(npm shims .cmd/.ps1 are rejected — set BRAVO_OPENCODE_EXE to "
            "the native exe)\n")
        return None

    # If caller passed the default model but also a task_type, resolve via tier.
    if model == "opencode/big-pickle" and task_type != "default":
        model = model_for_task(task_type)

    # SECURITY: prompt travels via stdin, never argv (untrusted data — see
    # module docstring §2). Only fixed strings go on the command line.
    full_prompt = prompt
    if system:
        full_prompt = f"<system>\n{system}\n</system>\n\n{prompt}"

    args = [
        opencode_bin, "run",
        "--model", model,
        "--agent", OPENCODE_AGENT,
        "--format", "default",
        "--dir", str(cwd or PROJECT_ROOT),
    ]

    env = {
        **os.environ,
        "CI": "true",
        "NONINTERACTIVE": "true",
        "NO_COLOR": "1",
        "FORCE_COLOR": "0",
        "PAGER": "cat",
    }

    try:
        proc = subprocess.run(
            args,
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            creationflags=WINDOWLESS_FLAGS,
            env=env,
            cwd=str(cwd or PROJECT_ROOT),
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(f"[opencode_cli] timed out after {timeout}s\n")
        return None
    except OSError as e:
        sys.stderr.write(f"[opencode_cli] spawn failed: {e}\n")
        return None

    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        out = (proc.stdout or "").strip()
        detail = err[:300] if err else (f"(stderr empty) stdout: {out[:300]}" if out
                                        else "(no output on either stream)")
        sys.stderr.write(f"[opencode_cli] exit {proc.returncode}: {detail}\n")
        return None

    raw = (proc.stdout or "")
    if not raw.strip():
        return None

    cleaned = _clean_output(raw)
    return cleaned or None


# ── CLI self-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"[opencode_cli] binary: {resolve_opencode_bin() or 'NOT FOUND'}")
    print(f"[opencode_cli] testing with model: opencode/big-pickle")
    result = run_opencode_cli("Reply with PONG and nothing else.", timeout=60)
    if result:
        print(f"[opencode_cli] SUCCESS: {result[:200]}")
    else:
        print("[opencode_cli] FAILED: returned None")
        sys.exit(1)
