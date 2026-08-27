"""ownership — read brain/OWNERSHIP_MAP.yaml and answer "whose surface is this?".

The map exists because "who is working on what" lived in prose and in two
agents' heads, which produced 226 co-touched files and 117 same-file cross-side
edits inside 48h across 90 days. Prose cannot be queried before an edit.

Three answers matter, and they are different:
  owner(repo, path) -> 'bravo' | 'apex' | 'shared' | None
      'shared' is not "nobody owns it" — it is the measured-contested set, where
      a lease is mandatory. None means the path is outside the map, which the
      map's `default: shared` deliberately treats as contested too: unknown is
      contested by definition.

Consumed by scripts/state/coord_guard.py (nudge on unclaimed contested edits)
and scripts/integrations/coord_claim.py (warn when claiming a peer's surface).
Kept dependency-light and failure-tolerant: a malformed or missing map degrades
to "everything is shared", never to "everything is fine".
"""
from __future__ import annotations

import json
import sys as _sys
from pathlib import Path
from typing import Any

_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import repo_paths  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = PROJECT_ROOT / "brain" / "OWNERSHIP_MAP.yaml"

_cache: dict[str, Any] | None = None


# PyYAML costs ~1s to import, and this module is consulted on EVERY Edit/Write
# via coord_guard. That made the coordination hook twice as expensive as the
# three guards beside it. The YAML stays the human-editable source of truth; a
# JSON sidecar is compiled from it on first use and reused until the YAML's
# mtime changes, so the hot path parses a small JSON and imports nothing.
CACHE_PATH = PROJECT_ROOT / "state" / "ownership_map.cache.json"


def _compile() -> dict:
    import yaml  # noqa: PLC0415
    data = yaml.safe_load(MAP_PATH.read_text(encoding="utf-8")) or {}
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".json.tmp")
        # default=str because PyYAML returns real date objects for unquoted
        # `updated: 2026-08-27`. Without it json.dumps raises TypeError, the
        # sidecar is never written, and every Edit silently pays the ~700ms
        # PyYAML import again — a cache that looks present and never caches.
        tmp.write_text(json.dumps({"mtime": MAP_PATH.stat().st_mtime, "data": data},
                                  default=str), encoding="utf-8")
        tmp.replace(CACHE_PATH)
    except Exception as e:  # noqa: BLE001
        # Do NOT swallow this. A silently-failing cache is invisible and costs a
        # second per edit forever; stderr on the CLI path is how it gets noticed.
        print(f"[ownership] WARN cache write failed ({type(e).__name__}: {e}) — "
              f"falling back to parsing YAML on every call", file=_sys.stderr)
    return data


def load(force: bool = False) -> dict:
    global _cache
    if _cache is not None and not force:
        return _cache
    try:
        if not force:
            cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            if cached.get("mtime") == MAP_PATH.stat().st_mtime:
                _cache = cached["data"]
                return _cache
    except Exception:  # noqa: BLE001
        pass
    try:
        _cache = _compile()
    except Exception:  # noqa: BLE001
        # Degrade to "contested" rather than to "unowned". A missing or malformed
        # map must not read as permission.
        _cache = {"default": "shared", "repos": {}, "agents": {}}
    return _cache


def _matches(pattern: str, path: str) -> bool:
    """Delegates to repo_paths.covers — ONE definition of "does this pattern
    cover this path", not two.

    This function used to carry its own copy. The two agreed on every vector
    tested, which is exactly how this defect hides: coverage semantics are a
    NEGOTIATED INTERFACE with APEX (contract §3.2), so the day someone updates
    covers() to match a future agreement, a private copy here would silently
    keep answering the old way and the ownership map would start disagreeing
    with the guard that enforces it.

    Same precedent as agent_activity.py importing its denylists from notify.py
    rather than copying them — that copy drifted within the hour.
    """
    return repo_paths.covers(pattern, path)


def owner(repo: str, path: str) -> str | None:
    """Most specific match wins — a longer pattern beats a broader one, so
    `components/conversations/**` (apex) is not swallowed by `**` (bravo)."""
    m = load()
    entry = (m.get("repos") or {}).get(repo)
    if not entry:
        return m.get("default")
    best: tuple[int, str] | None = None
    for who, patterns in (entry.get("owners") or {}).items():
        for pat in patterns or []:
            if _matches(str(pat), path):
                score = len(str(pat).replace("**", ""))
                if best is None or score > best[0]:
                    best = (score, who)
    return best[1] if best else m.get("default")


def is_contested(repo: str, path: str) -> bool:
    """True when a lease is mandatory before editing."""
    return owner(repo, path) == "shared"


def agent_for_git_identity(name: str) -> str | None:
    for key, meta in (load().get("agents") or {}).items():
        if name in (meta.get("git_identities") or []):
            return key
    return None


def surfaces(agent: str, repo: str) -> list[str]:
    entry = (load().get("repos") or {}).get(repo) or {}
    return list((entry.get("owners") or {}).get(agent) or [])


if __name__ == "__main__":
    sys = _sys
    if len(sys.argv) < 3:
        print("usage: ownership.py <repo> <repo-relative-path>")
        raise SystemExit(2)
    r, p = sys.argv[1], sys.argv[2]
    o = owner(r, p)
    print(f"{r}/{p} -> owner={o}" + ("  [LEASE REQUIRED]" if o == "shared" else ""))
