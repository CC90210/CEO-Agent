"""Regression tests for the post-Supabase Python data-plane boundary."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest import mock

import pytest


REPO = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO / "scripts" / "_bootstrap" / "sitecustomize.py"
ECOSYSTEM = REPO / "ecosystem.config.js"
TURSO = "turso_cloud"
ROLLBACK = "legacy_supabase_rollback"


def _load_bootstrap():
    """Load helpers without applying the default Turso patch to this test run."""
    spec = importlib.util.spec_from_file_location(
        "_empire_switch_fail_closed_test", BOOTSTRAP)
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(
        os.environ,
        {"EMPIRE_DATA_BACKEND": ROLLBACK},
        clear=False,
    ):
        spec.loader.exec_module(module)
    return module


@pytest.fixture()
def bootstrap():
    return _load_bootstrap()


def test_unset_backend_installs_turso_by_default(bootstrap, monkeypatch):
    monkeypatch.delenv("EMPIRE_DATA_BACKEND", raising=False)
    install = mock.Mock()
    monkeypatch.setattr(bootstrap, "_install", install)

    assert bootstrap._activate() == TURSO
    install.assert_called_once_with()


def test_explicit_legacy_rollback_is_the_only_mode_that_skips_patch(
    bootstrap, monkeypatch,
):
    monkeypatch.setenv("EMPIRE_DATA_BACKEND", ROLLBACK)
    install = mock.Mock()
    monkeypatch.setattr(bootstrap, "_install", install)

    assert bootstrap._activate() == ROLLBACK
    install.assert_not_called()


@pytest.mark.parametrize("backend", ["supabase", "supabase_cloud", "turso_local", "typo"])
def test_old_or_unknown_backend_names_stop_startup(bootstrap, monkeypatch, backend):
    monkeypatch.setenv("EMPIRE_DATA_BACKEND", backend)
    recorded = mock.Mock()
    monkeypatch.setattr(bootstrap, "_record_failure", recorded)

    with pytest.raises(SystemExit, match="startup blocked"):
        bootstrap._activate()

    recorded.assert_called_once()


def test_patch_failure_uses_system_exit_so_pth_loader_cannot_swallow_it(
    bootstrap, monkeypatch,
):
    monkeypatch.setenv("EMPIRE_DATA_BACKEND", TURSO)
    fault = RuntimeError("compat import failed")
    monkeypatch.setattr(bootstrap, "_install", mock.Mock(side_effect=fault))
    recorded = mock.Mock()
    monkeypatch.setattr(bootstrap, "_record_failure", recorded)

    # site.py catches Exception while processing .pth files. SystemExit derives
    # directly from BaseException, so this is what makes startup fail closed.
    with pytest.raises(SystemExit, match="no silent Supabase fallback"):
        bootstrap._activate()

    recorded.assert_called_once_with(fault)


def test_diagnostic_probe_does_not_create_a_false_incident_marker(
    bootstrap, monkeypatch,
):
    monkeypatch.setenv("EMPIRE_TURSO_SWITCH_PROBE", "1")
    with mock.patch("pathlib.Path.write_text") as write_text:
        bootstrap._record_failure(RuntimeError("deliberate probe fault"))
    write_text.assert_not_called()


def _load_ecosystem(backend: str | None) -> subprocess.CompletedProcess:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required to execute the PM2 ecosystem config")
    env = dict(os.environ)
    if backend is None:
        env.pop("EMPIRE_DATA_BACKEND", None)
    else:
        env["EMPIRE_DATA_BACKEND"] = backend
    probe = (
        "const cfg=require(process.argv[1]);"
        "console.log(JSON.stringify(cfg.apps.map(a=>({"
        "name:a.name,backend:a.env.EMPIRE_DATA_BACKEND,"
        "required:a.env.EMPIRE_TURSO_PATCH_REQUIRED}))));"
    )
    return subprocess.run(
        [node, "-e", probe, str(ECOSYSTEM)],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_bare_pm2_config_stamps_every_daemon_turso_fail_closed():
    result = _load_ecosystem(None)
    assert result.returncode == 0, result.stderr
    apps = json.loads(result.stdout.strip().splitlines()[-1])
    assert apps, "ecosystem exported no daemons"
    assert all(app["backend"] == TURSO for app in apps), apps
    assert all(app["required"] == "1" for app in apps), apps


def test_pm2_config_allows_only_the_explicit_legacy_rollback():
    rollback = _load_ecosystem(ROLLBACK)
    assert rollback.returncode == 0, rollback.stderr
    apps = json.loads(rollback.stdout.strip().splitlines()[-1])
    assert all(app["backend"] == ROLLBACK for app in apps), apps
    assert all(app["required"] == "0" for app in apps), apps

    old_mode = _load_ecosystem("supabase")
    assert old_mode.returncode != 0
    assert "Invalid EMPIRE_DATA_BACKEND" in old_mode.stderr
