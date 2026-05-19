"""PostToolUse hook — fires `memory_retriever.py update` after edits to indexed dirs.

Cheap and non-blocking: only triggers if the edited path is under
`memory/`, `skills/`, `brain/`, or one of the entry-point markdown files.
The retriever's incremental `update` is hash-gated so unchanged files cost
nothing. Spawned in a detached subprocess so the agent never waits.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.hook_runtime import PROJECT_ROOT, read_hook_input  # noqa: E402
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

INDEXED_DIRS = ("memory", "skills", "brain")
ENTRY_FILES = {"CLAUDE.md", "AGENTS.md", "GEMINI.md", "ANTIGRAVITY.md", "OPENCODE.md"}


def _is_indexed(path_str: str | None) -> bool:
    if not path_str:
        return False
    try:
        p = Path(path_str).resolve()
        rel = p.relative_to(PROJECT_ROOT.resolve())
    except (OSError, ValueError):
        return False
    parts = rel.parts
    if not parts:
        return False
    if parts[0] in INDEXED_DIRS:
        return True
    if len(parts) == 1 and parts[0] in ENTRY_FILES:
        return True
    return False


def main() -> int:
    payload = read_hook_input()
    if not payload:
        return 0

    if payload.get("tool_name") not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return 0

    target = payload.get("tool_input", {}).get("file_path")
    if not _is_indexed(target):
        return 0

    kwargs: dict = {
        "cwd": str(PROJECT_ROOT),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        DETACHED_PROCESS = 0x00000008
        kwargs["creationflags"] = DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "memory_retriever.py"), "update"],
            **kwargs,
         creationflags=WINDOWLESS_FLAGS)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
