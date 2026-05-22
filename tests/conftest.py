"""Make repo root + scripts/ + scripts/core/ + scripts/state/ importable so
tests can `import bravo_cli.*`, `import event_bus`, `import state_manager`,
`import memory_retriever`, etc. without an editable install.

After the 2026-05 reorg, modules ended up under scripts/{core,state,...}/.
The tests in tests/ were written against the flat scripts/ layout and use
bare imports. Adding the subdirs to sys.path here keeps the tests
working without rewriting every import line.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
SCRIPTS_CORE = SCRIPTS / "core"
SCRIPTS_STATE = SCRIPTS / "state"

# Order matters: repo root first (so `bravo_cli`, `tests`, etc. resolve as
# packages), then scripts/ + subdirs (so flat `event_bus.py`,
# `state_manager.py`, `memory_retriever.py` imports resolve).
for path in (ROOT, SCRIPTS, SCRIPTS_CORE, SCRIPTS_STATE):
    s = str(path)
    if s not in sys.path:
        sys.path.insert(0, s)
