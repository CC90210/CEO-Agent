"""Make the repo root importable so `import bravo_cli.*` works in tests
without needing an editable install. Pytest auto-discovers conftest.py."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
