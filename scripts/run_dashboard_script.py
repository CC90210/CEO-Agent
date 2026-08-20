"""run_dashboard_script.py — run any oasis-command-center TS script with creds.

The dashboard repo cannot read .env.agents, and secret_guard blocks
`node --env-file=.env.local` outright. Every task that needs to execute a
dashboard script has so far grown its own wrapper (run_reseed_sunbiz_forms.py,
run_seed_oasis_forms.py); this is the general form, so the next one does not
add a fourth copy. Credentials are loaded via the sanctioned secret_loader and
passed into the node child's environment ONLY — never printed, never written.

    python scripts/run_dashboard_script.py scripts/probe-cron-route.ts
    python scripts/run_dashboard_script.py scripts/seed-oasis-funnel.ts --apply

Everything after the script path is forwarded to the script untouched.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

CAPABILITY_META = {
    "category": "release.oasis",
    "lifecycle": "active",
    "risk": "external_write",
    "triggers": [
        "run a dashboard script",
        "execute oasis-command-center tsx script",
        "probe the dashboard database path",
    ],
    "owner": "bravo",
    "project": "oasis",
    "bridge": {"visible": False},
}

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from lib.subprocess_helpers import safe_run  # noqa: E402

DASHBOARD_DIR = Path(r"C:\Users\User\APPS\oasis-command-center")

# Production runs Turso; this pair is what actually carries the connection.
REQUIRED = ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN")

# Several dashboard scripts still hard-require the Supabase-shaped pair even
# though getServiceSupabase() hands back a Turso proxy. Supabase is retired, so
# those keys are absent; these compat placeholders satisfy the check without
# pointing at anything real. Any real value present in .env.agents wins.
COMPAT_DEFAULTS = {
    "BRAVO_SUPABASE_URL": "https://bravo.turso.compat",
    "BRAVO_SUPABASE_SERVICE_ROLE_KEY": "turso-compat-key",
    "EMPIRE_DATA_BACKEND": "turso_cloud",
}


def dashboard_env() -> dict[str, str]:
    """Environment for a dashboard child process, with credentials injected.

    The single definition. run_seed_oasis_forms.py imports this rather than
    keeping a second copy — two transcriptions of the same credential rules
    drift, and the one that drifts is the one nobody ran that week.

    Raises RuntimeError when a required key is absent, so a caller fails with a
    named cause instead of a child process dying on a confusing downstream
    error. No value is ever printed.
    """
    from lib.secret_loader import load_env  # type: ignore

    loaded = load_env()
    env = dict(os.environ)
    for k in REQUIRED:
        v = (loaded.get(k) or "").strip()
        if not v:
            raise RuntimeError(f"{k} missing from .env.agents")
        env[k] = v
    for k, fallback in COMPAT_DEFAULTS.items():
        env[k] = (loaded.get(k) or "").strip() or fallback
    return env


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__, file=sys.stderr)
        return 2
    script = args[0]
    forwarded = args[1:]

    if not DASHBOARD_DIR.exists():
        print(f"ERROR: dashboard dir not found: {DASHBOARD_DIR}", file=sys.stderr)
        return 2
    if not (DASHBOARD_DIR / script).exists():
        print(f"ERROR: script not found: {script}", file=sys.stderr)
        return 2

    try:
        env = dashboard_env()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    proc = safe_run(
        ["node", "--conditions=react-server", "--import", "tsx", script, *forwarded],
        cwd=str(DASHBOARD_DIR),
        env=env,
    )
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
