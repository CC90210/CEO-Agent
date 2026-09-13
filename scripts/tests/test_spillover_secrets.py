"""Tests for scripts/spillover/lane_key.py (CONTRACT.md section 9) and the
'omniroute-api-key' live-secret pattern added to scripts/audit_mcp_secrets.py
for the same feature (CONTRACT.md section 1/2).

Everything that touches the real DPAPI store or icacls runs against a
throwaway HOME_DIR (tmp_path) via the BRAVO_SPILLOVER_HOME override that
CONTRACT.md section 2 names for exactly this purpose -- nothing here ever
touches the real %LOCALAPPDATA%\\bravo-spillover.
"""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LANE_KEY = REPO_ROOT / "scripts" / "spillover" / "lane_key.py"
SECRET_GUARD = REPO_ROOT / "scripts" / "state" / "secret_guard.py"
AUDIT_MCP = REPO_ROOT / "scripts" / "audit_mcp_secrets.py"

WINDOWS_ONLY = pytest.mark.skipif(
    platform.system() != "Windows", reason="DPAPI and icacls are Windows-only"
)

PYTHON = sys.executable
EXIT_OK, EXIT_USAGE, EXIT_MISSING, EXIT_CRYPTO = 0, 1, 2, 3

# The REAL install (never touched by this suite - see the isolation guard below).
_REAL_LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
_REAL_BRAVO_SPILLOVER_HOME = _REAL_LOCALAPPDATA / "bravo-spillover"
# Only the subpaths this feature's own tools ever write to (CONTRACT.md
# section 2). NEVER walk the whole HOME_DIR - omniroute-src/ and
# omniroute-npm/ are a full git checkout + a built Next.js app +
# node_modules (hundreds of thousands of files, another agent's live build
# in this same session); an unscoped recursive walk hung for minutes in an
# earlier version of this guard and would have raced that build for no reason.
_WATCHED_SUBPATHS = ("secrets", "state", "bin", "app", "config.json")


def _snapshot(root):
    if not root.exists():
        return None
    paths = []
    for name in _WATCHED_SUBPATHS:
        sub = root / name
        if sub.is_file():
            paths.append(name)
        elif sub.is_dir():
            paths.extend(str(p.relative_to(root)) for p in sub.rglob("*"))
    return sorted(paths)


@pytest.fixture(autouse=True)
def _isolated_spillover_home(tmp_path, monkeypatch):
    """home_dir() resolves HOME_DIR at CALL time from BRAVO_SPILLOVER_HOME
    (verified by reading lane_key.py and audit_mcp_secrets.py). This makes
    every test in this file set both BRAVO_SPILLOVER_HOME and LOCALAPPDATA
    to a fresh tmp_path before it runs, on top of the explicit `home`
    fixture/env already passed to most calls here."""
    home = tmp_path / "bravo-spillover-default"
    monkeypatch.setenv("BRAVO_SPILLOVER_HOME", str(home))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData-Local"))
    return home


@pytest.fixture(scope="session", autouse=True)
def _guard_real_bravo_spillover_untouched():
    """Session-wide proof the REAL %LOCALAPPDATA%/bravo-spillover is
    byte-for-byte the same (within the watched subpaths) before and after
    this file's tests run - lane_key.py DOES write (DPAPI blobs), so this
    is the one file in this trio where that proof matters most."""
    before = _snapshot(_REAL_BRAVO_SPILLOVER_HOME)
    yield
    after = _snapshot(_REAL_BRAVO_SPILLOVER_HOME)
    assert after == before, (
        f"a test touched the REAL {_REAL_BRAVO_SPILLOVER_HOME} "
        f"(before={before!r}, after={after!r})"
    )


def _run_lane_key(args, home, **kw) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["BRAVO_SPILLOVER_HOME"] = str(home)
    return subprocess.run(
        [PYTHON, "-S", str(LANE_KEY), *args],
        env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30, **kw,
    )


@pytest.fixture
def home(tmp_path):
    """A throwaway HOME_DIR, never the real bravo-spillover install."""
    return tmp_path / "bravo-spillover"


# --------------------------------------------------------- generate / exists / get ---

@WINDOWS_ONLY
def test_generate_then_exists_then_get_round_trips(home):
    gen = _run_lane_key(["generate", "jwt_secret"], home)
    assert gen.returncode == EXIT_OK, gen.stderr

    ex = _run_lane_key(["exists", "jwt_secret"], home)
    assert ex.returncode == EXIT_OK
    assert ex.stdout.strip() == "true"

    got = _run_lane_key(["get", "jwt_secret"], home)
    assert got.returncode == EXIT_OK
    assert len(got.stdout.strip()) > 20  # secrets.token_urlsafe(32) default


@WINDOWS_ONLY
def test_api_key_secret_name_also_round_trips(home):
    """CONTRACT section 16: jwt_secret and api_key_secret are new secret names
    beside omniroute_lane / storage_encryption / initial_password. lane_key is
    name-agnostic (NAME_RE only constrains format, nothing enumerates names),
    so this pins that the new name actually works end-to-end rather than just
    trusting the regex allows it."""
    gen = _run_lane_key(["generate", "api_key_secret"], home)
    assert gen.returncode == EXIT_OK, gen.stderr
    got = _run_lane_key(["get", "api_key_secret"], home)
    assert got.returncode == EXIT_OK
    assert len(got.stdout.strip()) > 20


@WINDOWS_ONLY
def test_generate_refuses_to_overwrite_without_force(home):
    first = _run_lane_key(["generate", "storage_encryption"], home)
    assert first.returncode == EXIT_OK, first.stderr
    v1 = _run_lane_key(["get", "storage_encryption"], home).stdout.strip()

    second = _run_lane_key(["generate", "storage_encryption"], home)
    assert second.returncode == EXIT_USAGE, second.stderr
    v2 = _run_lane_key(["get", "storage_encryption"], home).stdout.strip()
    assert v1 == v2, "a refused overwrite must leave the stored value untouched"

    forced = _run_lane_key(["generate", "storage_encryption", "--force"], home)
    assert forced.returncode == EXIT_OK, forced.stderr
    v3 = _run_lane_key(["get", "storage_encryption"], home).stdout.strip()
    assert v3 != v1


def test_exists_on_a_missing_secret_is_exit_2_and_prints_false(home):
    r = _run_lane_key(["exists", "no_such_secret"], home)
    assert r.returncode == EXIT_MISSING
    assert r.stdout.strip() == "false"


def test_get_on_a_missing_secret_is_exit_2(home):
    r = _run_lane_key(["get", "no_such_secret"], home)
    assert r.returncode == EXIT_MISSING
    assert r.stdout.strip() == ""  # nothing printed on a miss


def test_get_without_a_name_is_a_usage_error_not_a_silent_read():
    """'get never runs in non-test code paths without a name': the verb takes a
    required positional `name` (argparse), so the ONLY possible outcome of a
    bare `get` is a usage error before any store/decrypt call is reached --
    there is no path where get executes and prints a value with no name."""
    r = subprocess.run([PYTHON, "-S", str(LANE_KEY), "get"], env=dict(os.environ),
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == EXIT_USAGE
    assert r.stdout.strip() == ""


def test_a_malformed_name_is_rejected_before_touching_storage(home):
    r = _run_lane_key(["get", "../evil"], home)
    assert r.returncode == EXIT_USAGE
    assert not (home / "secrets").exists()


# ------------------------------------------------------------------------ DPAPI ---

@WINDOWS_ONLY
def test_dpapi_round_trip_in_process(home, monkeypatch):
    """The CLI test above proves generate/get round-trip through subprocess
    boundaries; this proves the underlying store()/load() primitive does too,
    and that the on-disk blob is not just the plaintext with extra steps."""
    spec = importlib.util.spec_from_file_location("lane_key_dpapi_probe", LANE_KEY)
    lane_key = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lane_key)
    monkeypatch.setenv("BRAVO_SPILLOVER_HOME", str(home))

    lane_key.store("initial_password", "correct horse battery staple")
    assert lane_key.load("initial_password") == "correct horse battery staple"

    blob = Path(lane_key.blob_path("initial_password"))
    assert blob.is_file()
    raw = blob.read_bytes()
    assert b"correct horse battery staple" not in raw, "the blob must not hold the plaintext"


@WINDOWS_ONLY
def test_load_of_a_missing_blob_is_none_not_an_exception(home, monkeypatch):
    spec = importlib.util.spec_from_file_location("lane_key_dpapi_probe2", LANE_KEY)
    lane_key = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lane_key)
    monkeypatch.setenv("BRAVO_SPILLOVER_HOME", str(home))
    assert lane_key.load("never_stored") is None
    assert lane_key.exists("never_stored") is False


# -------------------------------------------------------------------------- ACL ---

@WINDOWS_ONLY
def test_the_secret_blob_acl_grants_only_the_current_user(home):
    r = _run_lane_key(["generate", "omniroute_lane"], home)
    assert r.returncode == EXIT_OK, r.stderr
    blob = home / "secrets" / "omniroute_lane.key"
    assert blob.is_file()

    icacls = subprocess.run(["icacls", str(blob)], capture_output=True, text=True, timeout=30)
    assert icacls.returncode == 0, icacls.stderr
    out = icacls.stdout
    # Real observed shape: "<path> DOMAIN\\user:(F)" on one line, then a blank
    # line, then "Successfully processed 1 files; Failed processing 0 files".
    # Exactly one ACE line, one account on it -- that IS "owner-only".
    ace_lines = [ln for ln in out.splitlines() if ":(" in ln]
    assert len(ace_lines) == 1, f"expected exactly one ACE line, got: {ace_lines!r}\nfull output: {out!r}"
    line = ace_lines[0]
    assert line.count(":(") == 1, f"more than one account on the ACE line: {line!r}"
    for bad in ("Everyone", "BUILTIN\\Users", "Authenticated Users", "NT AUTHORITY\\SYSTEM"):
        assert bad.lower() not in line.lower(), f"{bad} present in blob ACL: {line!r}"
    user = os.environ.get("USERNAME", "")
    if user:
        assert user.lower() in line.lower(), f"current user {user!r} not in ACL: {line!r}"


@WINDOWS_ONLY
def test_the_secrets_directory_acl_also_locks_to_the_current_user(home):
    r = _run_lane_key(["generate", "omniroute_lane"], home)
    assert r.returncode == EXIT_OK, r.stderr
    sdir = home / "secrets"
    icacls = subprocess.run(["icacls", str(sdir)], capture_output=True, text=True, timeout=30)
    assert icacls.returncode == 0, icacls.stderr
    ace_lines = [ln for ln in icacls.stdout.splitlines() if ":(" in ln]
    assert len(ace_lines) == 1, f"expected exactly one ACE line, got: {ace_lines!r}"
    for bad in ("Everyone", "BUILTIN\\Users", "Authenticated Users", "NT AUTHORITY\\SYSTEM"):
        assert bad.lower() not in ace_lines[0].lower()


# ------------------------------------------------------------------ secret_guard ---

def _feed_secret_guard(command: str, tool_name: str = "Bash",
                       mode: str = "enforce") -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": tool_name, "tool_input": {"command": command}})
    env = dict(os.environ)
    env["EMPIRE_HOOK_SECRET_GUARD"] = mode
    return subprocess.run(
        [PYTHON, str(SECRET_GUARD)], input=payload, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30, cwd=str(REPO_ROOT),
    )


@pytest.mark.parametrize("command", [
    "python scripts/spillover/lane_key.py get omniroute_lane",
    "python scripts/spillover/lane_key.py get jwt_secret",
    "\"C:/Users/User/Business-Empire-Agent/.venv/Scripts/python.exe\" -S bin/lane_key.py get storage_encryption",
    "python -c \"import lane_key; print(lane_key.load('x'))\"",
    "python -c \"from lane_key import load; print(load('x'))\"",
])
def test_secret_guard_blocks_lane_key_get_on_bash(command):
    r = _feed_secret_guard(command, tool_name="Bash")
    assert r.returncode == 2, f"expected block, got rc={r.returncode}, stderr={r.stderr!r}"
    assert "BLOCKED by secret_guard" in r.stderr
    assert "lane_key" in r.stderr.lower()


def test_secret_guard_blocks_lane_key_get_on_powershell():
    command = "& $python scripts\\spillover\\lane_key.py get jwt_secret"
    r = _feed_secret_guard(command, tool_name="PowerShell")
    assert r.returncode == 2, r.stderr
    assert "BLOCKED by secret_guard" in r.stderr


@pytest.mark.parametrize("command", [
    "python scripts/spillover/lane_key.py exists omniroute_lane",
    "python scripts/spillover/lane_key.py generate jwt_secret",
    "python scripts/spillover/lane_key.py set jwt_secret --stdin",
])
def test_secret_guard_allows_every_other_lane_key_verb(command):
    r = _feed_secret_guard(command, tool_name="Bash")
    assert r.returncode == 0, f"unexpected block: {r.stderr!r}"


def test_secret_guard_lane_key_get_report_mode_does_not_block():
    r = _feed_secret_guard("python scripts/spillover/lane_key.py get jwt_secret", mode="report")
    assert r.returncode == 0
    assert "would block" in r.stderr.lower()


# -------------------------------------------------------------- audit_mcp_secrets ---

def _load_audit_module(home: str | None = None):
    """A fresh module object each call (never cached in sys.modules), so the
    BRAVO_SPILLOVER_HOME-dependent MCP_CONFIG_PATHS entry can be exercised per
    test without cross-test leakage -- same technique as
    test_secret_guard_traversal.py."""
    prior = os.environ.get("BRAVO_SPILLOVER_HOME")
    if home is not None:
        os.environ["BRAVO_SPILLOVER_HOME"] = home
    try:
        spec = importlib.util.spec_from_file_location("audit_mcp_secrets_spillover_probe", AUDIT_MCP)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if home is not None:
            if prior is None:
                os.environ.pop("BRAVO_SPILLOVER_HOME", None)
            else:
                os.environ["BRAVO_SPILLOVER_HOME"] = prior


@pytest.mark.parametrize("key", [
    "sk-0123456789abcdef-a1b2c3-9f8e7d6c",  # new: {16-hex machineId}-{6-hex keyId}-{8-hex crc}
    "sk-a1b2c3d4",                          # old: sk-{8-char random}
])
def test_omniroute_api_key_pattern_flags_a_synthetic_key(key):
    audit = _load_audit_module()
    hits = [label for label, pat in audit.LIVE_SECRET_PATTERNS if pat.search(key)]
    assert "omniroute-api-key" in hits, f"{key!r} was not flagged; hits={hits}"


@pytest.mark.parametrize("key,label", [
    ("sk-ant-api03-" + "x" * 40, "anthropic-api-key"),
    ("sk-proj-" + "y" * 40, "openai-api-key"),
])
def test_omniroute_api_key_pattern_does_not_double_flag_existing_sk_families(key, label):
    audit = _load_audit_module()
    hits = [lbl for lbl, pat in audit.LIVE_SECRET_PATTERNS if pat.search(key)]
    assert label in hits, f"control pattern {label} did not fire on its own fixture"
    assert "omniroute-api-key" not in hits, f"{key!r} double-flagged: {hits}"


def test_scan_file_reports_the_omniroute_kind(tmp_path):
    audit = _load_audit_module()
    cfg = tmp_path / "config.json"
    cfg.write_text('{"lane_key": "sk-0123456789abcdef-a1b2c3-9f8e7d6c"}', encoding="utf-8")
    findings = audit.scan_file(str(cfg))
    assert any(f["kind"] == "omniroute-api-key" for f in findings), findings


def test_home_dir_config_json_is_in_the_scanned_paths(tmp_path):
    audit = _load_audit_module(home=str(tmp_path))
    expected = os.path.join(str(tmp_path), "config.json")
    assert expected in audit.MCP_CONFIG_PATHS


def test_spillover_config_json_scan_would_catch_a_leaked_key(tmp_path):
    """End-to-end: a live OmniRoute key sitting in HOME_DIR/config.json is
    exactly the leak this audit exists to catch -- the same guarantee every
    other entry in MCP_CONFIG_PATHS carries."""
    audit = _load_audit_module(home=str(tmp_path))
    cfg_path = Path(tmp_path) / "config.json"
    cfg_path.write_text(json.dumps({"proxy": {"lane_key": "sk-a1b2c3d4"}}), encoding="utf-8")
    findings = audit.scan_file(str(cfg_path))
    assert any(f["kind"] == "omniroute-api-key" for f in findings)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
