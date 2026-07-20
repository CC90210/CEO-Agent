"""Regression tests for credential-fallback and history scanning policy."""

from __future__ import annotations

import ast
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCAN_PATH = ROOT / "scripts" / "scan_secrets.py"
BREEZE_PATH = ROOT / "scripts" / "breeze_set_tenant_email.py"


def _load_scanner():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("scan_secrets_contract", SCAN_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_breeze_helper():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("breeze_helper_contract", BREEZE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_sensitive_env_literal_fallback_is_detected_without_leaking_value():
    scanner = _load_scanner()
    unsafe = "os.environ" + '.get("CLIENT_PASSWORD", "not-a-real-fixture-secret")'

    hits = scanner._scan_text(unsafe)

    assert hits == [
        ("Hardcoded sensitive env fallback", "CLIENT_PASSWORD=<literal fallback>")
    ]
    assert "not-a-real-fixture-secret" not in repr(hits)


def test_documented_placeholder_tokens_are_not_findings():
    scanner = _load_scanner()

    assert scanner._scan_text("123456789:EXAMPLE-TELEGRAM-BOT-TOKEN-PLACE-ME") == []
    assert scanner._scan_text("123456789:ABCdefGHIjklMNOPQRSTUV-EXAMPLE") == []
    assert scanner._scan_text("xoxb-EXAMPLE-SLACK-TOKEN-PLACE-ME") == []


def test_secret_shaped_filename_is_detected_in_history(tmp_path: Path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=tmp_path, check=True
    )
    (tmp_path / ".env.production").write_text(
        "SAFE_FIXTURE=not-a-token\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", ".env.production"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=tmp_path, check=True)

    result = scanner.scan_history(tmp_path)

    assert any(
        finding["rule"] == "Secret-shaped filename"
        and finding["path"] == ".env.production"
        for finding in result["findings"]
    )


def test_historical_rename_cannot_hide_secret_shaped_filename(tmp_path: Path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / ".env.production").write_text("SAFE=true\n", encoding="utf-8")
    subprocess.run(["git", "add", ".env.production"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "sensitive name"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "mv", ".env.production", "safe.txt"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "commit", "-qm", "rename"], cwd=tmp_path, check=True)

    result = scanner.scan_history(tmp_path)

    assert result.get("error") is None
    assert any(
        finding["rule"] == "Secret-shaped filename"
        and finding["path"] == ".env.production"
        for finding in result["findings"]
    )


def test_merged_side_branch_cannot_hide_historical_secret_filename(tmp_path: Path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "base.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "base.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    subprocess.run(["git", "switch", "-qc", "feature"], cwd=tmp_path, check=True)
    (tmp_path / ".env.production").write_text("SAFE=true\n", encoding="utf-8")
    subprocess.run(["git", "add", ".env.production"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "feature secret name"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "switch", "-q", "main"], cwd=tmp_path, check=True)
    (tmp_path / "main.txt").write_text("main\n", encoding="utf-8")
    subprocess.run(["git", "add", "main.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "main"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "merge", "-q", "-s", "ours", "feature", "-m", "ours merge"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "branch", "-D", "feature"], cwd=tmp_path, check=True)

    result = scanner.scan_history(tmp_path)

    assert result.get("error") is None
    assert any(
        finding["rule"] == "Secret-shaped filename"
        and finding["path"] == ".env.production"
        for finding in result["findings"]
    )


def test_tree_tag_path_is_covered_by_history_filename_policy(tmp_path: Path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    blob = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"],
        cwd=tmp_path,
        check=True,
        input=b"SAFE=true\n",
        capture_output=True,
    ).stdout.strip().decode("ascii")
    tree = subprocess.run(
        ["git", "mktree"],
        cwd=tmp_path,
        check=True,
        input=f"100644 blob {blob}\t.env.production\n".encode("ascii"),
        capture_output=True,
    ).stdout.strip().decode("ascii")
    subprocess.run(["git", "tag", "tree-snapshot", tree], cwd=tmp_path, check=True)

    result = scanner.scan_history(tmp_path)

    assert result.get("error") is None
    assert any(
        finding["rule"] == "Secret-shaped filename"
        and finding["path"] == ".env.production"
        for finding in result["findings"]
    )


def test_secret_shaped_untracked_filename_is_detected_in_tree(tmp_path: Path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".env.production").write_text(
        "SAFE_FIXTURE=not-a-token\n", encoding="utf-8"
    )

    result = scanner.scan_tree(tmp_path)

    assert any(
        finding["rule"] == "Secret-shaped filename"
        and finding["path"] == ".env.production"
        for finding in result["findings"]
    )


def test_breeze_helper_requires_sealed_login_credentials():
    source = BREEZE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    string_literals = {
        node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
    }

    assert "BREEZE_QA_FUNDER_EMAIL" in string_literals
    assert "BREEZE_QA_FUNDER_PASSWORD" in string_literals
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"get", "getenv"}
        and len(node.args) > 1
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and "PASSWORD" in target.id.upper()
            for target in (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
        )
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for node in ast.walk(tree)
    )


def test_breeze_helper_is_noop_without_apply(monkeypatch):
    helper = _load_breeze_helper()
    monkeypatch.setattr(
        helper,
        "load_env",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("secrets loaded")),
    )
    monkeypatch.setattr(sys, "argv", ["breeze_set_tenant_email.py"])

    assert helper.main() == 0


def test_git_failures_are_tool_errors_not_clean_scans(monkeypatch, tmp_path):
    scanner = _load_scanner()
    monkeypatch.setattr(scanner, "_git_cmd", lambda *_args, **_kwargs: (1, "boom"))

    tree = scanner.scan_tree(tmp_path)
    history = scanner.scan_history(tmp_path)

    assert tree["error"]
    assert history["error"]
    assert scanner._format_findings(tree) == 2
    assert scanner._format_findings(history) == 2


def test_unreadable_tracked_file_is_an_incomplete_scan(monkeypatch, tmp_path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    target = tmp_path / "tracked.py"
    target.write_text("safe = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.py"], cwd=tmp_path, check=True)

    original = Path.read_bytes

    def fail_target(path: Path, *args, **kwargs):
        if path == target:
            raise OSError("fixture unreadable")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", fail_target)
    result = scanner.scan_tree(tmp_path)

    assert result["error"] == (
        "could not read worktree file tracked.py; tree scan incomplete"
    )
    assert scanner._format_findings(result) == 2


def test_large_tracked_text_file_is_scanned(tmp_path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    target = tmp_path / "large.py"
    unsafe = "os.environ" + '.get("CLIENT_PASSWORD", "not-a-real-fixture-secret")'
    target.write_text(("# padding\n" * 240_000) + unsafe, encoding="utf-8")
    subprocess.run(["git", "add", "large.py"], cwd=tmp_path, check=True)

    result = scanner.scan_tree(tmp_path)

    assert result.get("error") is None
    assert any(
        finding["rule"] == "Hardcoded sensitive env fallback"
        for finding in result["findings"]
    )


def test_oversized_staged_blob_fails_closed(monkeypatch, tmp_path: Path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    target = tmp_path / "large.txt"
    target.write_text("safe-but-large", encoding="utf-8")
    subprocess.run(["git", "add", "large.txt"], cwd=tmp_path, check=True)
    monkeypatch.setattr(scanner, "MAX_SCAN_BLOB_BYTES", 4)

    result = scanner.scan_tree(tmp_path)

    assert "scan refused to load it" in result["error"]
    assert scanner._format_findings(result) == 2


def test_oversized_index_aggregate_fails_closed(monkeypatch, tmp_path: Path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "one.txt").write_text("12345678", encoding="utf-8")
    (tmp_path / "two.txt").write_text("abcdefgh", encoding="utf-8")
    subprocess.run(["git", "add", "one.txt", "two.txt"], cwd=tmp_path, check=True)
    monkeypatch.setattr(scanner, "MAX_INDEX_SNAPSHOT_BYTES", 12)

    result = scanner.scan_tree(tmp_path)

    assert "staged snapshot is" in result["error"]
    assert scanner._format_findings(result) == 2


def test_index_aliases_decode_shared_blob_only_once(monkeypatch, tmp_path: Path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "one.txt").write_text("identical\n", encoding="utf-8")
    (tmp_path / "two.txt").write_text("identical\n", encoding="utf-8")
    subprocess.run(["git", "add", "one.txt", "two.txt"], cwd=tmp_path, check=True)
    original = scanner._decode_scan_bytes
    calls = 0

    def counted(data: bytes) -> str:
        nonlocal calls
        calls += 1
        return original(data)

    monkeypatch.setattr(scanner, "_decode_scan_bytes", counted)

    snapshot, _gitlinks, _symlinks = scanner._read_index_snapshot(
        tmp_path, {"one.txt", "two.txt"}
    )

    assert calls == 1
    assert snapshot["one.txt"] is snapshot["two.txt"]


def test_missing_worktree_file_is_scanned_from_staged_blob(tmp_path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    target = tmp_path / "staged.py"
    unsafe = "os.environ" + '.get("CLIENT_PASSWORD", "not-a-real-fixture-secret")'
    target.write_text(unsafe, encoding="utf-8")
    subprocess.run(["git", "add", "staged.py"], cwd=tmp_path, check=True)
    target.unlink()

    result = scanner.scan_tree(tmp_path)

    assert result.get("error") is None
    assert any(
        finding["path"] == "staged.py"
        and finding["rule"] == "Hardcoded sensitive env fallback"
        for finding in result["findings"]
    )


def test_clean_worktree_edit_cannot_hide_secret_staged_in_index(tmp_path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    target = tmp_path / "staged.py"
    unsafe = "os.environ" + '.get("CLIENT_PASSWORD", "not-a-real-fixture-secret")'
    target.write_text(unsafe, encoding="utf-8")
    subprocess.run(["git", "add", "staged.py"], cwd=tmp_path, check=True)
    target.write_text("safe = True\n", encoding="utf-8")

    result = scanner.scan_tree(tmp_path)

    assert result.get("error") is None
    assert any(
        finding["path"] == "staged.py"
        and finding["rule"] == "Hardcoded sensitive env fallback"
        for finding in result["findings"]
    )


def test_safe_index_cannot_hide_secret_in_unstaged_worktree(tmp_path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    target = tmp_path / "tracked.py"
    target.write_text("safe = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.py"], cwd=tmp_path, check=True)
    unsafe = "os.environ" + '.get("CLIENT_PASSWORD", "not-a-real-fixture-secret")'
    target.write_text(unsafe, encoding="utf-8")

    result = scanner.scan_tree(tmp_path)

    assert result.get("error") is None
    assert any(
        finding["path"] == "tracked.py"
        and finding["rule"] == "Hardcoded sensitive env fallback"
        for finding in result["findings"]
    )


def test_utf16_tracked_text_cannot_hide_secret(tmp_path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    target = tmp_path / "encoded.py"
    token = "sk-" + ("A" * 32)
    target.write_text(f'API_KEY = "{token}"\n', encoding="utf-16")
    subprocess.run(["git", "add", "encoded.py"], cwd=tmp_path, check=True)

    result = scanner.scan_tree(tmp_path)

    assert result.get("error") is None
    assert any(
        finding["path"] == "encoded.py"
        and finding["rule"] == "OpenAI API key"
        for finding in result["findings"]
    )


def test_malformed_utf16_suffix_cannot_hide_valid_secret_prefix(tmp_path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    target = tmp_path / "malformed.bin"
    token = "sk-" + ("A" * 32)
    target.write_bytes(token.encode("utf-16-le") + b"\xff")
    subprocess.run(["git", "add", "malformed.bin"], cwd=tmp_path, check=True)

    result = scanner.scan_tree(tmp_path)

    assert result.get("error") is None
    assert any(
        finding["path"] == "malformed.bin"
        and finding["rule"] == "OpenAI API key"
        for finding in result["findings"]
    )


def test_tracked_file_in_vendor_named_directory_is_never_skipped(tmp_path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    target = tmp_path / "dist" / "leak.txt"
    target.parent.mkdir()
    token = "sk-" + ("A" * 32)
    target.write_text(f'API_KEY = "{token}"\n', encoding="utf-8")
    subprocess.run(["git", "add", "dist/leak.txt"], cwd=tmp_path, check=True)

    result = scanner.scan_tree(tmp_path)

    assert result.get("error") is None
    assert any(
        finding["path"] == "dist/leak.txt"
        and finding["rule"] == "OpenAI API key"
        for finding in result["findings"]
    )


def test_tracked_binary_named_file_is_never_skipped(tmp_path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    target = tmp_path / "release.pdf"
    token = "sk-" + ("A" * 32)
    target.write_bytes(token.encode("ascii"))
    subprocess.run(["git", "add", "release.pdf"], cwd=tmp_path, check=True)

    result = scanner.scan_tree(tmp_path)

    assert result.get("error") is None
    assert any(
        finding["path"] == "release.pdf"
        and finding["rule"] == "OpenAI API key"
        for finding in result["findings"]
    )


def test_checked_out_gitlink_is_not_read_as_a_worktree_file(tmp_path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "base.txt").write_text("safe\n", encoding="utf-8")
    subprocess.run(["git", "add", "base.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (tmp_path / "vendor" / "sub").mkdir(parents=True)
    subprocess.run(
        ["git", "update-index", "--add", "--cacheinfo", "160000", head, "vendor/sub"],
        cwd=tmp_path,
        check=True,
    )

    result = scanner.scan_tree(tmp_path)

    assert result.get("error") is None


def test_git_smudge_filter_cannot_hide_secret_in_raw_index_blob(tmp_path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "filter.redact.smudge", "python -c \"print('SAFE')\""],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / ".gitattributes").write_text("leak.txt filter=redact\n", encoding="utf-8")
    target = tmp_path / "leak.txt"
    token = "sk-" + ("A" * 32)
    target.write_text(token, encoding="utf-8")
    subprocess.run(["git", "add", ".gitattributes", "leak.txt"], cwd=tmp_path, check=True)
    target.write_text("SAFE\n", encoding="utf-8")

    result = scanner.scan_tree(tmp_path)

    assert result.get("error") is None
    assert any(
        finding["path"] == "leak.txt" and finding["rule"] == "OpenAI API key"
        for finding in result["findings"]
    )


def test_placeholder_word_inside_real_secret_is_not_suppressed():
    scanner = _load_scanner()
    token = "sk-" + ("A" * 12) + "EXAMPLE" + ("B" * 12)
    fallback = "os.environ" + '.get("CLIENT_PASSWORD", "ProdEXAMPLEpassword2026!")'

    token_hits = scanner._scan_text(token)
    fallback_hits = scanner._scan_text(fallback)

    assert any(rule == "OpenAI API key" for rule, _match in token_hits)
    assert fallback_hits == [
        ("Hardcoded sensitive env fallback", "CLIENT_PASSWORD=<literal fallback>")
    ]


def test_utf16_bom_with_long_nul_free_prefix_cannot_hide_secret(tmp_path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    target = tmp_path / "wide.py"
    token = "sk-" + ("A" * 32)
    target.write_text(("中" * 5000) + "\n" + token, encoding="utf-16")
    subprocess.run(["git", "add", "wide.py"], cwd=tmp_path, check=True)

    result = scanner.scan_tree(tmp_path)

    assert result.get("error") is None
    assert any(
        finding["path"] == "wide.py" and finding["rule"] == "OpenAI API key"
        for finding in result["findings"]
    )


def test_non_ascii_tracked_path_is_scanned_without_git_quoting_drift(tmp_path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    target = tmp_path / "café.txt"
    token = "sk-" + ("A" * 32)
    target.write_text(token, encoding="utf-8")
    subprocess.run(["git", "add", target.name], cwd=tmp_path, check=True)

    result = scanner.scan_tree(tmp_path)

    assert result.get("error") is None
    assert any(
        finding["path"] == "café.txt" and finding["rule"] == "OpenAI API key"
        for finding in result["findings"]
    )


@pytest.mark.skipif(os.name == "nt", reason="Windows filenames cannot contain backslashes")
def test_literal_backslash_filename_keeps_index_and_worktree_identity(tmp_path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    target = tmp_path / "odd\\name.txt"
    target.write_text("safe\n", encoding="utf-8")
    subprocess.run(["git", "add", "--", target.name], cwd=tmp_path, check=True)
    token = "sk-" + ("A" * 32)
    target.write_text(token, encoding="utf-8")

    result = scanner.scan_tree(tmp_path)

    assert result.get("error") is None
    assert any(
        finding["path"] == target.name and finding["rule"] == "OpenAI API key"
        for finding in result["findings"]
    )


def test_history_scans_utf16_blob_that_git_diff_treats_as_binary(tmp_path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    target = tmp_path / "encoded.txt"
    token = "sk-" + ("A" * 32)
    target.write_text(token + "\n", encoding="utf-16")
    subprocess.run(["git", "add", "encoded.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "encoded fixture"], cwd=tmp_path, check=True)

    result = scanner.scan_history(tmp_path)

    assert result.get("error") is None
    assert any(
        finding["path"] == "encoded.txt"
        and finding["rule"] == "OpenAI API key"
        for finding in result["findings"]
    )


def test_allowlisted_baseline_name_cannot_hide_tree_or_aliased_history_secret(tmp_path):
    scanner = _load_scanner()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    token = "sk-" + ("A" * 32)
    (tmp_path / ".secrets.baseline").write_text(token, encoding="utf-8")
    (tmp_path / "leak.txt").write_text(token, encoding="utf-8")
    subprocess.run(
        ["git", "add", ".secrets.baseline", "leak.txt"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "commit", "-qm", "aliased fixture"], cwd=tmp_path, check=True)

    tree = scanner.scan_tree(tmp_path)
    history = scanner.scan_history(tmp_path)

    assert any(finding["rule"] == "OpenAI API key" for finding in tree["findings"])
    assert any(finding["rule"] == "OpenAI API key" for finding in history["findings"])
