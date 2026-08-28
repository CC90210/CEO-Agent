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
        claim_mod._validate_paths("ceo-agent",
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
    """bravo owns `**` in ceo-agent (this repo; slug is remote-derived, the
    directory is named Business-Empire-Agent), but the shared handover docs
    must still resolve to `shared` — otherwise the broad rule swallows them."""
    assert ownership.owner("ceo-agent", "scripts/foo.py") == "bravo"
    assert ownership.owner("ceo-agent",
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
    # ISOLATED mirror. Writing the live one races the guard running on the
    # operator's real edits and the watchdog's 5-minute pass — that produced a
    # flake that passed in isolation and failed in the suite.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mirror = Path(td) / "mirror.json"
        mirror.write_text(json.dumps({"fetched_at": time.time(), "claims": claims}),
                          encoding="utf-8")
        env = {**os.environ, "EMPIRE_HOOK_COORD_GUARD": mode,
               "COORD_GUARD_CACHE_TTL_SEC": "600", "COORD_AGENT_KEY": "bravo",
               "COORD_GUARD_MIRROR": str(mirror)}
        return subprocess.run([sys.executable, str(GUARD)], input=json.dumps(payload),
                              capture_output=True, text=True, env=env, timeout=120)


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
                   [_lease(repo="ceo-agent", path="README.md")
                    | {"agent": "apex"}])
    # peer lease is on Business-Empire-Agent/README.md and so is the edit -> blocked
    assert r.returncode == 2
    r2 = _run_guard({"tool_name": "Edit",
                     "tool_input": {"file_path": f"{OCC}/README.md"}},
                    [_lease(repo="ceo-agent", path="README.md")
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


# ================= APEX contract conformance (2026-08-27) =====================
# APEX (Adon's agent, machine UPPAECHELON) and Bravo must answer these
# IDENTICALLY or a lease means different things to each of us. Vectors are
# copied verbatim from APEX's contract §3.1 / §3.2 / §3.3. Do not "fix" a
# failure here by changing the expectation — it is a negotiated interface.

@pytest.mark.parametrize("url", [
    "https://github.com/CC90210/oasis-command-center.git",
    "https://github.com/CC90210/oasis-command-center",
    "git@github.com:CC90210/oasis-command-center.git",       # scp-like, colon
    "ssh://git@github.com/CC90210/Oasis-Command-Center.git",  # case normalises
])
def test_apex_slug_vectors(url):
    assert repo_paths.slug_from_url(url) == "oasis-command-center"


def test_a_worktree_resolves_to_the_same_slug_as_its_main_checkout():
    """THE blocking defect APEX reported: the slug was the top-level DIRECTORY
    name, so its 85 linked worktrees of oasis-command-center produced 85
    distinct slugs and 84 of them silently protected nothing.

    Reproduced locally before the fix (a worktree resolved to 'wt-probe').
    """
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        wt = Path(td) / "wt"
        r = subprocess.run(["git", "worktree", "add", "--detach", str(wt), "HEAD"],
                           cwd=REPO_ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            pytest.skip(f"could not create worktree: {r.stderr[:120]}")
        try:
            main = repo_paths.resolve(REPO_ROOT / "README.md")
            linked = repo_paths.resolve(wt / "README.md")
            assert main and linked
            assert main[0] == linked[0], (
                f"worktree slug {linked[0]!r} != main slug {main[0]!r} — "
                "the gate would protect nothing in this worktree")
            assert linked[1] == "README.md", "repo-relative path must anchor at the worktree"
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(wt)],
                           cwd=REPO_ROOT, capture_output=True, text=True)


def test_slug_is_remote_derived_not_directory_name():
    """This repo's directory is Business-Empire-Agent; its remote is CEO-Agent.
    The slug must follow the REMOTE, or Bravo and APEX key on different names."""
    got = repo_paths.resolve(REPO_ROOT / "README.md")
    assert got is not None and got[0] == "ceo-agent"


@pytest.mark.parametrize("glob,path,expected", [
    ("lib/drips/executor.ts", "lib/drips/executor.ts", True),
    ("lib/drips", "lib/drips/x.ts", True),
    ("lib/drips", "lib/dripsfoo.ts", False),          # prefix != directory
    ("services/leadgen/**", "services/leadgen/index.mjs", True),
    ("services/leadgen/**", "services/leadgen/a/b/c.mjs", True),
    ("app/api/**", "app/api/leads/route.ts", True),
    ("components/*", "components/leads/table.tsx", True),   # deliberate over-match
    ("lib/drips/**", "lib/sms/x.ts", False),
])
def test_apex_coverage_vectors(glob, path, expected):
    assert repo_paths.covers(glob, path) is expected


@pytest.mark.parametrize("bad", ["pipeline", "settings", "auth", "Turso"])
def test_single_extensionless_segment_is_refused_as_a_concept_name(claim_mod, bad):
    """APEX §3.3: `Makefile` is legal only because it exists; `pipeline` is not."""
    with pytest.raises(ValueError):
        claim_mod._validate_paths("ceo-agent", [bad], strict=False)


def test_real_extensionless_file_is_still_allowed(claim_mod):
    assert claim_mod._validate_paths("ceo-agent", ["LICENSE"], strict=False) == ["LICENSE"]


# --- APEX §4.4: every matcher must fire ALONE -------------------------------
# APEX shipped an escalation lint containing \bexhaust\b, which cannot match
# "exhausted" (no word boundary). The rule was DEAD, and the suite stayed green
# because a DIFFERENT alternative caught the same test sentence. Verifying that
# a result appears is not verifying that the component under test produced it.

ESCALATION_SENTENCES = [
    "Anthropic API credits exhausted and Groq fallback failed",  # the 2026-08-25 row
    "billing quota exceeded on the provider",
    "we are out of credits",
    "auth token expired for the mailbox",
    "returned 401 unauthorized from the API",
    "the failover failed as well",
    "operator-email service is down",
    "tt-agent stopped for 29 hours",
    "cannot connect to the database",
    "top up at console.anthropic.com",
]


@pytest.mark.parametrize("sentence", ESCALATION_SENTENCES)
def test_escalation_patterns_each_fire_alone(sentence):
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "integrations"))
    import agent_activity
    assert agent_activity.escalation_hits(sentence), (
        f"no escalation pattern matched {sentence!r} — a dead alternative hides "
        "behind a live one exactly like APEX's \bexhaust\b did")


@pytest.mark.parametrize("benign", [
    "Shipped the drip timezone fix",
    "Reviewed PR 331 and merged to main",
    "Pipeline tabs done, moved to Applications",
    "Refactored the lead scoring helper",
])
def test_escalation_matcher_does_not_cry_wolf(benign):
    """A probe that cries wolf gets ignored, and an ignored probe is worse than
    none — APEX's own words about its capability probe."""
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "integrations"))
    import agent_activity
    assert agent_activity.escalation_hits(benign) == []


def test_post_refuses_a_failure_row_under_a_non_blocked_status():
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "integrations"))
    import agent_activity
    with pytest.raises(ValueError) as e:
        agent_activity.post("working", "Re: turnkey release",
                            detail="Anthropic API credits exhausted and Groq fallback failed.")
    assert "blocked" in str(e.value).lower()


def test_guard_shouts_when_it_is_blind():
    """APEX §4.2: absence of data must never present as absence of a problem.
    With no readable lease data the edit is allowed, but the operator MUST see
    that it was allowed without a check."""
    import os
    import subprocess
    import tempfile
    _td = tempfile.TemporaryDirectory()
    mirror = Path(_td.name) / "mirror.json"
    backup = None
    try:
        mirror.write_text("not json{{{", encoding="utf-8")
        env = {**os.environ, "EMPIRE_HOOK_COORD_GUARD": "enforce",
               "TURSO_DATABASE_URL": "libsql://unreachable-xyz.turso.io",
               "COORD_AGENT_KEY": "bravo", "COORD_GUARD_MIRROR": str(mirror)}
        r = subprocess.run(
            [sys.executable, str(GUARD)],
            input=json.dumps({"tool_name": "Edit",
                              "tool_input": {"file_path": f"{OCC}/lib/drips/executor.ts"}}),
            capture_output=True, text=True, env=env, timeout=180)
        assert r.returncode == 0, "a collision gate must not wedge work when blind"
        assert "BLIND" in r.stderr and "WITHOUT A CHECK" in r.stderr
    finally:
        _td.cleanup()


# ============ APEX + Codex findings, 2026-08-27 (round 2) =====================

def test_tiebreak_compares_instants_not_strings():
    """APEX implemented contract v3's tie-break and found the rule unsound.

    Python emits `...T23:32:12.667878+00:00`, JS emits `...T23:32:12.667Z`. At an
    equal millisecond prefix the STRINGS order on a digit vs 'Z', which has
    nothing to do with real time. If one side compares strings (as v3 literally
    said) and the other compares instants, each can conclude the peer is later
    and BOTH KEEP — two holders from two correct-looking implementations.
    """
    from integrations.coord_claim import parse_ts
    py = "2026-08-27T23:32:12.667000+00:00"
    js = "2026-08-27T23:32:12.667Z"
    assert py < js, "precondition: the naive string order this fix exists for"
    assert parse_ts(py) == parse_ts(js), "same instant must compare equal"
    # and a genuinely earlier JS stamp must sort earlier despite the Z suffix
    earlier_js = "2026-08-27T23:32:12.100Z"
    assert parse_ts(earlier_js) < parse_ts(py)


@pytest.mark.parametrize("a,b", [
    ("lib/*/x.ts", "lib/a/**"),
    ("app/api/**", "app/*/leads/route.ts"),
    ("components/*/Pane.tsx", "components/conversations/**"),
    ("lib/drips/**", "lib/*/executor.ts"),
])
def test_intersecting_globs_are_detected(a, b):
    """Codex P1 on APEX's side, identical here: two globs can overlap without
    either matching the other AS A STRING, so covers() alone is blind to exactly
    the broad claims the contract encourages."""
    assert repo_paths.overlaps(a, b), f"{a} and {b} intersect but were not detected"
    assert not repo_paths.covers(a, b) or not repo_paths.covers(b, a), (
        "precondition: covers() alone should NOT catch this pair")


@pytest.mark.parametrize("a,b", [
    ("lib/drips/**", "components/**"),
    ("components/conversations/**", "components/campaigns/**"),
    ("lib/a/*.ts", "lib/b/*.ts"),
    ("app/api/**", "lib/x.ts"),
])
def test_disjoint_globs_do_not_false_conflict(a, b):
    """The companion test. A conflict predicate that fires on everything is as
    useless as one that never fires — it just fails in the friendlier direction."""
    assert not repo_paths.overlaps(a, b)


def test_glob_intersection_witness_is_real():
    """Prove the pair actually shares a path, so the test is not asserting a
    property we invented."""
    assert repo_paths.covers("lib/*/x.ts", "lib/a/x.ts")
    assert repo_paths.covers("lib/a/**", "lib/a/x.ts")
    assert repo_paths.overlaps("lib/*/x.ts", "lib/a/**")


def test_canonical_timestamp_is_fixed_width_even_at_zero_microseconds():
    """APEX pinned the wire format and kept a LEXICAL comparison, so Bravo must
    emit fixed-width stamps or its peer's ordering breaks — and breaks exactly
    on a tie-break, since a tie-break only runs on same-instant inserts.

    datetime.isoformat() does NOT do this: it drops the fractional part entirely
    when microseconds are zero, so the same instant gets two shapes that are not
    string-equal, and the tie becomes invisible to the rule meant to resolve it.
    """
    from datetime import datetime, timezone
    from integrations import coord_claim
    zero = datetime(2026, 8, 27, 17, 15, 47, 0, tzinfo=timezone.utc)
    some = datetime(2026, 8, 27, 17, 15, 47, 116239, tzinfo=timezone.utc)
    a, b = coord_claim._iso(zero), coord_claim._iso(some)
    assert a == "2026-08-27T17:15:47.000000+00:00", a
    assert b == "2026-08-27T17:15:47.116239+00:00", b
    assert len(a) == len(b), "fixed width is the whole point"
    assert not a.endswith("Z") and not b.endswith("Z")
    # lexical order now matches chronological order, which is what APEX relies on
    assert (a < b) == (zero < some)
    # and the naive implementation would have failed this
    assert zero.isoformat() != a, "isoformat() is not canonical — that is the bug"


def test_canonical_and_parsed_comparisons_agree():
    """The interop property: APEX compares lexically, Bravo compares instants.
    With the format pinned, both reach the same verdict for every ordering."""
    from datetime import datetime, timedelta, timezone
    from integrations.coord_claim import _iso, parse_ts
    base = datetime(2026, 8, 27, 17, 15, 47, 0, tzinfo=timezone.utc)
    for delta in (0, 1, 999, 116239, 999999):
        other = base + timedelta(microseconds=delta)
        sa, sb = _iso(base), _iso(other)
        lexical = (sa < sb, sa == sb, sa > sb)
        instant = (parse_ts(sa) < parse_ts(sb), parse_ts(sa) == parse_ts(sb),
                   parse_ts(sa) > parse_ts(sb))
        assert lexical == instant, f"diverged at delta={delta}: {lexical} vs {instant}"


# ---- the dead-matcher class, killed rather than fixed case by case ----------

def test_no_regex_in_agent_activity_contains_a_control_character():
    r"""A `` written through a shell heredoc becomes a literal BACKSPACE
    (\x08), producing a pattern that can never match anything.

    This has now happened THREE times in this file — `top\s*up\s+at\b` and both
    ends of the narration pattern — and each time it was invisible, because a
    dead alternative hides behind a live one. APEX taught the general form of
    this (its section 4.4) and then hit it again on its own lint.

    Fixing instances is not enough; this asserts the class cannot return.
    """
    src = (REPO_ROOT / "scripts" / "integrations" / "agent_activity.py").read_text(
        encoding="utf-8")
    bad = [(i + 1, repr(ln)) for i, ln in enumerate(src.splitlines())
           if any(ord(c) < 32 and c != "\t" for c in ln)]
    assert not bad, f"control characters in source (dead-regex risk): {bad[:3]}"


@pytest.mark.parametrize("prose", [
    "Fixed the bug where the bridge said credits exhausted",
    "Documented why auth token expired handling matters",
    "Reviewing APEX handover which mentions service is down",
    "Testing for the case where quota exceeded fires",
])
def test_escalation_lint_allows_describing_a_failure(prose):
    """APEX reported this on its own lint: it refused two of APEX's own posts for
    DESCRIBING a blocker rather than reporting one. Bravo's copy had the same
    defect. A lint that blocks honest prose gets routed around with the override
    flag, and an override used by habit is the same as no lint at all."""
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "integrations"))
    import agent_activity
    assert agent_activity.escalation_hits(prose) == []


@pytest.mark.parametrize("report", [
    "Anthropic API credits exhausted and Groq fallback failed",
    "operator-email service is down",
    "credits exhausted, fixing now",          # narration AFTER the phrase still fires
    "cannot connect to the database",
])
def test_escalation_lint_still_catches_real_reports(report):
    """The companion. Loosening a lint until it never fires is not a fix — and
    `credits exhausted, fixing now` must still escalate, because position
    matters: describing precedes, reporting does not."""
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "integrations"))
    import agent_activity
    assert agent_activity.escalation_hits(report), f"{report!r} must escalate"


# ======== APEX round 3, 2026-08-28 ===========================================

def test_repo_slug_must_be_remote_derived_not_the_directory_name(claim_mod):
    """APEX found TEN live Bravo leases keyed `business-empire-agent` — the
    directory name — while the agreed slug is `ceo-agent`.

    The grammar was enforced on PATHS and not on the REPO field, and acquire()
    simply trusted `--repo`. Leases in that namespace are invisible: APEX
    resolves the same repo to `ceo-agent`, finds zero conflicts, and edits
    straight through the files Bravo holds. Neither side sees an error, which is
    why it has to be refused at write time — there is no later moment when a
    namespace mismatch becomes visible.
    """
    with pytest.raises(ValueError) as e:
        claim_mod._validate_repo("business-empire-agent")
    assert "ceo-agent" in str(e.value)
    assert "DIRECTORY name" in str(e.value)


def test_repo_validation_allows_a_genuine_sibling_repo(claim_mod):
    """Companion: refusing everything would be as useless as refusing nothing.
    A different repo under ~/APPS is legitimate and must still work."""
    assert claim_mod._validate_repo("oasis-command-center") == "oasis-command-center"


def test_repo_slug_is_lowercased(claim_mod):
    """slug_from_url lowercases, so a capitalised repo would match no peer row."""
    assert claim_mod._validate_repo("OASIS-Command-Center") == "oasis-command-center"


@pytest.mark.parametrize("text,should_escalate", [
    # APEX's counterexamples: a LIVE blocker beside a fixed one
    ("Fixed the retry loop. Separately, credits exhausted and we are stuck.", True),
    ("Resolved the timeout. Note that operator-email service is down.", True),
    # descriptions still suppressed
    ("Fixed the bug where the bridge said credits exhausted", False),
    ("Reviewing APEX handover which mentions service is down", False),
    # plain reports still fire
    ("Anthropic API credits exhausted and Groq fallback failed", True),
    ("cannot connect to the database", True),
])
def test_narration_governs_its_own_clause_not_the_whole_row(text, should_escalate):
    """APEX found the false negative in whole-row scanning and concluded a bare
    verb list cannot converge, because the verbs are subject-dependent. That is
    correct — and it is why the fix is SCOPE rather than another verb. Judging
    each sentence independently changes the unit, not the vocabulary.

    Bake-off on APEX's nine-sentence set: whole-row 2/9 wrong, APEX's 2/9,
    per-sentence 0/9.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "integrations"))
    import agent_activity
    assert bool(agent_activity.escalation_hits(text)) is should_escalate


def test_conflicts_validates_the_repo_too(claim_mod):
    """The READ path is the more dangerous half.

    The write bug APEX found created invisible leases. The read bug tells you it
    is SAFE TO EDIT when it is not — and `conflicts` is the exact command an
    agent runs immediately before editing.

    Measured before the fix: `conflicts --repo business-empire-agent` returned
    "clear — no peer lease covers those paths" with exit 0, while 18 real leases
    were live under `ceo-agent`. Fixing acquire() alone was a half-fix.
    """
    with pytest.raises(ValueError) as e:
        claim_mod.conflicts("business-empire-agent", ["scripts/harness_eval.py"])
    assert "ceo-agent" in str(e.value)


def test_agent_key_is_validated_like_the_repo_field(claim_mod):
    """The same ungrammared-field class, one field over.

    `agent` is a LOOKUP KEY — conflicts() and live_claims() filter on it, and
    each side's peer filter checks a fixed set. A key outside those sets is
    invisible to BOTH agents, and its holder sees no conflicts from either.

    Not hypothetical: `apex-racetest` reached the live table, written by Bravo's
    own concurrency test. One env var created a namespace nobody queries —
    exactly how `business-empire-agent` happened.
    """
    with pytest.raises(ValueError) as e:
        claim_mod._validate_agent("apex-racetest")
    assert "not a known agent key" in str(e.value)
    assert "OWNERSHIP_MAP" in str(e.value)


@pytest.mark.parametrize("key", ["bravo", "apex", "knut", "cc-agent", "BRAVO"])
def test_real_agent_keys_and_aliases_still_work(claim_mod, key):
    """Companion. Known agents, their aliases, and legacy wire keys must pass —
    a validator that refuses everything is as useless as one that refuses
    nothing. Case is normalised."""
    assert claim_mod._validate_agent(key) == key.lower()


def test_known_agents_come_from_the_ownership_map_not_a_second_list():
    """Sixth instance of the duplicate-definition class avoided deliberately:
    the agent roster is read from OWNERSHIP_MAP, so adding an agent in one place
    is enough."""
    src = (REPO_ROOT / "scripts" / "integrations" / "coord_claim.py").read_text(encoding="utf-8")
    fn = src[src.index("def _validate_agent"):src.index("def _validate_paths")]
    # Assert the PROPERTY (the roster comes from the map), not the call spelling.
    # The first version asserted `ownership.load()` and went red the moment the
    # roster moved behind validate_agent_key — a test pinned to an
    # implementation detail rather than the behaviour it cares about.
    assert "ownership." in fn and "validate_agent_key" in fn


def test_an_expired_own_lease_does_not_suppress_the_contested_nudge():
    """Half-fix found by the defect sweep, in coord_guard itself.

    The expiry filter lived in the PEER reader; the nudge filtered own-leases
    inline without it. So an EXPIRED own-lease still suppressed the nudge, and
    the agent would edit a contested file believing it held a lease it no longer
    held — while the peer correctly saw the path as free and could take it.

    Both classes at once: a fix applied to one reader and not its sibling, and
    two implementations of one question.
    """
    import os
    import subprocess
    import tempfile
    import time as _t
    from datetime import datetime, timedelta, timezone
    expired = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    own_expired = {"agent": "bravo", "repo": "oasis-command-center",
                   "path_glob": "lib/drips/executor.ts", "task": "stale",
                   "status": "held", "expires_at": expired}
    with tempfile.TemporaryDirectory() as td:
        mirror = Path(td) / "m.json"
        mirror.write_text(json.dumps({"fetched_at": _t.time(), "claims": [own_expired]}),
                          encoding="utf-8")
        env = {**os.environ, "EMPIRE_HOOK_COORD_GUARD": "enforce",
               "COORD_GUARD_CACHE_TTL_SEC": "600", "COORD_AGENT_KEY": "bravo",
               "COORD_GUARD_MIRROR": str(mirror)}
        r = subprocess.run(
            [sys.executable, str(GUARD)],
            input=json.dumps({"tool_name": "Edit",
                              "tool_input": {"file_path": f"{OCC}/lib/drips/executor.ts"}}),
            capture_output=True, text=True, env=env, timeout=180)
    assert r.returncode == 0, "an expired own-lease must never BLOCK"
    assert "CONTESTED" in r.stderr, (
        "an expired own-lease must not suppress the nudge — the agent would "
        "edit a contested file believing it still held the lease")


def test_a_live_own_lease_still_suppresses_the_nudge():
    """Companion: the fix must not make the nudge fire when we genuinely hold
    the path, or it becomes noise and gets ignored."""
    import os
    import subprocess
    import tempfile
    import time as _t
    from datetime import datetime, timedelta, timezone
    live = (datetime.now(timezone.utc) + timedelta(minutes=60)).isoformat()
    own_live = {"agent": "bravo", "repo": "oasis-command-center",
                "path_glob": "lib/drips/executor.ts", "task": "current",
                "status": "held", "expires_at": live}
    with tempfile.TemporaryDirectory() as td:
        mirror = Path(td) / "m.json"
        mirror.write_text(json.dumps({"fetched_at": _t.time(), "claims": [own_live]}),
                          encoding="utf-8")
        env = {**os.environ, "EMPIRE_HOOK_COORD_GUARD": "enforce",
               "COORD_GUARD_CACHE_TTL_SEC": "600", "COORD_AGENT_KEY": "bravo",
               "COORD_GUARD_MIRROR": str(mirror)}
        r = subprocess.run(
            [sys.executable, str(GUARD)],
            input=json.dumps({"tool_name": "Edit",
                              "tool_input": {"file_path": f"{OCC}/lib/drips/executor.ts"}}),
            capture_output=True, text=True, env=env, timeout=180)
    assert r.returncode == 0
    assert "CONTESTED" not in r.stderr


def test_migration_allocator_does_not_contradict_its_own_validator():
    """Half-fix found by the defect sweep.

    `next_free()` used `prefixed OR unprefixed` while `check`/`reserve` used the
    UNION, so the tool recommended 015 and then refused 015. An allocator whose
    own validator rejects its recommendation burns the operator's trust on first
    use — and the operator is an agent that will simply take the number anyway.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import check_migration_collision as m
    n = m.next_free("bravo")
    assert n not in m.taken_numbers("bravo"), (
        f"next_free() recommended {n:03d} but taken_numbers() considers it taken")


def test_migration_taken_set_unions_prefixed_and_unprefixed():
    """Migration numbers share one ordering on disk regardless of prefix, so a
    number taken by an unprefixed file must block a prefixed one."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import check_migration_collision as m
    disk = m.taken_on_disk()
    union = m.taken_numbers("bravo")
    assert disk.get("bravo", set()) <= union
    assert disk.get("", set()) <= union


# ---- the ungrammared-lookup-key class, closed across every writer ----------

def test_agent_roster_has_exactly_one_definition():
    """Sixth avoided instance of the duplicate-definition class.

    coord_claim, agent_activity and event_bus all key rows on an agent name.
    Writing the roster in each would guarantee drift — which is exactly what
    OWNERSHIP_MAP exists to prevent. All of them resolve through
    lib.ownership.validate_agent_key.
    """
    from lib import ownership
    src = (REPO_ROOT / "scripts" / "integrations" / "coord_claim.py").read_text(encoding="utf-8")
    fn = src[src.index("def _validate_agent"):src.index("def _validate_paths")]
    assert "ownership.validate_agent_key" in fn, "coord_claim must delegate, not copy"
    aa = (REPO_ROOT / "scripts" / "integrations" / "agent_activity.py").read_text(encoding="utf-8")
    assert "ownership.validate_agent_key" in aa, "agent_activity must use the shared roster"
    assert ownership.known_agent_keys() >= {"bravo", "apex"}


def test_agent_activity_refuses_an_unknown_agent_key():
    """`agent` is the ONLY key every read path in agent_activity filters on
    (PEER_KEYS / SELF_KEYS). An unknown value writes a row neither agent can
    see — the same silent-namespace failure as the repo-slug bug, one table
    over. coord_claim got this check first; its sibling had none."""
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "integrations"))
    import agent_activity
    with pytest.raises(ValueError) as e:
        agent_activity.post("working", "should never be written", agent="apex-racetest")
    assert "not a known agent key" in str(e.value)


@pytest.mark.parametrize("key", ["bravo", "apex", "knut", "cc-agent"])
def test_shared_roster_accepts_every_real_key(key):
    """A validator that refuses everything is as useless as one that refuses
    nothing — aliases and legacy wire keys must keep working."""
    from lib import ownership
    assert ownership.validate_agent_key(key) == key.lower()


def test_event_bus_validates_a_named_target_but_never_raises():
    """The third writer, completing a fix my own commit message claimed was
    already complete — it said 'three consumers' while only two were wired.

    `target_agent` is the routing key the consumer dequeues on, so an unknown
    value publishes an event nobody claims. But publish() documents NEVER
    RAISES and long-lived subscriber daemons depend on that, so a routing typo
    must not become a crashed daemon. It warns loudly and KEEPS the value —
    never silently rewriting it to None, which would look like a broadcast and
    be its own silent failure.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "core"))
    import event_bus
    assert event_bus._validated_target(None) is None          # broadcast is legal
    assert event_bus._validated_target("apex") == "apex"
    kept = event_bus._validated_target("apex-racetest")       # must NOT raise
    assert kept == "apex-racetest", "a bad target is kept and warned, not rewritten"


@pytest.mark.parametrize("text,should_escalate", [
    # APEX's remaining gap: quoting a failure read as making one, and refused
    # two of APEX's own messages.
    ('The lint refused my post for saying "credits exhausted"', False),
    ("Example of a blocker: `operator-email service is down`", False),
    ('Docs say to post "cannot connect" as blocked', False),
    # narration (per-sentence scoping) still holds
    ("Fixed the bug where the bridge said credits exhausted", False),
    ("Resolved the timeout. Note that operator-email service is down.", True),
    # real reports must still fire
    ("Anthropic API credits exhausted and Groq fallback failed", True),
    ("operator-email service is down", True),
    ("Fixed the retry loop. Separately, credits exhausted and we are stuck.", True),
])
def test_citation_is_syntax_not_vocabulary(text, should_escalate):
    """APEX diagnosed why a bigger verb list cannot fix this: the verbs are
    SUBJECT-DEPENDENT — a runbook mentioning an outage is documentation, a person
    mentioning one is a report — so the list oscillates rather than converging.
    They stopped rather than churn, which was right.

    Quotes and backticks are not vocabulary. They are structure, and structure
    converges — the same reason per-sentence scoping worked where more verbs did
    not. Together these two structural rules take the combined citation +
    narration + report set to 0/9.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "integrations"))
    import agent_activity
    assert bool(agent_activity.escalation_hits(text)) is should_escalate
