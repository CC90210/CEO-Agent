"""The credential-store parser must give one answer, not four.

Before scripts/lib/env_store.py existed, five tools each had their own copy of
this loop and they disagreed on two real forms: `export KEY=value` and a quoted
value. A key was therefore POPULATED to secret_disk_hunt and MISSING to
secret_apply_authorized — so an applier could refuse a source key whose value it
had just read. These cases pin the forms that caused that.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "env_store", ROOT / "scripts" / "lib" / "env_store.py")
env_store = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(env_store)

SAMPLE = "\n".join([
    "# a comment",
    "",
    "PLAIN=value1",
    "export EXPORTED=value2",
    "QUOTED=\"value3\"",
    "SINGLE='value4'",
    "EMPTY=",
    "# FILL STUBBED=",
    "  SPACED  =  value5  ",
    "WITH_EQUALS=a=b",
])

VALUE_CASES = [
    ("PLAIN", "value1", "plain assignment"),
    ("EXPORTED", "value2", "export prefix is honoured (3 tools used to miss this)"),
    ("QUOTED", "value3", "double quotes stripped (2 tools used to keep them)"),
    ("SINGLE", "value4", "single quotes stripped"),
    ("SPACED", "value5", "whitespace around key and value"),
    ("WITH_EQUALS", "a=b", "only the FIRST = splits"),
]


def main() -> int:
    bad = 0
    parsed = env_store.parse_text(SAMPLE)

    for key, expected, label in VALUE_CASES:
        got = parsed.get(key)
        ok = got == expected
        bad += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {key:14} -> {got!r:12} expected {expected!r:12}  {label}")

    # An empty value is an open slot, not a credential.
    ok = "EMPTY" not in parsed
    bad += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  EMPTY excluded from populated values")

    # A commented FILL stub is not an assignment at all.
    ok = "STUBBED" not in parsed and "# FILL STUBBED" not in parsed
    bad += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  commented FILL stub is not populated")

    # key_names answers a DIFFERENT question and must include the empty one.
    names = env_store.key_names(SAMPLE)
    ok = "EMPTY" in names and "EXPORTED" in names and "STUBBED" not in names
    bad += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  key_names includes declared-but-empty, excludes comments")

    # Unreadable input must not abort a directory scan.
    ok = env_store.parse_file(ROOT / "does" / "not" / "exist") == {}
    bad += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  missing file returns empty rather than raising")

    print("\ntest_env_store_parity:", "OK" if not bad else f"{bad} FAILED")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
