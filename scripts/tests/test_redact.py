"""Tests for lib/redact.py.

This function is the last thing standing between a child process's raw stderr
and (a) a file on disk in tmp/cron_failures/ and (b) a Telegram message. The
2026-07-21 precedent is concrete: a transient network error leaked
TELEGRAM_BOT_TOKEN into PM2 logs because the requests exception embedded the
request URL. A redactor with no tests is a liability, not a control.

All credentials below are fabricated.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.redact import MIN_SECRET_LEN, redact_secrets  # noqa: E402

FAKE_ENV = {
    "BRAVO_SUPABASE_SERVICE_ROLE_KEY":
        "eyJhbGciOiJIUzI1NiJ9.FAKEPAYLOAD_aaaaaaaaaaaaaa.FAKESIG_bbbbbbbbbbbbbb",
    "GMAIL_APP_PASSWORD": "abcdefghijklmnop",
    "TELEGRAM_BOT_TOKEN": "8012345678:AAF_fakeTokenValue_1234567890abcd",
    "BRAVO_SUPABASE_URL": "https://phctllmtsogkovoilwos.supabase.co",
    "SHORT": "abc",
}


# ── env-value redaction ──────────────────────────────────────────────────────

@pytest.mark.parametrize("key", [
    "BRAVO_SUPABASE_SERVICE_ROLE_KEY", "GMAIL_APP_PASSWORD", "TELEGRAM_BOT_TOKEN",
])
def test_env_values_are_replaced(key):
    text = f"failure while using {FAKE_ENV[key]} in the request"
    out = redact_secrets(text, FAKE_ENV)
    assert FAKE_ENV[key] not in out
    assert f"[REDACTED:{key}]" in out


def test_non_secret_keys_stay_readable():
    """Redacting the project URL would make every traceback unreadable for no
    security gain — you cannot authenticate with a public REST endpoint."""
    out = redact_secrets(f"connecting to {FAKE_ENV['BRAVO_SUPABASE_URL']}", FAKE_ENV)
    assert "phctllmtsogkovoilwos.supabase.co" in out


def test_short_values_are_not_redacted():
    """Blanking a 3-char value would shred ordinary prose, and a 3-char value is
    not a secret."""
    out = redact_secrets("abc is a common substring in abcdef", FAKE_ENV)
    assert "[REDACTED:SHORT]" not in out
    assert MIN_SECRET_LEN >= 8


def test_longest_first_so_no_dangling_tail():
    """If one value is a prefix of another, replacing the short one first leaves
    the remainder of the long one exposed."""
    env = {"SHORT_KEY": "aaaaaaaaaaaabbbb", "LONG_KEY": "aaaaaaaaaaaabbbbCCCCDDDD"}
    out = redact_secrets("token=aaaaaaaaaaaabbbbCCCCDDDD end", env)
    assert "CCCCDDDD" not in out, "tail of the longer secret survived"


# ── shape-based patterns (secrets that never came from env_vars) ─────────────

@pytest.mark.parametrize("text,leak", [
    ("POST https://api.telegram.org/bot9998887776:BBB_otherToken_zzzzzzzzzzzz/send",
     "BBB_otherToken_zzzzzzzzzzzz"),
    ("key eyJhbGciOiJIUzI1NiJ9.OTHERPAYLOAD_cccccc.OTHERSIG_dddddd rejected",
     "OTHERSIG_dddddd"),
    ("charge failed for sk_live_51ZzYyXxWwVvUuTtSs", "sk_live_51ZzYyXxWwVvUuTtSs"),
    ("psql postgres://svc:n0tTh3P4ssw0rd@db.internal:5432/app", "n0tTh3P4ssw0rd"),
    ("Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345", "abcdefghijklmnopqrstuvwxyz012345"),
])
def test_unknown_secrets_are_caught_by_shape(text, leak):
    """A token the model never saw in .env.agents still must not reach disk."""
    out = redact_secrets(text, {})
    assert leak not in out, f"leaked: {out}"


def test_prose_after_a_credential_word_is_not_shredded():
    """The >=20-char token-charset floor is what keeps ordinary sentences
    readable — over-redaction makes a dump useless, which is its own failure."""
    text = "Authorization: administrator privileges are required for this token check"
    assert redact_secrets(text, {}) == text


def test_db_url_keeps_its_shape_for_debugging():
    out = redact_secrets("postgres://svc:n0tTh3P4ssw0rd@db.internal:5432/app", {})
    assert "postgres://svc:" in out and "@db.internal:5432/app" in out


# ── robustness: a redaction failure must never swallow the diagnostic ────────

def test_empty_and_none_are_safe():
    assert redact_secrets("", FAKE_ENV) == ""
    assert redact_secrets(None, FAKE_ENV) is None  # type: ignore[arg-type]


def test_no_env_still_applies_shape_patterns():
    out = redact_secrets("bot1234567890:AAA_tok_eeeeeeeeeeeeeeee", None)
    assert "AAA_tok_eeeeeeeeeeeeeeee" not in out


def test_non_string_env_values_do_not_crash():
    out = redact_secrets("hello", {"A": None, "B": 12345, "C": "x" * 20})  # type: ignore[dict-item]
    assert out == "hello"


def test_realistic_traceback_end_to_end():
    text = (
        "Traceback (most recent call last):\n"
        '  File "scripts/x.py", line 9, in <module>\n'
        f"    supabase.create_client(url, '{FAKE_ENV['BRAVO_SUPABASE_SERVICE_ROLE_KEY']}')\n"
        f"requests.exceptions.HTTPError: 401 for "
        f"https://api.telegram.org/bot{FAKE_ENV['TELEGRAM_BOT_TOKEN']}/sendMessage\n"
    )
    out = redact_secrets(text, FAKE_ENV)
    for secret in (FAKE_ENV["BRAVO_SUPABASE_SERVICE_ROLE_KEY"],
                   FAKE_ENV["TELEGRAM_BOT_TOKEN"]):
        assert secret not in out
    # The diagnostic value must survive redaction, or the dump is useless.
    assert "Traceback (most recent call last):" in out
    assert "line 9" in out
    assert "401" in out
