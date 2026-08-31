"""One reading of the credential store, shared by every tool that reads it.

Five tools had grown their own copy of this loop, and they disagreed:
`secret_disk_hunt` understood an `export KEY=` prefix and stripped surrounding
quotes; `secret_fuzzy_match`, `secret_apply_authorized` and
`public_bundle_recover` did neither. So a quoted or export-prefixed entry was
POPULATED to one tool and MISSING to another — and an applier would refuse a
source key whose value was sitting right there, reporting "not populated" about
a line it had just read.

Disagreement about what counts as populated is the whole failure mode. There is
one parser now.

Deliberately NOT unified: `secret_store_restructure.parse_pairs`. That one
rewrites the file, so it must keep values byte-exact — quotes included — and
must retain empty entries rather than dropping them. Normalising there would
silently rewrite every quoted value in the store.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["parse_text", "parse_file", "key_names"]


def parse_text(text: str) -> dict[str, str]:
    """{KEY: effective value} for every populated assignment.

    Comments, blanks and empty values are skipped — a key with no value is an
    open slot, not a credential. `export ` prefixes are honoured and one layer
    of matching surrounding quotes is removed, because both forms appear in
    real env files and both mean the same thing.
    """
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if k.lower().startswith("export "):
            k = k[7:].strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        if k and v:
            out[k] = v
    return out


def parse_file(path: Path, max_bytes: int | None = None) -> dict[str, str]:
    """parse_text over a file, returning {} for anything unreadable.

    Callers scan directories of candidate files, so an unreadable or oversized
    file must not abort the scan.
    """
    try:
        if max_bytes is not None and path.stat().st_size > max_bytes:
            return {}
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    return parse_text(text)


def key_names(text: str) -> set[str]:
    """Every assigned key name, INCLUDING ones whose value is empty.

    Distinct from parse_text: "is this key declared anywhere?" is a different
    question from "does it hold a value?", and conflating them is how a stubbed
    key reads as absent.
    """
    names: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k = line.partition("=")[0].strip()
        if k.lower().startswith("export "):
            k = k[7:].strip()
        if k:
            names.add(k)
    return names
