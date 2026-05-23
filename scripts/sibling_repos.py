"""Shared sibling-agent repo path resolver.

Bravo, Maven (CMO-Agent), Atlas (CFO-Agent), and Aura each live in
their own repo. Cross-agent operations — agent_inbox cross-repo posting,
ceo_dashboard subprocessing to Maven's late_tool, future Atlas runway
queries — all need to know where each sibling lives on disk.

Single source of truth so the same paths/env-overrides aren't duplicated
across multiple scripts. Override per machine via env vars in
.env.agents (or process env): BRAVO_REPO, MAVEN_REPO, ATLAS_REPO, AURA_REPO.

Public API:
    SIBLING_REPOS  -- dict[str, Path] keyed by lowercased agent name
    repo_for(name) -> Path | None
    script_in(agent, *parts) -> Path | None
        Returns Path to a script in a sibling repo, or None if the repo
        isn't installed on this machine (caller should fall back gracefully).
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

# Platform-aware defaults. Windows is CC's primary; Mac is the travel rig.
# Env var overrides (BRAVO_REPO, MAVEN_REPO, ...) always win — set them in
# .env.agents or process env when a sibling lives somewhere non-standard.
_IS_MAC = platform.system() == "Darwin"
_HOME = Path(os.path.expanduser("~"))

if _IS_MAC:
    _BRAVO_DEFAULT = _HOME / "CEO-Agent"
    _MAVEN_DEFAULT = _HOME / "CMO-Agent"
    _ATLAS_DEFAULT = _HOME / "APPS" / "CFO-Agent"
    _AURA_DEFAULT = _HOME / "AURA"
    _LIFE_DEFAULT = _HOME / "life-preservation"
    _DASHBOARD_DEFAULT = _HOME / "oasis-command-center"
else:
    _BRAVO_DEFAULT = Path(r"C:\Users\User\CEO-Agent")
    _MAVEN_DEFAULT = Path(r"C:\Users\User\CMO-Agent")
    _ATLAS_DEFAULT = Path(r"C:\Users\User\APPS\CFO-Agent")
    _AURA_DEFAULT = Path(r"C:\Users\User\AURA")
    _LIFE_DEFAULT = Path(r"C:\Users\User\life-preservation")
    _DASHBOARD_DEFAULT = Path(r"C:\Users\User\APPS\oasis-command-center")

SIBLING_REPOS: dict[str, Path] = {
    "bravo": Path(os.environ.get("BRAVO_REPO", str(_BRAVO_DEFAULT))),
    "maven": Path(os.environ.get("MAVEN_REPO", str(_MAVEN_DEFAULT))),
    "atlas": Path(os.environ.get("ATLAS_REPO", str(_ATLAS_DEFAULT))),
    "aura":  Path(os.environ.get("AURA_REPO",  str(_AURA_DEFAULT))),
    "life-preservation": Path(
        os.environ.get("LIFE_PRESERVATION_REPO", str(_LIFE_DEFAULT))
    ),
    # The OASIS Command Center dashboard repo. Strictly speaking it's a
    # consumer rather than a sibling agent — but it lives next to the
    # agent repos on disk and many scripts need to locate it, so it goes
    # through the same resolver to avoid path duplication.
    "oasis-command-center": Path(
        os.environ.get("COMMAND_CENTER_REPO", str(_DASHBOARD_DEFAULT))
    ),
}


def repo_for(name: str) -> Path | None:
    """Return the repo path for a sibling agent if it exists on disk.

    Returns None for unknown names or for repos not present on this
    machine — callers MUST handle the None case (graceful degradation).
    """
    repo = SIBLING_REPOS.get(name.lower())
    if repo and repo.exists():
        return repo
    return None


def script_in(agent: str, *parts: str) -> Path | None:
    """Resolve a path inside a sibling agent's repo.

    Example:
        script_in("maven", "scripts", "late_tool.py")
        # -> Windows: Path("C:/Users/User/CMO-Agent/scripts/late_tool.py")
        # -> Mac:     Path("/Users/<user>/CMO-Agent/scripts/late_tool.py")

    Returns None if the agent's repo isn't installed.
    """
    repo = repo_for(agent)
    if repo is None:
        return None
    return repo.joinpath(*parts)