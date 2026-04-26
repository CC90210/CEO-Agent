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
from pathlib import Path

SIBLING_REPOS: dict[str, Path] = {
    "bravo": Path(os.environ.get("BRAVO_REPO", r"C:\Users\User\Business-Empire-Agent")),
    "maven": Path(os.environ.get("MAVEN_REPO", r"C:\Users\User\CMO-Agent")),
    "atlas": Path(os.environ.get("ATLAS_REPO", r"C:\Users\User\APPS\CFO-Agent")),
    "aura":  Path(os.environ.get("AURA_REPO",  r"C:\Users\User\AURA")),
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
        # -> Path("C:/Users/User/CMO-Agent/scripts/late_tool.py")

    Returns None if the agent's repo isn't installed.
    """
    repo = repo_for(agent)
    if repo is None:
        return None
    return repo.joinpath(*parts)