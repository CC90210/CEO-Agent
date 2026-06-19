"""run_reseed_sunbiz_forms.py — inject Supabase service-role creds and run the
oasis-command-center SunBiz form re-seed (scripts/reseed-sunbiz-forms.ts).

The re-seed pushes the canonical form templates (lib/forms/sunbiz-templates.ts)
to the LIVE `forms` rows so field-schema changes (multi-file dropzone, industry
combobox, name prefill, signature, removed confirmation) appear on the public
forms. The dashboard repo has no access to .env.agents; this wrapper loads the
service-role creds via the sanctioned secret_loader and passes them into the
node child's env ONLY — they are never printed.

    python scripts/run_reseed_sunbiz_forms.py            # dry run (no writes, no snapshot)
    python scripts/run_reseed_sunbiz_forms.py --apply    # write (snapshots first)

Safe to re-run; idempotent. The tsx script snapshots each live form before
--apply so a revert is a single restore.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

DASHBOARD_DIR = Path(r"C:\Users\User\APPS\oasis-command-center")


def main() -> int:
    from lib.secret_loader import load_env  # type: ignore

    loaded = load_env()
    env = dict(os.environ)
    for k in ("BRAVO_SUPABASE_URL", "BRAVO_SUPABASE_SERVICE_ROLE_KEY"):
        v = (loaded.get(k) or "").strip()
        if not v:
            print(f"ERROR: {k} missing from .env.agents", file=sys.stderr)
            return 2
        env[k] = v

    if not DASHBOARD_DIR.exists():
        print(f"ERROR: dashboard dir not found: {DASHBOARD_DIR}", file=sys.stderr)
        return 2

    cmd = ["node", "--import", "tsx", "scripts/reseed-sunbiz-forms.ts"]
    if "--apply" in sys.argv:
        cmd.append("--apply")

    proc = subprocess.run(cmd, cwd=str(DASHBOARD_DIR), env=env)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
