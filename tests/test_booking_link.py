"""Contract suite for scripts/lib/booking_link.py — the Python booking-link resolver.

WHY (2026-09-24): the command center retired its calendar link on 2026-09-09
(lib/booking-link.ts), but the Python side kept it as a module constant frozen
at import. An Instagram DM bot handed that dead page to a real prospect. These
pins make the dead link unrepresentable as a resolved value, and keep the two
stacks' retired lists identical.

No network, no env file: every resolution runs against an injected mapping or
a patched os.environ with the env-file seam stubbed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib import booking_link as bl  # noqa: E402

RETIRED = "https://calendar.app.google/tpfvJYBGircnGu8G8"
GOOD = {key: f"https://book.example.com/{key.lower()}" for key in bl.BOOKING_URL_ENV_KEYS}

# The TypeScript twin. Path.home() so the same test finds it on Windows and Mac.
TS_TWIN = Path.home() / "APPS" / "oasis-command-center" / "lib" / "booking-link.ts"


@pytest.fixture
def no_env(monkeypatch):
    """os.environ without any booking key, and an env-file seam that must not be
    reached unless a test installs its own."""
    for key in bl.BOOKING_URL_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(bl, "_env_file_values", lambda: {})
    return monkeypatch


# ── resolution order ─────────────────────────────────────────────────────────

def test_keys_resolve_in_declared_order():
    assert bl.BOOKING_URL_ENV_KEYS == (
        "BOOKING_LINK", "BOOKING_MEET_LINK", "NEXT_PUBLIC_BOOKING_URL",
        "NEXT_PUBLIC_FOUNDER_BOOKING_URL", "OASIS_FOUNDER_BOOKING_URL",
    )
    env = dict(GOOD)
    for key in bl.BOOKING_URL_ENV_KEYS:
        assert bl.resolve_booking_url(env) == GOOD[key]
        del env[key]
    assert bl.resolve_booking_url(env) == ""


def test_blank_values_are_skipped_and_values_trimmed():
    env = {"BOOKING_LINK": "   ", "BOOKING_MEET_LINK": "  https://book.example.com/x  "}
    assert bl.resolve_booking_url(env) == "https://book.example.com/x"


# ── refusals ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("variant", [
    RETIRED,
    RETIRED.lower(),
    RETIRED.upper().replace("HTTPS://", "https://"),
    RETIRED + "/",
    RETIRED + "///",
    f"  {RETIRED}  ",
])
def test_retired_link_is_refused_in_any_case_or_trailing_slash(variant):
    assert bl.is_retired_booking_url(variant)
    assert not bl.is_usable_booking_url(variant)
    assert bl.resolve_booking_url({"BOOKING_LINK": variant}) == ""


def test_retired_link_falls_through_to_the_next_usable_key():
    env = {"BOOKING_LINK": RETIRED, "NEXT_PUBLIC_BOOKING_URL": GOOD["NEXT_PUBLIC_BOOKING_URL"]}
    assert bl.resolve_booking_url(env) == GOOD["NEXT_PUBLIC_BOOKING_URL"]


@pytest.mark.parametrize("bad", [
    "http://book.example.com/30min",   # a link handed to strangers is https only
    "book.example.com/30min",
    "https://",
    "mailto:conaugh@oasisai.work",
    "javascript:alert(1)",
    "https://[::1",                    # malformed: must not raise
])
def test_non_https_or_hostless_is_refused(bad):
    assert not bl.is_usable_booking_url(bad)
    assert bl.resolve_booking_url({"BOOKING_LINK": bad}) == ""


def test_none_and_empty_are_not_usable():
    assert not bl.is_usable_booking_url(None)
    assert not bl.is_usable_booking_url("")
    assert not bl.is_retired_booking_url(None)
    assert bl.resolve_booking_url({}) == ""


def test_contains_retired_booking_url_finds_it_with_or_without_scheme():
    assert bl.contains_retired_booking_url(f"grab whatever slot fits you here: {RETIRED}")
    assert bl.contains_retired_booking_url("calendar.app.google/TPFVJYBGIRCNGU8G8")
    assert not bl.contains_retired_booking_url("book at https://book.example.com/x")
    assert not bl.contains_retired_booking_url(None)


# ── misconfigured flag ───────────────────────────────────────────────────────

def test_misconfigured_distinguishes_unset_from_dead():
    assert bl.booking_url_misconfigured({}) is False                      # nobody set it
    assert bl.booking_url_misconfigured({"BOOKING_LINK": "  "}) is False
    assert bl.booking_url_misconfigured({"BOOKING_LINK": RETIRED}) is True  # dead one again
    assert bl.booking_url_misconfigured({"BOOKING_MEET_LINK": "http://x.example.com"}) is True
    assert bl.booking_url_misconfigured(
        {"BOOKING_LINK": RETIRED, "OASIS_FOUNDER_BOOKING_URL": GOOD["OASIS_FOUNDER_BOOKING_URL"]}
    ) is False


# ── env=None: os.environ first, env file only as a fallback ─────────────────

def test_default_env_prefers_os_environ_and_skips_the_file(no_env):
    no_env.setenv("BOOKING_MEET_LINK", GOOD["BOOKING_MEET_LINK"])

    def file_must_not_be_read():
        raise AssertionError("env file read although os.environ had a usable link")

    no_env.setattr(bl, "_env_file_values", file_must_not_be_read)
    assert bl.resolve_booking_url() == GOOD["BOOKING_MEET_LINK"]


def test_default_env_falls_back_to_the_env_file(no_env):
    no_env.setenv("BOOKING_LINK", RETIRED)  # present in os.environ but refused
    no_env.setattr(bl, "_env_file_values",
                   lambda: {"NEXT_PUBLIC_BOOKING_URL": GOOD["NEXT_PUBLIC_BOOKING_URL"]})
    assert bl.resolve_booking_url() == GOOD["NEXT_PUBLIC_BOOKING_URL"]
    assert bl.booking_url_misconfigured() is False


def test_default_env_with_nothing_usable_anywhere(no_env):
    assert bl.resolve_booking_url() == ""
    assert bl.booking_url_misconfigured() is False
    no_env.setattr(bl, "_env_file_values", lambda: {"BOOKING_LINK": RETIRED})
    assert bl.resolve_booking_url() == ""
    assert bl.booking_url_misconfigured() is True


def test_env_file_seam_reads_through_the_secret_loader(monkeypatch):
    """The real seam asks lib.secret_loader.get for each key, and nothing else."""
    for key in bl.BOOKING_URL_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    import lib.secret_loader as sl

    asked: list[str] = []

    def fake_get(key, default=None):
        asked.append(key)
        return RETIRED if key == "BOOKING_LINK" else None

    monkeypatch.setattr(sl, "get", fake_get)
    assert bl._env_file_values() == {"BOOKING_LINK": RETIRED}
    assert asked == list(bl.BOOKING_URL_ENV_KEYS)
    assert bl.resolve_booking_url() == ""
    assert bl.booking_url_misconfigured() is True


def test_a_refused_loader_is_reported_not_hidden(monkeypatch, capsys):
    """An interactive shell makes the loader refuse by policy. The resolver
    still answers from os.environ, and says on stderr that the file was skipped."""
    for key in bl.BOOKING_URL_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    import lib.secret_loader as sl

    def refuse(key, default=None):
        raise sl.SecretLoaderRefused("interactive shell")

    monkeypatch.setattr(sl, "get", refuse)
    assert bl.resolve_booking_url() == ""
    assert "env-file fallback refused" in capsys.readouterr().err


# ── callers: no link means no booking line, never a dead one ────────────────

@pytest.mark.parametrize("configured", [None, RETIRED])
def test_branded_shell_and_outreach_drop_the_booking_line_without_a_usable_link(no_env, configured):
    import email_template
    import outreach_engine

    if configured:
        no_env.setenv("BOOKING_LINK", configured)
    plain = email_template.render_branded_plaintext("hello", brand="oasis")
    html = email_template.render_branded_html("hello", brand="oasis")
    body = outreach_engine.build_email_body(
        "Sam", "Acme", "HVAC", "https://meet.google.com/abc-defg-hij", "2026-09-25T14:00:00+00:00")
    assert "Book a call" not in plain
    assert "calendar.app.google" not in (plain + html).lower()
    assert "grab any slot" not in body and "Book a call" not in body
    assert "calendar.app.google" not in body.lower()
    assert body.rstrip().endswith("oasisai.work")


def test_branded_shell_and_outreach_keep_a_usable_link(no_env):
    import email_template
    import outreach_engine

    no_env.setenv("BOOKING_LINK", GOOD["BOOKING_LINK"])
    plain = email_template.render_branded_plaintext("hello", brand="oasis")
    body = outreach_engine.build_email_body(
        "Sam", "Acme", "HVAC", "https://meet.google.com/abc-defg-hij", "2026-09-25T14:00:00+00:00")
    assert f"Book a call: {GOOD['BOOKING_LINK']}" in plain
    assert f"grab any slot that works for you: {GOOD['BOOKING_LINK']}" in body
    assert body.rstrip().endswith(f"Book a call: {GOOD['BOOKING_LINK']}")


# ── parity with the TypeScript twin ──────────────────────────────────────────

def _ts_retired_urls(source: str) -> frozenset[str]:
    m = re.search(r"RETIRED_BOOKING_URLS[^=]*=\s*\[(.*?)\]", source, re.DOTALL)
    assert m, "RETIRED_BOOKING_URLS array not found in lib/booking-link.ts"
    return frozenset(re.findall(r'"([^"]+)"', m.group(1)))


def test_retired_list_matches_the_command_center():
    """One list per stack, parity asserted here (same pattern as tenant_brand).
    A link retired on one side and live on the other is the 2026-09-24 incident."""
    if not TS_TWIN.exists():
        pytest.skip(f"command-center twin not on this machine: {TS_TWIN}")
    ts = _ts_retired_urls(TS_TWIN.read_text(encoding="utf-8"))
    assert ts, "parsed an empty retired list from the TypeScript twin"
    assert ts == bl.RETIRED_BOOKING_URLS
