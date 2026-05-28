"""agent_roots.py — locate sibling agent runtimes from CEO-Agent code.

CEO-Agent hosts the bridge daemon and builder tooling that need to
discover SunBiz-Agent (and future sibling tenant runtimes — Atlas,
Maven, Aura, Hermes all share the same naming pattern). This module
is the canonical resolver so the probe ladder lives in exactly one
place — duplicates across bridge_tools.py, bridge_chat_server.py, and
build_bridge_manifest.py all delegate here.

The mirror helper on the SunBiz side is
SunBiz-Agent/scripts/lib/bravo_bootstrap.py — same shape, opposite
direction. It lives on the SunBiz side because the SunBiz daemons need
it BEFORE any cross-repo import can resolve.
"""

from __future__ import annotations

import os
from pathlib import Path


def _probe(env_var: str, default_home_name: str, win_path: str) -> Path | None:
    """Generic probe: env var → ~/<default_home_name> → Windows-only
    fallback. Returns the first candidate whose scripts/ subdir exists,
    or None."""
    env = os.environ.get(env_var)
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    candidates.append(Path.home() / default_home_name)
    if os.name == "nt":
        candidates.append(Path(win_path))
    for c in candidates:
        if (c / "scripts").is_dir():
            return c
    return None


def resolve_sunbiz_root() -> Path | None:
    """Locate the SunBiz-Agent runtime root. Honors SUNBIZ_AGENT_ROOT
    env var, then ~/SunBiz-Agent, then C:\\Users\\User\\SunBiz-Agent
    on Windows. Returns None if no candidate resolves."""
    return _probe(
        env_var="SUNBIZ_AGENT_ROOT",
        default_home_name="SunBiz-Agent",
        win_path="C:/Users/User/SunBiz-Agent",
    )


def resolve_bravo_root() -> Path | None:
    """Locate CEO-Agent. Mostly useful when CEO-Agent code is being
    invoked from outside its own root (e.g. from a sidecar bundle that
    needs to find the source tree). Honors BRAVO_AGENT_ROOT, then
    ~/CEO-Agent, then C:\\Users\\User\\Business-Empire-Agent."""
    return _probe(
        env_var="BRAVO_AGENT_ROOT",
        default_home_name="CEO-Agent",
        win_path="C:/Users/User/Business-Empire-Agent",
    )
