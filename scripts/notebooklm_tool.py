"""
NotebookLM CLI — Wrapper for notebooklm-py (v0.3.3)
Provides notebook management, source ingestion, chat, and artifact generation.
Auth: Browser-based (storage_state.json in ~/.notebooklm/). Run `notebooklm login` once.

Usage (from any agent via terminal):
  python scripts/notebooklm_tool.py list
  python scripts/notebooklm_tool.py create --title "Research Topic"
  python scripts/notebooklm_tool.py use <notebook_id>
  python scripts/notebooklm_tool.py status
  python scripts/notebooklm_tool.py ask "What are the key findings?"
  python scripts/notebooklm_tool.py source add <url_or_file>
  python scripts/notebooklm_tool.py source list
  python scripts/notebooklm_tool.py generate audio [--wait]
  python scripts/notebooklm_tool.py generate report [--wait]
  python scripts/notebooklm_tool.py download audio <output_path>
  python scripts/notebooklm_tool.py summary

All commands support --json flag for agent consumption.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Find notebooklm executable
VENV_DIR = Path(__file__).parent.parent / ".venv" / "Scripts"
NOTEBOOKLM_EXE = str(VENV_DIR / "notebooklm.exe")
if not os.path.exists(NOTEBOOKLM_EXE):
    NOTEBOOKLM_EXE = "notebooklm"  # Fall back to PATH


def run_notebooklm(args_list, timeout=120):
    """Run a notebooklm CLI command and return output."""
    cmd = [NOTEBOOKLM_EXE] + args_list
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace"
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            if "Authentication expired" in stderr or "login" in stderr.lower():
                return None, "AUTH_EXPIRED: Run 'notebooklm login' in terminal to re-authenticate."
            return None, stderr or stdout
        return stdout, None
    except subprocess.TimeoutExpired:
        return None, "TIMEOUT: Command took too long."
    except FileNotFoundError:
        return None, "NOT_FOUND: notebooklm-py not installed. Run: pip install notebooklm-py"


def main():
    json_output = "--json" in sys.argv
    if json_output:
        sys.argv.remove("--json")

    args = sys.argv[1:]
    if not args:
        print("Usage: python scripts/notebooklm_tool.py <command> [args...]")
        print("\nCommands: list, create, use, status, ask, summary, source, generate, download")
        print("Run 'notebooklm --help' for full reference.")
        sys.exit(0)

    output, err = run_notebooklm(args)

    if err:
        if json_output:
            print(json.dumps({"status": "error", "error": err}))
        else:
            print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    if json_output:
        # Try to parse as JSON, otherwise wrap as text
        try:
            parsed = json.loads(output)
            print(json.dumps({"status": "success", "data": parsed}, indent=2))
        except (json.JSONDecodeError, TypeError):
            print(json.dumps({"status": "success", "output": output}))
    else:
        print(output)


if __name__ == "__main__":
    main()
