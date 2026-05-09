"""Lock the popup fix: every subprocess.run / subprocess.Popen in
bridge_chat_server.py must pass creationflags=_WINDOWLESS_FLAGS so the
Windows-side bridge heartbeat doesn't pop a system32 cmd.exe every 60s
when it probes for `playwright`, `whisper`, `ffmpeg`.

This is a TEXT-LEVEL test against the source — there's no way to spawn
the bridge in pytest, so we assert the contract that every subprocess
call site has the right flag.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "bravo_cli" / "bridge_chat_server.py"


def _all_subprocess_calls() -> list[tuple[int, str, str]]:
    """Return (line_number, kind, full_block) for every subprocess.run /
    subprocess.Popen / subprocess.call in the file. Walks parens to capture
    the entire multi-line call."""
    text = SRC.read_text(encoding="utf-8")
    out: list[tuple[int, str, str]] = []
    for m in re.finditer(r"subprocess\.(Popen|run|call|check_output|check_call)\(", text):
        kind = m.group(1)
        start = m.start()
        end = m.end()
        depth = 1
        while end < len(text) and depth > 0:
            if text[end] == "(":
                depth += 1
            elif text[end] == ")":
                depth -= 1
            end += 1
        line = text[:start].count("\n") + 1
        out.append((line, kind, text[start:end]))
    return out


def test_every_subprocess_passes_windowless_flags():
    """No popup may slip in. Every subprocess call must reference
    _WINDOWLESS_FLAGS — either directly or via a helper that wraps it."""
    leaks: list[str] = []
    for line, kind, block in _all_subprocess_calls():
        if "_WINDOWLESS_FLAGS" not in block and "creationflags" not in block:
            leaks.append(f"line {line} subprocess.{kind} missing creationflags")
    assert not leaks, (
        "bridge_chat_server.py has unprotected subprocess calls — these "
        "will pop cmd.exe windows on Windows when their target is a .cmd "
        "shim:\n  " + "\n  ".join(leaks)
    )


def test_cmd_resolving_probes_use_startupinfo():
    """For probes that resolve to .cmd shims (`playwright.cmd`, `whisper.cmd`),
    CREATE_NO_WINDOW alone is not enough — the cmd.exe wrapper still flashes
    unless STARTUPINFO + SW_HIDE is also passed. Verify the heartbeat probes
    use both."""
    text = SRC.read_text(encoding="utf-8")
    # The four heartbeat probes should each be in a code block that
    # references both flags. Cheap proof: every line that calls
    # subprocess.run on a known .cmd-shim binary must have a startupinfo.
    cmd_shim_probes = ("\"playwright\"", "\"whisper\"")
    for probe in cmd_shim_probes:
        # Find the call site
        for m in re.finditer(r"subprocess\.run\([^)]*" + re.escape(probe), text):
            window = text[m.start():m.start() + 600]
            assert "startupinfo=" in window, (
                f"probe {probe} at offset {m.start()} missing startupinfo "
                f"— cmd.exe wrapper will still flash"
            )
