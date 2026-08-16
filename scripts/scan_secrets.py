#!/usr/bin/env python3
"""Secret scanner — hunt for leaked credentials before they hit GitHub.

Runs in two modes:

1. Working-tree scan (default)
   Walks every tracked file + every untracked-but-not-gitignored file and
   checks against a library of known secret shapes.

2. History scan (--history)
   Walks every commit in all branches/tags and flags any commit that
   introduced content matching a secret shape. Use this after you've
   already leaked something once — it tells you which commit to scrub.

Exit codes:
    0  = no secrets found
    1  = secrets found (details printed)
    2  = tool error (no scan performed)

Usage:
    python scripts/scan_secrets.py                    # quick tree scan
    python scripts/scan_secrets.py --history          # full git history
    python scripts/scan_secrets.py --json             # machine-readable
    python scripts/scan_secrets.py --path ../CMO-Agent # scan a sibling repo

Add-ons for future hardening (deliberately not done here to stay stdlib-only):
    - Pre-commit hook wiring (simple one-liner in .git/hooks/pre-commit)
    - Allowlist for known-safe test fixtures
    - Integration with GitGuardian or trufflehog for deeper scans
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterator
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Secret shapes ─────────────────────────────────────────────────────────────
#
# Each rule: (display name, regex, minimum length to consider a match).
# Regex match is case-sensitive by default — that helps cut false positives.
# We explicitly avoid matching placeholder strings like "INSERT_YOUR_KEY".

SECRET_RULES: list[tuple[str, re.Pattern[str]]] = [
    # AI providers
    ("Anthropic API key",
     re.compile(r"\bsk-ant-(?:api03|oat01|admin01)-[A-Za-z0-9_\-]{60,}")),
    ("OpenAI API key",
     re.compile(r"\bsk-(?!ant-)(?!proj-)[A-Za-z0-9]{30,}")),
    ("OpenAI project key",
     re.compile(r"\bsk-proj-[A-Za-z0-9_\-]{40,}")),
    ("Google API key",
     re.compile(r"\bAIza[A-Za-z0-9_\-]{35}\b")),
    # Source control / infra
    ("GitHub personal access token",
     re.compile(r"\bghp_[A-Za-z0-9]{36,}")),
    ("GitHub OAuth token",
     re.compile(r"\bgho_[A-Za-z0-9]{36,}")),
    ("GitHub fine-grained PAT",
     re.compile(r"\bgithub_pat_[A-Za-z0-9_]{80,}")),
    # Cloud / platform
    ("Supabase service role (sbp_)",
     re.compile(r"\bsbp_[A-Za-z0-9]{40,}")),
    ("Stripe live secret key",
     re.compile(r"\bsk_live_[A-Za-z0-9]{24,}")),
    ("Stripe test secret key",
     re.compile(r"\bsk_test_[A-Za-z0-9]{24,}")),
    ("Stripe restricted key",
     re.compile(r"\brk_(?:live|test)_[A-Za-z0-9]{24,}")),
    ("AWS access key id",
     re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    # Chat / messaging
    ("Slack bot token",
     re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("Discord bot token (3-part)",
     re.compile(r"\b[MN][A-Za-z0-9]{23}\.[A-Za-z0-9_\-]{6}\.[A-Za-z0-9_\-]{27,}")),
    ("Telegram bot token",
     re.compile(r"\b\d{6,}:[A-Za-z0-9_\-]{30,}")),
    ("Twilio account SID",
     re.compile(r"\bAC[a-f0-9]{32}\b")),
    # Meta / Facebook (this incident's flavor)
    ("Facebook access token (EAA)",
     re.compile(r"\bEAA[A-Za-z0-9]{100,}")),
    ("Meta app_id|app_secret access token",
     re.compile(r"\b\d{14,20}\|[A-Za-z0-9]{20,40}\b")),
    # Generic catches
    ("Private key block",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----")),
    ("PGP private key block",
     re.compile(r"-----BEGIN PGP PRIVATE KEY BLOCK-----")),
    ("JWT",
     re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    # Human-style passwords do not match provider-token shapes, but a literal
    # fallback for a sensitive environment key is still a credential leak.
    ("Hardcoded sensitive env fallback", re.compile(
        r"(?:os\.environ\.get|os\.getenv)\(\s*[\"']"
        r"(?P<env_key>[A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY)[A-Z0-9_]*)"
        r"[\"']\s*,\s*[\"'](?P<env_fallback>[^\"'\r\n]{8,})[\"']\s*\)",
        re.IGNORECASE,
    )),
]

HISTORICAL_SECRET_FILENAME_RE = re.compile(
    r"(^|/)\.env(?:\.|$)|\.(?:pem|key|p12|pfx)$|credentials\.json$|"
    r"service_account.*\.json$|(?:^|/)(?:id_rsa|id_ed25519)$",
    re.IGNORECASE,
)
HISTORICAL_FILENAME_ALLOW_RE = re.compile(
    r"\.(?:template|example|sample|dist)$", re.IGNORECASE
)

# Filename substrings that ALWAYS warrant a flag (like `.long_lived_token.txt`
# — even if the contents happen to look innocent, a file named like this
# almost certainly holds a secret).
SUSPICIOUS_FILENAMES = [
    "long_lived_token",
    "_token.txt",
    "_token.json",
    "credentials.json",
    "service_account.json",
    "id_rsa",
    "id_ed25519",
]

SELF_SCANNER_PATH = "scripts/scan_secrets.py"
SELF_SCANNER_SAFE_LITERALS = (
    're.compile(r"-----BEGIN PGP PRIVATE KEY BLOCK-----")',
)

# Don't scan binary / large / irrelevant extensions.
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".mp3", ".mp4", ".mov",
    ".zip", ".tar", ".gz", ".7z", ".exe", ".dll", ".so", ".dylib", ".wasm",
    ".pyc", ".pyo", ".whl", ".egg", ".ttf", ".otf", ".woff", ".woff2",
    ".ico", ".icns", ".ldb", ".db-wal", ".sqlite-shm",
}

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".next", ".nuxt", ".cache", ".claude/worktrees",
}

GIT_BLOB_BATCH_BYTES = 16 * 1024 * 1024
MAX_SCAN_BLOB_BYTES = 64 * 1024 * 1024
MAX_INDEX_SNAPSHOT_BYTES = 256 * 1024 * 1024


def _git_cmd(args: list[str], cwd: Path) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=120,
         creationflags=WINDOWLESS_FLAGS)
        return r.returncode, r.stdout or ""
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def _git_bytes(
    args: list[str], cwd: Path, *, input_bytes: bytes | None = None
) -> bytes:
    """Run Git without text decoding so NUL-delimited paths remain exact."""
    env = dict(os.environ)
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            input=input_bytes,
            capture_output=True,
            timeout=120,
            creationflags=WINDOWLESS_FLAGS,
            env=env,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"git {' '.join(args)} failed") from exc
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed")
    return completed.stdout


def _decode_git_path(raw: bytes) -> str:
    # Git's raw ``-z`` output already uses repository-style separators.
    # Rewriting backslashes would corrupt a legal literal backslash in a Unix
    # filename and disconnect the index representation from its worktree path.
    return raw.decode("utf-8", errors="surrogateescape")


def _git_ls_files_z(repo_root: Path, *args: str) -> list[str]:
    output = _git_bytes(
        ["-c", "core.quotepath=false", "ls-files", *args, "-z"],
        repo_root,
    )
    return [_decode_git_path(raw) for raw in output.split(b"\0") if raw]


def _is_ignored(path: Path, repo_root: Path) -> bool:
    rc, _ = _git_cmd(["check-ignore", "-q", str(path)], cwd=repo_root)
    return rc == 0


def _iter_tree_files(repo_root: Path) -> Iterator[Path]:
    """Yield every file that git would include (tracked OR untracked-not-ignored).

    We ask git directly rather than walking the filesystem so gitignored
    content (.venv, node_modules, tmp/, browser caches) is skipped cleanly.
    A gitignored file cannot leak via git, so there's no reason to scan it —
    and Chromium caches in tmp/ produce endless false positives otherwise.
    """
    cached = set(_git_ls_files_z(repo_root, "--cached"))
    for normalized in _git_ls_files_z(
        repo_root, "--cached", "--others", "--exclude-standard"
    ):
        # Never exempt a tracked path: once content is in Git, directory names
        # such as dist/ or node_modules/ are not a security boundary. Cache and
        # vendor skips apply only to untracked content.
        parts = normalized.split("/")
        skipped_untracked_dir = any(
            skip in parts if "/" not in skip else normalized.startswith(skip + "/")
            for skip in SKIP_DIRS
        )
        if normalized not in cached and skipped_untracked_dir:
            continue
        # Keep Git's lexical path. Resolving here follows symlinks, which can
        # both escape the repository and make the raw staged path disappear
        # from cached-path comparisons on Unix.
        p = repo_root / Path(normalized)
        if normalized not in cached and p.suffix.lower() in SKIP_EXTENSIONS:
            continue
        yield p


def _cached_tree_paths(repo_root: Path) -> set[str]:
    """Return normalized paths present in Git's index.

    The index and worktree are separate security boundaries: a staged secret
    can be hidden by a later clean worktree edit, while an unstaged secret can
    be absent from the index. Callers must inspect both representations.
    """
    return set(_git_ls_files_z(repo_root, "--cached"))


def _git_object_info(repo_root: Path, oids: list[bytes]) -> dict[bytes, tuple[bytes, int]]:
    """Return raw object type and size for each requested object id."""
    if not oids:
        return {}
    output = _git_bytes(
        ["cat-file", "--batch-check"],
        repo_root,
        input_bytes=b"".join(oid + b"\n" for oid in oids),
    )
    lines = output.splitlines()
    if len(lines) != len(oids):
        raise RuntimeError("git cat-file metadata count mismatch")
    info: dict[bytes, tuple[bytes, int]] = {}
    for requested_oid, line in zip(oids, lines):
        fields = line.split()
        if len(fields) != 3 or fields[0] != requested_oid:
            raise RuntimeError("invalid git cat-file metadata")
        try:
            size = int(fields[2])
        except ValueError as exc:
            raise RuntimeError("invalid git object size") from exc
        info[requested_oid] = (fields[1], size)
    return info


def _read_raw_git_blobs(repo_root: Path, oids: list[bytes]) -> dict[bytes, bytes]:
    """Read exact blob bytes for *oids* through one cat-file batch."""
    if not oids:
        return {}
    batch_output = _git_bytes(
        ["cat-file", "--batch"],
        repo_root,
        input_bytes=b"".join(oid + b"\n" for oid in oids),
    )
    blobs: dict[bytes, bytes] = {}
    cursor = 0
    for requested_oid in oids:
        header_end = batch_output.find(b"\n", cursor)
        if header_end < 0:
            raise RuntimeError("truncated git cat-file header; scan incomplete")
        header = batch_output[cursor:header_end].split()
        cursor = header_end + 1
        if (
            len(header) != 3
            or header[0] != requested_oid
            or header[1] != b"blob"
        ):
            raise RuntimeError("git cat-file returned an unexpected index object")
        try:
            size = int(header[2])
        except ValueError as exc:
            raise RuntimeError("invalid git cat-file size") from exc
        end = cursor + size
        if end > len(batch_output) or batch_output[end:end + 1] != b"\n":
            raise RuntimeError("truncated git blob; scan incomplete")
        blobs[requested_oid] = batch_output[cursor:end]
        cursor = end + 1
    return blobs


def _oid_batches(
    oids: list[bytes], sizes: dict[bytes, int]
) -> Iterator[list[bytes]]:
    """Yield bounded cat-file requests without silently skipping large blobs."""
    batch: list[bytes] = []
    batch_size = 0
    for oid in oids:
        size = sizes[oid]
        if batch and (
            batch_size + size > GIT_BLOB_BATCH_BYTES or len(batch) >= 128
        ):
            yield batch
            batch = []
            batch_size = 0
        batch.append(oid)
        batch_size += size
    if batch:
        yield batch


def _read_index_snapshot(
    repo_root: Path, paths: set[str]
) -> tuple[dict[str, str], set[str], set[str]]:
    """Read raw index blobs in one batch, bypassing checkout/smudge filters."""

    stage_output = _git_bytes(
        ["-c", "core.quotepath=false", "ls-files", "--stage", "-z"],
        repo_root,
    )
    entries: dict[str, tuple[bytes, bytes]] = {}
    gitlinks: set[str] = set()
    symlinks: set[str] = set()
    unresolved: set[str] = set()
    for record in stage_output.split(b"\0"):
        if not record:
            continue
        metadata, separator, raw_path = record.partition(b"\t")
        fields = metadata.split()
        if not separator or len(fields) != 3:
            raise RuntimeError("could not parse git index; tree scan incomplete")
        mode, oid, stage = fields
        rel = _decode_git_path(raw_path)
        if stage != b"0":
            unresolved.add(rel)
            continue
        if mode == b"160000":
            gitlinks.add(rel)
            continue
        if mode == b"120000":
            symlinks.add(rel)
        entries[rel] = (mode, oid)

    conflicted = paths & unresolved
    if conflicted:
        raise RuntimeError(
            f"unmerged staged file {sorted(conflicted)[0]}; tree scan incomplete"
        )
    missing = paths - set(entries) - gitlinks
    if missing:
        raise RuntimeError(
            f"staged file missing from raw index: {sorted(missing)[0]}"
        )

    requested_oids = sorted({entries[rel][1] for rel in paths if rel in entries})
    object_info = _git_object_info(repo_root, requested_oids)
    blob_sizes: dict[bytes, int] = {}
    for oid in requested_oids:
        kind, size = object_info.get(oid, (b"", 0))
        if kind != b"blob":
            raise RuntimeError("git index referenced a non-blob object")
        if size > MAX_SCAN_BLOB_BYTES:
            raise RuntimeError(
                f"staged blob {oid[:12].decode('ascii', errors='replace')} is "
                f"{size} bytes; scan refused to load it"
            )
        blob_sizes[oid] = size
    aggregate_size = sum(blob_sizes.values())
    if aggregate_size > MAX_INDEX_SNAPSHOT_BYTES:
        raise RuntimeError(
            f"staged snapshot is {aggregate_size} bytes; scan limit is "
            f"{MAX_INDEX_SNAPSHOT_BYTES} bytes"
        )
    decoded_blobs: dict[bytes, str] = {}
    for oid_batch in _oid_batches(requested_oids, blob_sizes):
        raw_batch = _read_raw_git_blobs(repo_root, oid_batch)
        for oid, raw in raw_batch.items():
            decoded_blobs[oid] = _decode_scan_bytes(raw)

    snapshot = {rel: "" for rel in paths & gitlinks}
    for rel in paths & set(entries):
        snapshot[rel] = decoded_blobs[entries[rel][1]]
    return snapshot, gitlinks, symlinks


def _decode_scan_bytes(data: bytes) -> str:
    """Decode likely source/config text without making UTF-16 a blind spot.

    ASCII-shaped credentials remain visible under UTF-8-compatible encodings.
    NUL-bearing content is additionally decoded as UTF-16/32 in both byte
    orders so a text file with a missing or unusual BOM cannot bypass regexes.
    """
    candidates = [data.decode("utf-8-sig", errors="ignore")]
    has_unicode_bom = data.startswith(
        (b"\xff\xfe", b"\xfe\xff", b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")
    )
    if has_unicode_bom or b"\x00" in data:
        for encoding in ("utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"):
            try:
                decoded = data.decode(encoding, errors="ignore")
            except (UnicodeDecodeError, UnicodeError):
                continue
            if decoded not in candidates:
                candidates.append(decoded)
    return "\n".join(candidates)


def _is_explicit_placeholder(rule_name: str, matched: str) -> bool:
    """Allow only unmistakable documentation fixtures, never substrings."""
    if rule_name == "Hardcoded sensitive env fallback":
        return False
    if (rule_name, matched) == (
        "Telegram bot token",
        "123456789:ABCdefGHIjklMNOPQRSTUV-EXAMPLE",
    ):
        return True
    upper = matched.upper()
    if "EXAMPLE" in upper and "PLACE-ME" in upper:
        return True
    if upper.endswith(("YOUR_API_KEY_HERE", "INSERT_YOUR_APP_SECRET")):
        return True
    # Conventional all-X provider examples remain safe without allowing a
    # production token that merely contains one placeholder-looking word.
    payload = re.sub(r"^(?:SK-(?:PROJ-)?|XOX[BAPRS]-)", "", upper)
    return len(payload) >= 12 and set(payload) <= {"X", "-", "_"}


def _scan_text(text: str) -> list[tuple[str, str]]:
    """Return list of (rule_name, matched_snippet) for any secret found."""
    hits = []
    for name, rgx in SECRET_RULES:
        for m in rgx.finditer(text):
            matched = m.group(0)
            if _is_explicit_placeholder(name, matched):
                continue
            if name == "Hardcoded sensitive env fallback":
                # Never expose any portion of a human-style password. The key
                # name is enough to locate and remediate the unsafe fallback.
                hits.append((name, f"{m.group('env_key')}=<literal fallback>"))
                continue
            # Redact the middle of the match — keep 8 chars at each end.
            redacted = (matched[:8] + "..." + matched[-8:]
                        if len(matched) > 20 else matched[:4] + "...")
            hits.append((name, redacted))
    return hits


def _sanitize_scanner_source(path: str, text: str) -> str:
    """Remove exact self-referential regex literals, not their whole lines."""
    if path != SELF_SCANNER_PATH:
        return text
    sanitized = text
    for literal in SELF_SCANNER_SAFE_LITERALS:
        sanitized = sanitized.replace(literal, "<scanner-rule-literal>")
    return sanitized


# --- git remote credentials (added 2026-08-16) --------------------------------
# A remote of the form https://<token>@host/owner/repo stores a live credential
# in plaintext in .git/config. Nothing else in this scanner can see it: the file
# is never committed, so --history misses it; it is outside the tree walk; and
# "config" is not a suspicious filename. It leaks to anyone with filesystem
# access, any backup, any screen-share of `git remote -v`, and any script that
# echoes the remote — which is exactly how it surfaced.
_REMOTE_CRED_RE = re.compile(r"^(?P<scheme>https?://)(?P<cred>[^/@]+)@(?P<rest>.+)$")

# Classify without ever emitting the value.
_CRED_KINDS = (
    ("ghp_", "GitHub classic PAT"),
    ("github_pat_", "GitHub fine-grained PAT"),
    ("gho_", "GitHub OAuth token"),
    ("ghs_", "GitHub server token"),
    ("glpat-", "GitLab PAT"),
    ("xoxb-", "Slack bot token"),
)


def scan_remotes(repo_root: Path) -> dict:
    """Report remotes whose URL embeds a credential. Never returns the value."""
    findings: list[dict] = []
    rc, out = _git_cmd(["remote"], repo_root)
    if rc != 0:
        return {"mode": "remotes", "repo": str(repo_root),
                "remotes_scanned": 0, "findings": [], "error": out.strip()}
    names = [n for n in out.split() if n]
    for name in names:
        rc, url = _git_cmd(["remote", "get-url", name], repo_root)
        if rc != 0:
            continue
        m = _REMOTE_CRED_RE.match(url.strip())
        if not m:
            continue
        cred = m.group("cred")
        kind = next((label for prefix, label in _CRED_KINDS
                     if cred.startswith(prefix)), None)
        if kind is None:
            # user:password, or a token shape we do not recognise. Still a
            # credential in plaintext — report it, still without the value.
            kind = ("username:password" if ":" in cred else "unrecognised token")
        findings.append({
            "path": f".git/config [remote \"{name}\"]",
            "rule": f"Credential embedded in remote URL ({kind})",
            # The clean URL is safe to print and is the remediation.
            "match": f"{m.group('scheme')}{m.group('rest')}",
        })
    return {"mode": "remotes", "repo": str(repo_root),
            "remotes_scanned": len(names), "findings": findings}


def scan_tree(repo_root: Path) -> dict:
    findings: list[dict] = []
    files_scanned = 0
    try:
        paths = list(_iter_tree_files(repo_root))
        cached_paths = _cached_tree_paths(repo_root)
        eligible_cached_paths = {
            str(p.relative_to(repo_root)).replace("\\", "/")
            for p in paths
            if str(p.relative_to(repo_root)).replace("\\", "/") in cached_paths
        }
        index_snapshot, gitlink_paths, symlink_paths = _read_index_snapshot(
            repo_root, eligible_cached_paths
        )
    except RuntimeError as exc:
        return {
            "mode": "tree",
            "repo": str(repo_root),
            "files_scanned": 0,
            "findings": [],
            "error": str(exc),
        }
    for p in paths:
        rel = p.relative_to(repo_root)
        rel_str = str(rel).replace("\\", "/")
        if (
            HISTORICAL_SECRET_FILENAME_RE.search(rel_str)
            and not HISTORICAL_FILENAME_ALLOW_RE.search(rel_str)
        ):
            findings.append({
                "path": rel_str,
                "rule": "Secret-shaped filename",
                "match": "<filename only>",
            })
        # Suspicious filename — flag even before reading
        for needle in SUSPICIOUS_FILENAMES:
            if needle in rel_str.lower():
                findings.append({"path": rel_str, "rule": "Suspicious filename",
                                 "match": needle})
                break
        # A gitlink stores only a pinned commit id in this repository. Its
        # nested worktree is a separate repository and reading the directory
        # as a file would turn a normal checkout into a scanner failure.
        if rel_str in gitlink_paths:
            continue
        contents: list[str] = []
        if rel_str in cached_paths:
            staged_text = index_snapshot.get(rel_str)
            if staged_text is None:
                return {
                    "mode": "tree",
                    "repo": str(repo_root),
                    "files_scanned": files_scanned,
                    "findings": findings,
                    "error": f"staged file missing from snapshot: {rel_str}",
                }
            contents.append(staged_text)
        if p.is_symlink():
            try:
                worktree_text = str(os.readlink(p))
            except OSError:
                return {
                    "mode": "tree",
                    "repo": str(repo_root),
                    "files_scanned": files_scanned,
                    "findings": findings,
                    "error": f"could not read worktree symlink {rel_str}; tree scan incomplete",
                }
            if not contents or worktree_text != contents[0]:
                contents.append(worktree_text)
        elif p.exists():
            try:
                worktree_size = p.stat().st_size
                if worktree_size > MAX_SCAN_BLOB_BYTES:
                    raise RuntimeError(
                        f"worktree file {rel_str} is {worktree_size} bytes; "
                        "scan refused to load it"
                    )
                worktree_text = _decode_scan_bytes(p.read_bytes())
            except RuntimeError as exc:
                return {
                    "mode": "tree",
                    "repo": str(repo_root),
                    "files_scanned": files_scanned,
                    "findings": findings,
                    "error": str(exc),
                }
            except Exception:
                return {
                    "mode": "tree",
                    "repo": str(repo_root),
                    "files_scanned": files_scanned,
                    "findings": findings,
                    "error": f"could not read worktree file {rel_str}; tree scan incomplete",
                }
            # Avoid doing the same regex work twice for unchanged tracked files.
            if not contents or worktree_text != contents[0]:
                contents.append(worktree_text)
        elif rel_str not in cached_paths:
            return {
                "mode": "tree",
                "repo": str(repo_root),
                "files_scanned": files_scanned,
                "findings": findings,
                "error": f"untracked file disappeared during scan: {rel_str}",
            }

        path_hits: set[tuple[str, str]] = set()
        for text in contents:
            files_scanned += 1
            for rule_name, redacted in _scan_text(
                _sanitize_scanner_source(rel_str, text)
            ):
                path_hits.add((rule_name, redacted))
        for rule_name, redacted in sorted(path_hits):
            findings.append({"path": rel_str, "rule": rule_name,
                             "match": redacted})
    return {"mode": "tree", "repo": str(repo_root),
            "files_scanned": files_scanned, "findings": findings}


def _first_commit_for_object(repo_root: Path, oid: bytes) -> str:
    """Best-effort attribution for a raw historical blob finding."""
    oid_text = oid.decode("ascii", errors="replace")
    rc, output = _git_cmd(
        ["log", "--all", "--reverse", "--format=%H", f"--find-object={oid_text}"],
        cwd=repo_root,
    )
    if rc == 0:
        commits = [line.strip() for line in output.splitlines() if line.strip()]
        if commits:
            return commits[0][:8]
    return oid_text[:8]


def _first_commit_for_path(repo_root: Path, path: str) -> str:
    """Best-effort attribution for a historical path-policy finding."""
    rc, output = _git_cmd(
        ["log", "--all", "--reverse", "--format=%H", "--", path],
        cwd=repo_root,
    )
    if rc == 0:
        commits = [line.strip() for line in output.splitlines() if line.strip()]
        if commits:
            return commits[0][:8]
    return "<history>"


def _historical_paths(repo_root: Path) -> set[str]:
    """Return every path named by reachable history, independent of blob aliases."""
    output = _git_bytes(
        [
            "-c",
            "core.quotepath=false",
            "log",
            "--all",
            "--full-history",
            "--format=",
            "--name-only",
            "-z",
            "--",
            ".",
        ],
        repo_root,
    )
    return {_decode_git_path(raw) for raw in output.split(b"\0") if raw}


def scan_history(repo_root: Path) -> dict:
    """Scan every reachable historical blob as raw bytes.

    Diff text is not a safe boundary because Git labels UTF-16/NUL-bearing
    content as binary. Reachable-object enumeration plus ``cat-file`` sees the
    exact committed bytes and deduplicates identical blobs across commits.
    """
    rc, count_out = _git_cmd(["rev-list", "--count", "--all"], cwd=repo_root)
    if rc != 0:
        return {"mode": "history", "error": "git rev-list failed",
                "repo": str(repo_root)}
    try:
        commits_scanned = int(count_out.strip() or "0")
    except ValueError:
        return {"mode": "history", "error": "invalid git rev-list count",
                "repo": str(repo_root)}

    findings: list[dict] = []
    blobs_scanned = 0
    try:
        object_output = _git_bytes(
            ["rev-list", "--objects", "--all", "-z"], repo_root
        )
        paths_by_oid: dict[bytes, set[str]] = {}
        listed_oids: set[bytes] = set()
        pending_oid: bytes | None = None
        for record in object_output.split(b"\0"):
            if not record:
                continue
            # With -z, modern Git emits ``<oid>\0path=<raw path>\0`` so
            # filenames containing whitespace/newlines remain unambiguous.
            if record.startswith(b"path="):
                if pending_oid is None:
                    raise RuntimeError("git rev-list emitted a path without an object")
                paths_by_oid.setdefault(pending_oid, set()).add(
                    _decode_git_path(record[len(b"path="):])
                )
                pending_oid = None
                continue
            oid, separator, raw_path = record.partition(b" ")
            listed_oids.add(oid)
            if separator and raw_path:
                paths_by_oid.setdefault(oid, set()).add(_decode_git_path(raw_path))
                pending_oid = None
            else:
                pending_oid = oid

        object_info = _git_object_info(repo_root, sorted(listed_oids))
        blob_paths: dict[bytes, list[str]] = {}
        blob_sizes: dict[bytes, int] = {}
        attribution_cache: dict[bytes, str] = {}

        def attribution(oid: bytes) -> str:
            if oid not in attribution_cache:
                attribution_cache[oid] = _first_commit_for_object(repo_root, oid)
            return attribution_cache[oid]

        filename_seen: set[tuple[str, str]] = set()
        historical_paths = _historical_paths(repo_root)
        for advisory_paths in paths_by_oid.values():
            historical_paths.update(advisory_paths)
        for path in sorted(historical_paths):
            if (
                HISTORICAL_SECRET_FILENAME_RE.search(path)
                and not HISTORICAL_FILENAME_ALLOW_RE.search(path)
            ):
                filename_seen.add((path, "Secret-shaped filename"))
                findings.append({
                    "commit": _first_commit_for_path(repo_root, path),
                    "object": "<path-only>",
                    "rule": "Secret-shaped filename",
                    "path": path,
                    "match": "<filename only>",
                })
            for needle in SUSPICIOUS_FILENAMES:
                if needle in path.lower():
                    key = (path, "Suspicious filename")
                    if key not in filename_seen:
                        filename_seen.add(key)
                        findings.append({
                            "commit": _first_commit_for_path(repo_root, path),
                            "object": "<path-only>",
                            "rule": "Suspicious filename",
                            "path": path,
                            "match": needle,
                        })
                    break

        for oid in sorted(listed_oids):
            kind, size = object_info.get(oid, (b"", 0))
            if kind != b"blob":
                continue
            paths = paths_by_oid.get(oid, set())
            if size > MAX_SCAN_BLOB_BYTES:
                raise RuntimeError(
                    f"historical blob {oid[:12].decode('ascii', errors='replace')} "
                    f"is {size} bytes; scan refused to skip it"
                )
            # Object names are advisory: rev-list emits only one traversal name
            # for a deduplicated blob. Never let that one name (or extension)
            # exempt the raw bytes, because the same object may also have lived
            # at a sensitive historical path.
            blob_paths[oid] = sorted(paths) or [f"<blob:{oid[:12].decode('ascii')}>" ]
            blob_sizes[oid] = size

        finding_seen: set[tuple[bytes, str, str, str]] = set()
        for oid_batch in _oid_batches(sorted(blob_paths), blob_sizes):
            for oid, raw in _read_raw_git_blobs(repo_root, oid_batch).items():
                text = _decode_scan_bytes(raw)
                blobs_scanned += 1
                for path in blob_paths[oid]:
                    scan_text = _sanitize_scanner_source(path, text)
                    for rule_name, redacted in _scan_text(scan_text):
                        key = (oid, path, rule_name, redacted)
                        if key in finding_seen:
                            continue
                        finding_seen.add(key)
                        findings.append({
                            "commit": attribution(oid),
                            "object": oid.decode("ascii", errors="replace")[:12],
                            "rule": rule_name,
                            "path": path,
                            "match": redacted,
                        })
    except RuntimeError as exc:
        return {
            "mode": "history",
            "repo": str(repo_root),
            "commits_scanned": commits_scanned,
            "blobs_scanned": blobs_scanned,
            "findings": findings,
            "error": str(exc),
        }

    return {
        "mode": "history",
        "repo": str(repo_root),
        "commits_scanned": commits_scanned,
        "blobs_scanned": blobs_scanned,
        "findings": findings,
    }


def _format_findings(result: dict) -> int:
    if result.get("error"):
        print(f"ERROR  secret scan incomplete: {result['error']}", file=sys.stderr)
        return 2
    findings = result.get("findings", [])
    mode = result.get("mode", "?")
    if not findings:
        scope = (f"{result.get('files_scanned', 0)} files"
                 if mode == "tree"
                 else f"{result.get('commits_scanned', 0)} commits")
        print(f"OK  clean - scanned {scope} in {result['repo']}")
        return 0
    print(f"FAIL  {len(findings)} finding(s) in {result['repo']}  ({mode})")
    print()
    for f in findings:
        if mode == "tree":
            print(f"    [{f['rule']}]  {f['path']}")
        else:
            print(f"    [{f['rule']}]  commit {f.get('commit', '?')}  {f.get('path', '?')}")
        print(f"        match: {f['match']}")
    print()
    print("Remediation:")
    print("  1. Revoke / rotate each exposed credential at its provider.")
    print("  2. Remove the live-tree value and add a regression guard.")
    print("  3. If repository policy requires history rewriting, obtain explicit operator")
    print("     approval and coordinate every clone before filter-repo/force-push.")
    print("  4. Add the file pattern to .gitignore so it can't re-land.")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--history", action="store_true",
                    help="Scan all commits in all branches (slow, thorough)")
    ap.add_argument("--path", default=".",
                    help="Repo root to scan (default: cwd)")
    ap.add_argument("--json", action="store_true",
                    help="Machine-readable output")
    args = ap.parse_args()

    repo_root = Path(args.path).resolve()
    if not (repo_root / ".git").exists():
        print(f"Not a git repo: {repo_root}")
        return 2

    result = scan_history(repo_root) if args.history else scan_tree(repo_root)

    # Remotes are checked on every run, in both modes. They are cheap (one git
    # call per remote) and they are the one credential location neither the tree
    # walk nor the history walk can reach.
    remotes = scan_remotes(repo_root)
    if remotes.get("findings"):
        result.setdefault("findings", []).extend(remotes["findings"])
    result["remotes_scanned"] = remotes.get("remotes_scanned", 0)
    if args.json:
        print(json.dumps(result, indent=2))
        if result.get("error"):
            return 2
        return 0 if not result.get("findings") else 1
    return _format_findings(result)


if __name__ == "__main__":
    sys.exit(main())
