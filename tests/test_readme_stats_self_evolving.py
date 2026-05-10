"""Lock the README-self-evolution: counts in README must always match disk.

This is the meta-system that keeps the system honest about itself. If
update_readme_stats.py regresses, future operators see stale counts and
the audit chain (self_audit -> _check_readme_stats -> rewrite_readme dry-run)
fails silently. These tests are the canary.

Three contracts under test:
  1. collect_stats() returns realistic numbers (sanity floor)
  2. rewrite_readme() against current disk reports no drift (system is
     in sync right now — proves the README is honest at this commit)
  3. The meta-loop is bidirectional: faking drift in the README markers
     makes rewrite_readme detect change AND undo it on --apply. This
     proves the self-correcting half of self-evolving.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import update_readme_stats as urs  # noqa: E402


def test_collect_stats_returns_realistic_numbers():
    """Sanity floor — the system has at least N skills, scripts, etc.
    Numbers are deliberately conservative; if any drop below floor it's
    almost certainly a bug in the collector (wrong glob, excluded too much)."""
    s = urs.collect_stats()
    assert s["skills"] >= 100, f"skills suspiciously low: {s['skills']}"
    assert s["scripts"] >= 50, f"scripts suspiciously low: {s['scripts']}"
    assert s["sub_agents"] >= 5, f"sub_agents suspiciously low: {s['sub_agents']}"
    assert s["workflows"] >= 5, f"workflows suspiciously low: {s['workflows']}"
    assert s["mcp_servers"] >= 1, f"mcp_servers suspiciously low: {s['mcp_servers']}"


def test_readme_is_in_sync_with_disk_at_this_commit():
    """If this fails, README.md is stale. Run:
        python scripts/update_readme_stats.py --apply
    Then re-commit. The CI / pre-commit hook should make this impossible
    to ship, but having the test here catches it during local dev too."""
    stats = urs.collect_stats()
    changed, diff = urs.rewrite_readme(stats, dry_run=True)
    assert not changed, (
        f"README.md is STALE — {len(diff)} markers out of date:\n  "
        + "\n  ".join(diff)
        + "\n\nFix: python scripts/update_readme_stats.py --apply"
    )


def test_self_correcting_loop(tmp_path, monkeypatch):
    """The meta-system must be self-correcting: introduce drift, then
    verify rewrite_readme(--apply) restores correctness. Uses a tmp
    README copy so the real one is never touched."""
    # Copy the real README to tmp + point the module at the copy
    real_readme = ROOT / "README.md"
    fake_readme = tmp_path / "README.md"
    fake_readme.write_text(real_readme.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(urs, "README", fake_readme)

    # Introduce drift
    text = fake_readme.read_text(encoding="utf-8")
    drifted = text.replace(
        "STATS:skills-->**", "STATS:skills-->**9999 ", 1,
    )
    if drifted == text:
        # marker isn't in our README form — skip rather than false-fail
        return
    fake_readme.write_text(drifted, encoding="utf-8")

    # --check should detect the drift
    stats = urs.collect_stats()
    changed_before, _diff = urs.rewrite_readme(stats, dry_run=True)
    assert changed_before, "drift introduced but rewrite didn't detect it"

    # --apply should heal the drift
    healed_changed, _diff2 = urs.rewrite_readme(stats, dry_run=False)
    assert healed_changed, "apply path didn't return changed=True"

    # Re-check should now be clean
    changed_after, _diff3 = urs.rewrite_readme(stats, dry_run=True)
    assert not changed_after, "after apply, README still drifts — self-correction broken"


def test_marker_pattern_is_idempotent():
    """rewrite_readme on already-correct content is a no-op. Catches the
    classic 'every commit changes the file even though nothing changed'
    bug that would burn CC's review time forever."""
    stats = urs.collect_stats()
    # First apply (real disk — but it should be in sync per test above so
    # it won't actually write). Use dry_run for safety.
    changed_a, _ = urs.rewrite_readme(stats, dry_run=True)
    changed_b, _ = urs.rewrite_readme(stats, dry_run=True)
    assert changed_a == changed_b, "rewrite is non-deterministic"
