"""run_seed_oasis_forms.py — inject service-role creds and re-seed the LIVE
OASIS funnel forms (the /start funnel and the AI-audit funnel).

Mirrors run_reseed_sunbiz_forms.py for the OASIS tenant. Forms are DB rows, not
code: the TypeScript seeds (lib/forms/oasis-funnel-seed.ts,
lib/forms/oasis-ai-audit-seed.ts) are only the source of truth once they are
pushed to the `forms` table. Editing the seed alone changes nothing a visitor
sees — a lesson that cost real leads on 2026-08-20, when both live rows still
carried on_complete_stage='new_contact' (a stage retired from the 14-stage
pipeline) and every inbound lead landed in a column that does not render.

The dashboard repo cannot read .env.agents, and secret_guard blocks
`node --env-file=.env.local` outright. This wrapper loads the credentials via
the sanctioned secret_loader and passes them into the node child's environment
ONLY; they are never printed and never reach the agent's context.

    python scripts/run_seed_oasis_forms.py                # dry run, both forms
    python scripts/run_seed_oasis_forms.py --apply        # write both
    python scripts/run_seed_oasis_forms.py --only ai-audit --apply

Idempotent — the seeders upsert by (tenant_id, slug). Safe to re-run.
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
        "reseed oasis forms",
        "deploy oasis funnel form",
        "refresh live oasis forms",
        "push form field changes live",
    ],
    "owner": "bravo",
    "project": "oasis",
    "bridge": {"visible": False},
}

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from lib.subprocess_helpers import safe_run  # noqa: E402

DASHBOARD_DIR = Path(r"C:\Users\User\APPS\oasis-command-center")

# slug -> seeder script inside the dashboard repo
SEEDERS = {
    "start": "scripts/seed-oasis-funnel.ts",
    "ai-audit": "scripts/seed-ai-audit-funnel.ts",
}

# Production runs Turso, so the Turso pair is what actually carries the write.
REQUIRED = ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN")

# The seeders hard-require the Supabase-shaped pair and exit 3 without it, even
# though getServiceSupabase() hands back a Turso proxy when EMPIRE_DATA_BACKEND
# is turso_cloud. Supabase is retired, so those keys are absent from .env.agents;
# the same compat placeholders scripts/enrich_oasis_leads.py already uses satisfy
# the check without pointing at anything real. Real values win when present.
COMPAT_DEFAULTS = {
    "BRAVO_SUPABASE_URL": "https://bravo.turso.compat",
    "BRAVO_SUPABASE_SERVICE_ROLE_KEY": "turso-compat-key",
    "EMPIRE_DATA_BACKEND": "turso_cloud",
}


def main() -> int:
    from lib.secret_loader import load_env  # type: ignore

    argv = sys.argv[1:]
    apply = "--apply" in argv
    only = None
    if "--only" in argv:
        i = argv.index("--only")
        if i + 1 >= len(argv):
            print("ERROR: --only needs a form slug", file=sys.stderr)
            return 2
        only = argv[i + 1].strip().lower()
        if only not in SEEDERS:
            print(f"ERROR: unknown form {only!r}; known: {', '.join(SEEDERS)}", file=sys.stderr)
            return 2

    if not DASHBOARD_DIR.exists():
        print(f"ERROR: dashboard dir not found: {DASHBOARD_DIR}", file=sys.stderr)
        return 2

    loaded = load_env()
    env = dict(os.environ)
    for k in REQUIRED:
        v = (loaded.get(k) or "").strip()
        if not v:
            print(f"ERROR: {k} missing from .env.agents", file=sys.stderr)
            return 2
        env[k] = v
    for k, fallback in COMPAT_DEFAULTS.items():
        env[k] = (loaded.get(k) or "").strip() or fallback

    targets = {only: SEEDERS[only]} if only else SEEDERS
    failures = 0
    for slug, script in targets.items():
        if not (DASHBOARD_DIR / script).exists():
            print(f"SKIP {slug}: seeder not found ({script})", file=sys.stderr)
            failures += 1
            continue
        cmd = ["node", "--import", "tsx", script]
        if apply:
            cmd.append("--apply")
        print(f"\n=== {slug} {'(APPLY)' if apply else '(dry run)'} — {script} ===")
        proc = safe_run(cmd, cwd=str(DASHBOARD_DIR), env=env)
        if proc.returncode != 0:
            failures += 1
            print(f"FAILED {slug}: exit {proc.returncode}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
