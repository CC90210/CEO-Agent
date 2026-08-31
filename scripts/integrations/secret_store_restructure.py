"""secret_store_restructure.py — group and sort the agents credential store.

Rewrites the store so keys are grouped by app prefix and sorted within each
group, with unprefixed/global keys in their own section.

THIS REWRITES THE FILE EVERY OTHER TOOL DEPENDS ON, so it is built to fail
rather than corrupt:

  * A timestamped backup is taken before anything is written.
  * The rewrite is verified by re-parsing the RESULT and asserting the
    key -> value mapping is byte-identical to the original. Any difference —
    a lost key, a changed value, a duplicate collapsing — ABORTS and restores
    the backup. Comparison is on values, not on a digest of the file, because
    reordering legitimately changes the file digest.
  * `# FILL` placeholder lines are preserved verbatim and kept with their group,
    so the outstanding-gap tooling keeps working.
  * Comment lines are carried with the key they precede, so the reasoning
    someone wrote next to a credential is not orphaned by sorting.

No value is printed. Output is counts and group names only.

    python scripts/integrations/secret_store_restructure.py          # preview
    python scripts/integrations/secret_store_restructure.py --apply
"""

from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import sys
from pathlib import Path

CAPABILITY_META = {
    "category": "release.cloudflare",
    "lifecycle": "active",
    "risk": "credential_store_write",
    "triggers": ["sort the agents env store", "group secrets by app prefix"],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": False},
}

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / ".env.agents"

APP_PREFIXES = (
    "ARTHRISIL_WEBSITE__", "BLUE_RISE_WEBSITE__", "BREEZEADVANCE_WEBSITE__",
    "BREEZE_PORTAL__", "IG_SETTER_PRO__", "LISTING_STUDIO__",
    "NOSTALGIC_REQUESTS__", "OASIS_AI_PLATFORM__", "OASIS_COMMAND_CENTER__",
    "OPT_IN_VAULT__", "PROPFLOW__", "SUNBIZ_FUNDING__", "TIKTIK__",
)
GLOBAL = "· global / shared (no app prefix)"


def parse_pairs(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        out[k.strip()] = v.strip()
    return out


def group_of(key: str) -> str:
    for p in APP_PREFIXES:
        if key.startswith(p):
            return p.rstrip("_")
    return GLOBAL


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    original = STORE.read_text(encoding="utf-8")
    before = parse_pairs(original)

    # Walk the file, attaching any run of comment/blank lines to the entry that
    # follows it. A trailing run with no entry after it is kept as a footer.
    entries: list[tuple[str, list[str], str]] = []   # (sort key, lines, group)
    pending: list[str] = []
    footer: list[str] = []
    for raw in original.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            if s.startswith("# FILL ") and "=" in s:
                key = s[len("# FILL "):].split("=", 1)[0].strip()
                entries.append((key, pending + [raw], group_of(key)))
                pending = []
            else:
                pending.append(raw)
            continue
        if "=" in s:
            key = s.split("=", 1)[0].strip()
            entries.append((key, pending + [raw], group_of(key)))
            pending = []
        else:
            pending.append(raw)
    footer = pending

    groups: dict[str, list[tuple[str, list[str]]]] = {}
    for key, lines, grp in entries:
        groups.setdefault(grp, []).append((key, lines))

    order = [GLOBAL] + [p.rstrip("_") for p in APP_PREFIXES if p.rstrip("_") in groups]
    order = [g for g in order if g in groups]

    print(f"{len(before)} populated keys · {len(entries)} entries · {len(groups)} groups")
    for g in order:
        fills = sum(1 for _k, ls in groups[g] if any(l.strip().startswith("# FILL ") for l in ls))
        print(f"   {g:34} {len(groups[g]):3} entries" + (f"  ({fills} outstanding)" if fills else ""))

    out: list[str] = []
    for g in order:
        out.append(f"# ===== {g} " + "=" * max(0, 62 - len(g)))
        for _key, lines in sorted(groups[g], key=lambda e: e[0]):
            out.extend(lines)
        out.append("")
    out.extend(footer)
    rebuilt = "\n".join(out).rstrip("\n") + "\n"

    after = parse_pairs(rebuilt)
    if after != before:
        lost = sorted(set(before) - set(after))
        changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
        print("\nABORT — the rewrite is not value-identical. Nothing was written.")
        if lost:
            print(f"   {len(lost)} key(s) would be LOST: {', '.join(lost[:8])}")
        if changed:
            print(f"   {len(changed)} value(s) would CHANGE: {', '.join(changed[:8])}")
        return 1
    print(f"\nverified: {len(after)} keys, all values byte-identical to the original")

    if not args.apply:
        print("preview only — re-run with --apply to write it.")
        return 0
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = STORE.with_name(f".env.agents.bak.{stamp}")
    shutil.copy2(STORE, backup)
    STORE.write_text(rebuilt, encoding="utf-8", newline="\n")

    # Re-read from disk — verifying the in-memory string is not the same as
    # verifying what actually landed.
    final = parse_pairs(STORE.read_text(encoding="utf-8"))
    if final != before:
        shutil.copy2(backup, STORE)
        print("POST-WRITE VERIFY FAILED — backup restored, store unchanged.")
        return 1
    print(f"written and re-verified from disk ({len(final)} keys). Backup taken.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
