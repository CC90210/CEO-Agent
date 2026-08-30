"""Provisioning tool tests — safety refusals must not depend on machine state.

turso_admin is the only piece of the Turso migration that touches the cloud, and
the only one that handles a live database token. Two properties matter more than
its happy path: a destructive command must be refused on its own terms, and a
minted token must never reach stdout (which is the agent's context and the
session transcript).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from integrations import turso_admin as ta  # noqa: E402


class Args:
    def __init__(self, **kw):
        self.json = False
        self.__dict__.update(kw)


# ------------------------------------------------------------------ registry

def test_every_database_has_a_url_and_token_var():
    assert set(ta.EMPIRE_DATABASES) == set(ta.TOKEN_VAR)
    for name, url_var in ta.EMPIRE_DATABASES.items():
        assert url_var.endswith("DATABASE_URL")
        assert ta.TOKEN_VAR[name].endswith("AUTH_TOKEN")


def test_one_database_per_supabase_project():
    """Breeze holds merchant bank data — it must not share a database."""
    assert ta.EMPIRE_DATABASES.keys() == {
        "bravo-empire", "breeze-portal", "nostalgic-requests", "propflow", "oasis-platform"}


def test_bravo_uses_the_canonical_env_var_db_turso_reads():
    from lib import db_turso  # noqa: PLC0415

    url, token, mode = db_turso.resolve_target(
        {ta.EMPIRE_DATABASES["bravo-empire"]: "libsql://x", "TURSO_AUTH_TOKEN": "t"})
    assert url == "libsql://x", "turso_admin must write the var db_turso actually reads"


# ------------------------------------------------- safety refusals (no creds)

def test_destroy_refuses_mismatched_confirmation_without_needing_credentials(capsys):
    rc = ta.cmd_destroy(Args(db="bravo-empire", confirm="bravo"))
    assert rc == 2
    assert "REFUSED" in capsys.readouterr().err


def test_destroy_refusal_does_not_depend_on_configuration(monkeypatch, capsys):
    """Even fully configured, a mismatched confirm must still refuse."""
    monkeypatch.setattr(ta, "_creds", lambda: ("platform-token", "org"))
    rc = ta.cmd_destroy(Args(db="bravo-empire", confirm="typo"))
    assert rc == 2
    assert "REFUSED" in capsys.readouterr().err


def test_token_refuses_to_print_to_stdout(capsys):
    rc = ta.cmd_token(Args(db="bravo-empire", write_env=False))
    assert rc == 2
    assert "Refusing to print" in capsys.readouterr().err


def test_token_rejects_unknown_database(capsys):
    rc = ta.cmd_token(Args(db="not-a-db", write_env=True))
    assert rc == 2
    assert "unknown empire database" in capsys.readouterr().err


# --------------------------------------------------------- credential guidance

def test_missing_credentials_names_both_keys_and_the_fix(monkeypatch):
    monkeypatch.setattr(ta, "load_env", lambda: {})
    with pytest.raises(ta.NotConfigured) as exc:
        ta._creds()
    msg = str(exc.value)
    assert "TURSO_PLATFORM_TOKEN" in msg and "TURSO_ORG" in msg
    assert "api-tokens mint" in msg
    # The distinction that actually blocked this migration must be spelled out.
    assert "TURSO_API_KEY is NOT this credential" in msg


def test_platform_token_alone_is_not_enough(monkeypatch):
    monkeypatch.setattr(ta, "load_env", lambda: {"TURSO_PLATFORM_TOKEN": "t"})
    with pytest.raises(ta.NotConfigured, match="TURSO_ORG"):
        ta._creds()


# ------------------------------------------------------------- env file write

def test_write_env_returns_key_names_only_never_values(tmp_path, monkeypatch):
    env = tmp_path / ".env.agents"
    env.write_text("EXISTING=keep\n", encoding="utf-8")
    monkeypatch.setattr(ta, "ENV_FILE", env)

    written = ta._write_env({"TURSO_DATABASE_URL": "libsql://h",
                             "TURSO_AUTH_TOKEN": "super-secret-jwt"})

    assert written == ["TURSO_AUTH_TOKEN", "TURSO_DATABASE_URL"]
    assert "super-secret-jwt" not in " ".join(written), "return value must not carry secrets"
    body = env.read_text(encoding="utf-8")
    assert "EXISTING=keep" in body, "unrelated keys must survive"
    assert "TURSO_AUTH_TOKEN=super-secret-jwt" in body


def test_write_env_replaces_rather_than_duplicating(tmp_path, monkeypatch):
    env = tmp_path / ".env.agents"
    env.write_text("TURSO_AUTH_TOKEN=old\nOTHER=x\n", encoding="utf-8")
    monkeypatch.setattr(ta, "ENV_FILE", env)

    ta._write_env({"TURSO_AUTH_TOKEN": "new"})

    body = env.read_text(encoding="utf-8")
    assert body.count("TURSO_AUTH_TOKEN=") == 1, "a rotated token must not leave a stale duplicate"
    assert "TURSO_AUTH_TOKEN=new" in body
    assert "OTHER=x" in body


def test_write_env_creates_the_file_when_absent(tmp_path, monkeypatch):
    env = tmp_path / ".env.agents"
    monkeypatch.setattr(ta, "ENV_FILE", env)
    ta._write_env({"TURSO_ORG": "cc"})
    assert "TURSO_ORG=cc" in env.read_text(encoding="utf-8")


# ---------------------------------------------------------------- API errors

def test_401_explains_the_token_type_confusion(monkeypatch):
    class R:
        status_code = 401
        text = "unauthorized"
        content = b"x"

    monkeypatch.setattr(ta.requests, "request", lambda *a, **k: R())
    with pytest.raises(ta.TursoAPIError, match="DATABASE token, not a Platform API token"):
        ta._call("GET", "/v1/organizations/x/databases", "tok")
