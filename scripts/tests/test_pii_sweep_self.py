"""Self-test for pii_sweep.py — enforces the V3 STANDING LAW:
  "Redaction tooling and redaction paperwork must never contain or emit the
   strings they redact."

Two assertions:
  1. output ∩ input_strings = ∅ — run the tool over a throwaway repo seeded with
     known fixture strings; the tool's stdout must reference carriers as `string #N`
     and must NOT echo any fixture string (not even a masked prefix).
  2. no adjudicated string appears in the tool's own source — checked against the
     local gitignored adjudication file when present (CC's machine); gracefully
     skipped where the file is absent (CI), since it is never committed.

Offline, deterministic, no network. Creates a local git repo in a tmp dir.
"""
from __future__ import annotations
import os, subprocess, sys, tempfile
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "pii_sweep.py"
FIXTURES = ["ZZQAFIXTURENAMEALPHA", "ZZQAFIXTURENAMEBRAVO"]


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _seed_repo(d: Path):
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "qa@example.com")
    _git(d, "config", "user.name", "qa")
    (d / "carrier.md").write_text(
        f"lead one {FIXTURES[0]} and lead two {FIXTURES[1]} in prose\n", encoding="utf-8")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "seed")


def test_output_never_echoes_input_strings():
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "qa"
        repo.mkdir()
        _seed_repo(repo)
        strings_file = Path(td) / "strings.txt"
        strings_file.write_text("\n".join(FIXTURES) + "\n", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(TOOL), str(repo), "--strings", str(strings_file)],
            capture_output=True, text=True)
        out = r.stdout + r.stderr
        # The law: not one fixture string may appear in the tool's output.
        for s in FIXTURES:
            assert s not in out, f"LAW VIOLATION: tool echoed redact string {s!r} in its output"
        # It must still detect + report them as indexed carriers.
        assert "string #" in out, f"expected indexed carrier output, got:\n{out}"
        assert r.returncode == 1, "fixture strings are on the branch — sweep should report DIRTY (exit 1)"


def test_tool_source_contains_no_redact_strings():
    src = TOOL.read_text(encoding="utf-8")
    for s in FIXTURES:
        assert s not in src, f"fixture string {s!r} leaked into tool source"
    # If CC's local adjudication file exists, prove the tool source is clean of it.
    adj = TOOL.parent.parent / "state" / "pii_adjudication.txt"
    if not adj.exists():
        return  # gitignored; absent in CI — nothing to assert
    redact = []
    for ln in adj.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or ln.lower().startswith("safe:"):
            continue
        redact.append(ln.split("==>", 1)[0].strip())
    for s in redact:
        assert s and s not in src, f"LAW VIOLATION: adjudicated string appears in tool source"
