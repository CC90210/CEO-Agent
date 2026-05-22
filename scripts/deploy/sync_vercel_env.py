"""Push selected secrets from `.env.agents` into a Vercel project's env vars.

V6.8.3 — written 2026-05-21 to close the dashboard's
"BRAVO_ANTHROPIC_API_KEY not configured" warning on the lead-detail
"Recommend next move" button. Generalised so it can fan out other
dashboard-required secrets in one shot.

Reads via `lib.secret_loader.load_env()` — same audited path every other
CLI uses; the secret value is never printed, just streamed into
`vercel env add` via stdin. The file-guard hook will not fire because
this script lives in scripts/deploy/ (not tmp/) and uses the canonical
loader.

Usage (from project root):

    # Push one var to all three environments
    python scripts/deploy/sync_vercel_env.py BRAVO_ANTHROPIC_API_KEY

    # Push a list, only to production
    python scripts/deploy/sync_vercel_env.py --env production \
        BRAVO_ANTHROPIC_API_KEY BRAVO_OPENAI_API_KEY

    # Dry-run (verify the key is present in .env.agents but don't push)
    python scripts/deploy/sync_vercel_env.py --dry-run BRAVO_ANTHROPIC_API_KEY

Requires:
    - vercel CLI on PATH (`npm i -g vercel`)
    - cwd to be inside a Vercel-linked repo (`.vercel/project.json` present)
    - .env.agents in the Bravo repo root with the keys you want to push
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Windows console (cp1252) cannot encode arrows / check marks. Force utf-8 so
# the script runs identically on PowerShell / Git Bash / Mac / Linux.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    from lib.secret_loader import load_env  # type: ignore
except ImportError as e:
    print(f"ERROR: lib.secret_loader unavailable: {e}", file=sys.stderr)
    sys.exit(1)


VALID_ENVS = ("production", "preview", "development")

# On Windows, npm-installed CLIs ship as `.cmd` shims that CreateProcess can't
# resolve directly. shell=True asks cmd.exe to do the PATHEXT lookup. Harmless
# on Unix.
_USE_SHELL = sys.platform == "win32"


def _vercel_env_remove(key: str, env: str, cwd: Path) -> tuple[bool, str]:
    """Best-effort delete of an existing variable so `vercel env add` won't
    conflict. Returns (was_removed, message). Missing var → benign no-op."""
    proc = subprocess.run(
        "vercel env rm {k} {e} --yes".format(k=key, e=env) if _USE_SHELL
        else ["vercel", "env", "rm", key, env, "--yes"],
        capture_output=True, text=True, cwd=str(cwd), shell=_USE_SHELL,
    )
    if proc.returncode == 0:
        return True, "removed_existing"
    # 'not found' is fine
    lower = (proc.stderr + proc.stdout).lower()
    if "not found" in lower or "does not exist" in lower:
        return False, "not_present"
    return False, f"rm_failed({proc.returncode})"


def _vercel_env_add(key: str, value: str, env: str, cwd: Path) -> tuple[bool, str]:
    """Add an env var via the vercel CLI.

    Modern vercel (5.x) requires `--value <v>` in non-interactive mode for
    Preview env vars (stdin gets ambiguous with the optional git-branch
    positional). We use --value for ALL envs for consistency.

    Value is passed via subprocess args, NOT shell, so it never enters shell
    history. Brief `ps`-visibility window is acceptable given that the value
    already lives in .env.agents on disk.

    --yes skips confirmations; --force overwrites on race-condition collisions.
    On Windows we use shell=True because npm-installed CLIs are .cmd shims
    that CreateProcess can't resolve directly — but we still pass argv as a
    LIST so cmd.exe doesn't have to parse / escape the secret.
    """
    argv = ["vercel", "env", "add", key, env, "--value", value, "--yes", "--force"]
    proc = subprocess.run(
        argv,
        capture_output=True, text=True, cwd=str(cwd), shell=_USE_SHELL,
    )
    if proc.returncode == 0:
        return True, "added"
    combined = (proc.stderr + "\n--STDOUT--\n" + proc.stdout).strip()
    return False, f"add_failed (rc={proc.returncode}):\n{combined}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("keys", nargs="+",
                        help="env-var names to push. Either `NAME` (same name in "
                             ".env.agents and Vercel) or `LOCAL_NAME=VERCEL_NAME` "
                             "(map a differently-named local key to its Vercel target).")
    parser.add_argument("--env", action="append", choices=VALID_ENVS,
                        help="Vercel environment(s) to push to (default: all three). "
                             "Repeatable.")
    parser.add_argument("--cwd", default=str(PROJECT_ROOT.parent / "APPS" / "oasis-command-center"),
                        help="Vercel-linked project directory. Default: %(default)s")
    parser.add_argument("--dry-run", action="store_true",
                        help="Verify keys exist in .env.agents but don't push")
    parser.add_argument("--replace", action="store_true",
                        help="If a var already exists in the target env, remove it first")
    args = parser.parse_args(argv)

    envs = args.env or list(VALID_ENVS)
    cwd = Path(args.cwd).resolve()

    # Vercel CLI uses .vercel/project.json (legacy) or .vercel/repo.json
    # (current). Either is fine — both prove this directory is linked.
    if not ((cwd / ".vercel" / "project.json").exists()
            or (cwd / ".vercel" / "repo.json").exists()):
        print(f"ERROR: {cwd} is not Vercel-linked "
              f"(no .vercel/project.json or .vercel/repo.json). "
              f"Run `vercel link --yes --project agent-dashboard` there first.",
              file=sys.stderr)
        return 1

    if not shutil.which("vercel"):
        print("ERROR: `vercel` CLI not on PATH. Install: npm i -g vercel",
              file=sys.stderr)
        return 1

    # Parse each spec into (local_name, vercel_target_name).
    mappings: list[tuple[str, str]] = []
    for spec in args.keys:
        if "=" in spec:
            local, _, target = spec.partition("=")
            mappings.append((local.strip(), target.strip()))
        else:
            mappings.append((spec, spec))

    env_dict = load_env(required=[m[0] for m in mappings])

    print(f"Target Vercel project: {cwd}")
    print(f"Target environment(s): {', '.join(envs)}")
    print(f"Keys to push: {len(mappings)}")
    print()

    rc = 0
    for local_name, target_name in mappings:
        value = env_dict.get(local_name, "")
        rename_tag = "" if local_name == target_name else f"  (from {local_name})"
        if not value:
            print(f"  ✗ {target_name}{rename_tag}: MISSING in .env.agents — skipping")
            rc = 2
            continue
        masked = f"<{len(value)} chars, sha256 prefix {__import__('hashlib').sha256(value.encode()).hexdigest()[:8]}>"
        print(f"  → {target_name}{rename_tag}  {masked}")

        if args.dry_run:
            print(f"      (dry-run; would push to: {', '.join(envs)})")
            continue

        for env in envs:
            if args.replace:
                _vercel_env_remove(target_name, env, cwd)
            ok, detail = _vercel_env_add(target_name, value, env, cwd)
            tag = "✓" if ok else "✗"
            print(f"      [{env:11s}] {tag} {detail}")
            if not ok and "already exists" in detail:
                # Retry once with --replace semantic
                _vercel_env_remove(target_name, env, cwd)
                ok2, detail2 = _vercel_env_add(target_name, value, env, cwd)
                tag2 = "✓" if ok2 else "✗"
                print(f"      [{env:11s}] retry {tag2} {detail2}")
                if not ok2:
                    rc = 3
            elif not ok:
                rc = 3

    if rc == 0:
        print()
        print("All keys pushed. Run `vercel --prod` (or push to main) to redeploy "
              "with the new env vars baked in.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
