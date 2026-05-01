"""Cross-platform install helper — shared between install.ps1 and install.sh.

Idempotent. Never mutates .env.agents. Creates ~/.bravo/ tree, profiles, env
template (keys-only), and optionally a bravo shim.

Usage:
    python install/bootstrap.py --home ~/.bravo --env-file .env.agents
    python install/bootstrap.py --home ~/.bravo --no-shim
    python install/bootstrap.py --check
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.profile_home import ensure_home, DEFAULT_HOME, SUBDIRS  # noqa: E402


def extract_env_keys(env_path: Path) -> list[str]:
    """Parse .env-style file, return list of keys (never values)."""
    keys: list[str] = []
    if not env_path.exists():
        return keys
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key = s.split("=", 1)[0].strip()
        if key and (key.isidentifier() or all(c.isalnum() or c == "_" for c in key)):
            keys.append(key)
    return sorted(set(keys))


def write_env_template(keys: list[str], output_path: Path) -> bool:
    """Write .env.template with keys-only. Never overwrite a populated file."""
    if output_path.exists():
        text = output_path.read_text(encoding="utf-8", errors="ignore")
        populated = any(
            "=" in line and line.split("=", 1)[1].strip()
            and not line.strip().startswith("#")
            for line in text.splitlines()
        )
        if populated:
            return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "# Bravo environment template.\n"
        "# Fill values in your real .env (e.g. ~/.bravo/.env) or the repo's\n"
        "# parent .env.agents. Never commit populated .env files.\n\n"
        + "\n".join(f"{k}=" for k in keys) + "\n"
    )
    output_path.write_text(body, encoding="utf-8")
    return True


def write_shim(home: Path, repo: Path) -> Path:
    """Write ~/.bravo/bin/bravo.cmd (Windows) or bin/bravo (POSIX)."""
    bin_dir = home / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        shim = bin_dir / "bravo.cmd"
        shim.write_text(
            "@echo off\r\n"
            "setlocal\r\n"
            f'python "{repo}\\bravo_cli\\main.py" %*\r\n',
            encoding="utf-8",
        )
    else:
        shim = bin_dir / "bravo"
        shim.write_text(
            "#!/usr/bin/env bash\n"
            'set -e\n'
            f'exec python3 "{repo}/bravo_cli/main.py" "$@"\n',
            encoding="utf-8",
        )
        shim.chmod(0o755)
    return shim


def check_prereqs() -> dict:
    """Return which tools are present. Never install them."""
    def which(name: str) -> str | None:
        return shutil.which(name)
    return {
        # Required — installer hard-fails without these.
        "python": which("python") or which("python3"),
        "node": which("node"),
        "npm": which("npm"),
        "git": which("git"),
        # Optional — used by specific scripts; surface-level detection.
        "uv": which("uv"),
        "rg": which("rg"),
        "ffmpeg": which("ffmpeg"),
        "gh": which("gh"),  # GitHub CLI — some scripts use it for repo ops
        "browser-harness": which("browser-harness"),
    }


def install_mcp_config(repo_root: Path) -> tuple[bool, str]:
    """Seed .claude/mcp.json from the committed template on fresh clones.

    The real config is gitignored (it references user-local paths and loads
    credentials through .cmd wrappers). The template (.claude/mcp.json.template)
    ships in git and the installer substitutes ${REPO_ROOT} + ${USER_HOME}
    placeholders.

    Idempotent — if .claude/mcp.json already exists, we leave it alone.
    """
    target = repo_root / ".claude" / "mcp.json"
    template = repo_root / ".claude" / "mcp.json.template"
    if target.exists():
        return True, "mcp.json already present — preserved"
    if not template.exists():
        return True, "no template — skipped"
    try:
        body = template.read_text(encoding="utf-8")
        body = body.replace("${REPO_ROOT}", str(repo_root).replace("\\", "\\\\"))
        body = body.replace("${USER_HOME}", str(Path.home()).replace("\\", "\\\\"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        return True, f"seeded from template → {target}"
    except Exception as exc:  # noqa: BLE001
        return False, f"seed failed: {exc}"


def verify_requirements(repo_root: Path) -> tuple[bool, str]:
    """Dry-run pip against requirements.txt from a fresh dep state.

    The --ignore-installed flag makes pip resolve the whole tree as if
    nothing were installed — that's what a client's fresh paste-install
    actually hits. This is the process fix for the three hotfix cycles
    where I shipped a pin change, CC's fresh install failed with a
    conflict pip already knew about, and I only caught it from their
    terminal output.

    Returns (ok, detail). Call this before committing any requirements.txt
    change. Run via `bravo doctor` or
    `python install/bootstrap.py --verify-requirements`.
    """
    req = repo_root / "requirements.txt"
    if not req.exists():
        return True, "no requirements.txt"
    import subprocess
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "--dry-run", "--ignore-installed",
             "--disable-pip-version-check", "-r", str(req)],
            capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            # Count "Would install" packages for a quick sanity read.
            would_install = 0
            for line in r.stdout.splitlines():
                if line.startswith("Would install"):
                    would_install = len(line.replace("Would install", "").split())
            return True, f"resolver clean ({would_install} packages resolve)"
        # Extract the actual conflict line for the error detail.
        err_line = "unknown conflict"
        for line in (r.stderr or r.stdout).splitlines():
            s = line.strip()
            if s.startswith("ERROR:") or "conflicting dependencies" in s.lower():
                err_line = s[:200]
                break
        return False, err_line
    except Exception as exc:  # noqa: BLE001
        return False, f"verify error: {exc}"


def _run_install_with_log(
    cmd: list[str],
    *,
    log_name: str,
    timeout: int,
    error_matcher,
    tool: str,
    cwd: Path | None = None,
    shell: bool = False,
    preface: str | None = None,
) -> tuple[bool, str]:
    """Run a package-install subprocess with log-file capture + error extraction.

    Shared scaffold for pip and npm. Rationale: PowerShell on Windows
    chokes on verbose package-manager output; fully silent hides real
    errors. Solution is to capture everything to a log file, keep the
    console quiet, and on failure grep the log for the first actionable
    error line.

    error_matcher(line: str) -> bool — called per stripped log line to
    decide whether this is the error worth surfacing.
    """
    import subprocess

    log_dir = Path.home() / ".bravo" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_name
    if preface:
        print(preface.replace("{log}", str(log_path)))
    try:
        with open(log_path, "w", encoding="utf-8", errors="replace") as f:
            r = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                timeout=timeout,
                stdout=f,
                stderr=subprocess.STDOUT,
                shell=shell,
            )
        if r.returncode == 0:
            return True, f"installed ({tool} skips already-satisfied)"
        err_line = ""
        try:
            for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
                s = line.strip()
                if error_matcher(s):
                    err_line = s[:200]
                    break
        except Exception:
            pass
        return False, (err_line or f"{tool} exit {r.returncode}") + f" (full log: {log_path})"
    except subprocess.TimeoutExpired:
        mins = timeout // 60
        return False, f"{tool} timed out after {mins} min — see {log_path}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{tool} error: {exc}"


def install_python_deps(repo_root: Path) -> tuple[bool, str]:
    """Run `pip install -r requirements.txt` if that file exists."""
    req = repo_root / "requirements.txt"
    if not req.exists():
        return True, "no requirements.txt — skipped"
    return _run_install_with_log(
        [sys.executable, "-m", "pip", "install", "-q",
         "--disable-pip-version-check", "-r", str(req)],
        log_name="pip-install.log",
        timeout=1200,
        error_matcher=lambda s: s.startswith("ERROR:") or "could not find" in s.lower(),
        tool="pip",
        preface="    (first run takes 2-5 min. full log: {log})",
    )


def create_command_center_account(
    repo_root: Path,                  # noqa: ARG001 — kept for caller compat
    email: str,
    full_name: str,
    brand: str = "OASIS AI",
    mrr_target: float = 5000.0,       # noqa: ARG001 — operator edits in dashboard
    primary_agent: str = "bravo",     # noqa: ARG001 — operator edits in dashboard
    *,
    prefer_oauth: bool = False,
    api_url: str | None = None,
    api_secret: str | None = None,
) -> tuple[bool, str]:
    """Create the operator's OASIS Command Center account via the live API.

    POSTs to /api/auth/provision-cli on the Command Center deployment. The
    endpoint creates a Supabase Auth user, fires an invite email (or skips
    it if prefer_oauth=True), and provisions a tenant + profile via the
    signup_tenant RPC. Idempotent — re-running for an existing email is a no-op.

    Args:
      email, full_name, brand: operator details
      prefer_oauth: if True, no invite email is sent — the operator signs in
        with Google instead
      api_url: override the default https://agent-dashboard-cc90210.vercel.app
      api_secret: Bearer token for the endpoint. If unset, reads CLI_SIGNUP_SECRET
        from the env. Get this from the project owner.
    """
    if not email or "@" not in email:
        return False, "email is required and must look like an email"
    if not full_name or not full_name.strip():
        return False, "full_name is required"

    base = (api_url or os.environ.get("OASIS_COMMAND_CENTER_URL")
            or "https://agent-dashboard-cc90210.vercel.app").rstrip("/")
    secret = api_secret or os.environ.get("CLI_SIGNUP_SECRET")
    if not secret:
        return False, "CLI_SIGNUP_SECRET not set — ask CC for the wizard signup token"

    import urllib.request
    import urllib.error
    body = json.dumps({
        "email": email,
        "full_name": full_name,
        "brand": brand,
        "prefer_oauth": prefer_oauth,
    }).encode()
    req = urllib.request.Request(
        f"{base}/api/auth/provision-cli",
        data=body, method="POST",
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
            "User-Agent": "oasis-setup-wizard/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read()).get("error", "unknown")
        except Exception:  # noqa: BLE001
            err = f"HTTP {e.code}"
        return False, f"signup failed: {err}"
    except Exception as e:  # noqa: BLE001
        return False, f"signup network error: {e}"

    if not payload.get("ok"):
        return False, f"signup rejected: {payload.get('error', 'unknown')}"

    sign_in = payload.get("sign_in_url", base + "/login")
    if payload.get("welcome_sent"):
        return True, f"account created — invite email sent. Sign in: {sign_in}"
    if payload.get("is_new_user"):
        return True, f"account created. Sign in with Google at: {sign_in}"
    return True, f"account already existed; sign in at: {sign_in}"


def _legacy_create_command_center_account_via_seed(
    repo_root: Path,
    email: str,
    full_name: str,
    brand: str = "OASIS AI",
    mrr_target: float = 5000.0,
) -> tuple[bool, str]:
    """LEGACY: invokes scripts/seed_profile.py directly (requires service-role
    key on the local machine). Kept for development; production wizards must
    use the create_command_center_account API path which only needs the
    public Bearer token."""
    seed_script = repo_root / "scripts" / "seed_profile.py"
    if not seed_script.exists():
        return False, f"seed_profile.py missing at {seed_script}"

    if not email or "@" not in email:
        return False, "email is required and must look like an email"
    if not full_name or not full_name.strip():
        return False, "full_name is required"

    import subprocess
    cmd = [
        sys.executable,
        str(seed_script),
        "--email", email,
        "--full-name", full_name,
        "--brand", brand,
        "--mrr-target", str(mrr_target),
        "--no-plan",
        "--json",
    ]
    try:
        r = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip().splitlines()
            first = err[0] if err else f"exit {r.returncode}"
            return False, f"seed failed: {first[:200]}"
        try:
            payload = json.loads(r.stdout.strip().splitlines()[-1])
            return True, f"account created: profile_id={payload.get('profile_id', '?')}"
        except Exception:
            return True, "account created"
    except subprocess.TimeoutExpired:
        return False, "seed timed out (Supabase unreachable?)"
    except Exception as exc:  # noqa: BLE001
        return False, f"seed error: {exc}"


def install_node_deps(repo_root: Path) -> tuple[bool, str]:
    """Run `npm install` at repo root if package.json exists."""
    pkg = repo_root / "package.json"
    if not pkg.exists():
        return True, "no package.json — skipped"
    return _run_install_with_log(
        ["npm", "install", "--silent", "--no-audit", "--no-fund"],
        log_name="npm-install.log",
        timeout=900,
        error_matcher=lambda s: s.lower().startswith("npm err") or s.startswith("ERROR"),
        tool="npm",
        cwd=repo_root,
        shell=(os.name == "nt"),  # Windows needs shell for npm.cmd
    )


def run(args: argparse.Namespace) -> int:
    home = Path(args.home).expanduser()
    repo = Path(args.repo).expanduser() if args.repo else REPO_ROOT

    # --verify-requirements mode: dry-run resolver, exit non-zero on conflict.
    # Use before committing any requirements.txt pin change.
    if getattr(args, "verify_requirements", False):
        ok, detail = verify_requirements(repo)
        mark = "+" if ok else "!"
        print(f"  [{mark}] requirements.txt: {detail}")
        return 0 if ok else 1

    # --create-command-center-account mode: wizard hook. POSTs to the
    # Command Center's /api/auth/provision-cli endpoint. Idempotent.
    if getattr(args, "create_command_center_account", False):
        if not args.email or not args.full_name:
            print("ERROR: --email and --full-name are required for --create-command-center-account",
                  file=sys.stderr)
            return 2
        ok, detail = create_command_center_account(
            repo,
            email=args.email,
            full_name=args.full_name,
            brand=args.brand or "OASIS AI",
            mrr_target=args.mrr_target,
            primary_agent=args.primary_agent or "bravo",
            prefer_oauth=getattr(args, "prefer_oauth", False),
        )
        payload = {"command_center_account": {"ok": ok, "detail": detail}}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            mark = "+" if ok else "!"
            print(f"  [{mark}] command-center: {detail}")
        return 0 if ok else 1

    # --install-deps mode: short-circuit to dep install only.
    # Both install.ps1 and install.sh call this one path — no duplication
    # of the subprocess invocations in shell.
    if getattr(args, "install_deps", False):
        py_ok, py_detail = install_python_deps(repo)
        node_ok, node_detail = install_node_deps(repo)
        mcp_ok, mcp_detail = install_mcp_config(repo)
        payload = {
            "python_deps": {"ok": py_ok, "detail": py_detail},
            "node_deps":   {"ok": node_ok, "detail": node_detail},
            "mcp_config":  {"ok": mcp_ok, "detail": mcp_detail},
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            py_mark = "+" if py_ok else "!"
            node_mark = "+" if node_ok else "!"
            mcp_mark = "+" if mcp_ok else "!"
            print(f"  [{py_mark}] python: {py_detail}")
            print(f"  [{node_mark}] node:   {node_detail}")
            print(f"  [{mcp_mark}] mcp:    {mcp_detail}")
        return 0 if (py_ok and node_ok and mcp_ok) else 1

    report: dict = {"home": str(home), "repo": str(repo), "actions": []}

    # Prereqs (report only) — kept in sync with install.sh / install.ps1
    # which both require python, git, node, AND npm.
    prereqs = check_prereqs()
    report["prereqs"] = prereqs
    missing_required = [k for k in ("python", "git", "node", "npm") if not prereqs.get(k)]
    if missing_required:
        report["actions"].append(f"missing required tools: {missing_required}")

    if args.check:
        print(json.dumps(report, indent=2))
        return 0 if not missing_required else 2

    # Create tree + profiles + seed config
    ensure_home(home)
    report["actions"].append(f"home ensured: {home}")
    report["subdirs"] = [s for s in SUBDIRS if (home / s).exists()]

    # Env template (keys only)
    env_source = Path(args.env_file).expanduser() if args.env_file else (repo / ".env.agents")
    if env_source.exists():
        keys = extract_env_keys(env_source)
        written = write_env_template(keys, home / ".env.template")
        report["env_keys_extracted"] = len(keys)
        report["actions"].append(
            f"env template {'written' if written else 'preserved (populated)'}: {len(keys)} keys"
        )
    else:
        report["actions"].append(
            f"env source not found: {env_source} (skipping template)"
        )

    # Shim
    if not args.no_shim:
        shim = write_shim(home, repo)
        report["shim"] = str(shim)
        report["actions"].append(f"shim: {shim}")

    # Output
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"bravo home: {home}")
        for action in report["actions"]:
            print(f"  {action}")
        if missing_required:
            print(f"\nWARNING: missing required tools: {missing_required}")
            print("  Install them and re-run this script.")
            return 2
        print(f"\nNext: add {home / 'bin'} to PATH, then run:  bravo doctor")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="install/bootstrap.py",
        description="Bravo install bootstrap — idempotent, secrets-safe",
    )
    parser.add_argument("--home", default=str(DEFAULT_HOME),
                        help=f"Bravo home directory (default: {DEFAULT_HOME})")
    parser.add_argument("--repo", default=str(REPO_ROOT),
                        help="Repository root (default: detected)")
    parser.add_argument("--env-file", default=None,
                        help="Source env file for keys (default: <repo>/.env.agents)")
    parser.add_argument("--no-shim", action="store_true",
                        help="Skip installing the bravo shim into ~/.bravo/bin")
    parser.add_argument("--check", action="store_true",
                        help="Check prereqs and exit without writing anything")
    parser.add_argument("--install-deps", action="store_true",
                        help="Install Python + Node package dependencies "
                             "(pip install -r requirements.txt + npm install). "
                             "Both idempotent; safe to re-run.")
    parser.add_argument("--verify-requirements", action="store_true",
                        help="Pip dry-run the resolver (ignores existing installs) "
                             "to catch conflicts BEFORE committing pin changes. "
                             "Returns non-zero on conflict.")
    parser.add_argument("--create-command-center-account", action="store_true",
                        help="Register the operator with the OASIS AI Agent "
                             "Command Center (idempotent). Requires --email "
                             "and --full-name. Uses /api/auth/provision-cli.")
    parser.add_argument("--prefer-oauth", action="store_true",
                        help="Don't send an invite email; operator will sign in "
                             "with Google instead.")
    parser.add_argument("--email", default=None,
                        help="Operator email (used by --create-command-center-account)")
    parser.add_argument("--full-name", default=None,
                        help="Operator full name")
    parser.add_argument("--brand", default=None,
                        help="Brand name (defaults to OASIS AI)")
    parser.add_argument("--mrr-target", type=float, default=5000.0,
                        help="MRR target in USD (default: 5000)")
    parser.add_argument("--primary-agent", default="bravo",
                        help="Primary agent name (default: bravo)")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON report")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
