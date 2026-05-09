"""Lock the popup fix: every subprocess.run / subprocess.Popen in the
bravo_cli package must pass creationflags so the Windows-side bridge
doesn't pop a system32 cmd.exe at any of its periodic ticks.

This is a TEXT-LEVEL test — there's no way to spawn the bridge in
pytest. We assert the contract that every subprocess call site has the
right flag, AND that .cmd-shim probes also pass startupinfo (because
CREATE_NO_WINDOW alone is not enough for the cmd.exe wrapper).
"""

import re
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "bravo_cli"
COVERED_FILES = ["bridge_chat_server.py", "warm_claude_pool.py", "local_bridge.py"]


def _all_subprocess_calls(path: Path) -> list[tuple[int, str, str]]:
    """Return (line_number, kind, full_block) for every subprocess.run /
    subprocess.Popen / subprocess.call in the file. Walks parens to capture
    the entire multi-line call."""
    text = path.read_text(encoding="utf-8")
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


def test_every_subprocess_in_bravo_cli_passes_windowless_flags():
    """No popup may slip in across the three popup-prone bravo_cli modules.
    Every subprocess call must reference WINDOWLESS_FLAGS / creation_flags
    — either via the helper import or via a creationflags= kwarg."""
    leaks: list[str] = []
    for fname in COVERED_FILES:
        path = PKG / fname
        for line, kind, block in _all_subprocess_calls(path):
            if "WINDOWLESS_FLAGS" not in block and "creationflags" not in block:
                leaks.append(f"{fname}:{line} subprocess.{kind} missing creationflags")
    assert not leaks, (
        "bravo_cli has unprotected subprocess calls — these will pop "
        "cmd.exe windows on Windows when their target is a .cmd shim:\n  "
        + "\n  ".join(leaks)
    )


def test_cmd_resolving_probes_use_startupinfo():
    """For probes that resolve to .cmd shims (`playwright.cmd`, `whisper.cmd`),
    CREATE_NO_WINDOW alone is not enough — the cmd.exe wrapper still flashes
    unless STARTUPINFO + SW_HIDE is also passed. Verify the heartbeat probes
    use both."""
    text = (PKG / "bridge_chat_server.py").read_text(encoding="utf-8")
    cmd_shim_probes = ("\"playwright\"", "\"whisper\"")
    for probe in cmd_shim_probes:
        for m in re.finditer(r"subprocess\.run\([^)]*" + re.escape(probe), text):
            window = text[m.start():m.start() + 600]
            assert "startupinfo=" in window, (
                f"probe {probe} at offset {m.start()} missing startupinfo "
                f"— cmd.exe wrapper will still flash"
            )


def test_helper_module_exists_and_exports_both_names():
    """The shared helper must exist and expose both names. Catches an
    accidental rename that breaks the three call sites in lockstep."""
    helper = PKG / "_subprocess_helpers.py"
    assert helper.is_file(), "bravo_cli/_subprocess_helpers.py must exist"
    text = helper.read_text(encoding="utf-8")
    assert "WINDOWLESS_FLAGS" in text, "helper must export WINDOWLESS_FLAGS"
    assert "def windowless_startupinfo" in text, (
        "helper must export windowless_startupinfo() for .cmd-shim callers"
    )
