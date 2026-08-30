from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

SCRIPTS_CORE = Path(__file__).resolve().parents[1] / "core"
if str(SCRIPTS_CORE) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_CORE))

import memory_aging as ma  # noqa: E402


def _frontmatter(last_updated: str = "2026-08-20") -> str:
    return (
        "---\n"
        "tags: [daily]\n"
        f"last_updated: {last_updated}\n"
        "freshness_threshold_days: 14\n"
        "---\n"
    )


def _long_entry(entry_date: str, title: str) -> str:
    body = "".join(f"line {index}\n" for index in range(205))
    return f"### {entry_date} — {title}\n{body}"


def _configure_temp_log(tmp_path: Path, monkeypatch, content: str) -> Path:
    memory = tmp_path / "memory"
    memory.mkdir()
    log = memory / "SESSION_LOG.md"
    log.write_text(content, encoding="utf-8")
    monkeypatch.setattr(ma, "ROOT", tmp_path)
    monkeypatch.setattr(ma, "TODAY", date(2026, 8, 20))
    return log


def test_archive_preserves_header_once_and_is_idempotent(tmp_path, monkeypatch):
    recent = "### 2026-08-19 — Recent\nkeep me\n"
    log = _configure_temp_log(
        tmp_path,
        monkeypatch,
        _frontmatter() + _long_entry("2026-07-01", "Old") + recent,
    )

    actions = ma._archive_session_log(dry_run=False)

    result = log.read_text(encoding="utf-8")
    archive = tmp_path / "memory" / "ARCHIVES" / "sessions-2026-07.md"
    archived_once = archive.read_text(encoding="utf-8")
    assert result.count("tags: [daily]") == 1
    assert "### 2026-07-01 — Old" not in result
    assert recent in result
    assert archived_once.count("### 2026-07-01 — Old") == 1
    assert actions[-1]["detail"] == "Kept 1 recent session(s), archived 1 old session(s)"

    assert ma._archive_session_log(dry_run=False) == []
    assert log.read_text(encoding="utf-8") == result
    assert archive.read_text(encoding="utf-8") == archived_once


def test_archive_rewrites_source_when_every_dated_entry_is_old(tmp_path, monkeypatch):
    header = _frontmatter()
    log = _configure_temp_log(
        tmp_path,
        monkeypatch,
        header + _long_entry("2026-07-01", "Only old entry"),
    )

    ma._archive_session_log(dry_run=False)

    assert log.read_text(encoding="utf-8") == header
    assert ma._archive_session_log(dry_run=False) == []


def test_archive_never_multiplies_preexisting_duplicate_headers(tmp_path, monkeypatch):
    log = _configure_temp_log(
        tmp_path,
        monkeypatch,
        _frontmatter("2026-08-11")
        + _frontmatter("2026-08-08")
        + _long_entry("2026-07-01", "Old"),
    )

    ma._archive_session_log(dry_run=False)

    # Repair is intentionally owned by state_sync; memory aging must at least
    # stop making an already-corrupt file exponentially worse.
    assert log.read_text(encoding="utf-8").count("tags: [daily]") == 2

