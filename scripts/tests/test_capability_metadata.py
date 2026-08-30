"""Capability metadata and graph-wiring regression tests."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_capability_graph as bcg  # noqa: E402


REVIEWED_SCRIPTS = {
    "break_glass_drill",
    "breeze_set_tenant_email",
    "check_brain_freshness",
    "consolidate_mca_phone_sheet",
    "enrich_sheet_inplace",
    "harness_plugin",
    "history_secret_scan",
    "migrate_lender_industry_restrictions_key",
    "pause_controller",
    "pii_sweep",
    "run_reseed_sunbiz_forms",
    "seed_sunbiz_application_form_fields",
    "skill_spector",
}

EXPECTED_CLASSIFICATION = {
    "break_glass_drill": ("governance.resilience", "active", "read_only", True),
    "breeze_set_tenant_email": ("client.onboarding", "one_off", "external_write", False),
    "check_brain_freshness": ("governance.knowledge", "active", "read_only", True),
    "consolidate_mca_phone_sheet": ("client.data_operations", "one_off", "external_write", False),
    "enrich_sheet_inplace": ("lead.data_operations", "manual", "external_write", False),
    "harness_plugin": ("governance.runtime", "deprecated", "read_only", False),
    "history_secret_scan": ("security.secrets", "deprecated", "read_only", False),
    "migrate_lender_industry_restrictions_key": ("database.migration", "one_off", "external_write", False),
    "pause_controller": ("outbound.safety", "active", "external_write", True),
    "pii_sweep": ("security.privacy", "active", "destructive", True),
    "run_reseed_sunbiz_forms": ("release.sunbiz", "active", "external_write", False),
    "seed_sunbiz_application_form_fields": ("database.migration", "one_off", "external_write", False),
    "skill_spector": ("security.agent_governance", "active", "read_only", True),
}


def _reviewed_path(stem: str) -> Path:
    candidates = (SCRIPTS / f"{stem}.py", SCRIPTS / "_archive" / f"{stem}.py")
    return next((path for path in candidates if path.is_file()), candidates[0])


def test_reviewed_scripts_have_complete_literal_metadata():
    for stem in REVIEWED_SCRIPTS:
        path = _reviewed_path(stem)
        meta = bcg.read_capability_meta(path)
        assert meta is not None, f"{stem} is missing CAPABILITY_META"
        assert not bcg.validate_capability_meta(meta), f"{stem}: {bcg.validate_capability_meta(meta)}"


def test_reviewed_scripts_match_approved_classification():
    for stem, expected in EXPECTED_CLASSIFICATION.items():
        meta = bcg.read_capability_meta(_reviewed_path(stem))
        assert meta is not None
        actual = (meta["category"], meta["lifecycle"], meta["risk"], meta["bridge"]["visible"])
        assert actual == expected, f"{stem}: expected {expected}, got {actual}"


def test_script_nodes_surface_metadata_in_the_graph():
    nodes = {node["name"]: node for node in bcg.discover_scripts()}
    assert "harness_plugin" not in nodes
    assert "history_secret_scan" not in nodes
    pause = nodes["pause_controller"]
    assert pause["category"] == "outbound.safety"
    assert pause["lifecycle"] == "active"
    assert pause["risk"] == "external_write"
    assert "pause outbound" in pause["triggers"]
    assert pause["project"] == "sunbiz"
    assert pause["bridge"]["subcommands"]["status"]["confirm"] is False
    assert pause["bridge"]["subcommands"]["pause"]["confirm"] is True


def test_nested_scripts_are_opt_in_via_literal_metadata(tmp_path, monkeypatch):
    scripts = tmp_path / "scripts"
    nested = scripts / "integrations"
    archived = scripts / "_archive"
    nested.mkdir(parents=True)
    archived.mkdir()
    (scripts / "legacy_top_level.py").write_text('"""Legacy top-level CLI."""\n', encoding="utf-8")
    (nested / "unregistered.py").write_text('"""Nested helper, not a capability."""\n', encoding="utf-8")
    literal_meta = textwrap.dedent(
        '''
        """Registered nested CLI."""
        CAPABILITY_META = {
            "category": "data.test",
            "lifecycle": "active",
            "risk": "read_only",
            "triggers": ["test nested discovery"],
            "owner": "bravo",
            "project": "empire",
            "bridge": {"visible": False},
        }
        '''
    )
    (nested / "registered.py").write_text(literal_meta, encoding="utf-8")
    (archived / "archived.py").write_text(literal_meta, encoding="utf-8")

    monkeypatch.setattr(bcg, "PROJECT_ROOT", tmp_path)
    nodes = {node["name"]: node for node in bcg.discover_scripts()}
    assert set(nodes) == {"legacy_top_level", "registered"}
    assert nodes["registered"]["path"] == "scripts/integrations/registered.py"


def test_canonical_nested_operator_scripts_are_graph_registered():
    nodes = {node["name"]: node for node in bcg.discover_scripts()}
    expected = {
        # data.turso_compat since the 2026-08-09 Turso cutover (6036b6a6):
        # supabase_tool is the deprecated compat shim, not the live DB path.
        "supabase_tool": ("scripts/integrations/supabase_tool.py", "data.turso_compat"),
        "send_gateway": ("scripts/integrations/send_gateway.py", "outbound.gateway"),
        "cloak_browser_tool": ("scripts/browser/cloak_browser_tool.py", "browser.research"),
        "agent_inbox": ("scripts/core/agent_inbox.py", "orchestration.messaging"),
    }
    for stem, (path, category) in expected.items():
        assert nodes[stem]["path"] == path
        assert nodes[stem]["category"] == category
        assert nodes[stem]["discovery"] == "auto-capability-meta"


def test_workflow_index_is_not_a_workflow_node(tmp_path, monkeypatch):
    workflows = tmp_path / ".agents" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "INDEX.md").write_text("# Generated index\n", encoding="utf-8")
    (workflows / "ship.md").write_text("# Ship\n", encoding="utf-8")
    monkeypatch.setattr(bcg, "PROJECT_ROOT", tmp_path)
    assert [node["id"] for node in bcg.discover_workflows()] == ["workflow:ship"]


def test_runtime_entrypoints_are_explicit_and_deterministic():
    nodes = bcg.discover_runtime_entrypoints()
    assert [node["id"] for node in nodes] == [
        "runtime:bridge_chat_server",
        "runtime:cron_engine",
        "runtime:telegram_agent",
    ]
    assert all(node["kind"] == "runtime" for node in nodes)


def test_script_edges_cover_calls_and_bridge_exposure():
    nodes = [
        {
            "id": "script:caller",
            "kind": "script",
            "name": "caller",
            "_source": "import target\nsubprocess.run(['python', 'scripts/other.py'])",
            "bridge": {"visible": True},
        },
        {"id": "script:target", "kind": "script", "name": "target", "_source": ""},
        {"id": "script:other", "kind": "script", "name": "other", "_source": ""},
        {
            "id": "script:configured",
            "kind": "script",
            "name": "configured",
            "_source": 'HELPER_TOOL = "target.py"',
        },
        {
            "id": "runtime:bridge_chat_server",
            "kind": "runtime",
            "name": "bridge_chat_server",
            "_source": "",
        },
    ]
    edges = {(edge["from"], edge["to"], edge["kind"]) for edge in bcg.infer_edges(nodes)}
    assert ("script:caller", "script:target", "calls") in edges
    assert ("script:caller", "script:other", "calls") in edges
    assert ("script:configured", "script:target", "references") in edges
    assert ("script:caller", "runtime:bridge_chat_server", "exposed_via") in edges


def test_runtime_edges_cover_cron_telegram_and_bridge_exposure():
    nodes = bcg.discover_scripts() + bcg.discover_runtime_entrypoints()
    edges = {(edge["from"], edge["to"], edge["kind"]) for edge in bcg.infer_edges(nodes)}
    assert ("runtime:cron_engine", "script:break_glass_drill", "schedules") in edges
    assert ("runtime:telegram_agent", "script:pause_controller", "exposes") in edges
    # turso_tool replaced supabase_tool here at the 2026-08-09 cutover: the
    # compat shim is bridge-hidden (visible: False) by design, so it must NOT
    # carry an exposed_via edge — pinned both directions.
    for stem in ("turso_tool", "send_gateway", "cloak_browser_tool", "agent_inbox"):
        assert (f"script:{stem}", "runtime:bridge_chat_server", "exposed_via") in edges
    assert ("script:supabase_tool", "runtime:bridge_chat_server", "exposed_via") not in edges


def test_security_pattern_literals_are_not_misclassified_as_script_calls():
    nodes = [
        {
            "id": "script:scanner",
            "kind": "script",
            "name": "scanner",
            "_source": 'PRIVILEGED_TOOLS = {"target.py"}',
        },
        {"id": "script:target", "kind": "script", "name": "target", "_source": ""},
    ]
    edges = bcg.infer_edges(nodes)
    assert edges == []


def test_normalized_graph_comparison_ignores_only_generated_timestamp():
    base = {
        "generated_at": "old",
        "nodes": [{"id": "script:x", "kind": "script", "risk": "read_only"}],
        "edges": [],
        "drift": [],
        "totals": {"nodes_total": 1},
    }
    timestamp_only = {**base, "generated_at": "new"}
    metadata_change = {
        **base,
        "generated_at": "new",
        "nodes": [{"id": "script:x", "kind": "script", "risk": "external_write"}],
    }
    assert bcg.normalize_graph(base) == bcg.normalize_graph(timestamp_only)
    assert bcg.normalize_graph(base) != bcg.normalize_graph(metadata_change)


def test_graph_check_fails_when_existing_node_metadata_changes(tmp_path, monkeypatch):
    disk_graph = {
        "generated_at": "old",
        "nodes": [{"id": "script:x", "kind": "script", "risk": "read_only"}],
        "edges": [],
        "drift": [],
        "totals": {"nodes_total": 1},
    }
    graph_path = tmp_path / "CAPABILITY_GRAPH.json"
    graph_path.write_text(json.dumps(disk_graph), encoding="utf-8")
    monkeypatch.setattr(bcg, "GRAPH_PATH", graph_path)
    changed = {
        **disk_graph,
        "generated_at": "new",
        "nodes": [{"id": "script:x", "kind": "script", "risk": "external_write"}],
    }
    assert bcg.cmd_check(changed) == 1
