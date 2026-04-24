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


def install_python_deps(repo_root: Path) -> tuple[bool, str]:
    """Run `pip install -r requirements.txt` if that file exists.

    Idempotent — pip skips already-satisfied packages on its own, but
    this helper short-circuits early when the file is absent. Returns
    (ok, detail) so both shell installers can print consistent messaging.
    """
    req = repo_root / "requirements.txt"
    if not req.exists():
        return True, "no requirements.txt — skipped"
    import subprocess
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "--disable-pip-version-check", "-r", str(req)],
            timeout=900)
        if r.returncode == 0:
            return True, "installed (pip skips already-satisfied)"
        return False, f"pip exit {r.returncode}"
    except Exception as exc:  # noqa: BLE001
        return False, f"pip error: {exc}"


def install_node_deps(repo_root: Path) -> tuple[bool, str]:
    """Run `npm install` at repo root if package.json exists.

    Idempotent — npm checks node_modules and only installs missing
    packages. Returns (ok, detail) for consistent shell output.
    """
    pkg = repo_root / "package.json"
    if not pkg.exists():
        return True, "no package.json — skipped"
    import subprocess
    try:
        r = subprocess.run(
            ["npm", "install", "--silent", "--no-audit", "--no-fund"],
            cwd=str(repo_root), timeout=900,
            shell=(os.name == "nt"))  # Windows needs shell for `npm.cmd`
        if r.returncode == 0:
            return True, "installed (npm skips already-installed)"
        return False, f"npm exit {r.returncode}"
    except Exception as exc:  # noqa: BLE001
        return False, f"npm error: {exc}"


def run(args: argparse.Namespace) -> int:
    home = Path(args.home).expanduser()
    repo = Path(args.repo).expanduser() if args.repo else REPO_ROOT

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
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON report")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
