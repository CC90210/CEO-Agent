"""Regression tests for the vault-hygiene tools.

Every case here is a bug that actually happened, not a hypothetical:

  * basename resolution           — wiki_link_auditor reported 20 broken links
                                    where 85 were real, because it resolved
                                    repo-root-relative instead of by basename.
  * vault-ignored targets         — links into `.claude/` look fine to a naive
                                    scanner and are red in Obsidian.
  * folder vs note                — `[[skills/x]]` is broken; `[[skills/x/SKILL]]` isn't.
  * CRLF preservation             — rewriting links must not normalize EOLs, or
                                    the repo's checksum gates break.
  * protected paths               — a bulk sweep clobbered generated docs and
                                    hash-pinned LOCKSTEP blocks (2026-07-28).
  * block-list frontmatter        — `tags:` as a YAML block list was reported
                                    missing, flagging correctly-tagged notes.
  * probe required-key sets       — reporting a service available on ANY matching
                                    key is a false positive; a lone SUPABASE_URL
                                    is not access.
  * probe never emits values      — the security boundary that lets an agent ask
                                    "do I have access?" without reading .env.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import capability_probe as probe  # noqa: E402
import obsidian_graph_doctor as doctor  # noqa: E402
from lib import frontmatter as fm  # noqa: E402
from lib.vault_scope import is_ignored, is_protected  # noqa: E402


# ---------------------------------------------------------------- frontmatter
class TestFrontmatter:
    def test_inline_list_parsed(self):
        block, body, eol = fm.split("---\ntags: [a, b]\n---\n# Title\n")
        assert fm.parse(block)["tags"] == "a, b"
        assert body == "# Title\n"
        assert eol == "\n"

    def test_block_list_parsed(self):
        """The form that used to be reported as a missing `tags:`."""
        text = "---\ntags:\n  - dashboard\n  - pinned\naliases:\n  - Home\n---\n# T\n"
        fields = fm.parse(fm.split(text)[0])
        assert fields["tags"] == "dashboard, pinned"
        assert fields["aliases"] == "Home"

    def test_crlf_eol_detected(self):
        _block, _body, eol = fm.split("---\r\ntags: [a]\r\n---\r\n# T\r\n")
        assert eol == "\r\n"

    def test_no_frontmatter(self):
        block, body, _ = fm.split("# Just a heading\n")
        assert block is None and body == "# Just a heading\n"
        assert fm.parse(block) == {}

    def test_has_field_true_for_valueless_key(self):
        """A block-list key has no inline value but IS declared."""
        block = fm.split("---\ntags:\n  - x\n---\n")[0]
        assert fm.has_field(block, "tags")
        assert not fm.has_field(block, "last_updated")

    def test_indented_key_is_not_top_level(self):
        block = fm.split("---\nmeta:\n  tags: nope\n---\n")[0]
        assert not fm.has_field(block, "tags")


# --------------------------------------------------------------- vault scope
class TestVaultScope:
    @pytest.mark.parametrize("rel", [
        "brain/WHEN_TO_USE_SKILLS.md",        # generated — re-emitted
        "memory/MEMORY_INDEX.md",             # generated
        "brain/_canonical/LOCKSTEP_tool_discipline.md",  # hash-pinned in harness.lock
        "CLAUDE.md", "AGENTS.md", "ZCODE.md",  # genome-managed entry points
    ])
    def test_protected_paths_refused(self, rel):
        assert is_protected(rel), f"{rel} must never be bulk-rewritten"

    @pytest.mark.parametrize("rel", ["brain/STATE.md", "docs/sop/x.md", "skills/a/SKILL.md"])
    def test_ordinary_notes_writable(self, rel):
        assert not is_protected(rel)

    def test_ignore_filters_match_obsidian(self):
        f = ["node_modules", ".claude", "tmp/", "skills/gws-"]
        assert is_ignored(".claude/agents/debugger.md", f)   # segment match
        assert is_ignored("tmp/scratch.md", f)               # trailing-slash prefix
        assert is_ignored("skills/gws-docs/SKILL.md", f)     # prefix filter
        assert not is_ignored("skills/outreach-send/SKILL.md", f)

    def test_hard_ignores_apply_without_config(self):
        assert is_ignored("node_modules/pkg/README.md", [])
        assert is_ignored("a/.git/x.md", [])


# ------------------------------------------------------------ link resolution
class TestLinkResolution:
    @staticmethod
    def _index(paths):
        notes = [REPO_ROOT / p for p in paths]
        # build_index keys off paths relative to REPO_ROOT
        by_path, by_base = {}, {}
        for p in paths:
            by_path[p.lower()] = p
            by_path[p[:-3].lower()] = p
            by_base.setdefault(Path(p).stem.lower(), []).append(p)
        return by_path, by_base, notes

    def test_basename_resolution(self):
        """`[[QUICK_REFERENCE]]` must find brain/QUICK_REFERENCE.md — the core
        Obsidian semantic the old auditor lacked."""
        by_path, by_base, _ = self._index(["brain/QUICK_REFERENCE.md"])
        assert doctor.resolve_link("QUICK_REFERENCE", by_path, by_base) == "brain/QUICK_REFERENCE.md"

    def test_exact_path_wins_over_basename(self):
        by_path, by_base, _ = self._index(["brain/A.md", "docs/A.md"])
        assert doctor.resolve_link("docs/A", by_path, by_base) == "docs/A.md"

    def test_shortest_path_breaks_ambiguity(self):
        by_path, by_base, _ = self._index(["a/DUP.md", "x/y/z/DUP.md"])
        assert doctor.resolve_link("DUP", by_path, by_base) == "a/DUP.md"

    def test_unresolvable_returns_none(self):
        by_path, by_base, _ = self._index(["brain/A.md"])
        assert doctor.resolve_link("ghost", by_path, by_base) is None

    def test_folder_link_does_not_resolve_to_its_note(self):
        """`[[skills/x]]` is broken even though skills/x/SKILL.md exists."""
        by_path, by_base, _ = self._index(["skills/n8n-patterns/SKILL.md"])
        assert doctor.resolve_link("skills/n8n-patterns", by_path, by_base) is None

    def test_attachments_ignored_not_broken(self):
        by_path, by_base, _ = self._index(["brain/A.md"])
        assert doctor.resolve_link("media/logo.png", by_path, by_base) is None


class TestLinkExtraction:
    def test_alias_and_anchor_stripped(self):
        assert doctor.extract_links("[[a/b|Label]] [[c#Section]] [[d^blk]]") == ["a/b", "c", "d"]

    def test_code_spans_excluded(self):
        """A wikilink inside backticks is documentation, not a link."""
        assert doctor.extract_links("`[[not_a_link]]` and [[real]]") == ["real"]
        assert doctor.extract_links("```\n[[fenced]]\n```\n[[real]]") == ["real"]


# ------------------------------------------------- private (gitignored) links
class TestPrivateLinks:
    """`gitignored_targets` decides whether CI goes red. It shipped untested and
    its first CI run failed on 71 links that were fine — worth locking down."""

    def test_operator_private_notes_are_not_broken(self):
        """memory/MISTAKES.md is gitignored on purpose (PII). A link to it is
        private, not broken — otherwise --strict can never pass in a clean
        checkout, which is exactly what happened on the gate's first run."""
        got = doctor.gitignored_targets({"memory/MISTAKES", "memory/PATTERNS"})
        assert got == {"memory/MISTAKES", "memory/PATTERNS"}

    def test_tracked_notes_are_not_classified_private(self):
        """A genuinely broken link must stay broken — this is the whole gate."""
        assert doctor.gitignored_targets({"brain/STATE", "docs/adr/INDEX"}) == set()

    def test_nonexistent_and_untracked_target_is_not_private(self):
        assert doctor.gitignored_targets({"brain/THIS_NOTE_NEVER_EXISTED"}) == set()

    def test_empty_input_short_circuits(self):
        assert doctor.gitignored_targets(set()) == set()

    def test_cross_repo_targets_skipped(self):
        """`../CMO-Agent/...` is outside this repo; check-ignore can't judge it."""
        assert doctor.gitignored_targets({"../CMO-Agent/brain/CONTENT_BIBLE"}) == set()

    def test_batches_survive_more_than_one_chunk(self):
        """Paths go as argv in chunks of 200 (Windows 8191-char limit). A real
        private target must still be found when it lands past the first chunk."""
        filler = {f"brain/_no_such_note_{i}" for i in range(250)}
        got = doctor.gitignored_targets(filler | {"memory/MISTAKES"})
        assert "memory/MISTAKES" in got

    def test_audit_separates_private_from_broken(self):
        report = doctor.audit()
        overlap = set(report["private_links"]) & {
            k for k, v in report["broken_links"].items() if v
        }
        for src in overlap:
            assert not (set(report["private_links"][src]) & set(report["broken_links"][src])), \
                "a link cannot be both private and broken"
        assert report["private_count"] == sum(
            len(v) for v in report["private_links"].values()
        )


# ------------------------------------------------------------ CRLF integrity
class TestRewriteIntegrity:
    def test_fix_links_preserves_crlf(self, tmp_path, monkeypatch):
        """Normalizing EOLs on rewrite breaks the repo's checksum gates."""
        target = tmp_path / "note.md"
        target.write_bytes(b"# T\r\n\r\nSee [[scripts/foo]] here.\r\n")
        monkeypatch.setattr(doctor, "REPO_ROOT", tmp_path)
        doctor.apply_link_fixes({"note.md": [("scripts/foo", "`scripts/foo.py`", "code-path")]})
        raw = target.read_bytes()
        assert b"\r\n" in raw, "CRLF file was normalized to LF"
        assert raw.replace(b"\r\n", b"") .count(b"\n") == 0, "a bare LF was introduced"
        assert b"`scripts/foo.py`" in raw and b"[[scripts/foo]]" not in raw

    def test_fix_links_leaves_code_samples_alone(self, tmp_path, monkeypatch):
        """Detection ignores code spans, so repair must too — otherwise a note
        with the same target in prose AND in a fence gets its example corrupted
        (found by Codex audit)."""
        target = tmp_path / "note.md"
        target.write_text(
            "Prose: [[scripts/foo]].\n\n```\nsee [[scripts/foo]] here\n```\n"
            "inline `[[scripts/foo]]` too\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(doctor, "REPO_ROOT", tmp_path)
        n = doctor.apply_link_fixes(
            {"note.md": [("scripts/foo", "`scripts/foo.py`", "code-path")]}
        )
        out = target.read_text(encoding="utf-8")
        assert n == 1, "only the prose occurrence should be rewritten"
        assert "Prose: `scripts/foo.py`." in out
        assert "see [[scripts/foo]] here" in out, "fenced example was corrupted"
        assert "inline `[[scripts/foo]]` too" in out, "inline code span was corrupted"

    def test_fix_links_rewrites_aliased_form(self, tmp_path, monkeypatch):
        target = tmp_path / "note.md"
        target.write_text("[[scripts/foo|the tool]]\n", encoding="utf-8")
        monkeypatch.setattr(doctor, "REPO_ROOT", tmp_path)
        n = doctor.apply_link_fixes({"note.md": [("scripts/foo", "`scripts/foo.py`", "code-path")]})
        assert n == 1
        assert target.read_text(encoding="utf-8").strip() == "`scripts/foo.py`"


# ---------------------------------------------------------- capability probe
class TestCapabilityProbe:
    def test_all_required_groups_must_be_satisfied(self):
        """A URL without a service-role key is NOT access (Codex P2)."""
        r = probe.probe("supabase", {"SUPABASE_URL"})
        assert r["available"] is False
        assert r["keys_missing"]

    def test_available_when_every_group_satisfied(self):
        r = probe.probe("supabase", {"SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"})
        assert r["available"] is True
        assert r["keys_missing"] == []

    def test_alias_satisfies_group(self):
        r = probe.probe("supabase", {"BRAVO_SUPABASE_URL", "BRAVO_SUPABASE_SERVICE_ROLE_KEY"})
        assert r["available"] is True

    def test_account_id_alone_is_not_stripe_access(self):
        assert probe.probe("stripe", {"STRIPE_OASIS_ACCT_ID"})["available"] is False
        assert probe.probe("stripe", {"STRIPE_ORG_KEY"})["available"] is True

    def test_every_service_declares_an_invoke_command(self):
        for name, (groups, invoke) in probe.SERVICES.items():
            assert groups and all(g for g in groups), f"{name} has an empty required group"
            assert invoke.strip(), f"{name} has no invoke command"

    def test_output_never_contains_a_secret_value(self, monkeypatch):
        """The security boundary: names and booleans leave, values never do.

        The sentinel is assembled at runtime — a literal key-shaped string here
        trips `security_audit.py secrets` and turns a CRITICAL gate into noise.
        """
        sentinel = "sk-" + "live-" + "SENTINEL-MUST-NOT-LEAK"
        monkeypatch.setattr(probe, "present_keys", lambda: {"STRIPE_ORG_KEY"})
        monkeypatch.setenv("STRIPE_ORG_KEY", sentinel)
        r = probe.probe("stripe", probe.present_keys())
        assert r["available"] is True
        assert sentinel not in repr(r), "probe leaked a credential VALUE"
        assert r["keys_present"] == ["STRIPE_ORG_KEY"], "only the NAME may escape"

    def test_json_flag_works_after_the_subcommand(self):
        """Every doc writes `check <svc> --json`. Registering --json only on the
        top-level parser makes argparse reject that form outright."""
        out = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "capability_probe.py"),
             "check", "supabase", "--json"],
            capture_output=True, text=True,
        )
        self_json = out.stdout.strip()
        assert "unrecognized arguments" not in (out.stderr or "")
        assert self_json.startswith("{"), f"expected JSON, got: {self_json[:80]!r}"

    def test_invoke_paths_that_look_local_actually_exist(self):
        """A probe that authorizes a service then names a nonexistent script is
        the false positive this tool exists to prevent (late_tool.py had moved
        to Maven's repo while the probe still pointed at scripts/integrations/)."""
        import re as _re
        missing = []
        for name, (_groups, invoke) in probe.SERVICES.items():
            for token in _re.findall(r"(?:^|\s)((?:scripts|bravo_cli)/[\w./-]+\.py)", invoke):
                if not (REPO_ROOT / token).is_file():
                    missing.append(f"{name} -> {token}")
        assert not missing, "probe names local scripts that do not exist: " + ", ".join(missing)

    def test_cli_exit_code_signals_availability(self):
        """Exit 1 is the ONLY evidence that permits 'I don't have access'."""
        out = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "capability_probe.py"),
             "check", "definitely-not-a-service"],
            capture_output=True, text=True,
        )
        assert out.returncode == 2  # unknown service, distinct from unavailable
