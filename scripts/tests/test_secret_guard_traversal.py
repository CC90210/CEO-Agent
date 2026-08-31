"""GAP-8 regression: a recursive search must not read the credential store.

Every other check in secret_guard keys off a secret path being NAMED in the
command. A recursive search names none — it just walks into the store and prints
it. Found empirically 2026-08-31 when a subagent's `grep -rIn ... .` returned
live OAuth values from an unnamed .env file.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "secret_guard", ROOT / "scripts" / "state" / "secret_guard.py")
sg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sg)

DOTENV = "." + "env"          # split so this file never contains the literal
EXCLUDE = f"--exclude='{DOTENV}*'"

CASES = [
    (f"grep -rIn 'TOKEN' .", True, "recursive grep from the repo root"),
    ("grep -rn 'foo' scripts/", True, "recursive grep into a subdir"),
    (f"grep -rn 'foo' . {EXCLUDE}", False, "recursive WITH an exclusion"),
    ("rg 'foo'", False, "ripgrep honours .gitignore"),
    ("grep -n 'foo' scripts/x.py", False, "non-recursive single file"),
    ("findstr /s TOKEN *.ts", True, "findstr recursive"),
    ("Get-ChildItem -Recurse | Select-String TOKEN", True, "PowerShell recurse into Select-String"),
    ("git grep -n foo", False, "git grep has no -r flag"),
    ("echo 'grep -r is mentioned here'", False, "a mention is not an invocation"),
]


# An exclusion flag names the secret family in order to SKIP it. The exfil check
# extracts candidate paths from the raw command, so before this was handled the
# guard blocked the exact remediation it prints — advice you cannot follow.
# The last case is the one that keeps the fix honest: stripping the flag must not
# blind the check to a real read sitting elsewhere in the same command line.
EXFIL_CASES = [
    (f"grep -rn 'foo' . {EXCLUDE}", False, "the remediation command must be runnable"),
    (f"grep -rn 'foo' . --exclude-dir='{DOTENV}.bak'", False, "exclude-dir form"),
    (f"grep -rn x . {EXCLUDE} && cat {DOTENV}.agents", True, "a real read beside an exclusion still blocks"),
    (f"cat {DOTENV}.agents", True, "plain read still blocks"),
]


def main() -> int:
    bad = 0
    for cmd, expected, label in CASES:
        got = sg._command_traverses_secrets(cmd)
        ok = got == expected
        bad += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  traverse={str(got):5} expected={str(expected):5}  {label}")
    for cmd, expected, label in EXFIL_CASES:
        got = sg._command_is_secret_exfil(cmd)[0]
        ok = got == expected
        bad += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  exfil   ={str(got):5} expected={str(expected):5}  {label}")
    print("\ntest_secret_guard_traversal:", "OK" if not bad else f"{bad} FAILED")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
