#!/usr/bin/env python3
"""lane_key.py - store and fetch Claude Spillover secrets (CONTRACT section 9).

Stdlib only. `omniroute_tool.py deploy` copies this file to HOME_DIR/bin/ and it
runs from there, outside the repo, so it imports nothing from the repo. The venv's
`site` import costs ~2 s (the Turso switch pulls in supabase), so callers launch it
with `python -S`.

Verbs:
  generate <name> [--bytes N] [--force]  store a new url-safe random value. Prints
                                         nothing. Refuses to replace an existing
                                         secret without --force: overwriting
                                         storage_encryption would leave OmniRoute's
                                         database unreadable.
  set <name> [--stdin]                   read a value at a hidden prompt (getpass).
                                         Refuses a non-TTY stdin unless --stdin.
  exists <name>                          print true|false (exit 0|2). Never decrypts.
  get <name>                             print the value to stdout. secret_guard
                                         blocks this verb for agent Bash/PowerShell.

Exit codes: 0 ok, 1 usage, 2 missing, 3 crypto or storage-protection error.

Storage:
  Windows  DPAPI (CryptProtectData, user scope, fixed entropy) blobs at
           HOME_DIR/secrets/<name>.key, each with an owner-only ACL
           (icacls /inheritance:r /grant:r <user>:F). DPAPI is at-rest protection
           only; the real controls are the loopback bind and the key's scope.
  macOS    login keychain generic password, service "bravo-spillover",
           account <name>, via /usr/bin/security.

HOME_DIR: %LOCALAPPDATA%\\bravo-spillover on Windows,
~/Library/Application Support/bravo-spillover on macOS. The env var
BRAVO_SPILLOVER_HOME overrides it (tests point it at a temp dir).

Values never go to a log or to any file other than the protected blob.
"""
from __future__ import annotations

import argparse
import os
import re
import secrets
import subprocess
import sys

EXIT_OK, EXIT_USAGE, EXIT_MISSING, EXIT_CRYPTO = 0, 1, 2, 3

IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"
KEYCHAIN_SERVICE = "bravo-spillover"
# Optional DPAPI entropy: a blob copied out of this tool's context does not
# decrypt with a bare CryptUnprotectData call. It is a speed bump, not a secret.
DPAPI_ENTROPY = b"bravo-spillover/lane_key/v1"
NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
CREATE_NO_WINDOW = 0x08000000


class CryptoError(Exception):
    """The platform store refused to protect, unprotect or lock down a secret."""


def home_dir() -> str:
    override = os.environ.get("BRAVO_SPILLOVER_HOME")
    if override:
        return override
    if IS_MAC:
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "bravo-spillover")
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "bravo-spillover")


def blob_path(name: str) -> str:
    return os.path.join(home_dir(), "secrets", f"{name}.key")


# --------------------------------------------------------------------------- #
# Windows: DPAPI through ctypes
# --------------------------------------------------------------------------- #
def _dpapi():
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    sig = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.POINTER(DATA_BLOB),
           ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    crypt32.CryptProtectData.argtypes = sig
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = sig
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return ctypes, DATA_BLOB, crypt32, kernel32


_CRYPTPROTECT_UI_FORBIDDEN = 0x1


def _dpapi_call(protect: bool, data: bytes) -> bytes:
    ctypes, DATA_BLOB, crypt32, kernel32 = _dpapi()
    in_buf = ctypes.create_string_buffer(data, len(data))
    ent_buf = ctypes.create_string_buffer(DPAPI_ENTROPY, len(DPAPI_ENTROPY))
    blob_in = DATA_BLOB(len(data), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    blob_ent = DATA_BLOB(len(DPAPI_ENTROPY), ctypes.cast(ent_buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(blob_in), None, ctypes.byref(blob_ent), None, None,
            _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
    if not ok:
        err = ctypes.get_last_error()
        raise CryptoError(f"{'CryptProtectData' if protect else 'CryptUnprotectData'} failed (winerror {err})")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


def _current_user() -> str:
    """DOMAIN\\user of this process (GetUserNameExW NameSamCompatible)."""
    import ctypes
    from ctypes import wintypes

    secur32 = ctypes.WinDLL("secur32", use_last_error=True)
    secur32.GetUserNameExW.argtypes = [ctypes.c_int, wintypes.LPWSTR, ctypes.POINTER(wintypes.ULONG)]
    secur32.GetUserNameExW.restype = wintypes.BOOLEAN
    size = wintypes.ULONG(512)
    buf = ctypes.create_unicode_buffer(size.value)
    if secur32.GetUserNameExW(2, buf, ctypes.byref(size)) and buf.value:
        return buf.value
    user = os.environ.get("USERNAME")
    if not user:
        raise CryptoError("cannot resolve the current user for the owner-only ACL")
    domain = os.environ.get("USERDOMAIN")
    return f"{domain}\\{user}" if domain else user


def _restrict_to_owner(path: str, is_dir: bool = False) -> None:
    """icacls <path> /inheritance:r /grant:r <user>:F - owner-only, nothing inherited.

    Copied here on purpose (not imported): this file is deployed outside the repo.
    """
    grant = f"{_current_user()}:{'(OI)(CI)F' if is_dir else 'F'}"
    proc = subprocess.run(
        ["icacls", path, "/inheritance:r", "/grant:r", grant],
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
        creationflags=CREATE_NO_WINDOW,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or ["no output"]
        raise CryptoError(f"icacls failed on {os.path.basename(path)} (exit {proc.returncode}): {tail[0][:160]}")


def _win_store(name: str, value: str) -> None:
    sdir = os.path.dirname(blob_path(name))
    if not os.path.isdir(sdir):
        os.makedirs(sdir, exist_ok=True)
        _restrict_to_owner(sdir, is_dir=True)
    blob = _dpapi_call(True, value.encode("utf-8"))
    final = blob_path(name)
    tmp = f"{final}.{os.getpid()}.tmp"
    try:
        with open(tmp, "wb") as fh:
            fh.write(blob)
        # Lock the tmp file BEFORE it takes the real name, so the final path never
        # exists with an inherited ACL. A same-volume rename keeps the DACL.
        _restrict_to_owner(tmp)
        os.replace(tmp, final)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _win_load(name: str) -> str | None:
    try:
        with open(blob_path(name), "rb") as fh:
            blob = fh.read()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CryptoError(f"cannot read the {name} blob: {exc.strerror or exc}") from exc
    try:
        return _dpapi_call(False, blob).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CryptoError(f"the {name} blob decrypted to non-UTF-8 bytes") from exc


# --------------------------------------------------------------------------- #
# macOS: login keychain through /usr/bin/security
# --------------------------------------------------------------------------- #
_ERR_SEC_ITEM_NOT_FOUND = 44


def _mac_store(name: str, value: str) -> None:
    # `security -i` reads the command from stdin, so the value never appears in
    # argv (visible to every process). -X takes it hex-encoded: no quoting rules.
    cmd = f"add-generic-password -U -a {name} -s {KEYCHAIN_SERVICE} -X {value.encode('utf-8').hex()}\n"
    proc = subprocess.run(["/usr/bin/security", "-i"], input=cmd, capture_output=True,
                          text=True, timeout=30)
    if proc.returncode != 0 or "error" in (proc.stderr or "").lower():
        raise CryptoError(f"security add-generic-password failed (exit {proc.returncode})")


def _mac_exists(name: str) -> bool:
    proc = subprocess.run(["/usr/bin/security", "find-generic-password", "-a", name, "-s", KEYCHAIN_SERVICE],
                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          timeout=30)
    if proc.returncode == 0:
        return True
    if proc.returncode == _ERR_SEC_ITEM_NOT_FOUND:
        return False
    raise CryptoError(f"security find-generic-password failed (exit {proc.returncode})")


def _mac_load(name: str) -> str | None:
    proc = subprocess.run(["/usr/bin/security", "find-generic-password", "-a", name, "-s", KEYCHAIN_SERVICE, "-w"],
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
    if proc.returncode == _ERR_SEC_ITEM_NOT_FOUND:
        return None
    if proc.returncode != 0:
        raise CryptoError(f"security find-generic-password failed (exit {proc.returncode})")
    return proc.stdout.rstrip("\n")


# --------------------------------------------------------------------------- #
# Platform dispatch
# --------------------------------------------------------------------------- #
def _unsupported() -> CryptoError:
    return CryptoError(f"no secure store on this platform ({sys.platform}); Windows DPAPI or macOS keychain only")


def store(name: str, value: str) -> None:
    if IS_WINDOWS:
        return _win_store(name, value)
    if IS_MAC:
        return _mac_store(name, value)
    raise _unsupported()


def exists(name: str) -> bool:
    if IS_WINDOWS:
        return os.path.isfile(blob_path(name))
    if IS_MAC:
        return _mac_exists(name)
    raise _unsupported()


def load(name: str) -> str | None:
    if IS_WINDOWS:
        return _win_load(name)
    if IS_MAC:
        return _mac_load(name)
    raise _unsupported()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
class _Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse exits 2 by default; 2 means "missing" here
        self.print_usage(sys.stderr)
        sys.stderr.write(f"lane_key: {message}\n")
        sys.exit(EXIT_USAGE)


def _parser() -> argparse.ArgumentParser:
    p = _Parser(prog="lane_key.py", description="Claude Spillover secret store (DPAPI / keychain).")
    sub = p.add_subparsers(dest="verb", required=True)
    g = sub.add_parser("generate", help="store a new random url-safe value (prints nothing)")
    g.add_argument("name")
    g.add_argument("--bytes", type=int, default=32, help="random bytes before encoding (16-512, default 32)")
    g.add_argument("--force", action="store_true", help="replace an existing secret")
    s = sub.add_parser("set", help="store a value read at a hidden prompt")
    s.add_argument("name")
    s.add_argument("--stdin", action="store_true", help="read one line from a non-TTY stdin instead")
    for verb, text in (("exists", "print true|false"), ("get", "print the value")):
        sub.add_parser(verb, help=text).add_argument("name")
    return p


def _read_value(from_stdin: bool) -> str | None:
    if from_stdin:
        line = sys.stdin.readline()
        return line.rstrip("\r\n")
    if sys.stdin is None or not sys.stdin.isatty():
        return None
    import getpass
    return getpass.getpass("value (hidden): ")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    name = args.name
    if not NAME_RE.match(name):
        sys.stderr.write("lane_key: name must be 1-64 of [A-Za-z0-9_]\n")
        return EXIT_USAGE
    try:
        if args.verb == "exists":
            present = exists(name)
            print("true" if present else "false")
            return EXIT_OK if present else EXIT_MISSING
        if args.verb == "get":
            value = load(name)
            if value is None:
                sys.stderr.write(f"lane_key: no secret named {name}\n")
                return EXIT_MISSING
            print(value)
            return EXIT_OK
        if args.verb == "generate":
            if not 16 <= args.bytes <= 512:
                sys.stderr.write("lane_key: --bytes must be between 16 and 512\n")
                return EXIT_USAGE
            if exists(name) and not args.force:
                sys.stderr.write(f"lane_key: {name} already exists; pass --force to replace it "
                                 "(anything encrypted with the old value becomes unreadable)\n")
                return EXIT_USAGE
            store(name, secrets.token_urlsafe(args.bytes))
            sys.stderr.write(f"lane_key: stored a new {name}\n")
            return EXIT_OK
        # set
        if not args.stdin and (sys.stdin is None or not sys.stdin.isatty()):
            sys.stderr.write("lane_key: stdin is not a terminal; refusing to read a secret from a pipe "
                             "(pass --stdin if that is intended)\n")
            return EXIT_USAGE
        value = _read_value(args.stdin)
        if not value:
            sys.stderr.write("lane_key: empty value, nothing stored\n")
            return EXIT_USAGE
        store(name, value)
        sys.stderr.write(f"lane_key: stored {name}\n")
        return EXIT_OK
    except CryptoError as exc:
        sys.stderr.write(f"lane_key: {exc}\n")
        return EXIT_CRYPTO
    except (OSError, subprocess.SubprocessError) as exc:
        sys.stderr.write(f"lane_key: storage error: {type(exc).__name__}: {exc}\n")
        return EXIT_CRYPTO


if __name__ == "__main__":
    sys.exit(main())
