"""Read the Cloudflare fleet registry — config/cloudflare/apps.json.

That file is where an app's checkout directory, worker name, kind and custom
domains are recorded, and wrangler_tool.py treats it as authoritative. Every
consumer that instead types an absolute path becomes a second place the same
answer is written down — which is wrong the moment a repo moves, and simply
wrong already on the Mac, where these repos do not live under C:\\Users.

Several scripts open this file directly and predate this helper; they are not
rewritten here. New consumers should use these functions so the count does not
keep growing.

Read-only: nothing in this module writes to the registry.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "config" / "cloudflare" / "apps.json"


class AppNotRegistered(KeyError):
    """Raised with a message naming the slug AND the file, not just the key."""


def registry() -> dict:
    """The whole registry document."""
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(f"fleet registry missing: {REGISTRY_PATH}")
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def apps() -> dict[str, dict]:
    """slug -> entry, for every registered app."""
    return registry().get("apps", {})


def app(slug: str) -> dict:
    """One app's entry, or a named error rather than a bare KeyError."""
    entry = apps().get(slug)
    if entry is None:
        known = ", ".join(sorted(apps())) or "(none)"
        raise AppNotRegistered(
            f"'{slug}' is not in {REGISTRY_PATH}. Registered: {known}"
        )
    return entry


def app_dir(slug: str) -> Path:
    """Where the app's repo is checked out.

    Raises rather than returning a guess: a tool that silently falls back to a
    default path will read the wrong repo's files and report confident nonsense
    about them.
    """
    entry = app(slug)
    directory = entry.get("dir")
    if not directory:
        raise AppNotRegistered(f"'{slug}' has no 'dir' in {REGISTRY_PATH}")
    return Path(directory)
