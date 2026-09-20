"""turso_tool `sql --dangerous-write` executes, COMMITS and counts.

The write door went through db.query(), the READ path. libsql answers
fetchall() with None for a statement that returns no rows, so an UPDATE died
with "'NoneType' object is not iterable". query() also never commits, so a
write that survived the crash would still have been rolled back at exit.

These run the real CLI handler against a local libSQL file and check the result
from a SECOND connection. A write read back through the connection that made it
proves nothing: that connection sees its own uncommitted transaction
(pattern_turso_execute_does_not_commit).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

libsql = pytest.importorskip("libsql")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from integrations import turso_tool as tt  # noqa: E402


@pytest.fixture
def db_file(tmp_path):
    path = tmp_path / "widgets.db"
    conn = libsql.connect(str(path))
    conn.execute("CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO widgets (name) VALUES ('a'), ('b'), ('c')")
    conn.commit()
    return path


def _run(db_file, *argv) -> int:
    # Flags go AFTER the subcommand: the subparser re-applies its own defaults.
    args = tt.build_parser().parse_args(
        ["sql", *argv, "--db-path", str(db_file), "--json"])
    return tt.cmd_sql(args)


def _committed(db_file) -> dict:
    """What a fresh connection sees, which is only what was committed."""
    conn = libsql.connect(str(db_file))
    return dict(conn.execute("SELECT id, name FROM widgets ORDER BY id").fetchall())


def test_an_update_commits_and_reports_the_rows_it_changed(db_file, capsys):
    assert _run(db_file, "UPDATE widgets SET name = 'z' WHERE id = 2",
                "--dangerous-write") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and out["committed"] is True
    assert out["affected"] == 1
    assert _committed(db_file) == {1: "a", 2: "z", 3: "c"}


def test_a_delete_reports_every_row_it_removed(db_file, capsys):
    assert _run(db_file, "DELETE FROM widgets WHERE id IN (1, 3)",
                "--dangerous-write") == 0
    assert json.loads(capsys.readouterr().out)["affected"] == 2
    assert _committed(db_file) == {2: "b"}


def test_a_write_that_matches_nothing_says_zero_not_unknown(db_file, capsys):
    assert _run(db_file, "UPDATE widgets SET name = 'z' WHERE id = 99",
                "--dangerous-write") == 0
    assert json.loads(capsys.readouterr().out)["affected"] == 0


def test_parameters_reach_the_write(db_file, capsys):
    assert _run(db_file, "UPDATE widgets SET name = ? WHERE name = ?",
                "--param", "p", "--param", "a", "--dangerous-write") == 0
    assert json.loads(capsys.readouterr().out)["affected"] == 1
    assert _committed(db_file)[1] == "p"


def test_returning_rows_are_reported_and_the_write_still_commits(db_file, capsys):
    assert _run(db_file, "UPDATE widgets SET name = 'r' WHERE id = 3 RETURNING id, name",
                "--dangerous-write") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["rows"] == [{"id": 3, "name": "r"}]
    assert _committed(db_file)[3] == "r"


def test_a_write_without_the_flag_is_still_refused_and_changes_nothing(db_file, capsys):
    assert _run(db_file, "UPDATE widgets SET name = 'z' WHERE id = 2") == 1
    assert json.loads(capsys.readouterr().out)["kind"] == "write_blocked"
    assert _committed(db_file)[2] == "b"


def test_reads_are_unchanged(db_file, capsys):
    assert _run(db_file, "SELECT name FROM widgets WHERE id = 1") == 0
    assert json.loads(capsys.readouterr().out) == {
        "ok": True, "count": 1, "rows": [{"name": "a"}]}
