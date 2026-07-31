"""Focused regression tests for the honest V7 self-audit contract."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.core import self_audit as sa  # noqa: E402


class TempRepoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, rel: str, text: str = "# Test\n") -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class PathRoleTests(TempRepoTestCase):
    def test_classifies_active_archive_canonical_template_and_private(self) -> None:
        cases = {
            "brain/ACTIVE.md": sa.PathRole.ACTIVE,
            "brain/_archive/OLD.md": sa.PathRole.ARCHIVE,
            "memory/ARCHIVES/sessions.md": sa.PathRole.ARCHIVE,
            "brain/_canonical/LOCKSTEP.md": sa.PathRole.CANONICAL,
            "memory/DECISIONS.template.md": sa.PathRole.TEMPLATE,
            "memory/research/private.md": sa.PathRole.PRIVATE,
            "APPS_CONTEXT/client.md": sa.PathRole.PRIVATE,
        }
        for rel, expected in cases.items():
            with self.subTest(rel=rel):
                self.assertEqual(sa.classify_path(self.root / rel, self.root), expected)

    def test_private_docs_are_not_link_sources_or_orphan_targets(self) -> None:
        target = self.write("brain/TARGET.md")
        private = self.write("memory/research/private.md", "[[brain/TARGET]]\n")
        docs = [target, private]

        links = sa.analyze_links(docs, self.root, entry_points=[])
        orphans = sa.find_orphans(docs, links, self.root, allowlist=set())

        self.assertEqual(links.inbound.get("brain/TARGET.md"), set())
        self.assertEqual(orphans, ["brain/TARGET.md"])
        self.assertNotIn("memory/research/private.md", orphans)

    def test_gitignored_docs_are_private_even_without_a_private_path_name(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.write(".gitignore", "memory/client-record.md\n")
        target = self.write("brain/TARGET.md")
        private = self.write("memory/client-record.md", "[[brain/TARGET]]\n")

        links = sa.analyze_links([target, private], self.root, entry_points=[])
        orphans = sa.find_orphans([target, private], links, self.root, allowlist=set())

        self.assertEqual(links.roles["memory/client-record.md"], sa.PathRole.PRIVATE)
        self.assertEqual(links.inbound["brain/TARGET.md"], set())
        self.assertEqual(orphans, ["brain/TARGET.md"])


class LinkGraphTests(TempRepoTestCase):
    def test_archives_are_neither_sources_nor_active_targets(self) -> None:
        active = self.write("brain/ACTIVE.md")
        archive = self.write("brain/_archive/OLD.md", "[[brain/ACTIVE]]\n")
        source = self.write("brain/SOURCE.md", "[[OLD]]\n")
        docs = [active, archive, source]

        links = sa.analyze_links(docs, self.root, entry_points=[])
        orphans = sa.find_orphans(docs, links, self.root, allowlist={"brain/SOURCE.md"})

        self.assertIn("brain/ACTIVE.md", orphans)
        self.assertEqual(links.inbound.get("brain/ACTIVE.md"), set())
        self.assertIn(("brain/SOURCE.md", "brain/_archive/OLD.md"), links.archive_boundary_violations)

    def test_archive_outside_catalog_cannot_satisfy_active_link(self) -> None:
        source = self.write("brain/SOURCE.md", "[old](../docs/_archive/OLD.md)\n")
        self.write("docs/_archive/OLD.md")

        links = sa.analyze_links([source], self.root, entry_points=[])

        self.assertIn(
            ("brain/SOURCE.md", "docs/_archive/OLD.md"),
            links.archive_boundary_violations,
        )

    def test_html_commented_links_do_not_create_edges(self) -> None:
        target = self.write("brain/TARGET.md")
        source = self.write("brain/SOURCE.md", "<!-- [[brain/TARGET]] -->\n")

        links = sa.analyze_links([target, source], self.root, entry_points=[])

        self.assertEqual(links.inbound["brain/TARGET.md"], set())

    def test_wiki_at_import_and_relative_markdown_links_create_inbound_edges(self) -> None:
        target = self.write("brain/TARGET.md")
        wiki = self.write("brain/WIKI.md", "[[brain/TARGET]]\n")
        at_import = self.write("brain/IMPORT.md", "@brain/TARGET.md\n")
        markdown = self.write("brain/MARKDOWN.md", "[target](TARGET.md)\n")
        self.write("scripts/tool.py", '"""Code target, not a knowledge node."""\n')
        code_link = self.write("brain/CODE.md", "[[scripts/tool.py]]\n")

        links = sa.analyze_links(
            [target, wiki, at_import, markdown, code_link],
            self.root,
            entry_points=[],
        )

        self.assertEqual(
            links.inbound["brain/TARGET.md"],
            {"brain/WIKI.md", "brain/IMPORT.md", "brain/MARKDOWN.md"},
        )
        self.assertEqual(links.broken_links, [])

    def test_skill_directory_wiki_link_resolves_to_skill_md(self) -> None:
        skill = self.write("skills/n8n-patterns/SKILL.md")
        source = self.write("brain/SOURCE.md", "[[skills/n8n-patterns]]\n")

        links = sa.analyze_links([skill, source], self.root, entry_points=[])

        self.assertEqual(links.inbound["skills/n8n-patterns/SKILL.md"], {"brain/SOURCE.md"})
        self.assertEqual(links.broken_links, [])

    def test_template_satisfies_live_file_fallback_without_entering_active_graph(self) -> None:
        source = self.write("brain/SOURCE.md", "[[memory/DECISIONS]]\n")
        template = self.write("memory/DECISIONS.template.md")

        links = sa.analyze_links([source, template], self.root, entry_points=[])
        orphans = sa.find_orphans([source, template], links, self.root, allowlist={"brain/SOURCE.md"})

        self.assertEqual(links.broken_links, [])
        self.assertNotIn("memory/DECISIONS.template.md", orphans)

    def test_canonical_docs_resolve_but_do_not_enter_active_reachability(self) -> None:
        target = self.write("brain/TARGET.md")
        canonical = self.write("brain/_canonical/LOCKSTEP.md", "[[brain/TARGET]]\n")
        source = self.write("brain/SOURCE.md", "[[brain/_canonical/LOCKSTEP]]\n")

        links = sa.analyze_links([target, canonical, source], self.root, entry_points=[])
        orphans = sa.find_orphans(
            [target, canonical, source],
            links,
            self.root,
            allowlist={"brain/SOURCE.md"},
        )

        self.assertEqual(links.broken_links, [])
        self.assertEqual(links.inbound["brain/TARGET.md"], set())
        self.assertEqual(orphans, ["brain/TARGET.md"])


class EntrypointTests(TempRepoTestCase):
    def test_discovers_all_default_live_entrypoints_including_opencode_and_zcode(self) -> None:
        expected = {
            "CLAUDE.md",
            "GEMINI.md",
            "ANTIGRAVITY.md",
            "AGENTS.md",
            "OPENCODE.md",
            "ZCODE.md",
        }
        for name in expected:
            self.write(name)

        found = {p.name for p in sa.discover_entry_points(self.root)}

        self.assertEqual(found, expected)

    def test_genome_manifest_overrides_default_entrypoints(self) -> None:
        self.write("CUSTOM.md")
        self.write("CLAUDE.md")
        self.write("genome.json", json.dumps({"entry_points": ["CUSTOM.md"]}))

        self.assertEqual(
            [p.name for p in sa.discover_entry_points(self.root)],
            ["CUSTOM.md"],
        )


class GateTests(TempRepoTestCase):
    def test_archive_metadata_and_manifest_are_mandatory(self) -> None:
        archive = self.write("brain/_archive/OLD.md", "# Missing metadata\n")
        self.write(
            "brain/_archive/README.md",
            "# Manifest\n\n| Archived record | Original path | Successor |\n",
        )
        result = sa.AuditResult()

        sa.check_archive_metadata(result, self.root, [archive])

        self.assertTrue(result.archive_metadata_issues)
        finalized = sa.finalize_audit_result(result)
        self.assertIn("invalid archive metadata", finalized.mandatory_gate_failures)
        self.assertFalse(finalized.healthy)

    def test_archive_manifest_is_recursive_and_one_to_one(self) -> None:
        self.write("brain/CURRENT.md")
        self.write("brain/_archive/nested/OLD.md", "# No metadata\n")
        self.write(
            "brain/_archive/README.md",
            "# Manifest\n\n"
            "| Archived record | Original path | Successor |\n"
            "|---|---|---|\n"
            "| `GHOST.md` | `brain/GHOST.md` | `brain/CURRENT.md` |\n",
        )
        result = sa.AuditResult()

        sa.check_archive_metadata(result, self.root, [])

        self.assertTrue(
            any("nested/OLD.md: missing status" in issue for issue in result.archive_metadata_issues)
        )
        self.assertIn(
            "brain/_archive/README.md: manifest record does not exist: GHOST.md",
            result.archive_metadata_issues,
        )

    def test_complete_archive_metadata_and_manifest_pass(self) -> None:
        self.write("brain/CURRENT.md")
        archive = self.write(
            "brain/_archive/OLD.md",
            "---\n"
            "status: archived\n"
            "archived_on: 2026-07-19\n"
            "archived_from: brain/OLD.md\n"
            "archive_reason: Completed migration.\n"
            "superseded_by: brain/CURRENT.md\n"
            "---\n"
            "# Old\n",
        )
        self.write(
            "brain/_archive/README.md",
            "# Manifest\n\n| `OLD.md` | `brain/OLD.md` | `brain/CURRENT.md` |\n",
        )
        result = sa.AuditResult()

        sa.check_archive_metadata(result, self.root, [archive])

        self.assertEqual(result.archive_metadata_issues, [])

    def test_archive_provenance_rejects_absolute_and_traversal_paths(self) -> None:
        archive = self.write(
            "brain/_archive/OLD.md",
            "---\n"
            "status: archived\n"
            "archived_on: 2026-07-19\n"
            "archived_from: ../outside.md\n"
            "archive_reason: Completed.\n"
            "superseded_by: C:/outside.md\n"
            "---\n# Old\n",
        )
        self.write(
            "brain/_archive/README.md",
            "| `OLD.md` | `../outside.md` | `C:/outside.md` |\n",
        )
        result = sa.AuditResult()

        sa.check_archive_metadata(result, self.root, [archive])

        self.assertTrue(
            any("archived_from must be a repository-relative path" in issue for issue in result.archive_metadata_issues)
        )
        self.assertTrue(
            any("superseded_by must be a repository-relative path" in issue for issue in result.archive_metadata_issues)
        )

    def test_graph_normalization_ignores_only_generated_at(self) -> None:
        first = {
            "generated_at": "one",
            "nodes": [{"id": "script:x", "description": "x", "owner": "bravo"}],
            "edges": [],
            "drift": [],
        }
        second = {**first, "generated_at": "two"}
        changed = {
            **second,
            "nodes": [{"id": "script:x", "description": "x", "owner": "atlas"}],
        }

        self.assertEqual(sa.normalize_graph(first), sa.normalize_graph(second))
        self.assertNotEqual(sa.normalize_graph(first), sa.normalize_graph(changed))
        complete_empty = {
            "generated_at": "one",
            "nodes": [],
            "edges": [],
            "drift": [],
        }
        self.assertNotEqual(
            sa.normalize_graph(complete_empty),
            sa.normalize_graph({"generated_at": "two"}),
        )

    def test_generated_doc_and_retrieval_source_drift_are_reported(self) -> None:
        self.write("brain/GENERATED.md", "stale\n")
        result = sa.AuditResult()
        sa.check_generated_docs(
            result,
            self.root,
            graph={},
            renderer=lambda _graph: {"brain/GENERATED.md": "fresh\n"},
        )

        db = self.root / "state" / "memory_index.db"
        db.parent.mkdir(parents=True)
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE source_state(source TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE memory_chunks(source TEXT)")
        conn.execute("CREATE TABLE chunk_meta(source TEXT)")
        conn.execute("INSERT INTO source_state(source) VALUES ('memory/GHOST_STATE.md')")
        conn.execute("INSERT INTO source_state(source) VALUES (NULL)")
        conn.execute("INSERT INTO source_state(source) VALUES ('')")
        conn.execute("INSERT INTO memory_chunks(source) VALUES ('memory/GHOST_CHUNK.md')")
        conn.execute("INSERT INTO memory_chunks(source) VALUES ('memory')")
        conn.execute("INSERT INTO chunk_meta(source) VALUES ('memory/GHOST_META.md')")
        conn.commit()
        conn.close()
        sa.check_retrieval_sources(result, self.root, db)

        self.assertEqual(result.generated_docs_drift, ["brain/GENERATED.md"])
        self.assertEqual(
            result.retrieval_missing_sources,
            [
                "memory",
                "memory/GHOST_CHUNK.md",
                "memory/GHOST_META.md",
                "memory/GHOST_STATE.md",
            ],
        )
        self.assertTrue(
            any("blank/non-string source row" in error for error in result.gate_errors)
        )

    def test_script_coverage_comes_from_structured_graph_metadata(self) -> None:
        self.write('scripts/tool.py', '"""A real tool."""\n')
        self.write('scripts/_archive/old.py', '"""Approved archived tool."""\n')
        graph = {
            "nodes": [
                {
                    "id": "script:tool",
                    "kind": "script",
                    "name": "tool",
                    "path": "scripts/tool.py",
                    "description": "A real tool.",
                    "tier": "tool",
                    "owner": "bravo",
                    "discovery": "auto-docstring",
                }
            ]
        }
        result = sa.AuditResult()

        sa.check_scripts(result, self.root, graph)

        self.assertEqual(result.scripts_total, 1)
        self.assertEqual(result.scripts_undocumented, [])
        self.assertEqual(result.script_metadata_issues, [])

        result = sa.AuditResult()
        sa.check_scripts(result, self.root, {"nodes": []})
        self.assertEqual(result.scripts_undocumented, ["scripts/tool.py"])

    def test_only_required_core_freshness_is_a_mandatory_gate(self) -> None:
        self.write(
            "brain/STALE.md",
            "---\nlast_updated: 2026-01-01\nfreshness_threshold_days: 10\n---\n# Stale\n",
        )
        self.write("brain/NO_DATE.md", "# No date\n")
        result = sa.AuditResult()

        sa.check_freshness(
            result,
            self.root,
            today=date(2026, 2, 1),
            required_core=set(),
        )

        self.assertEqual(result.freshness_stale, ["brain/STALE.md"])
        self.assertEqual(result.freshness_missing_dates, ["brain/NO_DATE.md"])
        self.assertEqual(result.freshness_required_stale, [])
        self.assertEqual(sa.compute_health_score(result), 99)

        self.write(
            "brain/EXECUTION_RULES.md",
            "---\nlast_updated: 2026-01-01\nfreshness_threshold_days: 10\n---\n# Required\n",
        )
        required_result = sa.AuditResult()
        sa.check_freshness(
            required_result,
            self.root,
            today=date(2026, 2, 1),
            required_core={"brain/EXECUTION_RULES.md"},
        )

        self.assertEqual(
            required_result.freshness_required_stale,
            ["brain/EXECUTION_RULES.md"],
        )
        self.assertLess(sa.compute_health_score(required_result), 85)

    def test_missing_required_core_document_is_a_mandatory_failure(self) -> None:
        self.write("brain/README.md", "# Brain\n")
        result = sa.AuditResult()

        sa.check_freshness(
            result,
            self.root,
            today=date(2026, 2, 1),
            required_core={"brain/EXECUTION_RULES.md"},
        )

        self.assertEqual(
            result.freshness_required_missing,
            ["brain/EXECUTION_RULES.md"],
        )
        self.assertLess(sa.compute_health_score(result), 85)

    def test_inactive_required_core_document_is_a_mandatory_failure(self) -> None:
        self.write(
            "brain/EXECUTION_RULES.md",
            "---\nstatus: private\nlast_updated: 2026-02-01\n---\n# Hidden core\n",
        )
        result = sa.AuditResult()

        sa.check_freshness(
            result,
            self.root,
            today=date(2026, 2, 1),
            required_core={"brain/EXECUTION_RULES.md"},
        )

        self.assertEqual(
            result.freshness_required_inactive,
            ["brain/EXECUTION_RULES.md"],
        )
        self.assertLess(sa.compute_health_score(result), 85)

    def test_score_100_requires_no_failures_or_warnings(self) -> None:
        self.assertEqual(sa.compute_health_score(sa.AuditResult()), 100)

        warning = sa.AuditResult(warnings=["warning"])
        self.assertEqual(sa.compute_health_score(warning), 99)

        failure = sa.AuditResult(generated_docs_drift=["brain/INDEX.md"])
        self.assertLess(sa.compute_health_score(failure), 85)

    def test_final_result_exposes_mandatory_gate_and_health_status(self) -> None:
        clean = sa.finalize_audit_result(sa.AuditResult())
        self.assertTrue(clean.mandatory_gate_passed)
        self.assertEqual(clean.mandatory_gate_failures, [])
        self.assertTrue(clean.healthy)

        drift = sa.finalize_audit_result(
            sa.AuditResult(generated_docs_drift=["brain/INDEX.md"])
        )
        self.assertFalse(drift.mandatory_gate_passed)
        self.assertIn("generated-doc drift", drift.mandatory_gate_failures)
        self.assertFalse(drift.healthy)


if __name__ == "__main__":
    unittest.main()
