"""Executable subset of the 20-Point Vibe-Security Matrix, run against THIS repo.

`test_20_point_security_contract.py` is a documentation gate: it proves the matrix
exists, is single-sourced, and has not rotted. That is necessary and it proves
nothing about the code. This file is the other half — the points that can be
checked mechanically against the Bravo harness, executed on every test run.

**Why only five points.** Business-Empire-Agent is a Python agent harness, not a
web application. Points 2, 4, 5, 10, 11, 12, 13, 19 and 20 are app-surface
concerns that live in oasis-command-center and the product repos; asserting them
here would either pass vacuously or fire on nothing. Points 3, 7, 8 and 14 need
schema and route context this repo does not own. Those are covered by
`prompts/20_POINT_SECURITY_AUDITOR_SYSTEM_PROMPT.md` run against the app repos.
A vacuous assertion is worse than an absent one: it reads as coverage.

**On the xfail markers.** One invariant still FAILS against a real, verified
finding from the 2026-08-15 audit (points 6 and 16 were hardened the same day and
their markers removed). It is recorded as `xfail(strict=True)`
rather than deleted or softened, because:
  - deleting them loses the invariant,
  - softening them (asserting the current broken count) pins the defect as
    correct, which is its own documented failure mode,
  - `strict=True` means the test FAILS if it ever unexpectedly passes — so
    whoever fixes the underlying bug is forced to come here and remove the
    marker. The gap cannot be silently closed or silently widened.
Each marker names the finding it encodes. Do not remove a marker without fixing
the code; do not remove the test without ADR-0016 being superseded.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# Built from parts, never as one literal: `secret_guard` pattern-matches shell
# command strings, and a test that cannot be grepped for is easier to keep than
# one that trips the guard every time someone greps this file.
ENVFILE = "." + "env"

SKIP_PARTS = ("_archive", "__pycache__", "node_modules", ".venv", "/tmp/", "\\tmp\\",
              "site-packages", ".git/")


def _tracked() -> list[str]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files"],
                         capture_output=True, text=True,
                         encoding="utf-8", errors="ignore").stdout
    return [l.strip() for l in out.splitlines() if l.strip()]


def _py_files(*roots: str) -> list[Path]:
    files: list[Path] = []
    for r in roots:
        base = REPO / r
        if not base.exists():
            continue
        files += [p for p in base.rglob("*.py")
                  if not any(s in p.as_posix() for s in SKIP_PARTS)]
    return files


def _scan(pattern: str, files: list[Path]) -> list[str]:
    rx = re.compile(pattern)
    hits: list[str] = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if rx.search(line):
                hits.append(f"{p.relative_to(REPO).as_posix()}:{i}: {line.strip()[:120]}")
    return hits


# ── Point 1 — no credential-shaped file is tracked in git ────────────────────

def test_point_1_no_credential_shaped_file_is_tracked():
    """The 2026-04-24 CMO leak was `.long_lived_token.txt` — gitignored patterns
    covered env files and missed the filename. Check the tracked set, not the
    ignore rules: what git actually carries is the only thing an attacker sees."""
    rx = re.compile(
        r"(^|/)%s($|\.)|_token\.txt$|token\.json$|credentials\.json$"
        r"|service_account\.json$|\.pem$|\.p12$|\.pfx$|(^|/)id_rsa|(^|/)id_ed25519"
        % re.escape(ENVFILE), re.I)
    tracked = [t for t in _tracked() if rx.search(t)]
    allowed = {f"{ENVFILE}.agents.template", f"{ENVFILE}.example", f"{ENVFILE}.template"}
    leaked = [t for t in tracked if Path(t).name not in allowed]
    assert not leaked, f"credential-shaped files tracked in git: {leaked}"


@pytest.mark.xfail(strict=True, reason=(
    "Open finding, 2026-08-15 audit — severity corrected to LOW on re-inspection. "
    "Five .obsidian/plugins/*/data.json files are tracked despite the .gitignore rule "
    "annotated CRITICAL because plugin data.json CAN hold API keys and TLS certs. "
    "Key names were inspected (never values) and these five hold none: dataview "
    "formatting, homepage layout, obsidian-git commit settings, linter rules, templater "
    "paths. The audit's 'RISKY' hits were substring false positives — 'authorInHistoryView' "
    "on auth, 'settingsConvertedToConfigKeyValues' and 'enabled_templates_hotkeys' on key. "
    "So this is an ignore-rule bypass, NOT an exposure, and no rotation is needed. "
    "NOT auto-fixed: RULE 6 forbids touching .obsidian config, and untracking could break "
    "CC's vault sync. Needs CC's call. Remove the marker once they are untracked."))
def test_point_1_no_plugin_data_json_is_tracked():
    tracked = [t for t in _tracked()
               if t.endswith("data.json") and ".obsidian" in t]
    assert not tracked, f"obsidian plugin data.json tracked: {tracked}"


# ── Point 9 — no hand-rolled password handling anywhere ─────────────────────

def test_point_9_no_custom_password_handling():
    """Supabase Auth owns credentials end to end. Any password hashing in this
    tree is a defect on sight, not a design to review — so the correct result is
    zero hits, and this test is expected to stay trivially green forever."""
    # Match hashing CALLS, not the words. The first draft of this scan matched
    # bare `bcrypt`/`scrypt` and fired on three false positives: prose in
    # etl_auth_to_turso.py's docstring (it copies existing hashes verbatim and
    # hashes nothing) and `Scrypt(...)` in field_encryption.py, which is a KDF
    # for field encryption — a correct use that has nothing to do with passwords.
    # A check with false positives trains people to ignore it, which is worse
    # than no check.
    hits = _scan(
        r"bcrypt\.(?:hashpw|checkpw|gensalt)\("
        r"|hashlib\.\w+\([^)]*passw"
        r"|\bmd5\([^)]*passw"
        r"|crypt\.crypt\(",
        _py_files("scripts", "bravo_cli", "gateway"))
    assert not hits, "hand-rolled password handling found:\n" + "\n".join(hits)


# ── Point 6 — no SQL assembled by string interpolation ──────────────────────

def test_point_6_identifiers_are_validated_at_the_sql_chokepoint():
    """Behavioural, not grep-based — deliberately.

    The first version of this test scanned for `sql = f'SELECT ... {table}'` and
    could not pass even after the hole was closed, because a regex cannot tell a
    VALIDATED interpolation from an unvalidated one. That is this repo's own
    "a security boundary needs a parser, not a regex" lesson pointed at itself:
    the grep says where identifiers reach SQL, and only executing the guard says
    whether they are safe.

    Values in the compat builder are always bound (`?`). Identifiers cannot be,
    so `CompatQuery._ident` is the single chokepoint every table and column name
    passes through. Assert it refuses, rather than assert the f-strings are gone.
    """
    import sys
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        from lib.turso_supabase_compat import CompatQuery
    except Exception as exc:  # pragma: no cover - env without the driver
        pytest.skip(f"turso compat not importable: {exc}")

    q = CompatQuery.__new__(CompatQuery)

    # Legitimate shapes must survive — an over-strict guard that breaks real
    # queries gets reverted, and then there is no guard at all.
    for good in ("leads", "tenant_id", "_private", "createdAt",
                 "data->>stage", "a->b->c"):
        assert q._q(good), f"guard broke a legitimate identifier: {good!r}"

    # Injection shapes must be refused, not escaped-and-hoped.
    for bad in ('lead"; ' + "DROP" + " TABLE leads; --",
                'tenant_id" OR "1"="1',
                "a b", "1abc", "", "col'--", "tab\nle"):
        with pytest.raises(ValueError):
            q._q(bad)

    # A JSON path lands inside a single-quoted literal, so it needs doubling
    # rather than identifier validation.
    assert "''" in q._q("data->>o'brien"), "apostrophe not escaped in json path"

    # The table name is validated at construction, covering every downstream
    # f-string that interpolates it.
    with pytest.raises(ValueError):
        CompatQuery(None, 'leads"; ' + "DELETE" + " FROM leads; --")


def test_point_6_payload_and_select_column_names_are_validated_too():
    """The first pass of this fix guarded `_q` and the table name, and I declared
    the chokepoint closed. Codex's independent audit found four interpolation
    sites still open in the same builder: select column lists, insert/upsert
    column names, the on-conflict target, and update SET names.

    Those matter more than the ones I had already fixed: insert/update column
    names come from PAYLOAD DICT KEYS, so a handler that spreads a request body
    into `.insert(body)` — point 15 — puts caller-controlled strings directly
    into identifier position. This is 'guard the class, not the instance': the
    same defect, thirty lines away, in a path I had not looked at.

    A stub db records SQL and fails the test if it is ever reached — the guard
    must reject before any statement is built.
    """
    import sys
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        from lib.turso_supabase_compat import CompatQuery
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"turso compat not importable: {exc}")

    class _Boom:
        def query(self, sql, args=None, **kw):
            raise AssertionError(f"guard bypassed — statement was built: {sql}")

        def commit(self):
            pass

    evil = 'x"; ' + "DROP" + " TABLE leads; --"

    # insert / upsert: column names come from payload keys
    with pytest.raises(ValueError):
        CompatQuery(_Boom(), "leads").insert({evil: 1}).execute()
    with pytest.raises(ValueError):
        CompatQuery(_Boom(), "leads").upsert({evil: 1}).execute()

    # update: SET names come from payload keys
    with pytest.raises(ValueError):
        CompatQuery(_Boom(), "leads").update({evil: 1}).eq("id", 1).execute()

    # select: column list is caller-supplied
    with pytest.raises(ValueError):
        CompatQuery(_Boom(), "leads").select(evil).execute()

    # on-conflict target
    with pytest.raises(ValueError):
        CompatQuery(_Boom(), "leads").upsert({"id": 1}, on_conflict=evil).execute()


def test_point_6_guard_lives_at_the_layer_every_caller_reaches():
    """The guard must sit in `db_turso`, not in the compat shim.

    Third iteration of the same mistake in one session, which is why this test
    exists rather than a comment. Pass 1 guarded `_q` and the table name and I
    called the chokepoint closed. Pass 2 (Codex) found four more sites in the
    same builder. Pass 3 — an exhaustive sweep — found sixteen in
    `lib/db_turso.py`, the layer BENEATH the shim, reached directly by every
    `get_db().insert(...)` / `.claim(...)` caller that never goes through the
    compat client at all. A guard in the shim would have protected exactly one
    of its callers while reading, in review, like full coverage.

    So: assert the canonical helper is in db_turso, and that the shim delegates
    rather than keeping a second copy that can drift.
    """
    import sys
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        from lib.db_turso import quote_ident
        from lib.turso_supabase_compat import CompatQuery
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"turso layer not importable: {exc}")

    assert quote_ident("leads") == '"leads"'
    for bad in ('x"; ' + "DROP" + " TABLE leads; --", "a b", "1abc", "", "c'--"):
        with pytest.raises(ValueError):
            quote_ident(bad)

    # One implementation, not two: the shim must route to db_turso's helper.
    compat_src = (REPO / "scripts" / "lib" / "turso_supabase_compat.py").read_text(
        encoding="utf-8")
    assert "quote_ident" in compat_src, "compat shim no longer delegates to db_turso"
    assert "_IDENT_RE" not in compat_src, (
        "compat shim reintroduced its own identifier regex — one guard, one place, "
        "or the two drift apart")


# ── Point 16 — a webhook receiver verifies before it acts ───────────────────

def test_point_16_webhook_secret_check_fails_closed():
    """A verification that is skipped when unconfigured is a decorative control:
    it reads as coverage in review and defends nothing in the environment where
    the variable was never set. Fail closed, or do not claim the defense."""
    src = (REPO / "scripts" / "hooks" / "webhook_listener.py")
    if not src.exists():
        pytest.skip("webhook_listener.py not present")
    # Strip comments FIRST. Without this the scan matched the fix's own comment,
    # which quotes the old broken line verbatim to explain what changed — so
    # documenting the defect re-triggered the detector for it. A scanner that
    # fires on prose about the bug is the same false-positive class that made the
    # point-9 scan useless on its first draft.
    text = "\n".join(
        l for l in src.read_text(encoding="utf-8", errors="ignore").splitlines()
        if not l.lstrip().startswith("#"))
    # The defect shape, read from the file rather than assumed:
    #     if <SECRET> and not hmac.compare_digest(...)
    # An unset token makes the whole condition False, so the 401 branch is never
    # reached and the request is accepted unverified. Fixed 2026-08-15 to
    #     if not <SECRET> or not hmac.compare_digest(...)
    # matching the n8n gate and _verify_stripe_sig in the same module.
    # Require the verification CALL on the same line. Without it this matched
    # line 179's health-status ternary —
    #     "status": "ok" if STRIPE_WEBHOOK_SECRET and (WEBHOOK_N8N_TOKEN or ...) else "warn"
    # — which reports configuration and gates nothing. Narrow the detector to the
    # shape that actually decides whether a request is rejected.
    gated_on_secret_being_set = re.search(
        r"if\s+[A-Za-z_]*SECRET[A-Za-z_]*\s+and\s+[^\n]*compare_digest", text)
    assert not gated_on_secret_being_set, (
        "webhook secret verification is gated on the secret being configured "
        f"({src.relative_to(REPO).as_posix()}) — an unset env var silently "
        "disables the check. It must fail closed instead.")


# ── Point 17 — no raw traceback is returned to a caller ─────────────────────

def test_point_17_traceback_is_logged_never_returned():
    """`format_exc()` is fine — returning it over HTTP is not. This scans for the
    formatted traceback appearing in the same statement as a response
    constructor, which is the shape that actually leaks."""
    hits = _scan(
        r"(?:HTTPException|JSONResponse|jsonify|Response|return\s+\{)"
        r".{0,120}format_exc\(\)"
        r"|format_exc\(\).{0,120}(?:HTTPException|JSONResponse|jsonify|detail=)",
        _py_files("scripts", "bravo_cli", "gateway"))
    assert not hits, "traceback returned to a caller:\n" + "\n".join(hits[:10])


# ── the file must not silently shrink ───────────────────────────────────────

def test_every_declared_invariant_has_a_test():
    """Guards this file against the quiet failure mode of a checklist: a point
    documented in the module docstring but never asserted. If you add a point to
    the executable subset, add it here too."""
    declared = {1, 6, 9, 16, 17}
    src = Path(__file__).read_text(encoding="utf-8")
    found = {int(m) for m in re.findall(r"^def test_point_(\d+)_", src, re.MULTILINE)}
    assert found == declared, f"declared={sorted(declared)} but tested={sorted(found)}"
