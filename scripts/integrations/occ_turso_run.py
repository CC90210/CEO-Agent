"""Run an OASIS Command Center maintenance script against the live Turso DB.

The command center's own scripts (scripts/*.ts there) read TURSO_DATABASE_URL /
TURSO_AUTH_TOKEN from the environment, but that repo holds no credentials — they
live in this repo's secret store, which no agent may read. This wrapper hands
exactly those two keys to the child process (the RULE 3 env-store -> child path,
same as wrangler_tool.py) and nothing else from the store. Values are never
printed.

  python scripts/integrations/occ_turso_run.py scripts/retire-oasis-sales-team.ts
  python scripts/integrations/occ_turso_run.py scripts/retire-oasis-sales-team.ts --apply

Only files under the command center's scripts/ directory are runnable.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.secret_loader import load_env  # noqa: E402

OCC_ROOT = Path(os.environ.get("OCC_ROOT", Path.home() / "APPS" / "oasis-command-center")).resolve()
TURSO_KEYS = ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    script = (OCC_ROOT / argv[0]).resolve()
    scripts_dir = (OCC_ROOT / "scripts").resolve()
    if scripts_dir not in script.parents or not script.is_file():
        print(f"refused: {argv[0]} is not a file under {scripts_dir}", file=sys.stderr)
        return 2

    secrets = load_env(required=TURSO_KEYS)
    env = dict(os.environ)
    for key in TURSO_KEYS:
        env[key] = secrets[key]
    # The command center's hybrid data client falls back to the retired Supabase
    # path unless this is exactly turso_cloud.
    env["EMPIRE_DATA_BACKEND"] = "turso_cloud"

    node = "node.exe" if os.name == "nt" else "node"
    cmd = [node, "--conditions=react-server", "--import", "tsx", str(script), *argv[1:]]
    return subprocess.run(cmd, cwd=OCC_ROOT, env=env).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
