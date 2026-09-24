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

import hashlib
import os
import re
import shutil
import stat
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager
from pathlib import Path

__all__ = [
    "parse_text",
    "parse_file",
    "key_names",
    "digest",
    "atomic_write_text",
    "locked_update_text",
    "update_env_values",
    "ensure_env_file",
    "harden_env_file",
    "recover_stale_temp_files",
    "EnvStoreError",
    "EnvStoreLockTimeout",
    "EnvStoreRecoveryError",
    "EnvStoreSecurityError",
    "EnvStoreValidationError",
    "DIGEST_LEN",
]

# One truncation length, because a digest is only useful if two tools that print
# it produce the SAME string for the same value. secret_identity_check used 12
# and secret_disk_hunt used 8, so their outputs could not be compared against
# each other at all — which defeats the entire point of reporting a digest
# instead of a value. 12 hex chars is 48 bits: ample against accidental
# collision across a few hundred keys, and short enough to scan by eye.
DIGEST_LEN = 12

DEFAULT_LOCK_TIMEOUT_SECONDS = 30.0
DEFAULT_STALE_TEMP_SECONDS = 60.0 * 60.0
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,255}$")
_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()
_WINDOWLESS_FLAGS = 0x08000000 if os.name == "nt" else 0


class EnvStoreError(RuntimeError):
    """Base class for credential-store failures (never contains values)."""


class EnvStoreLockTimeout(EnvStoreError):
    """Another writer held the canonical store longer than allowed."""


class EnvStoreRecoveryError(EnvStoreError):
    """A crash artifact needs explicit recovery before writes may continue."""


class EnvStoreSecurityError(EnvStoreError):
    """The store could not be hardened to the required filesystem policy."""


class EnvStoreValidationError(EnvStoreError, ValueError):
    """A proposed assignment is unsafe for a line-oriented env file."""


# PowerShell is used instead of os.chmod on Windows because chmod only toggles
# the DOS read-only bit there. SIDs avoid localized account-name bugs. A fresh
# ACL drops inherited/unknown readers, while retaining the current file owner,
# Local System, and the built-in Administrators group. The script verifies its
# own result and exits non-zero on any mismatch.
_WINDOWS_ACL_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$targetPath = $env:OASIS_ENVSTORE_TARGET_PATH
$ownerSource = $env:OASIS_ENVSTORE_OWNER_SOURCE
if ([string]::IsNullOrWhiteSpace($targetPath)) { throw 'target path missing' }
if (-not (Test-Path -LiteralPath $targetPath -PathType Leaf)) { throw 'target is not a file' }
if ([string]::IsNullOrWhiteSpace($ownerSource) -or
    -not (Test-Path -LiteralPath $ownerSource -PathType Leaf)) {
    $ownerSource = $targetPath
}

$sourceAcl = Get-Acl -LiteralPath $ownerSource
$ownerSid = $sourceAcl.GetOwner([System.Security.Principal.SecurityIdentifier])
$systemSid = New-Object System.Security.Principal.SecurityIdentifier('S-1-5-18')
$administratorsSid = New-Object System.Security.Principal.SecurityIdentifier('S-1-5-32-544')
$allowed = @($ownerSid, $systemSid, $administratorsSid) |
    Sort-Object -Property Value -Unique

$acl = New-Object System.Security.AccessControl.FileSecurity
$acl.SetOwner($ownerSid)
$acl.SetAccessRuleProtection($true, $false)
foreach ($sid in $allowed) {
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $sid,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
    [void]$acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $targetPath -AclObject $acl

$verify = Get-Acl -LiteralPath $targetPath
$verifiedOwner = $verify.GetOwner([System.Security.Principal.SecurityIdentifier])
if ($verifiedOwner.Value -ne $ownerSid.Value) { throw 'owner was not preserved' }
if (-not $verify.AreAccessRulesProtected) { throw 'ACL inheritance is still enabled' }
$allowedValues = @{}
foreach ($sid in $allowed) { $allowedValues[$sid.Value] = $false }
foreach ($rule in @($verify.Access)) {
    $ruleSid = $rule.IdentityReference.Translate(
        [System.Security.Principal.SecurityIdentifier]
    ).Value
    if (-not $allowedValues.ContainsKey($ruleSid)) { throw 'unexpected ACL principal' }
    if ($rule.AccessControlType -ne
        [System.Security.AccessControl.AccessControlType]::Allow) {
        throw 'deny ACL present'
    }
    if (($rule.FileSystemRights -band
        [System.Security.AccessControl.FileSystemRights]::FullControl) -ne
        [System.Security.AccessControl.FileSystemRights]::FullControl) {
        throw 'principal lacks full control'
    }
    $allowedValues[$ruleSid] = $true
}
foreach ($entry in $allowedValues.GetEnumerator()) {
    if (-not $entry.Value) { throw 'required ACL principal missing' }
}
"""


def _lock_key(path: Path) -> str:
    return os.path.normcase(str(path.absolute()))


def _thread_lock(path: Path) -> threading.RLock:
    key = _lock_key(path)
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


def _lock_file_path(path: Path) -> Path:
    base = path.name if path.name.startswith(".") else f".{path.name}"
    return path.with_name(f"{base}.lock")


def _try_lock_file(handle: object) -> bool:
    if os.name == "nt":
        import msvcrt

        handle.seek(0, os.SEEK_END)  # type: ignore[attr-defined]
        if handle.tell() == 0:  # type: ignore[attr-defined]
            handle.write(b"\0")  # type: ignore[attr-defined]
            handle.flush()  # type: ignore[attr-defined]
        handle.seek(0)  # type: ignore[attr-defined]
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
            return True
        except OSError:
            return False

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
        return True
    except OSError:
        return False


def _unlock_file(handle: object) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)  # type: ignore[attr-defined]
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


@contextmanager
def _exclusive_store_lock(
    path: Path,
    *,
    timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
):
    """Serialize writers across threads and processes without reading values."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(0.0, timeout)
    local_lock = _thread_lock(target)
    remaining = max(0.0, deadline - time.monotonic())
    if not local_lock.acquire(timeout=remaining):
        raise EnvStoreLockTimeout(f"Timed out waiting for env-store lock: {target}")
    lock_path = _lock_file_path(target)
    acquired_file_lock = False
    try:
        with lock_path.open("a+b", buffering=0) as handle:
            if os.name != "nt":
                os.chmod(lock_path, 0o600)
            while True:
                if _try_lock_file(handle):
                    acquired_file_lock = True
                    break
                if time.monotonic() >= deadline:
                    raise EnvStoreLockTimeout(
                        f"Timed out waiting for env-store lock: {target}"
                    )
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            try:
                yield
            finally:
                if acquired_file_lock:
                    _unlock_file(handle)
    finally:
        local_lock.release()


def _powershell_environment(target: Path, owner_source: Path) -> dict[str, str]:
    # Do not forward provider tokens to a helper that only needs filesystem
    # paths. These Windows variables are sufficient to launch PowerShell and
    # load its built-in security module.
    keep = {
        "ALLUSERSPROFILE",
        "APPDATA",
        "COMSPEC",
        "CommonProgramFiles",
        "CommonProgramFiles(x86)",
        "CommonProgramW6432",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "NUMBER_OF_PROCESSORS",
        "OS",
        "PATH",
        "PATHEXT",
        "PROCESSOR_ARCHITECTURE",
        "PROCESSOR_IDENTIFIER",
        "PROCESSOR_LEVEL",
        "PROCESSOR_REVISION",
        "ProgramData",
        "ProgramFiles",
        "ProgramFiles(x86)",
        "ProgramW6432",
        "PSModulePath",
        "SystemRoot",
        "TEMP",
        "TMP",
        "USERDOMAIN",
        "USERNAME",
        "USERPROFILE",
        "WINDIR",
    }
    keep_upper = {key.upper() for key in keep}
    child = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in keep_upper
    }
    child["OASIS_ENVSTORE_TARGET_PATH"] = str(target)
    child["OASIS_ENVSTORE_OWNER_SOURCE"] = str(owner_source)
    return child


def _harden_windows_acl(path: Path, *, owner_source: Path | None = None) -> None:
    target = Path(path)
    source = Path(owner_source) if owner_source is not None else target
    executable = shutil.which("powershell.exe") or shutil.which("powershell")
    if not executable:
        raise EnvStoreSecurityError(
            f"Windows ACL hardening failed for {target}: PowerShell unavailable"
        )
    import base64

    encoded = base64.b64encode(_WINDOWS_ACL_SCRIPT.encode("utf-16le")).decode("ascii")
    try:
        result = subprocess.run(
            [
                executable,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded,
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            creationflags=_WINDOWLESS_FLAGS,
            env=_powershell_environment(target, source),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EnvStoreSecurityError(
            f"Windows ACL hardening failed for {target}: {type(exc).__name__}"
        ) from exc
    if result.returncode != 0:
        raise EnvStoreSecurityError(
            f"Windows ACL hardening failed for {target} "
            f"(PowerShell exit {result.returncode})"
        )


def _secure_file_permissions(
    path: Path,
    *,
    mode: int = 0o600,
    owner_source: Path | None = None,
) -> None:
    target = Path(path)
    if os.name == "nt":
        _harden_windows_acl(target, owner_source=owner_source)
        return
    try:
        os.chmod(target, mode)
        actual = stat.S_IMODE(target.stat().st_mode)
    except OSError as exc:
        raise EnvStoreSecurityError(
            f"POSIX permission hardening failed for {target}: {type(exc).__name__}"
        ) from exc
    if actual != mode:
        raise EnvStoreSecurityError(
            f"POSIX permission hardening failed for {target}: "
            f"mode {actual:04o}, expected {mode:04o}"
        )


def _temp_pattern(path: Path) -> re.Pattern[str]:
    base = path.name if path.name.startswith(".") else f".{path.name}"
    return re.compile(
        rf"^{re.escape(base)}\.tmp\.\d+\.[0-9a-f]{{32}}$"
    )


def _matching_temp_files(path: Path) -> tuple[Path, ...]:
    pattern = _temp_pattern(path)
    try:
        entries = tuple(path.parent.iterdir())
    except FileNotFoundError:
        return ()
    return tuple(entry for entry in entries if pattern.fullmatch(entry.name))


def _canonical_is_safe_file(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode)


def _recover_stale_temp_files_unlocked(
    path: Path,
    *,
    stale_after_seconds: float,
    now: float,
) -> tuple[Path, ...]:
    # With no canonical regular file, a temp may be the only recoverable copy.
    # Never auto-delete it and never infer which candidate should be restored.
    if not _canonical_is_safe_file(path):
        return ()
    removed: list[Path] = []
    for candidate in _matching_temp_files(path):
        try:
            metadata = candidate.lstat()
        except OSError:
            continue
        if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            continue
        age = now - metadata.st_mtime
        if age < max(0.0, stale_after_seconds):
            continue
        try:
            candidate.unlink()
        except OSError as exc:
            raise EnvStoreRecoveryError(
                f"Could not remove stale env-store temp {candidate}: "
                f"{type(exc).__name__}"
            ) from exc
        removed.append(candidate)
    return tuple(removed)


def recover_stale_temp_files(
    path: Path,
    *,
    stale_after_seconds: float = DEFAULT_STALE_TEMP_SECONDS,
    now: float | None = None,
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
) -> tuple[Path, ...]:
    """Remove only old temps from this writer when a safe canonical exists."""
    target = Path(path)
    with _exclusive_store_lock(target, timeout=lock_timeout):
        return _recover_stale_temp_files_unlocked(
            target,
            stale_after_seconds=stale_after_seconds,
            now=time.time() if now is None else now,
        )


def _create_unique_temp(path: Path) -> tuple[int, Path]:
    base = path.name if path.name.startswith(".") else f".{path.name}"
    for _attempt in range(20):
        candidate = path.with_name(
            f"{base}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
        )
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            return fd, candidate
        except FileExistsError:
            continue
    raise EnvStoreError(f"Could not allocate a unique env-store temp beside {path}")


def _fsync_parent_directory(path: Path) -> None:
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path.parent, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_text_unlocked(
    path: Path,
    text: str,
    *,
    encoding: str,
    mode: int,
) -> None:
    owner_source = path if path.exists() else None
    fd, temp_path = _create_unique_temp(path)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _secure_file_permissions(
            temp_path,
            mode=mode,
            owner_source=owner_source,
        )
        os.replace(temp_path, path)
        _fsync_parent_directory(path)
    except BaseException:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError as cleanup_exc:
            raise EnvStoreRecoveryError(
                f"Env-store write failed and temp cleanup also failed: {temp_path}"
            ) from cleanup_exc
        raise


def atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    mode: int = 0o600,
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
) -> None:
    """Replace an env store atomically without creating a persistent backup.

    The temporary file is created beside ``path`` so ``os.replace`` stays on
    one filesystem.  It is flushed to disk before the replace.  Until that
    single replace succeeds, the original file is untouched; any earlier
    failure removes the temporary file and propagates the error.

    The old file is intentionally not copied elsewhere.  Versioned backups of
    a live secret store multiply both disk bloat and the number of credential
    copies an attacker could recover.
    """
    target = Path(path)
    if not isinstance(text, str):
        raise TypeError("env-store text must be str")
    with _exclusive_store_lock(target, timeout=lock_timeout):
        _recover_stale_temp_files_unlocked(
            target,
            stale_after_seconds=DEFAULT_STALE_TEMP_SECONDS,
            now=time.time(),
        )
        if not target.exists() and _matching_temp_files(target):
            raise EnvStoreRecoveryError(
                f"Canonical env store is missing while a recovery temp exists beside "
                f"{target}; manual recovery is required before writing"
            )
        _atomic_write_text_unlocked(
            target,
            text,
            encoding=encoding,
            mode=mode,
        )


def locked_update_text(
    path: Path,
    transform: Callable[[str], str],
    *,
    encoding: str = "utf-8",
    mode: int = 0o600,
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
) -> bool:
    """Read, transform, and atomically replace one store under one lock.

    ``transform`` is invoked only after the cross-process lock is held. This is
    the canonical mutation primitive; callers that read before acquiring this
    lock can still lose concurrent updates.
    """
    target = Path(path)
    with _exclusive_store_lock(target, timeout=lock_timeout):
        _recover_stale_temp_files_unlocked(
            target,
            stale_after_seconds=DEFAULT_STALE_TEMP_SECONDS,
            now=time.time(),
        )
        if not target.exists() and _matching_temp_files(target):
            raise EnvStoreRecoveryError(
                f"Canonical env store is missing while a recovery temp exists beside "
                f"{target}; manual recovery is required before writing"
            )
        if target.exists() and not target.is_file():
            raise EnvStoreError(f"Canonical env-store path is not a file: {target}")
        current = target.read_text(encoding=encoding) if target.exists() else ""
        replacement = transform(current)
        if not isinstance(replacement, str):
            raise TypeError("env-store transform must return str")
        if target.exists() and replacement == current:
            _secure_file_permissions(target, mode=mode, owner_source=target)
            return False
        _atomic_write_text_unlocked(
            target,
            replacement,
            encoding=encoding,
            mode=mode,
        )
        return True


def _assignment_key(raw: str) -> str | None:
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    key = line.partition("=")[0].strip()
    if key.lower().startswith("export "):
        key = key[7:].strip()
    return key or None


def _validated_updates(updates: Mapping[str, str]) -> dict[str, str]:
    validated: dict[str, str] = {}
    for key, value in updates.items():
        if not isinstance(key, str) or not _ENV_KEY_RE.fullmatch(key):
            raise EnvStoreValidationError(f"Invalid env key: {key!r}")
        if not isinstance(value, str):
            raise EnvStoreValidationError(f"Env value for {key} must be text")
        if any(marker in value for marker in ("\n", "\r", "\x00")):
            raise EnvStoreValidationError(
                f"Env value for {key} contains a forbidden line/control character"
            )
        validated[key] = value
    return validated


def update_env_values(
    path: Path,
    updates: Mapping[str, str],
    *,
    initial_text: str = "",
    encoding: str = "utf-8",
    mode: int = 0o600,
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
) -> bool:
    """Merge key/value assignments without exposing values or losing peers."""
    validated = _validated_updates(updates)

    def merge(current: str) -> str:
        source = current if current else initial_text
        output: list[str] = []
        replaced: set[str] = set()
        for raw in source.splitlines():
            key = _assignment_key(raw)
            if key not in validated:
                output.append(raw)
                continue
            if key in replaced:
                continue
            output.append(f"{key}={validated[key]}")
            replaced.add(key)
        for key, value in validated.items():
            if key not in replaced:
                output.append(f"{key}={value}")
        if not output:
            return ""
        return "\n".join(output).rstrip() + "\n"

    return locked_update_text(
        path,
        merge,
        encoding=encoding,
        mode=mode,
        lock_timeout=lock_timeout,
    )


def remove_env_keys(
    path: Path,
    keys: Iterable[str],
    *,
    encoding: str = "utf-8",
    mode: int = 0o600,
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
) -> bool:
    """Drop every assignment of `keys`, under the same lock as update_env_values.

    For retiring a duplicate copy of a secret (e.g. a bare name left beside the
    namespaced key a manifest actually deploys) so two values can never drift.
    Returns True when the file changed. Values are never read into the caller.
    """
    targets = set(keys)
    for key in targets:
        if not isinstance(key, str) or not _ENV_KEY_RE.fullmatch(key):
            raise EnvStoreValidationError(f"Invalid env key: {key!r}")

    def drop(current: str) -> str:
        kept = [raw for raw in current.splitlines() if _assignment_key(raw) not in targets]
        return ("\n".join(kept).rstrip() + "\n") if kept else ""

    return locked_update_text(path, drop, encoding=encoding, mode=mode, lock_timeout=lock_timeout)


def ensure_env_file(
    path: Path,
    *,
    initial_text: str,
    encoding: str = "utf-8",
    mode: int = 0o600,
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
) -> bool:
    """Create the canonical store once, or only re-harden it if it exists."""

    def initialize(current: str) -> str:
        return current if current else initial_text

    return locked_update_text(
        path,
        initialize,
        encoding=encoding,
        mode=mode,
        lock_timeout=lock_timeout,
    )


def harden_env_file(
    path: Path,
    *,
    mode: int = 0o600,
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
) -> None:
    """Apply the canonical filesystem policy without opening secret content."""
    target = Path(path)
    with _exclusive_store_lock(target, timeout=lock_timeout):
        if not _canonical_is_safe_file(target):
            raise EnvStoreSecurityError(
                f"Cannot harden missing, non-regular, or linked env store: {target}"
            )
        _secure_file_permissions(target, mode=mode, owner_source=target)


def digest(value: str, length: int = DIGEST_LEN) -> str:
    """A stable fingerprint of a secret, safe to print.

    The whole reason these tools can talk about credentials in front of an agent
    is that equality and difference are reportable without the value. Keep this
    the only implementation.
    """
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:length]


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
