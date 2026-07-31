"""Fail-closed write-mode tests for client-specific Google Sheet tools."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _load(name: str):
    sys.path.insert(0, str(SCRIPTS))
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_consolidation_defaults_to_no_writes(monkeypatch):
    module = _load("consolidate_mca_phone_sheet")
    monkeypatch.setattr(module, "gread", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        module,
        "build_outputs",
        lambda *_args: ([[]], [[]], {"rows": 0}),
    )
    writes: list[tuple] = []
    monkeypatch.setattr(
        module, "write_chunks", lambda *args, **kwargs: writes.append((args, kwargs))
    )
    monkeypatch.setattr(sys, "argv", ["consolidate_mca_phone_sheet.py", "--sample", "0"])

    assert module.main() == 0
    assert writes == []


def test_consolidation_requires_apply_for_writes(monkeypatch):
    module = _load("consolidate_mca_phone_sheet")
    monkeypatch.setattr(module, "gread", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        module,
        "build_outputs",
        lambda *_args: ([[]], [[]], {"rows": 0}),
    )
    writes: list[tuple] = []
    monkeypatch.setattr(
        module, "write_chunks", lambda *args, **kwargs: writes.append((args, kwargs))
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["consolidate_mca_phone_sheet.py", "--apply", "--sample", "0"],
    )

    assert module.main() == 0
    assert len(writes) == 2


def test_consolidation_requires_explicit_pii_output_for_samples(monkeypatch):
    module = _load("consolidate_mca_phone_sheet")
    monkeypatch.setattr(sys, "argv", ["consolidate_mca_phone_sheet.py", "--sample", "1"])

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert exc.value.code == 2


def test_enrichment_defaults_to_no_sheet_or_checkpoint_writes(monkeypatch, tmp_path, capsys):
    module = _load("enrich_sheet_inplace")
    monkeypatch.setattr(module, "CKPT", tmp_path / "checkpoint.json")
    monkeypatch.setattr(
        module,
        "read_leads",
        lambda *_args: [{"row": 2, "business": "Fixture Co", "address": "", "owner": ""}],
    )
    monkeypatch.setattr(
        module,
        "enrich_one",
        lambda *_args: {"business_match": True, "phone": "2125550100", "email": None},
    )
    writes: list[tuple] = []
    monkeypatch.setattr(
        module, "write_row", lambda *args, **kwargs: writes.append((args, kwargs))
    )
    from lib import claude_cli

    monkeypatch.setattr(claude_cli, "run_claude_cli", lambda *_args, **_kwargs: "ok")
    monkeypatch.setattr(
        sys, "argv", ["enrich_sheet_inplace.py", "--workers", "1", "--limit", "1"]
    )

    assert module.main() == 0
    assert writes == []
    assert not module._checkpoint_path(module.DEFAULT_SHEET_ID, module.DEFAULT_TAB).exists()
    output = capsys.readouterr().out
    assert "Fixture Co" not in output
    assert "212-555-0100" not in output
    assert module.DEFAULT_SHEET_ID not in output


def test_enrichment_apply_writes_and_checkpoints(monkeypatch, tmp_path):
    module = _load("enrich_sheet_inplace")
    monkeypatch.setattr(module, "CKPT", tmp_path / "checkpoint.json")
    monkeypatch.setattr(
        module,
        "read_leads",
        lambda *_args: [{"row": 2, "business": "Fixture Co", "address": "", "owner": ""}],
    )
    monkeypatch.setattr(
        module,
        "enrich_one",
        lambda *_args: {"business_match": True, "phone": "2125550100", "email": None},
    )
    writes: list[tuple] = []
    monkeypatch.setattr(
        module, "write_row", lambda *args, **kwargs: writes.append((args, kwargs))
    )
    from lib import claude_cli

    monkeypatch.setattr(claude_cli, "run_claude_cli", lambda *_args, **_kwargs: "ok")
    monkeypatch.setattr(
        sys,
        "argv",
        ["enrich_sheet_inplace.py", "--apply", "--workers", "1", "--limit", "1"],
    )

    assert module.main() == 0
    assert len(writes) == 1
    assert module._checkpoint_path(module.DEFAULT_SHEET_ID, module.DEFAULT_TAB).exists()


def test_enrichment_apply_does_not_write_or_checkpoint_failed_rows(monkeypatch, tmp_path):
    module = _load("enrich_sheet_inplace")
    monkeypatch.setattr(module, "CKPT", tmp_path / "checkpoint.json")
    monkeypatch.setattr(
        module,
        "read_leads",
        lambda *_args: [{"row": 2, "business": "Fixture Co", "address": "", "owner": ""}],
    )
    monkeypatch.setattr(
        module,
        "enrich_one",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("fixture failure")),
    )
    writes: list[tuple] = []
    monkeypatch.setattr(
        module, "write_row", lambda *args, **kwargs: writes.append((args, kwargs))
    )
    from lib import claude_cli

    monkeypatch.setattr(claude_cli, "run_claude_cli", lambda *_args, **_kwargs: "ok")
    monkeypatch.setattr(
        sys,
        "argv",
        ["enrich_sheet_inplace.py", "--apply", "--workers", "1", "--limit", "1"],
    )

    assert module.main() == 1
    assert writes == []
    assert not module._checkpoint_path(module.DEFAULT_SHEET_ID, module.DEFAULT_TAB).exists()


def test_enrichment_write_row_never_writes_blank_cells(monkeypatch):
    module = _load("enrich_sheet_inplace")
    calls: list[list[str]] = []
    monkeypatch.setattr(module, "_gtool", lambda args: calls.append(args) or 0)

    written = module.write_row(
        7,
        {"business_match": True, "phone": "2125550100", "email": None},
        "sheet",
        "Leads",
    )

    assert written == 1
    assert len(calls) == 1
    assert "Leads!I7" in calls[0]
    assert all('""' not in arg for arg in calls[0])


def test_enrichment_rejects_private_fetch_targets_before_launch(monkeypatch):
    module = _load("enrich_sheet_inplace")
    launches: list[object] = []
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: launches.append(object()),
    )

    assert module._render("http://127.0.0.1:9999/private") is None
    assert module._render("http://[::1]/private") is None
    assert launches == []


def test_enrichment_rejects_unsafe_final_redirect(monkeypatch):
    module = _load("enrich_sheet_inplace")

    class Result:
        returncode = 0
        stdout = '{"ok": true, "text": "private", "final_url": "http://127.0.0.1/private"}'
        stderr = ""

    monkeypatch.setattr(module, "_is_public_http_url", lambda _url: True)
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: Result())

    assert module._render("https://www.bing.com/search?q=fixture") is None


def test_enrichment_fetch_and_model_outages_raise_for_retry(monkeypatch):
    module = _load("enrich_sheet_inplace")
    monkeypatch.setattr(module, "_render", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="search fetch"):
        module.enrich_one("Fixture", "Toronto", "Owner")

    monkeypatch.setattr(module, "_render", lambda *_args, **_kwargs: "x" * 500)
    monkeypatch.setattr(module, "_ask", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="model extraction"):
        module.enrich_one("Fixture", "Toronto", "Owner")


def test_enrichment_supplemental_fetch_outage_raises_for_retry(monkeypatch):
    module = _load("enrich_sheet_inplace")
    responses = iter(["x" * 500, None])
    monkeypatch.setattr(module, "_render", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(
        module,
        "_ask",
        lambda *_args, **_kwargs: {
            "business_match": True,
            "official_url": "https://fixture.example",
            "phone": None,
            "email": None,
        },
    )
    monkeypatch.setattr(
        module,
        "_official_site_search_url",
        lambda *_args, **_kwargs: "https://www.bing.com/search?q=fixture",
    )

    with pytest.raises(RuntimeError, match="supplemental search fetch"):
        module.enrich_one("Fixture", "Toronto", "Owner")


def test_enrichment_empty_supplemental_content_raises_for_retry(monkeypatch):
    module = _load("enrich_sheet_inplace")
    responses = iter(["x" * 500, ""])
    monkeypatch.setattr(module, "_render", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(
        module,
        "_ask",
        lambda *_args, **_kwargs: {
            "business_match": True,
            "official_url": "https://fixture.example",
            "phone": None,
            "email": None,
        },
    )
    monkeypatch.setattr(
        module,
        "_official_site_search_url",
        lambda *_args, **_kwargs: "https://www.bing.com/search?q=fixture",
    )

    with pytest.raises(RuntimeError, match="no usable content"):
        module.enrich_one("Fixture", "Toronto", "Owner")


def test_enrichment_invalid_supplemental_schema_raises_for_retry(monkeypatch):
    module = _load("enrich_sheet_inplace")
    responses = iter(["x" * 500, "y" * 500])
    extractions = iter([
        {
            "business_match": True,
            "official_url": "https://fixture.example",
            "phone": None,
            "email": None,
        },
        {},
    ])
    monkeypatch.setattr(module, "_render", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(module, "_ask", lambda *_args, **_kwargs: next(extractions))
    monkeypatch.setattr(
        module,
        "_official_site_search_url",
        lambda *_args, **_kwargs: "https://www.bing.com/search?q=fixture",
    )

    with pytest.raises(RuntimeError, match="no valid result"):
        module.enrich_one("Fixture", "Toronto", "Owner")


def test_enrichment_checkpoints_are_namespaced_by_sheet_and_tab(tmp_path, monkeypatch):
    module = _load("enrich_sheet_inplace")
    monkeypatch.setattr(module, "CKPT", tmp_path / "checkpoint.json")

    first = module._checkpoint_path("sheet-a", "Leads")
    second = module._checkpoint_path("sheet-b", "Leads")
    third = module._checkpoint_path("sheet-a", "Other")

    assert len({first, second, third}) == 3
