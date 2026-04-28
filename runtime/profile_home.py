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

# Force UTF-8 output on Windows (cp1252 default breaks on any non-ASCII).
if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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

# Per-profile metadata. repo_path is derived from the current user's home at
# profile-write time via _resolve_repo_path() — never hardcoded to CC's
# machine layout. When someone clones via the OASIS AI wizard, their profile
# TOML files reflect THEIR user home, not mine.
PROFILES = {
    "bravo":  {"role": "Business operations brain",
               "browser_allowed": True,
               "repo_dir_name": "bravo-repo"},
    "atlas":  {"role": "CFO — finance, tax, trading, budgeting",
               "browser_allowed": True,
               "repo_dir_name": "atlas-repo",
               "approval_required_for_money_movement": True},
    "maven":  {"role": "CMO — content, ads, funnel, brand",
               "browser_allowed": True,
               "repo_dir_name": "maven-repo",
               "approval_required_for_publish": True,
               "approval_required_for_ad_budget": True},
    "aura":   {"role": "Life/Home agent — ambient, habits, routines",
               "browser_allowed": True,
               "repo_dir_name": "aura-repo",
               "approval_required_for_physical_devices": True},
    "hermes": {"role": "Wholesale commerce + EDI compliance agent",
               "browser_allowed": True,
               "repo_dir_name": "hermes-repo",
               "approval_required_for_client_portals": True,
               "approval_required_for_pos_takeover": True,
               "supports_a2000_modes": ("mock", "api", "edi", "playwright", "desktop")},
}


def _resolve_repo_path(slug: str, settings: dict) -> str:
    """Return the expected on-disk repo path for this profile.

    Preference order:
      1. Environment override — BRAVO_REPO_PATH / ATLAS_REPO_PATH / ...
      2. The sibling clone the OASIS AI wizard uses (~/<slug>-repo)
      3. Fall back to repo_dir_name under the user home.
    """
    env_key = f"{slug.upper()}_REPO_PATH"
    env_override = os.environ.get(env_key)
    if env_override:
        return env_override
    home = Path.home()
    dir_name = settings.get("repo_dir_name", f"{slug}-repo")
    return str(home / dir_name).replace("\\", "/")


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
            # Single source of truth for env-key parsing: install/bootstrap.py
            repo_install = REPO_ROOT / "install"
            if str(repo_install) not in sys.path:
                sys.path.insert(0, str(repo_install))
            from bootstrap import extract_env_keys, write_env_template  # type: ignore
            keys = extract_env_keys(ENV_SOURCE)
            write_env_template(keys, env_template)
        except Exception:
            pass
    # Seed profiles
    for name, settings in PROFILES.items():
        profile_path = home / "profiles" / f"{name}.toml"
        if profile_path.exists():
            continue
        profile_path.write_text(_render_profile(name, settings), encoding="utf-8")
    return home


def _render_profile(name: str, settings: dict) -> str:
    lines = [f"# Bravo profile: {name}", "", "[profile]", f'name = "{name}"']
    # Compute repo_path dynamically from the current user's home — never
    # serialize a machine-specific hardcoded path into the TOML.
    repo_path = _resolve_repo_path(name, settings)
    lines.append(f'repo_path = "{repo_path}"')
    for k, v in settings.items():
        # repo_dir_name is a lookup hint for _resolve_repo_path(), not part of
        # the serialized profile.
        if k == "repo_dir_name":
            continue
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
