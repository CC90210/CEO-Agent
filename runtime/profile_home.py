"""Profile home — manage ~/.bravo/ product runtime directory.

Hermes-equivalent of ~/.hermes/. Idempotent; never mutates .env.agents.

Layout:
    ~/.bravo/
      config.toml
      .env.template       (keys from .env.agents, empty values)
      bin/
        bravo.cmd         (Windows launcher)
        bravo             (POSIX launcher)
      profiles/
        bravo.toml
        atlas.toml
        maven.toml
        aura.toml
        hermes.toml
      sessions/
        bravo.sqlite
      logs/
      skills/
      browser/
        domain-skills/
        interaction-skills/
      cache/

Usage (library):
    from runtime.profile_home import ensure_home, list_profiles
    home = ensure_home()                   # creates tree if absent
    profiles = list_profiles()
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HOME = Path(os.path.expanduser("~/.bravo"))
CONFIG_EXAMPLE = REPO_ROOT / "config" / "bravo-config.example.toml"
ENV_SOURCE = REPO_ROOT / ".env.agents"  # read-only, keys only

SUBDIRS = [
    "bin",
    "profiles",
    "sessions",
    "logs",
    "skills",
    "browser/domain-skills",
    "browser/interaction-skills",
    "cache",
]

PROFILES = {
    "bravo": {
        "role": "business operations brain",
        "browser_allowed": True,
        "repo_path": "C:/Users/User/Business-Empire-Agent",
    },
    "atlas": {
        "role": "CFO — finance, tax, trading, budgeting",
        "browser_allowed": True,
        "repo_path": "C:/Users/User/APPS/CFO-Agent",
        "approval_required_for_money_movement": True,
    },
    "maven": {
        "role": "CMO — content, ads, funnel, brand",
        "browser_allowed": True,
        "repo_path": "C:/Users/User/CMO-Agent",
        "approval_required_for_publish": True,
        "approval_required_for_ad_budget": True,
    },
    "aura": {
        "role": "Life/Home agent — ambient, habits, routines",
        "browser_allowed": True,
        "repo_path": "C:/Users/User/AURA",
        "approval_required_for_physical_devices": True,
    },
    "hermes": {
        "role": "Client operations agent",
        "browser_allowed": True,
        "repo_path": "C:/Users/User/APPS/hermes",
        "approval_required_for_client_portals": True,
    },
}


def ensure_home(home: Path = DEFAULT_HOME) -> Path:
    """Create ~/.bravo/ tree idempotently. Returns the home path."""
    home.mkdir(parents=True, exist_ok=True)
    for sub in SUBDIRS:
        (home / sub).mkdir(parents=True, exist_ok=True)
    # Copy config example if no config.toml yet
    config_path = home / "config.toml"
    if not config_path.exists() and CONFIG_EXAMPLE.exists():
        shutil.copy2(CONFIG_EXAMPLE, config_path)
    # Write .env.template (keys only, empty values, never overwrite)
    env_template = home / ".env.template"
    if not env_template.exists() and ENV_SOURCE.exists():
        try:
            keys = _extract_env_keys(ENV_SOURCE)
            env_template.write_text(
                "# Bravo environment template — fill values locally.\n"
                "# Never commit populated .env files.\n\n"
                + "\n".join(f"{k}=" for k in keys) + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass
    # Seed profiles
    for name, settings in PROFILES.items():
        profile_path = home / "profiles" / f"{name}.toml"
        if profile_path.exists():
            continue
        profile_path.write_text(_render_profile(name, settings), encoding="utf-8")
    return home


def _extract_env_keys(env_path: Path) -> list[str]:
    """Return list of env keys from a .env file (never values)."""
    keys: list[str] = []
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" in s:
            k = s.split("=", 1)[0].strip()
            if k and k.isidentifier() or (k and all(c.isalnum() or c == "_" for c in k)):
                keys.append(k)
    return keys


def _render_profile(name: str, settings: dict) -> str:
    lines = [f"# Bravo profile: {name}", "", "[profile]", f'name = "{name}"']
    for k, v in settings.items():
        if isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        else:
            lines.append(f"{k} = {json.dumps(v)}")
    return "\n".join(lines) + "\n"


def list_profiles(home: Path = DEFAULT_HOME) -> list[str]:
    profiles_dir = home / "profiles"
    if not profiles_dir.exists():
        return []
    return sorted(p.stem for p in profiles_dir.glob("*.toml"))


def get_active_profile(home: Path = DEFAULT_HOME) -> str:
    """Read active profile from config.toml (best-effort)."""
    config = home / "config.toml"
    if not config.exists():
        return "bravo"
    try:
        text = config.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return "bravo"
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("active"):
            parts = s.split("=", 1)
            if len(parts) == 2:
                return parts[1].strip().strip('"').strip("'")
    return "bravo"


def info(home: Path = DEFAULT_HOME) -> dict:
    return {
        "home": str(home),
        "exists": home.exists(),
        "active_profile": get_active_profile(home) if home.exists() else None,
        "profiles": list_profiles(home) if home.exists() else [],
        "config_toml": str(home / "config.toml") if (home / "config.toml").exists() else None,
        "env_template": str(home / ".env.template") if (home / ".env.template").exists() else None,
        "subdirs_present": [s for s in SUBDIRS if (home / s).exists()],
    }


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="runtime.profile_home")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init", help="Create ~/.bravo/ tree idempotently")
    p_init.add_argument("--home", default=str(DEFAULT_HOME))
    p_info = sub.add_parser("info", help="Show profile-home state")
    p_info.add_argument("--home", default=str(DEFAULT_HOME))
    p_info.add_argument("--json", action="store_true")
    p_list = sub.add_parser("list", help="List profiles")
    p_list.add_argument("--home", default=str(DEFAULT_HOME))
    args = parser.parse_args(argv)

    home = Path(args.home).expanduser()

    if args.cmd == "init":
        created = ensure_home(home)
        print(f"Bravo home ready: {created}")
        print(f"Profiles: {', '.join(list_profiles(home))}")
        return 0
    if args.cmd == "info":
        i = info(home)
        if args.json:
            print(json.dumps(i, indent=2))
        else:
            print(f"home: {i['home']} (exists: {i['exists']})")
            if i["exists"]:
                print(f"active profile: {i['active_profile']}")
                print(f"profiles: {', '.join(i['profiles'])}")
                print(f"subdirs: {len(i['subdirs_present'])}/{len(SUBDIRS)} present")
        return 0
    if args.cmd == "list":
        for name in list_profiles(home):
            marker = "*" if name == get_active_profile(home) else " "
            print(f"{marker} {name}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
