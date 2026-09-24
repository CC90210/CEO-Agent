"""Regression coverage for the globally installed OASIS CLI launchers."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_windows_installer_generates_module_based_shims() -> None:
    installer = (REPO_ROOT / "install.ps1").read_text(encoding="utf-8-sig")

    assert 'pushd "$WizardRepo"' in installer
    assert '"$venvPy" -m bravo_cli.main %*' in installer
    assert '& $venvPy -m bravo_cli.main \'setup\'' in installer
    assert '"$venvPy" "$wizardEntry" %*' not in installer
    assert '& $venvPy $wizardEntry \'setup\'' not in installer


def test_windows_installer_is_syntactically_valid() -> None:
    if os.name != "nt":
        return

    installer_path = str(REPO_ROOT / "install.ps1").replace("'", "''")
    parse_command = (
        "$source=[IO.File]::ReadAllText('"
        + installer_path
        + "',[Text.UTF8Encoding]::new($false));"
        "$tokens=$null;$errors=$null;"
        "[Management.Automation.Language.Parser]::ParseInput("
        "$source,[ref]$tokens,[ref]$errors)|Out-Null;"
        "if($errors.Count){$errors|ForEach-Object{$_.Message};exit 1}"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", parse_command],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_unix_installer_generates_module_based_shims() -> None:
    installer = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")

    assert 'cd "$WIZARD_REPO"' in installer
    assert 'exec "$VENV_PY" -m bravo_cli.main "\\$@"' in installer
    assert '"$VENV_PY" -m bravo_cli.main setup' in installer
    assert 'exec "$VENV_PY" "$WIZARD_ENTRY" "\\$@"' not in installer
    assert '"$VENV_PY" "$WIZARD_ENTRY" setup' not in installer


def test_module_launcher_boots_when_invoked_outside_repo(tmp_path: Path) -> None:
    """Model the generated launcher from a caller whose cwd is unrelated."""

    if os.name == "nt":
        launcher = tmp_path / "oasis-test.cmd"
        launcher.write_text(
            "@echo off\r\n"
            f'pushd "{REPO_ROOT}"\r\n'
            f'"{sys.executable}" -m bravo_cli.main %*\r\n'
            'set "OASIS_EXIT_CODE=%ERRORLEVEL%"\r\n'
            "popd\r\n"
            "exit /b %OASIS_EXIT_CODE%\r\n",
            encoding="ascii",
        )
        command = ["cmd.exe", "/d", "/c", str(launcher), "bridge", "--help"]
    else:
        launcher = tmp_path / "oasis-test"
        launcher.write_text(
            "#!/usr/bin/env bash\n"
            f'cd "{REPO_ROOT}"\n'
            f'exec "{sys.executable}" -m bravo_cli.main "$@"\n',
            encoding="utf-8",
        )
        launcher.chmod(0o755)
        command = [str(launcher), "bridge", "--help"]

    outside_cwd = tmp_path / "outside"
    outside_cwd.mkdir()
    result = subprocess.run(
        command,
        cwd=outside_cwd,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "usage: bravo bridge" in result.stdout
