"""
Backend Template — Subprocess wrapper for CLI-Anything tools.
Adapted from HKUDS/CLI-Anything for Business-Empire-Agent.

Usage:
    Copy this file and customize for your target software.

    from backend import Backend
    backend = Backend(executable="gimp", args=["-i", "-b"])
    result = backend.run("(gimp-version)")
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
_p = Path(__file__).resolve()
while _p.parent != _p and not (_p / "scripts" / "_subprocess_helpers.py").exists():
    _p = _p.parent
sys.path.insert(0, str(_p / "scripts"))
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402


class Backend:
    """Subprocess wrapper for calling external software."""

    def __init__(
        self,
        executable: str,
        default_args: list[str] | None = None,
        timeout: int = 30,
        env_overrides: dict[str, str] | None = None,
    ):
        self.executable = executable
        self.default_args = default_args or []
        self.timeout = timeout
        self.env = {**os.environ, **(env_overrides or {})}
        self._resolved_path: str | None = None

    def resolve(self) -> str:
        """Find the executable on PATH. Raises if not found."""
        if self._resolved_path:
            return self._resolved_path

        path = shutil.which(self.executable)
        if not path and sys.platform == "win32":
            # On Windows, try common install paths with .exe extension
            exe_name = self.executable
            if not exe_name.endswith(".exe"):
                exe_name += ".exe"
            common_dirs = [
                Path(os.environ.get("PROGRAMFILES", "")) / self.executable / "bin",
                Path(os.environ.get("PROGRAMFILES", "")) / self.executable,
                Path(os.environ.get("LOCALAPPDATA", "")) / self.executable / "bin",
                Path(os.environ.get("LOCALAPPDATA", "")) / self.executable,
            ]
            for d in common_dirs:
                candidate = d / exe_name
                if candidate.exists():
                    path = str(candidate)
                    break

        if not path:
            raise FileNotFoundError(
                f"'{self.executable}' not found on PATH. "
                f"Install it or add it to your PATH."
            )

        self._resolved_path = path
        return path

    def run(
        self,
        args: list[str] | None = None,
        input_text: str | None = None,
        timeout: int | None = None,
        capture_json: bool = False,
    ) -> dict:
        """
        Execute the software with given arguments.

        Returns:
            dict with keys: output, error, code, json_data (if capture_json=True)
        """
        exe = self.resolve()
        full_args = [exe] + self.default_args + (args or [])
        effective_timeout = timeout or self.timeout

        try:
            result = subprocess.run(
                full_args,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                env=self.env,
                cwd=os.getcwd(),
             creationflags=WINDOWLESS_FLAGS)

            response = {
                "output": result.stdout.strip(),
                "error": result.stderr.strip(),
                "code": result.returncode,
            }

            if capture_json and result.stdout.strip():
                try:
                    response["json_data"] = json.loads(result.stdout.strip())
                except json.JSONDecodeError:
                    response["json_data"] = None

            return response

        except subprocess.TimeoutExpired:
            return {
                "output": "",
                "error": f"Command timed out after {effective_timeout}s",
                "code": -1,
            }
        except FileNotFoundError:
            return {
                "output": "",
                "error": f"Executable not found: {exe}",
                "code": -1,
            }

    def is_available(self) -> bool:
        """Check if the software is installed and accessible."""
        try:
            self.resolve()
            return True
        except FileNotFoundError:
            return False

    def version(self, version_flag: str = "--version") -> str | None:
        """Get the software version."""
        result = self.run([version_flag])
        if result["code"] == 0:
            return result["output"].split("\n")[0]
        return None


def load_env_credentials(key_name: str, env_file: str | None = None) -> str | None:
    """
    Load a credential from environment or .env.agents file.
    NEVER hardcode credentials — always use this function.
    """
    # Check environment first
    value = os.environ.get(key_name)
    if value:
        return value

    # Fall back to .env.agents
    if env_file is None:
        # Walk up from script location to find .env.agents
        current = Path(__file__).resolve().parent
        for _ in range(5):
            candidate = current / ".env.agents"
            if candidate.exists():
                env_file = str(candidate)
                break
            current = current.parent

    if env_file and os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == key_name:
                        return v.strip()

    return None
