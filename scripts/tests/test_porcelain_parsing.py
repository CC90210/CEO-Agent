"""`git status --porcelain` must never be parsed by column out of a stripped string.

THE CLASS, not the instance. Porcelain records are `XY<space>PATH`, so `ln[3:]`
is the obvious way to get the path — and it is correct only against RAW stdout.
Both of this repo's subprocess helpers return `stdout.strip()`, which eats the
leading space of the FIRST line only. A ` M brain/CAPABILITIES.md` line then
reads as `M brain/CAPABILITIES.md`, and `ln[3:]` returns
`rain/CAPABILITIES.md` — one character short, on exactly one line per call.

It shipped twice on 2026-08-28/29:

  * review_fix._changed_paths — the truncated path matched no allowlist, so the
    PR-diff bound rejected the model's correct fix as out-of-bounds on every
    single run. Three good patches were discarded before anyone noticed.
  * hooks/session_start._write_git_baseline — the truncated path went into the
    session baseline, so the SubagentStop gate saw the REAL file as
    new-this-session and nagged about a file that was already dirty at boot.
    That is the failure mode the baseline exists to prevent, and on 2026-07-02
    that nagging pressured a read-only agent into destructive remediation.
    Confirmed live in `state/session_git_baseline.json` before the fix.

The second one existed while I was fixing the first. A defect found in one file
is a question about every file, and this test is the answer being written down
instead of remembered.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = PROJECT_ROOT / "scripts"

# A helper that returns stripped output must not feed column-based parsing.
STRIPPING_HELPERS = ("_run(", "run(")


def _sources():
    for path in SCRIPTS.rglob("*.py"):
        parts = set(path.parts)
        if "tests" in parts or "_archive" in parts or "__pycache__" in parts:
            continue
        yield path


def _code_only(path: Path) -> dict:
    """Line number -> that line's CODE, with comments and string literals blanked.

    The first version of this scan searched raw text and flagged the two
    docstrings that explain the bug. A test that reads prose reports the
    explanation as the defect — the same useless-guard shape this file exists to
    prevent, one level up. Tokenising is the difference between checking what
    the code does and checking what it says.
    """
    import io as _io
    import tokenize

    source = path.read_text(encoding="utf-8", errors="replace")
    lines = {i + 1: ln for i, ln in enumerate(source.splitlines())}
    try:
        tokens = list(tokenize.generate_tokens(_io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return lines                       # unparseable: scan it raw rather than skip it
    for tok in tokens:
        # Blank COMMENTS and MULTI-LINE strings (docstrings) only.
        #
        # Blanking every STRING blanked the `"--porcelain"` literal this scan
        # searches FOR, so the check silently matched nothing — it passed with
        # the bug deliberately reintroduced. A guard that cannot fire is worse
        # than no guard, and this one had to be broken on purpose to find out.
        multiline_string = tok.type == tokenize.STRING and tok.end[0] > tok.start[0]
        if not (tok.type == tokenize.COMMENT or multiline_string):
            continue
        for n in range(tok.start[0], tok.end[0] + 1):
            if n in lines:
                lines[n] = ""              # blank the prose, keep the numbering
    return lines


def test_no_module_parses_porcelain_by_column_through_a_stripping_helper():
    """The scan that would have caught the second instance an hour earlier."""
    offenders = []
    for path in _sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        if "--porcelain" not in text:
            continue
        code = _code_only(path)
        numbers = sorted(code)
        for idx, n in enumerate(numbers):
            if "--porcelain" not in code[n]:
                continue
            # Look at the next ~12 CODE lines for a column slice on that output.
            window = "\n".join(code[m] for m in numbers[idx:idx + 12])
            if not re.search(r"\[\s*3\s*:\s*\]|\[\s*:\s*2\s*\]", window):
                continue
            # It is only a bug if the output came from a STRIPPING helper.
            if re.search(r"(_run_raw|subprocess\.run|\.stdout)", window):
                continue
            offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{n}")
    assert not offenders, (
        "porcelain parsed by column out of stripped output:\n  "
        + "\n  ".join(offenders))


def test_session_start_baseline_matches_git_exactly():
    """Behavioural proof, not a source scan: the baseline the validator gate
    reads must contain exactly the paths git reports — no truncation, nothing
    missing."""
    sys.path.insert(0, str(SCRIPTS / "hooks"))
    import session_start  # noqa: PLC0415

    raw = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "status", "--porcelain"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120,
    ).stdout
    expected = set()
    for line in raw.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip().strip('"')
        if path:
            expected.add(path)

    got = session_start._run_raw(["git", "status", "--porcelain"], timeout=60) or ""
    parsed = set()
    for line in got.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip().strip('"')
        if path:
            parsed.add(path)

    assert parsed == expected, (
        f"baseline parse disagrees with git: "
        f"missing={sorted(expected - parsed)} extra={sorted(parsed - expected)}")


def test_run_raw_does_not_strip():
    """The property the whole class depends on. If someone 'tidies' _run_raw by
    adding .strip(), both instances come straight back."""
    sys.path.insert(0, str(SCRIPTS / "hooks"))
    import session_start  # noqa: PLC0415

    out = session_start._run_raw(["git", "status", "--porcelain"], timeout=60)
    if not out:
        import pytest  # noqa: PLC0415
        pytest.skip("working tree is clean — nothing to parse")
    first = out.splitlines()[0]
    assert first[:2] != first[:2].strip() or first[0] not in " ", (
        "the first record lost its leading status space — _run_raw is stripping")
