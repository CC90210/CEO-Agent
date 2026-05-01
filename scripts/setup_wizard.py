"""
setup_wizard.py — Bravo credential setup wizard (thin entry-point shim).

This script is the install.sh-documented path for running the setup wizard:
    python scripts/setup_wizard.py

It delegates entirely to bravo_cli/wizard.py, which contains the full
2000+ line interactive wizard. This shim exists so that:
  1. The install.sh step reference (Step f) has a concrete path to call.
  2. Clients who find this script directly get the right experience.
  3. The --non-interactive flag and BRAVO_SETUP_CONFIG env var are
     forwarded to the wizard's main() function.

Do NOT duplicate wizard logic here. If you need to change setup behavior,
edit bravo_cli/wizard.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the repo root is on sys.path so bravo_cli is importable
# regardless of the caller's working directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from bravo_cli.main import main as _bravo_main
except ImportError as exc:
    print(
        f"[setup_wizard] Cannot import bravo_cli.main: {exc}\n"
        "Make sure you are running inside the repo virtualenv:\n"
        "  source .venv/bin/activate   # or .venv\\Scripts\\activate on Windows\n"
        "  pip install -r requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    """Forward to bravo_cli.main with 'setup' as the first argument.

    This function rewrites sys.argv so the downstream wizard sees:
        bravo_cli/main.py setup [extra-flags...]

    Supported pass-through flags:
        --non-interactive   Run without prompts (reads BRAVO_SETUP_CONFIG yaml)
        --profile NAME      Pre-select an agent profile (bravo/atlas/maven/hermes/aura)
        --skip-smoke        Skip the smoke tests at the end
    """
    # Preserve any flags the caller passed after the script name
    extra_args = sys.argv[1:]

    # Inject 'setup' as the subcommand if it is not already present
    if not extra_args or extra_args[0] != "setup":
        extra_args = ["setup"] + extra_args

    # Rewrite argv so bravo_cli/main.py's argparse sees the right shape
    sys.argv = [sys.argv[0]] + extra_args

    # BRAVO_SETUP_CONFIG support: if the env var points to a yaml file,
    # the wizard reads credentials/answers from it instead of prompting.
    config_path = os.environ.get("BRAVO_SETUP_CONFIG")
    if config_path:
        if not Path(config_path).exists():
            print(
                f"[setup_wizard] BRAVO_SETUP_CONFIG={config_path!r} does not exist.",
                file=sys.stderr,
            )
            sys.exit(1)
        # The wizard reads this env var internally — we just validate the path
        # here so the error message is clear before the wizard starts.

    _bravo_main()


if __name__ == "__main__":
    main()
