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

def test_read_only_subcommand_classified_correctly():
    """A subcommand with no mutating verb -> mutating=False."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        original = _with_repo_root(td_path)
        try:
            p = _make_script(bbm.SCRIPTS_DIR, "fake_reader.py", '''
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


def test_mutating_verb_in_subcommand_detected():
    """A subcommand with 'send' or 'delete' -> mutating=True."""
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
            assert by_sub["list"]["mutating"] is False
            assert by_sub["send"]["mutating"] is True, "send should be mutating"
            assert by_sub["delete-row"]["mutating"] is True, "delete-row should be mutating"
            assert by_sub["status"]["mutating"] is False
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
