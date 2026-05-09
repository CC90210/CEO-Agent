# Allows `python -m bravo_cli ...` to dispatch through main.py without the
# `.main` suffix. The MAC_COMMAND_CENTER_PROMPT.md and several skill docs
# reference the short form; without this shim, callers hit
# "ModuleNotFoundError: No module named 'bravo_cli.__main__'".
from .main import main
import sys

if __name__ == "__main__":
    sys.exit(main())
