"""Maven env regeneration must not silently discard existing credentials."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_maven_env as tool  # noqa: E402


def _configure(tmp_path: Path, monkeypatch, *, allow_drop: bool) -> tuple[Path, Path]:
    bravo = tmp_path / "bravo.env"
    maven = tmp_path / "maven.env"
    bravo.write_text("ANTHROPIC_API_KEY=shared-synthetic\n", encoding="utf-8")
    maven.write_text(
        "ANTHROPIC_API_KEY=maven-synthetic\n"
        "UNLISTED_PLUGIN_TOKEN=preserve-this-synthetic-value\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tool, "BRAVO_ENV", bravo)
    monkeypatch.setattr(tool, "MAVEN_ENV", maven)
    monkeypatch.setattr(tool, "DRY_RUN", False)
    monkeypatch.setattr(tool, "ALLOW_DROP_UNKNOWN", allow_drop, raising=False)
    return bravo, maven


def test_apply_preserves_unknown_existing_keys_by_default(tmp_path, monkeypatch):
    _, maven = _configure(tmp_path, monkeypatch, allow_drop=False)

    tool.main()

    written = tool.parse_env(maven)
    assert written["UNLISTED_PLUGIN_TOKEN"] == "preserve-this-synthetic-value"


def test_explicit_drop_override_reports_key_only_manifest(
    tmp_path, monkeypatch, capsys
):
    _, maven = _configure(tmp_path, monkeypatch, allow_drop=True)

    tool.main()

    output = capsys.readouterr().out
    written = tool.parse_env(maven)
    assert "UNLISTED_PLUGIN_TOKEN" not in written
    assert "UNLISTED_PLUGIN_TOKEN" in output
    assert "preserve-this-synthetic-value" not in output
