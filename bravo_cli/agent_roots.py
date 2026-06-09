"""Per-agent repo roots — single source of truth for the bridge.

When the chat widget targets `localhost:9100/chat?agent=atlas`, the bridge
resolves the agent to one of these directories, reads its entry brain file,
and runs the chat from inside that working directory.

Resolution order:
  1. Env override (BRAVO_AGENT_ROOT_<AGENT_SLUG>) — e.g. BRAVO_AGENT_ROOT_BRAVO=/some/path
  2. Default tilde paths below
  3. None — agent is "not paired locally" and the widget falls back to the
     cloud /api/chat path

The brain entry file per agent is the FIRST file found from the
ENTRY_CANDIDATES list inside the resolved root.
"""

from __future__ import annotations

import os
from pathlib import Path

HOME = Path.home()

# Default repo paths. Mirrors lib/agent-roots.ts in the oasis-command-center repo.
# Order matters: first existing path wins. CEO-Agent listed before the legacy
# Business-Empire-Agent so post-rename machines resolve to the current name.
DEFAULTS: dict[str, list[Path]] = {
    "bravo": [
        HOME / "CEO-Agent",
        HOME / "Business-Empire-Agent",
        Path.cwd() if (Path.cwd() / "brain" / "SOUL.md").exists() else HOME,
    ],
    "atlas": [
        HOME / "APPS" / "CFO-Agent",
        HOME / "CFO-Agent",
    ],
    "maven": [
        HOME / "CMO-Agent",
        HOME / "APPS" / "CMO-Agent",
    ],
    "aura": [
        HOME / "AURA",
        HOME / "Aura-Home-Agent",
    ],
    "hermes": [
        HOME / "hermes",
        HOME / "APPS" / "hermes",
    ],
    "life-preservation": [
        HOME / "life-preservation",
        HOME / "APPS" / "life-preservation",
    ],
    # SunBiz funding agent. The interactive personas are `solara` (ops) and
    # `helios` (funding) — the dashboard chat targets those slugs, so both must
    # resolve, not just the legacy `sunbiz` repo key. /srv/sunbiz/sunbiz-agent
    # is the VPS deploy path; ~/SunBiz-Agent is the dev/Mac layout.
    "sunbiz": [
        HOME / "SunBiz-Agent",
        Path("/srv/sunbiz/sunbiz-agent"),
        Path("C:/Users/User/SunBiz-Agent"),
    ],
    "solara": [
        HOME / "SunBiz-Agent",
        Path("/srv/sunbiz/sunbiz-agent"),
        Path("C:/Users/User/SunBiz-Agent"),
    ],
    "helios": [
        HOME / "SunBiz-Agent",
        Path("/srv/sunbiz/sunbiz-agent"),
        Path("C:/Users/User/SunBiz-Agent"),
    ],
}

# Brain entry file — first one found wins. CLAUDE.md is the convention; SOUL.md
# is the older identity-only file. README.md is a last-resort signal that we
# at least found A repo, even if it isn't agent-shaped.
ENTRY_CANDIDATES = ["CLAUDE.md", "AGENTS.md", "brain/SOUL.md", "README.md"]


# Canonical env var per slug, honoured alongside the generic
# BRAVO_AGENT_ROOT_<SLUG> form. Existing SunBiz tooling sets
# SUNBIZ_AGENT_ROOT, not BRAVO_AGENT_ROOT_SUNBIZ.
LEGACY_ENV_KEYS: dict[str, str] = {
    "bravo": "BRAVO_AGENT_ROOT",
    "sunbiz": "SUNBIZ_AGENT_ROOT",
}


def resolve_root(agent_slug: str) -> Path | None:
    """Return the absolute repo root for an agent, or None if not present."""
    slug = agent_slug.lower().strip()
    candidate_env_keys = [f"BRAVO_AGENT_ROOT_{slug.upper()}"]
    legacy = LEGACY_ENV_KEYS.get(slug)
    if legacy:
        candidate_env_keys.append(legacy)
    for env_key in candidate_env_keys:
        if env_key in os.environ:
            p = Path(os.environ[env_key]).expanduser().resolve()
            if p.is_dir():
                return p
    for candidate in DEFAULTS.get(slug, []):
        try:
            p = Path(candidate).expanduser().resolve()
            if p.is_dir():
                return p
        except Exception:
            continue
    return None


def resolve_entry_file(root: Path, agent_slug: str | None = None) -> Path | None:
    """Pick the brain entry file for a given agent root.

    Resolution order:
      1. <AGENT_SLUG_UPPER>.md (e.g. HELIOS.md, SOLARA.md) — explicit
         per-agent identity file. Required when a single repo hosts
         multiple agents (SunBiz-Agent has BOTH Solara and Helios).
      2. ENTRY_CANDIDATES — CLAUDE.md, AGENTS.md, brain/SOUL.md, README.md.
         These are the fallback / single-agent-repo convention.

    Without (1), a multi-agent repo would always serve CLAUDE.md (whoever
    happens to own that file) regardless of which agent the operator
    selected — the bug that caused Helios to respond as Solara on
    2026-06-09. The per-agent file is the FIX; the fallback chain stays
    for the common case of single-agent repos (Bravo, Atlas, Maven,
    Aura, Hermes).
    """
    if agent_slug:
        agent_specific = root / f"{agent_slug.upper()}.md"
        if agent_specific.is_file():
            return agent_specific
    for rel in ENTRY_CANDIDATES:
        p = root / rel
        if p.is_file():
            return p
    return None


def claude_identity_overlay(root: Path, agent_slug: str) -> tuple[str, str]:
    """For multi-agent repos, return the identity content + suppressed settings.

    The Claude Code CLI reads the project's CLAUDE.md from cwd as its system
    prompt. When a single repo hosts MULTIPLE agents (SunBiz-Agent has BOTH
    Solara at CLAUDE.md AND Helios at HELIOS.md), picking Helios from the
    dropdown but spawning claude in that cwd makes claude read CLAUDE.md
    (Solara's identity) regardless of dropdown — that was the 2026-06-09
    identity-bleed bug where Helios responded as Solara.

    The fix: when resolve_entry_file picks a file OTHER than CLAUDE.md (the
    signal that this is a multi-agent repo and the operator picked a
    specific persona), we tell the bridge to:
      1. Read the per-agent file (HELIOS.md / SOLARA.md / etc) from disk.
      2. Pass --setting-sources=local so claude SKIPS the project CLAUDE.md.
      3. Pass --append-system-prompt=<entry_text> so the agent-specific
         identity becomes the system prompt instead.

    Returns: (identity_text, setting_sources).
      - identity_text="" + setting_sources="project,local" — single-agent
        repo (entry IS CLAUDE.md, or no entry resolved). Let claude load
        CLAUDE.md naturally — preserves existing behavior for Bravo /
        Atlas / Maven / Aura / Hermes.
      - identity_text=<entry contents> + setting_sources="local" — multi-
        agent repo (entry is HELIOS.md / SOLARA.md / etc). Suppress project
        CLAUDE.md and inject the per-agent file.
    """
    entry = resolve_entry_file(root, agent_slug)
    if entry and entry.name.upper() != "CLAUDE.MD":
        try:
            return entry.read_text(encoding="utf-8", errors="ignore"), "local"
        except Exception:
            return "", "project,local"
    return "", "project,local"


def all_resolved() -> dict[str, dict[str, str | None]]:
    """Diagnostic helper — what does each agent resolve to right now?
    Used by `bravo bridge status` and the dashboard so the operator can see
    which agents are wired locally.
    """
    out: dict[str, dict[str, str | None]] = {}
    for slug in DEFAULTS:
        root = resolve_root(slug)
        entry = resolve_entry_file(root, slug) if root else None
        out[slug] = {
            "root": str(root) if root else None,
            "entry": str(entry) if entry else None,
        }
    return out


def under_root(root: Path, candidate: Path) -> bool:
    """Path-traversal guard — `candidate` must resolve INSIDE `root`.
    Used by the read_file tool so the chat agent can never read outside
    its own repo.
    """
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False
