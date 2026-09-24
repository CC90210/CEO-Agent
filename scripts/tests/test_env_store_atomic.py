"""Atomic, single-copy contract for the canonical agents env store.

The tests deliberately use synthetic values.  They never open the real
``.env.agents`` file.
"""

from __future__ import annotations

import importlib.util
import os
import re
import stat
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "env_store_atomic", ROOT / "scripts" / "lib" / "env_store.py"
)
env_store = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(env_store)


ENV_STORE_MUTATORS = (
    "scripts/integrations/arthrisil_stripe_setup.py",
    "scripts/integrations/n8n_webhook_secret.py",
    "scripts/integrations/oasis_store_stripe_setup.py",
    "scripts/integrations/public_bundle_recover.py",
    "scripts/integrations/secret_apply_authorized.py",
    "scripts/integrations/secret_disk_hunt.py",
    "scripts/integrations/secret_fuzzy_match.py",
    "scripts/integrations/secret_store_restructure.py",
    "scripts/integrations/turso_admin.py",
    "scripts/integrations/vercel_env_pull_sync.py",
    "scripts/integrations/vercel_secret_sync.py",
    "scripts/provision_maven_telegram.py",
    "scripts/provision_secrets.py",
    "scripts/set_secret.py",
    "scripts/turso_vps_bundle.py",
)


@pytest.fixture
def bypass_platform_acl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit tests platform-neutral; ACL behavior has focused tests below."""
    monkeypatch.setattr(
        env_store,
        "_secure_file_permissions",
        lambda *_args, **_kwargs: None,
        raising=False,
    )


def _noncanonical_files(directory: Path, target: Path) -> list[Path]:
    """Support files may exist, but no second plaintext credential file may."""
    sidecar_base = target.name if target.name.startswith(".") else f".{target.name}"
    return [
        item
        for item in directory.iterdir()
        if item != target and item.name != f"{sidecar_base}.lock"
    ]


def test_atomic_write_replaces_from_same_directory_without_leaving_a_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bypass_platform_acl: None,
) -> None:
    target = tmp_path / ".env.agents"
    target.write_text("ALPHA=old\n", encoding="utf-8")
    real_replace = os.replace
    seen: dict[str, Path] = {}

    def capture_replace(
        source: str | os.PathLike[str], destination: str | os.PathLike[str]
    ) -> None:
        seen["source"] = Path(source)
        seen["destination"] = Path(destination)
        real_replace(source, destination)

    monkeypatch.setattr(env_store.os, "replace", capture_replace)

    env_store.atomic_write_text(target, "ALPHA=new\n")

    assert target.read_text(encoding="utf-8") == "ALPHA=new\n"
    assert seen["source"].parent == target.parent
    assert seen["destination"] == target
    assert _noncanonical_files(tmp_path, target) == []


@pytest.mark.parametrize("failure_point", ["fsync", "replace"])
def test_atomic_write_failure_leaves_original_unchanged_and_removes_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
    bypass_platform_acl: None,
) -> None:
    target = tmp_path / ".env.agents"
    original = "ALPHA=original\n"
    target.write_text(original, encoding="utf-8")

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError(f"synthetic {failure_point} failure")

    monkeypatch.setattr(env_store.os, failure_point, fail)

    with pytest.raises(OSError, match=f"synthetic {failure_point} failure"):
        env_store.atomic_write_text(target, "ALPHA=replacement\n")

    assert target.read_text(encoding="utf-8") == original
    assert _noncanonical_files(tmp_path, target) == []


def test_atomic_write_uses_unique_exact_pattern_fsynced_temp_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bypass_platform_acl: None,
) -> None:
    target = tmp_path / ".env.agents"
    target.write_text("ALPHA=old\n", encoding="utf-8")
    real_replace = os.replace
    sources: list[Path] = []
    events: list[str] = []

    def capture_fsync(_fd: int) -> None:
        events.append("fsync")

    def capture_replace(
        source: str | os.PathLike[str], destination: str | os.PathLike[str]
    ) -> None:
        source_path = Path(source)
        sources.append(source_path)
        events.append("replace")
        real_replace(source, destination)

    monkeypatch.setattr(env_store.os, "fsync", capture_fsync)
    monkeypatch.setattr(env_store.os, "replace", capture_replace)

    env_store.atomic_write_text(target, "ALPHA=one\n")
    env_store.atomic_write_text(target, "ALPHA=two\n")

    assert len(sources) == 2
    assert sources[0] != sources[1]
    pattern = re.compile(r"^\.env\.agents\.tmp\.\d+\.[0-9a-f]{32}$")
    assert all(source.parent == target.parent for source in sources)
    assert all(pattern.fullmatch(source.name) for source in sources)
    assert events.index("fsync") < events.index("replace")
    assert _noncanonical_files(tmp_path, target) == []


def test_update_env_values_serializes_concurrent_writers_without_lost_keys(
    tmp_path: Path,
    bypass_platform_acl: None,
) -> None:
    target = tmp_path / ".env.agents"
    target.write_text("BASE=present\n", encoding="utf-8")

    def write_one(index: int) -> None:
        env_store.update_env_values(target, {f"KEY_{index}": f"value-{index}"})

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(write_one, range(48)))

    parsed = env_store.parse_file(target)
    assert parsed["BASE"] == "present"
    for index in range(48):
        assert parsed[f"KEY_{index}"] == f"value-{index}"


def test_update_env_values_collapses_duplicates_and_preserves_other_lines(
    tmp_path: Path,
    bypass_platform_acl: None,
) -> None:
    target = tmp_path / ".env.agents"
    target.write_text(
        "# keep this comment\nALPHA=old\nUNCHANGED=yes\nexport ALPHA=stale\n",
        encoding="utf-8",
    )

    env_store.update_env_values(target, {"ALPHA": "new", "BRAVO_KEY": "added"})

    text = target.read_text(encoding="utf-8")
    assert text.count("ALPHA=") == 1
    assert "ALPHA=new" in text
    assert "UNCHANGED=yes" in text
    assert "# keep this comment" in text
    assert "BRAVO_KEY=added" in text


def test_remove_env_keys_drops_every_copy_and_keeps_the_rest(
    tmp_path: Path,
    bypass_platform_acl: None,
) -> None:
    target = tmp_path / ".env.agents"
    target.write_text(
        "# keep\nDUP=a\nKEEP=yes\nexport DUP=b\nNS__DUP=canonical\n",
        encoding="utf-8",
    )

    assert env_store.remove_env_keys(target, ["DUP"]) is True
    text = target.read_text(encoding="utf-8")
    assert "DUP=a" not in text and "DUP=b" not in text
    assert "NS__DUP=canonical" in text, "only the named key goes, never a prefix match"
    assert "KEEP=yes" in text and "# keep" in text
    assert env_store.remove_env_keys(target, ["DUP"]) is False, "idempotent"
    with pytest.raises(env_store.EnvStoreValidationError):
        env_store.remove_env_keys(target, ["bad key"])


@pytest.mark.parametrize("relative_path", ENV_STORE_MUTATORS)
def test_env_store_mutators_hold_one_lock_across_read_modify_write(
    relative_path: str,
) -> None:
    """A writer must not read first and acquire the canonical lock afterward."""
    path = ROOT / relative_path
    source = path.read_text(encoding="utf-8")

    assert "atomic_write_text(" not in source, (
        f"{relative_path} reads and writes outside one env-store transaction"
    )
    assert any(
        primitive in source
        for primitive in ("locked_update_text(", "update_env_values(")
    ), (
        f"{relative_path} must mutate through the canonical locked API"
    )


@pytest.mark.parametrize("bad_value", ["one\ntwo", "one\rtwo", "one\x00two"])
def test_update_env_values_rejects_env_breaking_values_without_mutating_store(
    tmp_path: Path,
    bad_value: str,
    bypass_platform_acl: None,
) -> None:
    target = tmp_path / ".env.agents"
    original = "SAFE=original\n"
    target.write_text(original, encoding="utf-8")

    with pytest.raises(env_store.EnvStoreValidationError):
        env_store.update_env_values(target, {"UNSAFE": bad_value})

    assert target.read_text(encoding="utf-8") == original


def test_stale_temp_recovery_only_removes_old_exact_pattern_when_canonical_is_safe(
    tmp_path: Path,
) -> None:
    target = tmp_path / ".env.agents"
    target.write_text("SAFE=canonical\n", encoding="utf-8")
    old = tmp_path / f"{target.name}.tmp.123.{('a' * 32)}"
    fresh = tmp_path / f"{target.name}.tmp.456.{('b' * 32)}"
    decoy = tmp_path / f"{target.name}.tmp.not-a-real-writer"
    for path in (old, fresh, decoy):
        path.write_text("synthetic=test\n", encoding="utf-8")
    now = time.time()
    os.utime(old, (now - 7200, now - 7200))
    os.utime(fresh, (now - 30, now - 30))
    os.utime(decoy, (now - 7200, now - 7200))

    removed = env_store.recover_stale_temp_files(
        target, stale_after_seconds=3600, now=now
    )

    assert removed == (old,)
    assert not old.exists()
    assert fresh.exists()
    assert decoy.exists()
    assert target.read_text(encoding="utf-8") == "SAFE=canonical\n"


def test_stale_temp_recovery_keeps_only_recoverable_copy_when_canonical_missing(
    tmp_path: Path,
) -> None:
    target = tmp_path / ".env.agents"
    orphan = tmp_path / f"{target.name}.tmp.123.{('c' * 32)}"
    orphan.write_text("synthetic=recoverable\n", encoding="utf-8")
    old = time.time() - 7200
    os.utime(orphan, (old, old))

    assert env_store.recover_stale_temp_files(target, stale_after_seconds=1) == ()
    assert orphan.exists()


def test_update_refuses_to_overwrite_recovery_candidate_when_canonical_is_missing(
    tmp_path: Path,
    bypass_platform_acl: None,
) -> None:
    target = tmp_path / ".env.agents"
    orphan = tmp_path / f"{target.name}.tmp.123.{('d' * 32)}"
    orphan.write_text("synthetic=recoverable\n", encoding="utf-8")

    with pytest.raises(env_store.EnvStoreRecoveryError, match="manual recovery"):
        env_store.update_env_values(target, {"NEW_KEY": "new-value"})

    assert not target.exists()
    assert orphan.exists()


def test_permission_hardening_failure_is_loud_and_original_survives(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / ".env.agents"
    original = "SAFE=original\n"
    target.write_text(original, encoding="utf-8")

    def fail_hardening(*_args: object, **_kwargs: object) -> None:
        raise env_store.EnvStoreSecurityError("synthetic ACL failure")

    monkeypatch.setattr(env_store, "_secure_file_permissions", fail_hardening, raising=False)

    with pytest.raises(env_store.EnvStoreSecurityError, match="synthetic ACL failure"):
        env_store.atomic_write_text(target, "SAFE=replacement\n")

    assert target.read_text(encoding="utf-8") == original
    assert _noncanonical_files(tmp_path, target) == []


def test_windows_acl_contract_preserves_owner_system_and_administrators() -> None:
    script = env_store._WINDOWS_ACL_SCRIPT
    assert "GetOwner" in script
    assert "SetOwner" in script
    assert "S-1-5-18" in script
    assert "S-1-5-32-544" in script
    assert "SetAccessRuleProtection($true, $false)" in script


def test_harden_env_file_never_reads_or_rewrites_secret_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / ".env.agents"
    target.write_text("SYNTHETIC=untouched\n", encoding="utf-8")
    calls: list[tuple[Path, Path | None]] = []

    def capture(path: Path, *, mode: int, owner_source: Path | None) -> None:
        assert mode == 0o600
        calls.append((path, owner_source))

    monkeypatch.setattr(env_store, "_secure_file_permissions", capture)
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("secret content must not be opened")
        ),
    )

    env_store.harden_env_file(target)

    assert calls == [(target, target)]


def test_windows_acl_command_failure_raises_security_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "synthetic.env"
    target.write_text("SAFE=test\n", encoding="utf-8")
    monkeypatch.setattr(
        env_store.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=5, stdout="", stderr="denied"),
    )

    with pytest.raises(env_store.EnvStoreSecurityError, match="ACL hardening failed"):
        env_store._harden_windows_acl(target, owner_source=target)


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL integration")
def test_windows_acl_hardens_a_synthetic_store_end_to_end(tmp_path: Path) -> None:
    target = tmp_path / ".env.agents"
    env_store.atomic_write_text(target, "SYNTHETIC=test\n")
    assert target.read_text(encoding="utf-8") == "SYNTHETIC=test\n"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission semantics")
def test_posix_store_mode_is_exactly_0600(tmp_path: Path) -> None:
    target = tmp_path / ".env.agents"
    env_store.atomic_write_text(target, "SAFE=test\n")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_dashboard_and_wizard_route_env_mutations_through_canonical_api() -> None:
    dashboard = (ROOT / "bravo_cli" / "bridge_chat_server.py").read_text(encoding="utf-8")
    wizard = (ROOT / "bravo_cli" / "wizard.py").read_text(encoding="utf-8")

    dashboard_handler = dashboard[
        dashboard.index("def _handle_env_set"):dashboard.index("def _handle_diag")
    ]
    wizard_writer = wizard[wizard.index("def write_env"):wizard.index("def read_env")]
    assert "update_env_values(" in dashboard_handler
    assert "env_path.write_text(" not in dashboard_handler
    assert "update_env_values(" in wizard_writer
    assert ".tmp" not in wizard_writer


def test_wizard_cannot_recreate_legacy_scoped_env_duplicates() -> None:
    wizard = (ROOT / "bravo_cli" / "wizard.py").read_text(encoding="utf-8")
    assert "V6_SCOPED_ENV_FILES" not in wizard
    assert "_fan_out_scoped_env_files" not in wizard
    assert "_write_scoped_env_file" not in wizard
    assert ".env.agents.{" not in wizard


def test_production_code_cannot_create_persistent_env_agent_backups() -> None:
    """Scan all active production code, not only scripts/."""
    forbidden = re.compile(
        r"(?:\.env\.agents\.(?:bak(?:\.|['\"]|\$)|backup(?:\.|['\"]|\$)|"
        r"sunbiz_inherited_backup)|\.agents\.bak(?:[.\-]|['\"]|\$))"
    )
    duplicate_creator = re.compile(r"\.env\.agents\.(?:core|webhook|dashboard|\{)")
    allowed = {ROOT / "scripts" / "state" / "secret_guard.py"}
    excluded_dirs = {
        ".git", ".next", ".pytest_cache", "__pycache__", "node_modules",
        ".venv", "venv",
        "vendor", "vendors", "generated", "dist", "build", "coverage",
        "archive", "archives", "_archive", "tmp", "state", "memory", "evals",
    }
    offenders: list[str] = []

    source_suffixes = {".py", ".sh", ".ps1", ".js", ".mjs", ".cjs", ".ts", ".tsx"}
    for current, dirnames, filenames in os.walk(ROOT):
        directory = Path(current)
        relative_directory = directory.relative_to(ROOT)
        dirnames[:] = [
            name
            for name in dirnames
            if name.lower() not in excluded_dirs
            and (relative_directory / name).as_posix()
            != "apps/oasis-desktop/resources/sidecar"  # bundle-sidecar.js output
        ]
        for filename in filenames:
            path = directory / filename
            relative = path.relative_to(ROOT)
            if path.suffix.lower() not in source_suffixes:
                continue
            if path in allowed or "tests" in relative.parts or path.name.startswith("test_"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if forbidden.search(text) or duplicate_creator.search(text):
                offenders.append(relative.as_posix())

    assert offenders == [], "plaintext .env.agents duplicate creators: " + ", ".join(offenders)


def test_active_docs_never_instruct_plaintext_env_backup_or_legacy_fanout() -> None:
    plaintext_copy = re.compile(
        r"(?im)^\s*(?:cp|copy-item)\s+(?:-\S+\s+)*\.env\.agents\s+\S+"
    )
    legacy_copy = re.compile(r"\.env\.agents\.(?:bak|backup|core|webhook|dashboard)")
    docs = list((ROOT / "docs").rglob("*.md"))
    docs.extend(ROOT / name for name in ("ARCHITECTURE.md", "PLAYBOOK.md", "README.md"))
    offenders: list[str] = []
    for path in docs:
        if not path.is_file() or any(
            part.lower() in {"archive", "archives", "_archive", "generated", "vendor"}
            for part in path.relative_to(ROOT).parts
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if plaintext_copy.search(text) or legacy_copy.search(text):
            offenders.append(path.relative_to(ROOT).as_posix())

    assert offenders == [], "unsafe active env-store documentation: " + ", ".join(offenders)


def test_encrypted_backup_streams_plaintext_directly_into_gpg() -> None:
    source = (ROOT / "scripts" / "ops" / "env_backup.sh").read_text(encoding="utf-8")
    assert "mktemp -d" not in source
    assert "cp -a" not in source
    assert '<<<"$PASS"' not in source
    assert re.search(r'tar\s+-C\s+"\$REPO_ROOT"\s+-czf\s+-.*\|\s*gpg', source, re.DOTALL)
