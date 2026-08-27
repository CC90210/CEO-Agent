"""Tests for the cross-agent coordination substrate (coord_claim / coord_guard).

These pin the three properties the OLD claim mechanism lacked, each of which is
traceable to a measured failure in the 90 days to 2026-08-27:

  GRAMMAR  — agent_activity accepted files=["pipeline","Turso"] and
             ["oasis:app/lead-sheets/**"], then compared them by exact string.
             Overlap could never be detected. Now a claim must be a
             repo-relative path or it is refused.
  COVERAGE — a directory or glob claim must actually cover the files under it.
  ISOLATION— a lease in repo A must not block the same filename in repo B, and
             an agent must never be blocked by its own lease.

Plus the guard's decision table, which has exactly one denial condition.

No network: the DB layer is stubbed. These test the LOGIC, not Turso — the live
round-trip is proven separately by the acceptance test in the APEX handover.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from lib import ownership, repo_paths  # noqa: E402


# ---------------------------------------------------------------- grammar ----

@pytest.fixture()
def claim_mod(monkeypatch):
    """coord_claim with the DB stubbed out."""
    from integrations import coord_claim
    monkeypatch.setattr(coord_claim, "live_claims", lambda *a, **k: [])
    return coord_claim


@pytest.mark.parametrize("bad", [
    "oasis:app/lead-sheets/x.ts",   # APEX's namespace-prefix style
    "turso:leadgen_leads",          # a table, not a file
    "/etc/passwd",                  # POSIX absolute — is_absolute() is False on Windows
    "C:/Users/x/secret.ts",         # Windows absolute — is_absolute() is False on POSIX
    r"\\server\share\x.ts",         # UNC
    "../outside/x.ts",              # escaping the repo
])
def test_grammar_refuses_uncomparable_claims(claim_mod, bad):
    """The exact strings both agents actually wrote must now be refused.

    files=["pipeline","Turso"] was accepted for two months and protected
    nothing — it read as coverage while being unmatchable.
    """
    with pytest.raises(ValueError):
        claim_mod._validate_paths("oasis-command-center", [bad], strict=False)


def test_grammar_refuses_a_path_that_does_not_exist_in_the_repo(claim_mod):
    with pytest.raises(ValueError) as e:
        claim_mod._validate_paths("Business-Empire-Agent",
                                  ["definitely/not/here.ts"], strict=True)
    assert "protects nothing" in str(e.value)


def test_grammar_accepts_globs_without_stat(claim_mod):
    """Globs cannot be stat'd, so strict mode must not reject them."""
    out = claim_mod._validate_paths("oasis-command-center",
                                    ["lib/drips/**", "app/api/*/route.ts"], strict=True)
    assert out == ["lib/drips/**", "app/api/*/route.ts"]


def test_grammar_normalises_windows_separators(claim_mod):
    out = claim_mod._validate_paths("x", [r"lib\drips\executor.ts"], strict=False)
    assert out == ["lib/drips/executor.ts"]


# --------------------------------------------------------------- coverage ----

@pytest.mark.parametrize("glob,path,expected", [
    ("lib/drips/executor.ts", "lib/drips/executor.ts", True),
    ("lib/drips",             "lib/drips/executor.ts", True),   # dir covers children
    ("lib/drips/**",          "lib/drips/a/b.ts",      True),
    ("lib/*.ts",              "lib/x.ts",              True),
    ("lib/drips",             "lib/dripsfoo.ts",       False),  # prefix != directory
    ("lib/drips/executor.ts", "lib/drips/send.ts",     False),
    ("app/api/**",            "lib/x.ts",              False),
])
def test_covers(glob, path, expected):
    assert repo_paths.covers(glob, path) is expected


def test_directory_claim_does_not_leak_to_sibling_prefix():
    """`lib/drips` must not cover `lib/dripsfoo.ts`. A naive startswith() would
    silently over-claim a file the holder never intended to lock."""
    assert repo_paths.covers("lib/drips", "lib/drips/x.ts")
    assert not repo_paths.covers("lib/drips", "lib/dripsfoo.ts")


# -------------------------------------------------------------- ownership ----

def test_specific_pattern_beats_broad_pattern():
    """bravo owns `**` in Business-Empire-Agent, but the shared handover docs
    must still resolve to `shared` — otherwise the broad rule swallows them."""
    assert ownership.owner("Business-Empire-Agent", "scripts/foo.py") == "bravo"
    assert ownership.owner("Business-Empire-Agent",
                           "docs/APEX_SYSTEM_MESSAGE.md") == "shared"


def test_measured_apex_surfaces_resolve_to_apex():
    assert ownership.owner("oasis-command-center",
                           "components/conversations/Pane.tsx") == "apex"
    assert ownership.owner("oasis-command-center",
                           "components/campaigns/Sender.tsx") == "apex"


def test_unknown_path_defaults_to_contested_not_free():
    """Unknown must mean 'claim it', never 'help yourself'."""
    assert ownership.is_contested("oasis-command-center", "brand/new/thing.ts")
    assert ownership.is_contested("some-repo-we-have-never-seen", "x.ts")


def test_ownership_cache_roundtrips_dates():
    """PyYAML returns date objects for `updated: 2026-08-27`; json.dumps must not
    choke on them or the cache silently never writes and every edit re-imports
    PyYAML (~700ms)."""
    data = ownership._compile()
    assert ownership.CACHE_PATH.exists(), "sidecar cache was not written"
    cached = json.loads(ownership.CACHE_PATH.read_text(encoding="utf-8"))
    assert cached["data"]["repos"].keys() == data["repos"].keys()


# ------------------------------------------------------------ guard gate ----

GUARD = REPO_ROOT / "scripts" / "state" / "coord_guard.py"
OCC = "C:/Users/User/APPS/oasis-command-center"


def _run_guard(payload: dict, claims: list[dict], mode="enforce"):
    """Drive the hook with a pre-seeded mirror so no network is touched."""
    import os
    import time
    mirror = REPO_ROOT / "state" / "coord_claims_mirror.json"
    backup = mirror.read_text(encoding="utf-8") if mirror.exists() else None
    try:
        mirror.write_text(json.dumps({"fetched_at": time.time(), "claims": claims}),
                          encoding="utf-8")
        env = {**os.environ, "EMPIRE_HOOK_COORD_GUARD": mode,
               "COORD_GUARD_CACHE_TTL_SEC": "600", "COORD_AGENT_KEY": "bravo"}
        return subprocess.run([sys.executable, str(GUARD)], input=json.dumps(payload),
                              capture_output=True, text=True, env=env, timeout=120)
    finally:
        if backup is not None:
            mirror.write_text(backup, encoding="utf-8")
        elif mirror.exists():
            mirror.unlink()


def _lease(agent="apex", repo="oasis-command-center", path="lib/drips/executor.ts"):
    return {"agent": agent, "repo": repo, "path_glob": path, "task": "peer work",
            "branch": "apex/x", "machine": "ADONPC", "expires_at": "2099-01-01T00:00:00+00:00"}


def test_guard_blocks_only_on_a_live_peer_lease():
    r = _run_guard({"tool_name": "Edit",
                    "tool_input": {"file_path": f"{OCC}/lib/drips/executor.ts"}},
                   [_lease()])
    assert r.returncode == 2
    assert "APEX" in r.stderr and "peer work" in r.stderr


def test_guard_never_blocks_on_my_own_lease():
    """The single 'bravo' row on 2026-08-16 proved identity confusion is real;
    an agent blocked by its own claim would be unusable."""
    r = _run_guard({"tool_name": "Edit",
                    "tool_input": {"file_path": f"{OCC}/lib/drips/executor.ts"}},
                   [_lease(agent="bravo")])
    assert r.returncode == 0


def test_guard_does_not_block_a_same_named_file_in_another_repo():
    r = _run_guard({"tool_name": "Edit",
                    "tool_input": {"file_path": str(REPO_ROOT / "README.md")}},
                   [_lease(repo="Business-Empire-Agent", path="README.md")
                    | {"agent": "apex"}])
    # peer lease is on Business-Empire-Agent/README.md and so is the edit -> blocked
    assert r.returncode == 2
    r2 = _run_guard({"tool_name": "Edit",
                     "tool_input": {"file_path": f"{OCC}/README.md"}},
                    [_lease(repo="Business-Empire-Agent", path="README.md")
                     | {"agent": "apex"}])
    assert r2.returncode == 0, "a lease in one repo must not block another repo"


def test_guard_ignores_non_edit_tools():
    r = _run_guard({"tool_name": "Bash", "tool_input": {"command": "ls"}}, [_lease()])
    assert r.returncode == 0


def test_report_mode_never_blocks_but_does_record():
    r = _run_guard({"tool_name": "Edit",
                    "tool_input": {"file_path": f"{OCC}/lib/drips/executor.ts"}},
                   [_lease()], mode="report")
    assert r.returncode == 0
    assert "would block" in r.stderr


def test_off_mode_is_a_pure_passthrough():
    r = _run_guard({"tool_name": "Edit",
                    "tool_input": {"file_path": f"{OCC}/lib/drips/executor.ts"}},
                   [_lease()], mode="off")
    assert r.returncode == 0 and r.stderr.strip() == ""


def test_guard_nudges_on_unclaimed_contested_surface():
    """No peer lease, but a measured-contested path and no lease of our own —
    the exact state that produced every recorded collision."""
    r = _run_guard({"tool_name": "Edit",
                    "tool_input": {"file_path": f"{OCC}/lib/drips/executor.ts"}}, [])
    assert r.returncode == 0
    assert "CONTESTED" in r.stderr


def test_guard_is_silent_on_an_owned_surface():
    r = _run_guard({"tool_name": "Edit",
                    "tool_input": {"file_path": f"{OCC}/lib/cold-outreach/send.ts"}}, [])
    assert r.returncode == 0
    assert "CONTESTED" not in r.stderr


# ---------------------------------------- Codex adversarial review 2026-08-27 ----
# Four findings, all confirmed against the code and fixed. These pin the fixes.

def test_expiry_is_parsed_not_lexically_compared():
    """The old SQL did `expires_at > <now-iso>` — a LEXICAL comparison, sound
    only if every writer emits the identical UTC spelling. APEX is a second
    writer on this table.

    The bite is a non-UTC offset: a lease expiring at 16:34 UTC written as
    `18:34+02:00` sorts ABOVE a UTC "now" of 16:39, so an expired lease reads as
    live — here for a full two hours. Parsing makes the spelling irrelevant.
    """
    from datetime import datetime, timedelta, timezone
    from integrations.coord_claim import is_live, parse_ts
    now = datetime.now(timezone.utc)

    # expired 5 minutes ago, but written in +02:00 local time
    expired_utc = now - timedelta(minutes=5)
    expired_cet = expired_utc.astimezone(timezone(timedelta(hours=2))).isoformat()

    # the lexical trap this fix exists for: the EXPIRED string sorts as "future"
    assert expired_cet > now.isoformat(), "precondition: lexical order is wrong here"
    # ...and parsing gets it right anyway
    assert is_live({"expires_at": expired_cet}) is False

    assert is_live({"expires_at": (now + timedelta(minutes=5)).isoformat()
                    .replace("+00:00", "Z")}) is True
    assert is_live({"expires_at": (now - timedelta(minutes=5)).isoformat()
                    .replace("+00:00", "Z")}) is False
    assert parse_ts("not-a-date") is None


def test_unparseable_expiry_frees_the_path_rather_than_wedging_it():
    from integrations.coord_claim import is_live
    assert is_live({"expires_at": "garbage"}) is False
    assert is_live({"expires_at": None}) is False
    assert is_live({}) is False


def test_guard_mirror_ignores_expired_leases_during_an_outage():
    """A stale mirror must not keep enforcing a lease that has since expired —
    that would contradict the TTL guarantee for the whole outage."""
    from datetime import datetime, timedelta, timezone
    expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    r = _run_guard({"tool_name": "Edit",
                    "tool_input": {"file_path": f"{OCC}/lib/drips/executor.ts"}},
                   [_lease() | {"expires_at": expired}])
    assert r.returncode == 0, "an EXPIRED cached lease must not block"


def test_guard_mirror_still_blocks_on_an_unexpired_lease():
    """The companion to the test above — proving the fix did not just disable
    the gate. Break the test before trusting it."""
    r = _run_guard({"tool_name": "Edit",
                    "tool_input": {"file_path": f"{OCC}/lib/drips/executor.ts"}},
                   [_lease()])
    assert r.returncode == 2


def test_cron_skipped_jobs_are_visible_to_json_consumers():
    """The JSON path is what automation reads. Hiding pinned-elsewhere jobs
    there is how a job pinned to an offline machine vanishes fleet-wide."""
    import inspect
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "core"))
    import cron_engine
    src = inspect.getsource(cron_engine.cmd_due)
    assert "skipped_other_machine" in src
    # the early-return must sit INSIDE the json branch, not after it
    assert src.index("skipped_other_machine") < src.index("[cron] skipping")


def test_cron_filter_never_hides_an_unpinned_job():
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "core"))
    import cron_engine
    mine, theirs = cron_engine.filter_by_machine([
        {"name": "unpinned", "owner_machine": None},
        {"name": "blank", "owner_machine": "   "},
        {"name": "elsewhere", "owner_machine": "SOME-OTHER-BOX"},
    ])
    assert [j["name"] for j in mine] == ["unpinned", "blank"]
    assert [j["name"] for j in theirs] == ["elsewhere"]
