"""Tests for scripts/build_bridge_manifest.py.

Run via:
    python scripts/test_build_bridge_manifest.py
    python -m pytest scripts/test_build_bridge_manifest.py -v

No pytest dependency required — uses plain assertions + a tiny test
harness. Pattern matches scripts/test_send_gateway.py + scripts/test_name_utils.py.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

# Import the module under test
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import build_bridge_manifest as bbm  # type: ignore
import check_bridge_manifest as cbm  # type: ignore


def _make_script(tmp_dir: Path, name: str, content: str) -> Path:
    """Write a fixture script and return its path. Patches bbm.SCRIPTS_DIR
    so build_one() resolves relative-to correctly."""
    p = tmp_dir / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def _with_repo_root(tmp_dir: Path):
    """Patch bbm.REPO_ROOT and bbm.SCRIPTS_DIR for one test."""
    original_root = bbm.REPO_ROOT
    original_scripts = bbm.SCRIPTS_DIR
    bbm.REPO_ROOT = tmp_dir
    bbm.SCRIPTS_DIR = tmp_dir / "scripts"
    bbm.SCRIPTS_DIR.mkdir(exist_ok=True)
    return original_root, original_scripts


def _restore(original_root: Path, original_scripts: Path) -> None:
    bbm.REPO_ROOT = original_root
    bbm.SCRIPTS_DIR = original_scripts


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_explicit_read_only_header_classifies_subcommands_correctly():
    """Read-only behavior must be declared rather than inferred from a verb."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            p = _make_script(bbm.SCRIPTS_DIR, "fake_reader.py", '''
                # bridge_mutating: false
                """Read-only fake reader."""
                import argparse
                def main():
                    p = argparse.ArgumentParser()
                    sub = p.add_subparsers(dest="cmd")
                    sub.add_parser("list")
                    sub.add_parser("show")
                    args = p.parse_args()
            ''')
            entries = bbm.build_one(p)
            assert len(entries) == 2, f"expected 2 entries, got {len(entries)}"
            for e in entries:
                assert e["mutating"] is False, f"{e['key']} should be read-only"
            assert {e["subcmd"] for e in entries} == {"list", "show"}
        finally:
            _restore(*original)


def test_legacy_subcommands_fail_closed_without_declared_policy():
    """Verb names alone cannot grant a no-confirm execution path."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            p = _make_script(bbm.SCRIPTS_DIR, "fake_writer.py", '''
                """Test fixture for verb detection."""
                import argparse
                def main():
                    p = argparse.ArgumentParser()
                    sub = p.add_subparsers(dest="cmd")
                    sub.add_parser("list")        # read-only
                    sub.add_parser("send")        # mutating
                    sub.add_parser("delete-row")  # mutating
                    sub.add_parser("status")      # read-only
                    args = p.parse_args()
            ''')
            entries = bbm.build_one(p)
            by_sub = {e["subcmd"]: e for e in entries}
            assert by_sub["list"]["mutating"] is True
            assert by_sub["send"]["mutating"] is True, "send should be mutating"
            assert by_sub["delete-row"]["mutating"] is True, "delete-row should be mutating"
            assert by_sub["status"]["mutating"] is True
        finally:
            _restore(*original)


def test_header_override_mutating_false():
    """# bridge_mutating: false forces read-only even on a 'send' subcommand."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            p = _make_script(bbm.SCRIPTS_DIR, "fake_safe_send.py", '''
                # bridge_mutating: false
                """Sends nothing real, just simulates."""
                import argparse
                def main():
                    p = argparse.ArgumentParser()
                    sub = p.add_subparsers(dest="cmd")
                    sub.add_parser("send")  # would normally be mutating
                    args = p.parse_args()
            ''')
            entries = bbm.build_one(p)
            assert len(entries) == 1
            assert entries[0]["mutating"] is False, (
                "bridge_mutating: false header should override verb detection"
            )
        finally:
            _restore(*original)


def test_header_override_mutating_true():
    """# bridge_mutating: true forces mutating even on a list-only script."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            p = _make_script(bbm.SCRIPTS_DIR, "fake_dangerous_list.py", '''
                # bridge_mutating: true
                """List that has dangerous side effects."""
                import argparse
                def main():
                    p = argparse.ArgumentParser()
                    sub = p.add_subparsers(dest="cmd")
                    sub.add_parser("list")
                    args = p.parse_args()
            ''')
            entries = bbm.build_one(p)
            assert len(entries) == 1
            assert entries[0]["mutating"] is True, (
                "bridge_mutating: true header should force mutating"
            )
        finally:
            _restore(*original)


def test_visibility_opt_out():
    """# bridge_visible: false excludes the script entirely."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            p = _make_script(bbm.SCRIPTS_DIR, "fake_internal.py", '''
                # bridge_visible: false
                """Internal helper, not for chat."""
                import argparse
                def main():
                    p = argparse.ArgumentParser()
                    sub = p.add_subparsers(dest="cmd")
                    sub.add_parser("list")
                    args = p.parse_args()
            ''')
            entries = bbm.build_one(p)
            assert entries == [], "bridge_visible: false should exclude the script"
        finally:
            _restore(*original)


def test_blocklist_excludes():
    """A script in BLOCKLIST returns no entries even if otherwise eligible."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            # build_capability_graph.py is in the blocklist
            p = _make_script(bbm.SCRIPTS_DIR, "build_capability_graph.py", '''
                """Should be blocked."""
                import argparse
                def main():
                    p = argparse.ArgumentParser()
                    p.parse_args()
            ''')
            entries = bbm.build_one(p)
            assert entries == [], "blocklisted script must produce zero entries"
        finally:
            _restore(*original)


def test_underscore_prefix_excluded():
    """_internal.py is treated like a private module — excluded."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            p = _make_script(bbm.SCRIPTS_DIR, "_private_helper.py", '''
                """Private helper."""
                import argparse
                def main():
                    p = argparse.ArgumentParser()
                    p.add_subparsers(dest="cmd").add_parser("send")
                    p.parse_args()
            ''')
            entries = bbm.build_one(p)
            assert entries == [], "_-prefixed scripts should be excluded"
        finally:
            _restore(*original)


def test_no_docstring_no_argparse_excluded():
    """A script with no docstring and no argparse parser is auto-excluded
    (auto-detection requires both unless bridge_visible: true is set)."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            p = _make_script(bbm.SCRIPTS_DIR, "fake_naked.py", '''
                import sys
                print("hello")
            ''')
            entries = bbm.build_one(p)
            assert entries == [], "scripts without docstring + argparse are excluded"
        finally:
            _restore(*original)


def test_visibility_opt_in_overrides_missing_argparse():
    """# bridge_visible: true forces inclusion even with no argparse."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            p = _make_script(bbm.SCRIPTS_DIR, "fake_simple.py", '''
                # bridge_visible: true
                """A simple script with no argparse."""
                import sys
                print("hi")
            ''')
            entries = bbm.build_one(p)
            assert len(entries) == 1, "bridge_visible: true should force inclusion"
            assert entries[0]["subcmd"] is None
        finally:
            _restore(*original)


def test_capability_metadata_controls_each_subcommand_policy():
    """Literal CAPABILITY_META is authoritative over verb heuristics."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            p = _make_script(bbm.SCRIPTS_DIR, "fake_pause.py", '''
                """Pause controller fixture."""
                import argparse
                CAPABILITY_META = {
                    "category": "outbound.safety",
                    "lifecycle": "active",
                    "risk": "external_write",
                    "triggers": ["pause outbound"],
                    "owner": "bravo",
                    "project": "sunbiz",
                    "bridge": {
                        "visible": True,
                        "confirm": True,
                        "subcommands": {
                            "pause": {"visible": True, "confirm": True},
                            "status": {"visible": True, "confirm": False},
                        },
                    },
                }
                p = argparse.ArgumentParser()
                sub = p.add_subparsers(dest="cmd")
                sub.add_parser("pause")
                sub.add_parser("status")
            ''')
            by_sub = {entry["subcmd"]: entry for entry in bbm.build_one(p)}
            assert by_sub["pause"]["mutating"] is True
            assert by_sub["status"]["mutating"] is False
        finally:
            _restore(*original)


def test_declared_subcommands_are_an_allowlist_and_may_define_public_keys():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            p = _make_script(bbm.SCRIPTS_DIR, "alias_tool.py", '''
                """Alias fixture."""
                import argparse
                CAPABILITY_META = {
                    "category": "data.operations",
                    "lifecycle": "active",
                    "risk": "external_write",
                    "triggers": ["query data"],
                    "owner": "bravo",
                    "project": "empire",
                    "bridge": {
                        "visible": True,
                        "confirm": True,
                        "subcommands": {
                            "query": {
                                "key": "alias_sql",
                                "visible": True,
                                "confirm": True,
                            },
                        },
                    },
                }
                parser = argparse.ArgumentParser()
                sub = parser.add_subparsers(dest="cmd")
                sub.add_parser("query")
                sub.add_parser("delete")
            ''')
            entries = bbm.build_one(p)
            assert [(entry["key"], entry["subcmd"]) for entry in entries] == [
                ("alias_sql", "query"),
            ]
            assert entries[0]["mutating"] is True
        finally:
            _restore(*original)


def test_nested_scripts_require_literal_capability_metadata():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            nested = bbm.SCRIPTS_DIR / "integrations"
            nested.mkdir()
            _make_script(nested, "unregistered.py", '''
                """Nested legacy CLI must not be auto-exposed."""
                import argparse
                argparse.ArgumentParser()
            ''')
            _make_script(nested, "registered.py", '''
                """Nested registered CLI."""
                import argparse
                CAPABILITY_META = {
                    "category": "data.operations",
                    "lifecycle": "active",
                    "risk": "read_only",
                    "triggers": ["read data"],
                    "owner": "bravo",
                    "project": "empire",
                    "bridge": {"visible": True, "confirm": False},
                }
                argparse.ArgumentParser()
            ''')
            manifest = bbm.build_manifest()
            paths = {entry["path"] for entry in manifest["entries"]}
            assert "scripts/integrations/registered.py" in paths
            assert "scripts/integrations/unregistered.py" not in paths
        finally:
            _restore(*original)


def test_capability_metadata_hides_unsafe_script():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            p = _make_script(bbm.SCRIPTS_DIR, "fake_hidden.py", '''
                """Unsafe fixture."""
                import argparse
                CAPABILITY_META = {
                    "category": "data.operations",
                    "lifecycle": "one_off",
                    "risk": "external_write",
                    "triggers": ["rewrite data"],
                    "owner": "bravo",
                    "project": "oasis",
                    "bridge": {"visible": False},
                }
                argparse.ArgumentParser()
            ''')
            assert bbm.build_one(p) == []
        finally:
            _restore(*original)


def test_metadata_denied_arguments_are_emitted_for_runtime_enforcement():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            p = _make_script(bbm.SCRIPTS_DIR, "fake_scanner.py", '''
                """Read-only scan with a destructive legacy flag."""
                import argparse
                CAPABILITY_META = {
                    "category": "security.privacy",
                    "lifecycle": "active",
                    "risk": "destructive",
                    "triggers": ["scan pii"],
                    "owner": "bravo",
                    "project": "empire",
                    "bridge": {
                        "visible": True,
                        "confirm": False,
                        "deny_args": ["--rewrite"],
                    },
                }
                argparse.ArgumentParser()
            ''')
            entries = bbm.build_one(p)
            assert len(entries) == 1
            assert entries[0]["mutating"] is False
            assert entries[0]["deny_args"] == ["--rewrite"]
        finally:
            _restore(*original)


def test_metadata_confirmation_arguments_are_emitted_for_runtime_escalation():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            p = _make_script(bbm.SCRIPTS_DIR, "fake_capture.py", '''
                """Read a page, optionally writing a screenshot."""
                import argparse
                CAPABILITY_META = {
                    "category": "browser.research",
                    "lifecycle": "active",
                    "risk": "local_write",
                    "triggers": ["capture page"],
                    "owner": "bravo",
                    "project": "empire",
                    "bridge": {
                        "visible": True,
                        "confirm": False,
                        "confirm_args": ["--screenshot"],
                    },
                }
                argparse.ArgumentParser()
            ''')
            entries = bbm.build_one(p)
            assert entries[0]["mutating"] is False
            assert entries[0]["confirm_args"] == ["--screenshot"]
        finally:
            _restore(*original)


def test_unknown_flat_script_fails_closed_as_confirm_required():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            p = _make_script(bbm.SCRIPTS_DIR, "ambiguous_tool.py", '''
                """Ambiguous operator-facing tool."""
                import argparse
                argparse.ArgumentParser()
            ''')
            entries = bbm.build_one(p)
            assert len(entries) == 1
            assert entries[0]["mutating"] is True
        finally:
            _restore(*original)


def test_unknown_subcommands_fail_closed_as_confirm_required():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            p = _make_script(bbm.SCRIPTS_DIR, "ambiguous_commands.py", '''
                """Ambiguous operator-facing commands."""
                import argparse
                parser = argparse.ArgumentParser()
                sub = parser.add_subparsers(dest="cmd")
                sub.add_parser("list")
                sub.add_parser("status")
            ''')
            entries = bbm.build_one(p)
            assert entries
            assert all(entry["mutating"] is True for entry in entries)
        finally:
            _restore(*original)


def test_reviewed_real_script_bridge_contracts():
    scripts = bbm.REPO_ROOT / "scripts"
    manifest = bbm.build_manifest()
    assert manifest["version"] == 2
    manifest_keys = {entry["key"] for entry in manifest["entries"]}
    assert not any(key.startswith("harness_plugin") for key in manifest_keys)
    assert not any(key.startswith("history_secret_scan") for key in manifest_keys)
    for hidden in (
        "breeze_set_tenant_email.py",
        "consolidate_mca_phone_sheet.py",
        "enrich_sheet_inplace.py",
        "migrate_lender_industry_restrictions_key.py",
        "run_reseed_sunbiz_forms.py",
        "seed_sunbiz_application_form_fields.py",
    ):
        assert bbm.build_one(scripts / hidden) == [], hidden

    pause = {entry["subcmd"]: entry for entry in bbm.build_one(scripts / "pause_controller.py")}
    assert pause["status"]["mutating"] is False
    assert pause["get-mode"]["mutating"] is False
    assert pause["pause"]["mutating"] is True
    assert pause["resume"]["mutating"] is True
    assert pause["set-mode"]["mutating"] is True

    pii = bbm.build_one(scripts / "pii_sweep.py")
    assert len(pii) == 1
    assert pii[0]["mutating"] is False
    assert pii[0]["deny_args"] == ["--rewrite", "--strings"]
    assert pii[0]["fixed_args"] == ["."]


def test_canonical_nested_bridge_keys_are_backed_by_real_subcommands():
    manifest = bbm.build_manifest()
    entries = {entry["key"]: entry for entry in manifest["entries"]}
    expected = {
        # turso_* replaced supabase_* at the 2026-08-09 Turso cutover: the
        # supabase compat shim sets bridge visible: False, which excludes ALL
        # of its subcommand keys from the manifest (asserted absent below).
        "turso_status": ("scripts/integrations/turso_tool.py", "status", False),
        "turso_tables": ("scripts/integrations/turso_tool.py", "tables", False),
        "send_gateway_send": ("scripts/integrations/send_gateway.py", "send", True),
        "cloak_browser_scrape": ("scripts/browser/cloak_browser_tool.py", "scrape", False),
        "cloak_browser_check_stealth": (
            "scripts/browser/cloak_browser_tool.py",
            "check-stealth",
            False,
        ),
        "cloak_browser_download": ("scripts/browser/cloak_browser_tool.py", "download", True),
        "agent_inbox_send": ("scripts/core/agent_inbox.py", "post", True),
        "agent_inbox_inbox": ("scripts/core/agent_inbox.py", "list", False),
        "agent_inbox_ack": ("scripts/core/agent_inbox.py", "read", True),
    }
    for key, (path, subcmd, mutating) in expected.items():
        entry = entries[key]
        assert (entry["path"], entry["subcmd"], entry["mutating"]) == (
            path,
            subcmd,
            mutating,
        )

    for nonexistent in ("send_gateway_queue", "send_gateway_list", "send_gateway_pending"):
        assert nonexistent not in entries

    # The deprecated supabase compat shim is bridge-hidden wholesale.
    for retired in ("supabase_select", "supabase_insert", "supabase_sql",
                    "supabase_update", "supabase_delete"):
        assert retired not in entries
    assert "cloak_browser_clear_cache" not in entries


def test_manifest_drift_detects_denied_argument_policy_changes():
    disk = {
        "entries": [
            {"key": "pii_sweep", "mutating": False, "deny_args": [], "help": "old"},
        ]
    }
    live = {
        "entries": [
            {"key": "pii_sweep", "mutating": False, "deny_args": ["--rewrite"], "help": "new"},
        ]
    }
    diff = cbm._diff(live, disk)
    assert diff["policy_changed"] == ["pii_sweep"]


def test_manifest_drift_detects_schema_version_changes():
    disk = {"version": 1, "entries": []}
    live = {"version": 2, "entries": []}
    assert cbm._diff(live, disk)["version_changed"] is True


def test_oversized_script_skipped_at_manifest_level():
    """A script with >MAX_ENTRIES_PER_SCRIPT subcommands is skipped during
    full-manifest assembly (not at build_one — that's where the cap lives)."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            # Generate a script with cap+5 subcommands
            n = bbm.MAX_ENTRIES_PER_SCRIPT + 5
            sub_lines = "\n".join(f'                    sub.add_parser("cmd_{i}")' for i in range(n))
            _make_script(bbm.SCRIPTS_DIR, "fake_oversized.py", f'''
                """Oversized script."""
                import argparse
                def main():
                    p = argparse.ArgumentParser()
                    sub = p.add_subparsers(dest="cmd")
{sub_lines}
                    p.parse_args()
            ''')
            manifest = bbm.build_manifest()
            # The oversized script should NOT appear
            paths_in_manifest = {e["path"] for e in manifest["entries"]}
            assert "scripts/fake_oversized.py" not in paths_in_manifest, (
                "oversized scripts must be skipped at manifest level"
            )
        finally:
            _restore(*original)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

def _run_all() -> int:
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failures += 1
        except Exception as e:
            print(f"  ERR   {t.__name__}: {type(e).__name__}: {e}")
            failures += 1
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_all())
