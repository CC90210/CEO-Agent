#!/usr/bin/env python3
"""Regression test: provision_secrets._resolve_tenant honors slug AND the
Command Center profile slug.

Bug (2026-06-03): _resolve_tenant matched only tenants.slug, but the SunBiz
tenant is stored as slug='submissions' with
custom_fields.command_center_profile_slug='sun'. So the documented
`provision_secrets.py --tenant sun` failed with "tenant slug 'sun' not found".
The fix adds a command_center_profile_slug fallback (the convention the rest of
the runtime resolves by) while keeping exact-slug resolution.

Uses a fake Supabase client — no network. Run with
`python3 tests/test_provision_secrets_resolve.py` or under pytest.
"""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PS_PATH = REPO / "scripts" / "provision_secrets.py"

_spec = importlib.util.spec_from_file_location("provision_secrets", PS_PATH)
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)


# ---- minimal fake supabase client (only what _resolve_tenant touches) -------
class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = rows
        self._eq = None

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self._eq = (col, val)
        return self

    def limit(self, n):
        return self

    def execute(self):
        if self._eq:
            col, val = self._eq
            return _Resp([r for r in self._rows if r.get(col) == val][:1])
        return _Resp(list(self._rows))


class _FakeSB:
    def __init__(self, rows):
        self._rows = rows

    def table(self, name):
        assert name == "tenants"
        return _Query(self._rows)


ROWS = [
    {"id": "SUN", "slug": "submissions",
     "custom_fields": {"command_center_profile_slug": "sun"}},
    {"id": "OASIS", "slug": "oasis-ai-cc", "custom_fields": None},
]


def test_slug_exact():
    assert ps._resolve_tenant(_FakeSB(ROWS), "submissions") == "SUN"
    assert ps._resolve_tenant(_FakeSB(ROWS), "oasis-ai-cc") == "OASIS"


def test_profile_slug_fallback():
    # The fix: 'sun' is the command_center_profile_slug, not the slug.
    assert ps._resolve_tenant(_FakeSB(ROWS), "sun") == "SUN"


def test_unknown_exits_3():
    try:
        ps._resolve_tenant(_FakeSB(ROWS), "does-not-exist")
        raise AssertionError("expected SystemExit for unknown tenant")
    except SystemExit as e:
        assert e.code == 3


if __name__ == "__main__":
    test_slug_exact()
    test_profile_slug_fallback()
    test_unknown_exits_3()
    print("PASS: slug-exact, command_center_profile_slug fallback, and clean miss all correct")
