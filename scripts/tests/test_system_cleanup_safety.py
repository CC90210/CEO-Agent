from pathlib import Path

from scripts.core import system_cleanup


def test_non_oasis_directory_at_reserved_path_is_never_a_redundant_clone(
    tmp_path, monkeypatch
):
    home = tmp_path / "home"
    repo = home / ".oasis" / "wizard" / "repo"
    repo.mkdir(parents=True)
    (repo.parent / "operator-settings.json").write_text("keep", encoding="utf-8")

    monkeypatch.setattr(system_cleanup, "HOME", home)

    assert system_cleanup.find_redundant_clones() == []


def test_verified_redundant_clone_targets_repo_not_its_parent(tmp_path, monkeypatch):
    home = tmp_path / "home"
    repo = home / ".bravo" / "repo"
    repo.mkdir(parents=True)
    (repo / "payload.bin").write_bytes(b"payload")

    monkeypatch.setattr(system_cleanup, "HOME", home)
    monkeypatch.setattr(system_cleanup, "_is_oasis_repo", lambda path: path == repo)

    [candidate] = system_cleanup.find_redundant_clones()
    assert candidate["path"] == str(repo)
    assert candidate["is_oasis_clone"] is True


def test_redundant_clone_apply_moves_to_recoverable_quarantine(
    tmp_path, monkeypatch
):
    project = tmp_path / "active"
    project.mkdir()
    clone = tmp_path / "home" / ".bravo" / "repo"
    clone.mkdir(parents=True)
    (clone / "payload.bin").write_bytes(b"payload")
    monkeypatch.setattr(system_cleanup, "PROJECT_ROOT", project)

    report = {
        "redundant_clones": [{
            "path": str(clone),
            "size_bytes": 7,
            "size_human": "7.0 B",
        }],
        "pip_cache": {"exists": False},
        "npm_cache": {"exists": False},
        "tmp_old": {"size_human": "0 B"},
        "pycache_trees": {"size_human": "0 B"},
        "scaffold_backups": {"size_human": "0 B"},
        "_internal": {},
    }

    result = system_cleanup.apply_cleanup(report, set(), assume_yes=True)

    assert not clone.exists()
    held = list((project / "tmp" / ".hygiene_quarantine").iterdir())
    assert len(held) == 1
    assert (held[0] / "payload.bin").read_bytes() == b"payload"
    assert result["deleted"] == []
    assert result["quarantined"][0]["recoverable"] is True


def test_tmp_audit_excludes_quarantine_and_preserves_tree_with_fresh_child(
    tmp_path, monkeypatch
):
    repo = tmp_path / "active"
    tmp = repo / "tmp"
    quarantine = tmp / ".hygiene_quarantine"
    quarantine.mkdir(parents=True)
    held = quarantine / "held.log"
    held.write_bytes(b"held")
    mixed = tmp / "mixed-work"
    mixed.mkdir()
    old = mixed / "old.log"
    old.write_bytes(b"old")
    fresh = mixed / "fresh.log"
    fresh.write_bytes(b"fresh")

    import os
    import time

    old_time = time.time() - (30 * 86400)
    os.utime(held, (old_time, old_time))
    os.utime(old, (old_time, old_time))
    os.utime(mixed, (old_time, old_time))

    report = system_cleanup.find_old_tmp(repo, age_days=7)

    assert report["files"] == 0
    assert report["size_bytes"] == 0
    assert report["_paths"] == []
