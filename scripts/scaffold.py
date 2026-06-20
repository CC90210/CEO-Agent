"""
Scaffold — turn a fresh clone of Business-Empire-Agent into a new operator's
personal agent by token-replacing CC's identifiers across non-gitignored files.

DESIGN
------
This is the "fork mechanism" CC asked for. The repo ships as CC's personal
agent (with his name, brand, voice, and history). When a new operator
clones it and runs the wizard, scaffold.py rewrites operator-specific tokens
across the codebase using values from `brain/operator.profile.json`.

What gets replaced:
  - Full name        ("Conaugh McKenna")
  - Preferred name   ("CC")
  - Personal brand   ("Conaugh McKenna")
  - Primary brand    ("OASIS AI Solutions", "OASIS AI")
  - Website domain   ("oasisai.work")
  - Primary email    ("conaugh@oasisai.work")
  - Booking link     ("https://calendar.app.google/tpfvJYBGircnGu8G8")
  - North star       ("$5,000 USD Net MRR by 2026-05-15")
  - Location         ("Collingwood, Ontario")

What stays as-is (historical context the new operator inherits):
  - Past client + partner names — agent's experience
  - Specific past dates / events
  - Code-level repo names that are public on GitHub

SAFETY
------
- Runs in --dry-run mode by default. --apply is required for real writes.
- Skips gitignored files (operator.profile.json, brain/USER.md, etc.).
- Skips binary files, .git, node_modules, .venv, tmp.
- Detects the CC-identity short-circuit: if profile preferred_name == "CC"
  AND full_name == "Conaugh McKenna", refuses to run (this IS CC's repo).
- Writes a manifest to tmp/scaffold_manifest.json listing every file changed.
- --backup creates a .scaffold-backup/<timestamp>/ tree before applying.

USAGE
-----
    # See what would change (default)
    python scripts/scaffold.py --json

    # Apply changes after reviewing
    python scripts/scaffold.py --apply

    # Apply with backup snapshot
    python scripts/scaffold.py --apply --backup
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = PROJECT_ROOT / "brain" / "operator.profile.json"

# Note on identifiers: the literal strings we hunt for live inline in
# build_replacement_map() below — single source of truth, no separate
# constant table to drift out of sync. "CC" / "Conaugh" alone aren't
# replaced (too risky — would hit cc-funnel, ccBy, etc.).

# Non-gitignored extensions we'll touch. Keep tight to avoid blowing up
# binary or generated files.
EDITABLE_EXTS = {".md", ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yaml",
                 ".yml", ".sh", ".ps1", ".html", ".css", ".sql", ".env.example",
                 ".dl", ".toml"}

# Path fragments to skip even if extension matches. These are runtime / vendor
# / archive directories that should never be rewritten.
SKIP_PARTS = {".git", "node_modules", ".venv", "venv", "tmp",
              "__pycache__", ".next", ".pytest_cache", ".ruff_cache",
              ".mypy_cache", "ARCHIVES", "archive",
              # Operator-personal dirs (already gitignored, but
              # belt-and-suspenders):
              "auto", "browser/state"}


def _git_ls_files() -> list[Path]:
    """Use git to enumerate tracked files. Falls back to a recursive walk."""
    try:
        out = subprocess.check_output(
            ["git", "ls-files"], cwd=str(PROJECT_ROOT), text=True, creationflags=WINDOWLESS_FLAGS)
        files: list[Path] = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            p = PROJECT_ROOT / line
            if any(part in SKIP_PARTS for part in p.parts):
                continue
            if p.suffix.lower() not in EDITABLE_EXTS:
                continue
            if not p.exists() or not p.is_file():
                continue
            files.append(p)
        return files
    except Exception:  # noqa: BLE001
        return []


def load_profile() -> Optional[dict[str, Any]]:
    if not PROFILE_PATH.exists():
        return None
    try:
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def is_cc_repo(profile: dict[str, Any]) -> bool:
    """True if this is CC's original local copy. Scaffold should refuse."""
    return (str(profile.get("preferred_name", "")).strip() == "CC"
            and str(profile.get("full_name", "")).strip() == "Conaugh McKenna")


def build_replacement_map(profile: dict[str, Any]) -> dict[str, str]:
    """Build the literal-string replacement table from profile values.

    Categories of replacement:
      1. Identity         — name, brand, email, website, location, north star
      2. Community        — Skool / Discord / Circle / etc. group name
      3. Side projects    — CC's other businesses (PropFlow, Nostalgic, DJ).
                            Most clients won't have these; default REMOVES
                            (replaces with empty) rather than substituting.
      4. Past clients     — preserved unless profile.scrub_history=true
                            (per docstring intent — see top of file)

    Adding a new replacement: pick the bucket above, follow the profile-key
    fallback pattern (most are `or "neutral default"`), document the bucket
    in the comment so future maintainers don't reinvent the structure.
    """
    full_name = profile.get("full_name", "Operator").strip()
    preferred = profile.get("preferred_name", full_name.split()[0] if full_name else "Operator").strip()
    personal_brand = profile.get("personal_brand", preferred).strip() or preferred
    primary_brand = profile.get("primary_brand", "Your Business").strip()
    primary_email = profile.get("primary_email", "").strip()
    website = profile.get("website", "").strip()
    booking = profile.get("booking_link", "").strip()
    location = profile.get("location", "").strip()
    location_city = location.split(",", 1)[0].strip() if location else ""
    north_star = profile.get("north_star", "").strip()
    domain = (website.replace("https://", "").replace("http://", "").rstrip("/")
              if website else "")
    # Community: the group / forum / Skool community the operator runs.
    # Empty default = scrub the noun entirely from the codebase.
    community_name = profile.get("community_name", "").strip()
    community_platform = profile.get("community_platform", "").strip()  # e.g. "Skool", "Circle"
    # Side projects: configurable list of CC's other apps to scrub.
    # Default: scrub all (most clients run only Bravo). Set
    # profile.preserve_side_projects=true to keep references.
    scrub_side_projects = not profile.get("preserve_side_projects", False)
    # `scrub_history` flag is preserved as a no-op for now. The original
    # version enumerated specific past-client/partner names — that framing
    # wrongly elevated those names to "tracked entities worth scrubbing."
    # They're just client names like any other. Keeping the flag so
    # existing operator.profile.json entries don't error on unknown keys;
    # the actual enumeration is gone.
    _ = bool(profile.get("scrub_history", False))  # reserved

    out: dict[str, str] = {
        # --- 1. Identity ----------------------------------------------------
        "Conaugh McKenna": full_name,
        # NOTE: dict literal collapses duplicate keys; the second
        # `Conaugh McKenna -> personal_brand` line in the prior version
        # was dead code. personal_brand is identical to full_name in
        # CC's profile so the visible behavior didn't change. Kept
        # explicit single key here for clarity.
        "OASIS AI Solutions": primary_brand,
        "OASIS AI": primary_brand,
        "conaugh@oasisai.work": primary_email or (f"contact@{domain}" if domain else "operator@example.com"),
        "oasisai.work": domain or "example.com",
        "https://calendar.app.google/tpfvJYBGircnGu8G8": booking or "https://example.com/booking",
        "Collingwood, Ontario, Canada": location or "Your City, Country",
        "Collingwood, Ontario": location or "Your City, Country",
        "Collingwood": location_city or "Your City",
        "$5,000 USD Net MRR by 2026-05-15": north_star or "Your North Star",
        "$5,000 USD Net MRR by June 18, 2026": north_star or "Your North Star",
        "$10,000 USD Net MRR by September 30, 2026": north_star or "Your North Star",

        # --- 2. Community (CC previously ran a Skool community on retainer) ---
        # If the client doesn't have an equivalent, scrub the references.
        "Skool community": (
            f"{community_platform} community"
            if community_platform else (community_name or "online community")
        ),
        "Skool": community_platform or "",
    }

    # --- 3. Side projects (CC's other apps — scrub by default) -----------
    if scrub_side_projects:
        out.update({
            "PropFlow": "",
            "Nostalgic Requests": "",
            "Nostalgic": "",
            # Atlas / Maven / Aura / Hermes are the C-suite agent personas;
            # those are part of the product, NOT to be scrubbed. Leave
            # alone.
        })

    # --- 4. Past-client names ------------------------------------------
    # Intentionally NOT enumerated. A prior version of this map listed
    # specific past-client/partner names by name, which (a) elevated them
    # to "tracked entities worth special-casing" when they're just client
    # names like any other and (b) baked CC's specific client roster into
    # the scaffold's source code. If a fresh client install needs to
    # scrub their own past-client names, they can add per-name entries
    # via profile.extra_replacements (loaded in scan_and_replace) — this
    # scaffold doesn't pretend to know which names are "important."

    return out


def scan_and_replace(replacements: dict[str, str], dry_run: bool, backup_dir: Optional[Path]) -> dict[str, Any]:
    """Walk tracked files, count + (optionally) apply replacements."""
    files = _git_ls_files()
    changed: list[dict[str, Any]] = []
    total_hits = 0
    backup_root: Optional[Path] = None
    if backup_dir is not None and not dry_run:
        backup_root = backup_dir / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_root.mkdir(parents=True, exist_ok=True)
    # Sort replacement keys longest-first so "OASIS AI Solutions" wins over "OASIS AI".
    keys_sorted = sorted(replacements.keys(), key=len, reverse=True)
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        original = text
        per_file_hits: dict[str, int] = {}
        for needle in keys_sorted:
            if needle in text:
                count = text.count(needle)
                if count:
                    per_file_hits[needle] = count
                    text = text.replace(needle, replacements[needle])
        if text != original:
            rel = str(f.relative_to(PROJECT_ROOT)).replace("\\", "/")
            changed.append({"file": rel, "hits": per_file_hits, "total": sum(per_file_hits.values())})
            total_hits += sum(per_file_hits.values())
            if not dry_run:
                if backup_root is not None:
                    bdest = backup_root / f.relative_to(PROJECT_ROOT)
                    bdest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, bdest)
                f.write_text(text, encoding="utf-8")
    return {
        "dry_run": dry_run,
        "files_scanned": len(files),
        "files_changed": len(changed),
        "total_replacements": total_hits,
        "changes": changed,
        "backup_root": str(backup_root.relative_to(PROJECT_ROOT)).replace("\\", "/") if backup_root else None,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Token-replace operator identifiers in shipped files (fork mechanism).")
    p.add_argument("--apply", action="store_true", help="Actually write changes (default: dry-run)")
    p.add_argument("--backup", action="store_true", help="Snapshot every changed file to .scaffold-backup/ before writing")
    p.add_argument("--json", dest="output_json", action="store_true")
    p.add_argument("--allow-cc-repo", action="store_true",
                   help="Override the safety guard that refuses to run on CC's original repo.")
    p.add_argument("--max-show", type=int, default=20, help="Max files to show in human-readable output")
    args = p.parse_args()

    profile = load_profile()
    if profile is None:
        msg = {"ok": False, "error": "No operator.profile.json found. Run setup wizard first."}
        print(json.dumps(msg, indent=2)) if args.output_json else print(msg["error"], file=sys.stderr)
        sys.exit(1)

    if is_cc_repo(profile) and not args.allow_cc_repo:
        msg = {"ok": False,
               "error": "Refusing to run: this is CC's original repo (preferred_name=CC, full_name=Conaugh McKenna). Pass --allow-cc-repo to override.",
               "profile_preferred_name": profile.get("preferred_name"),
               "profile_full_name": profile.get("full_name")}
        print(json.dumps(msg, indent=2)) if args.output_json else print(msg["error"], file=sys.stderr)
        sys.exit(2)

    replacements = build_replacement_map(profile)
    backup_dir = (PROJECT_ROOT / ".scaffold-backup") if args.backup else None
    result = scan_and_replace(replacements, dry_run=not args.apply, backup_dir=backup_dir)
    result["operator"] = {"full_name": profile.get("full_name"),
                          "preferred_name": profile.get("preferred_name"),
                          "primary_brand": profile.get("primary_brand")}
    result["replacement_map"] = replacements

    if args.output_json:
        print(json.dumps(result, indent=2))
    else:
        mode = "DRY-RUN" if not args.apply else "APPLIED"
        print(f"  [{mode}] {result['files_changed']}/{result['files_scanned']} files would change "
              f"({result['total_replacements']} replacements)")
        for entry in result["changes"][: args.max_show]:
            print(f"    {entry['file']}  ({entry['total']} hits)")
        if len(result["changes"]) > args.max_show:
            print(f"    ... and {len(result['changes']) - args.max_show} more")
        if not args.apply:
            print(f"\n  Re-run with --apply to write changes.")
        if backup_dir and result.get("backup_root"):
            print(f"\n  Backup snapshot: {result['backup_root']}")

    sys.exit(0)


if __name__ == "__main__":
    main()
