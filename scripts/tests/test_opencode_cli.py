"""test_opencode_cli.py — unit tests for scripts/lib/opencode_cli.py.

Tests the OpenCode CLI wrapper's binary resolution (native exe only — npm
.cmd/.ps1 shims are REJECTED), output cleaning (ANSI / banner / status
header), tier model mapping, and (mocked) subprocess execution.

SECURITY CONTRACT under test:
  - the prompt NEVER appears in argv (it travels via stdin);
  - no shell is used (subprocess.run must not receive shell=True);
  - every call runs as the restricted bravo-oneshot agent.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.opencode_cli import (  # noqa: E402
    OPENCODE_AGENT,
    TIER_MODELS,
    _clean_output,
    _is_directly_executable,
    model_for_task,
    resolve_opencode_bin,
    run_opencode_cli,
)


# ── model_for_task ──────────────────────────────────────────────────────────

class TestModelForTask:
    def test_reasoning_returns_big_pickle(self):
        assert model_for_task("reasoning") == "opencode/big-pickle"

    def test_closing_returns_big_pickle(self):
        assert model_for_task("closing") == "opencode/big-pickle"

    def test_fast_returns_nemotron(self):
        assert model_for_task("fast") == "opencode/nemotron-3.5-lightning-free"

    def test_classify_returns_nemotron(self):
        assert model_for_task("classify") == "opencode/nemotron-3.5-lightning-free"

    def test_default_returns_big_pickle(self):
        assert model_for_task("default") == "opencode/big-pickle"

    def test_unknown_falls_to_default(self):
        assert model_for_task("nonexistent_tier") == "opencode/big-pickle"


# ── binary resolution ────────────────────────────────────────────────────────

class TestBinaryResolution:
    def test_exe_is_directly_executable_on_windows(self):
        with patch("lib.opencode_cli.os.name", "nt"):
            assert _is_directly_executable(Path("C:/x/opencode.exe")) is True

    def test_cmd_shim_rejected_on_windows(self):
        # .cmd/.ps1 require cmd.exe to execute — that re-opens the injection
        # door, so resolution must never accept them.
        with patch("lib.opencode_cli.os.name", "nt"):
            for shim in ("opencode.cmd", "opencode.ps1", "opencode.bat"):
                assert _is_directly_executable(Path(f"C:/x/{shim}")) is False

    def test_extensionless_binary_ok_on_unix(self):
        with patch("lib.opencode_cli.os.name", "posix"):
            assert _is_directly_executable(Path("/usr/local/bin/opencode")) is True

    def test_which_shim_only_environment_returns_none(self, tmp_path, monkeypatch):
        # No native candidates exist (empty dirs) and which() only finds the
        # .cmd shim → resolver must return None rather than a shell-dependent
        # path.
        monkeypatch.setenv("BRAVO_OPENCODE_EXE", "")
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        fake_shim = tmp_path / "fake-bin" / "opencode.cmd"
        fake_shim.parent.mkdir(parents=True, exist_ok=True)
        fake_shim.write_text("")
        with patch("lib.opencode_cli.shutil.which", return_value=str(fake_shim)), \
             patch("lib.opencode_cli.os.name", "nt"):
            assert resolve_opencode_bin() is None

    def test_override_env_wins(self, tmp_path):
        exe = tmp_path / "my-opencode.exe"
        exe.write_bytes(b"MZ")
        with patch.dict("os.environ", {"BRAVO_OPENCODE_EXE": str(exe)}), \
             patch("lib.opencode_cli.os.name", "nt"):
            assert resolve_opencode_bin() == str(exe)

    def test_override_rejects_shim(self, tmp_path, monkeypatch):
        shim = tmp_path / "shim.opencode.cmd"
        shim.write_text("")
        monkeypatch.setenv("APPDATA", str(tmp_path))
        with patch.dict("os.environ", {"BRAVO_OPENCODE_EXE": str(shim)}), \
             patch("lib.opencode_cli.os.name", "nt"), \
             patch("lib.opencode_cli.shutil.which", return_value=None), \
             patch.object(Path, "home", classmethod(lambda cls: tmp_path)):
            assert resolve_opencode_bin() is None


# ── output cleaning ──────────────────────────────────────────────────────────

class TestCleanOutput:
    def test_strips_escape_codes(self):
        raw = "\x1b[32mHello\x1b[0m World"
        out = _clean_output(raw)
        assert "Hello" in out
        assert "\x1b" not in out

    def test_strips_banner_art(self):
        raw = "█▀▀█ █▀▀█ █▀▀█\n\nActual output text"
        out = _clean_output(raw)
        assert "Actual output text" in out
        assert "█" not in out

    def test_strips_status_header_line(self):
        # `opencode run --format default` prepends "> agent · model"
        raw = "\x1b[0m\n> build · nemotron-3.5-lightning-free\n\x1b[0m\nPONG\n"
        assert _clean_output(raw) == "PONG"

    def test_preserves_normal_text_and_interior_lines(self):
        raw = "Line one\nLine two"
        assert _clean_output(raw) == "Line one\nLine two"

    def test_keeps_reply_containing_gt_symbol_mid_sentence(self):
        raw = "Use > redirects carefully"
        assert _clean_output(raw) == raw


# ── run_opencode_cli (mocked subprocess) ────────────────────────────────────

class TestRunOpencodeCli:
    @patch("lib.opencode_cli.resolve_opencode_bin", return_value=None)
    def test_returns_none_when_binary_missing(self, _mock):
        assert run_opencode_cli("test") is None

    @patch("lib.opencode_cli.resolve_opencode_bin", return_value="C:/x/opencode.exe")
    @patch("lib.opencode_cli.subprocess.run")
    def test_returns_stdout_on_success(self, mock_run, _mock_bin):
        mock_run.return_value = MagicMock(returncode=0,
                                          stdout="\x1b[0m\n> build · m\n\x1b[0m\nPONG\n",
                                          stderr="")
        assert run_opencode_cli("Reply with PONG") == "PONG"

    @patch("lib.opencode_cli.resolve_opencode_bin", return_value="C:/x/opencode.exe")
    @patch("lib.opencode_cli.subprocess.run")
    def test_prompt_travels_via_stdin_never_argv(self, mock_run, _mock_bin):
        """SECURITY: untrusted prompt content must not appear on the command
        line (cmd.exe metacharacter injection) — stdin only."""
        prompt = 'hi" & calc.exe & echo'
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        run_opencode_cli(prompt)
        args = mock_run.call_args[0][0]
        joined = " ".join(str(a) for a in args)
        assert prompt not in joined
        assert mock_run.call_args.kwargs.get("input") == prompt

    @patch("lib.opencode_cli.resolve_opencode_bin", return_value="C:/x/opencode.exe")
    @patch("lib.opencode_cli.subprocess.run")
    def test_no_shell_used(self, mock_run, _mock_bin):
        """SECURITY: shell=True would route argv through cmd.exe."""
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        run_opencode_cli("test")
        assert not mock_run.call_args.kwargs.get("shell")

    @patch("lib.opencode_cli.resolve_opencode_bin", return_value="C:/x/opencode.exe")
    @patch("lib.opencode_cli.subprocess.run")
    def test_runs_restricted_agent(self, mock_run, _mock_bin):
        """SECURITY: every call must use the tools-denied bravo-oneshot agent."""
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        run_opencode_cli("test")
        args = [str(a) for a in mock_run.call_args[0][0]]
        assert "--agent" in args
        assert args[args.index("--agent") + 1] == OPENCODE_AGENT

    @patch("lib.opencode_cli.resolve_opencode_bin", return_value="C:/x/opencode.exe")
    @patch("lib.opencode_cli.subprocess.run")
    def test_system_prompt_prepended_via_stdin(self, mock_run, _mock_bin):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        run_opencode_cli("body", system="You are Bravo.")
        sent = mock_run.call_args.kwargs.get("input") or ""
        assert "<system>" in sent and "You are Bravo." in sent and "body" in sent

    @patch("lib.opencode_cli.resolve_opencode_bin", return_value="C:/x/opencode.exe")
    @patch("lib.opencode_cli.subprocess.run")
    def test_returns_none_on_nonzero_exit(self, mock_run, _mock_bin):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        assert run_opencode_cli("test") is None

    @patch("lib.opencode_cli.resolve_opencode_bin", return_value="C:/x/opencode.exe")
    @patch("lib.opencode_cli.subprocess.run",
           side_effect=subprocess.TimeoutExpired(cmd="opencode", timeout=120))
    def test_returns_none_on_timeout(self, _mock_run, _mock_bin):
        assert run_opencode_cli("test") is None

    @patch("lib.opencode_cli.resolve_opencode_bin", return_value="C:/x/opencode.exe")
    @patch("lib.opencode_cli.subprocess.run", side_effect=OSError("no exec"))
    def test_returns_none_on_spawn_failure(self, _mock_run, _mock_bin):
        assert run_opencode_cli("test") is None

    @patch("lib.opencode_cli.resolve_opencode_bin", return_value="C:/x/opencode.exe")
    @patch("lib.opencode_cli.subprocess.run")
    def test_uses_task_type_model(self, mock_run, _mock_bin):
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        run_opencode_cli("test", task_type="fast")
        args_flat = " ".join(str(a) for a in mock_run.call_args[0][0])
        assert "nemotron" in args_flat


# ── TIER_MODELS consistency ─────────────────────────────────────────────────

class TestTierModels:
    def test_all_tiers_have_primary_and_fallback(self):
        for tier, (primary, fallback) in TIER_MODELS.items():
            assert primary, f"tier {tier} has empty primary"
            assert fallback, f"tier {tier} has empty fallback"
            assert primary != fallback, f"tier {tier} has identical primary/fallback"

    def test_default_tier_exists(self):
        assert "default" in TIER_MODELS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
