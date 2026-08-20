from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_STATE = Path(__file__).resolve().parents[1] / "state"
if str(SCRIPTS_STATE) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_STATE))

import state_sync as ss  # noqa: E402


def _fm(date: str) -> str:
    return (
        "---\n"
        "tags: [daily]\n"
        f"last_updated: {date}\n"
        "freshness_threshold_days: 14\n"
        "---\n"
    )


def test_normalize_session_log_collapses_repeated_frontmatter_without_losing_entries():
    original = _fm("2026-08-11") + _fm("2026-08-08") + "\n### 2026-08-20 — Keep me\nBody\n"

    normalized, removed = ss.normalize_session_log_frontmatter(original, "2026-08-20")

    assert removed == 1
    assert normalized.count("tags: [daily]") == 1
    assert "last_updated: 2026-08-20" in normalized
    assert "### 2026-08-20 — Keep me\nBody" in normalized


def test_append_session_log_repairs_frontmatter_before_append(tmp_path, monkeypatch):
    path = tmp_path / "SESSION_LOG.md"
    path.write_text(_fm("2026-08-11") * 3 + "\n### old\nold body\n", encoding="utf-8")
    monkeypatch.setattr(ss, "SESSION_LOG", path)
    monkeypatch.setattr(ss, "now_str", lambda: "2026-08-20")

    assert ss.append_session_log("new note", "bravo") == "appended"

    result = path.read_text(encoding="utf-8")
    assert result.count("tags: [daily]") == 1
    assert "### old\nold body" in result
    assert "**Note:** new note" in result


def test_explicit_repair_is_atomic_and_preserves_entry_count(tmp_path, monkeypatch):
    path = tmp_path / "SESSION_LOG.md"
    path.write_text(
        _fm("2026-08-11") * 4
        + "\n### 2026-08-19 — first\nBody\n"
        + "\n### 2026-08-20 — second\nBody\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ss, "now_str", lambda: "2026-08-20")

    removed, preserved = ss.repair_session_log_frontmatter(path)

    assert (removed, preserved) == (3, 2)
    repaired = path.read_text(encoding="utf-8")
    assert repaired.count("tags: [daily]") == 1
    assert not path.with_suffix(".md.repair.tmp").exists()


def test_append_session_log_repairs_frontmatter_even_when_note_is_deduped(tmp_path, monkeypatch):
    path = tmp_path / "SESSION_LOG.md"
    existing = (
        _fm("2026-08-11")
        + _fm("2026-08-08")
        + "\n### 2026-08-20 — Auto-sync\n"
        + "**Agent:** BRAVO state_sync\n"
        + "**Note:** same note\n"
    )
    path.write_text(existing, encoding="utf-8")
    monkeypatch.setattr(ss, "SESSION_LOG", path)
    monkeypatch.setattr(ss, "now_str", lambda: "2026-08-20")

    assert ss.append_session_log("same note", "bravo") == "deduped"

    result = path.read_text(encoding="utf-8")
    assert result.count("tags: [daily]") == 1
    assert result.count("**Note:** same note") == 1


def test_resolve_v6_mode_defaults_to_shadow_without_runtime_specific_env(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("EMPIRE_V6_MODE", raising=False)

    assert ss._resolve_v6_mode(None) == "shadow"


def test_resolve_v6_mode_precedence_is_cli_then_env_then_env_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".env.agents").write_text("EMPIRE_V6_MODE=off\n", encoding="utf-8")
    monkeypatch.setenv("EMPIRE_V6_MODE", "on")

    assert ss._resolve_v6_mode("shadow") == "shadow"
    assert ss._resolve_v6_mode(None) == "on"

    monkeypatch.delenv("EMPIRE_V6_MODE")
    assert ss._resolve_v6_mode(None) == "off"


def test_resolve_v6_mode_blank_env_file_value_uses_shadow_default(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".env.agents").write_text("EMPIRE_V6_MODE=\n", encoding="utf-8")
    monkeypatch.delenv("EMPIRE_V6_MODE", raising=False)

    assert ss._resolve_v6_mode(None) == "shadow"
