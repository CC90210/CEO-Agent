from __future__ import annotations

import json

from bravo_cli import bridge_chat_server as bridge


def test_cli_inventory_is_published_as_safe_heartbeat_metadata() -> None:
    calls = 0

    def probe(_name: str, _payload: dict) -> dict:
        nonlocal calls
        calls += 1
        return {
            "is_error": False,
            "output": json.dumps(
                {
                    "claude": {
                        "installed": True,
                        "authenticated": True,
                        "version": "2.1.215 (Claude Code)",
                        "install_hint_url": "https://example.test/claude",
                    },
                    "codex": {
                        "installed": True,
                        "authenticated": True,
                        "version": "codex-cli 0.146.0",
                        "install_hint_url": "https://example.test/codex",
                    },
                    "gemini": {
                        "installed": True,
                        "authenticated": False,
                        "version": "0.42.0",
                        "install_hint_url": "https://example.test/gemini",
                    },
                }
            ),
        }

    result = bridge._services_from_cli_inventory(
        probe=probe,
        now_iso="2026-08-25T16:30:00+00:00",
        use_cache=False,
    )

    assert calls == 1
    assert result["local_ai_clis"]["status"] == "healthy"
    metadata = result["local_ai_clis"]["metadata"]
    assert metadata["checked_at"] == "2026-08-25T16:30:00+00:00"
    assert metadata["providers"]["claude"] == {
        "installed": True,
        "authenticated": True,
        "version": "2.1.215 (Claude Code)",
    }
    assert metadata["providers"]["gemini"]["authenticated"] is False
    assert "install_hint_url" not in metadata["providers"]["codex"]


def test_invalid_cli_probe_is_not_published() -> None:
    result = bridge._services_from_cli_inventory(
        probe=lambda _name, _payload: {"is_error": True, "output": "nope"},
        now_iso="2026-08-25T16:30:00+00:00",
        use_cache=False,
    )
    assert result == {}


def test_cli_mutation_invalidation_bypasses_cached_auth_state() -> None:
    calls = 0

    def authenticated_probe(_name: str, _payload: dict) -> dict:
        nonlocal calls
        calls += 1
        return {
            "is_error": False,
            "output": json.dumps(
                {
                    provider: {
                        "installed": True,
                        "authenticated": True,
                        "version": "1.0",
                    }
                    for provider in ("claude", "codex", "gemini")
                }
            ),
        }

    bridge._CLI_INVENTORY_CACHE["services"] = {
        "local_ai_clis": {
            "status": "healthy",
            "metadata": {
                "providers": {
                    provider: {
                        "installed": True,
                        "authenticated": False,
                        "version": "1.0",
                    }
                    for provider in ("claude", "codex", "gemini")
                }
            },
        }
    }
    bridge._CLI_INVENTORY_CACHE["probed_at"] = bridge.time.monotonic()

    try:
        bridge._invalidate_cli_inventory_cache(refresh_window_s=180.0)
        result = bridge._services_from_cli_inventory(
            probe=authenticated_probe,
            now_iso="2026-08-25T16:31:00+00:00",
            use_cache=True,
        )
        assert calls == 1
        assert (
            result["local_ai_clis"]["metadata"]["providers"]["codex"]["authenticated"]
            is True
        )
    finally:
        bridge._CLI_INVENTORY_FORCE_FRESH_UNTIL = 0.0
        bridge._CLI_INVENTORY_CACHE["services"] = None
        bridge._CLI_INVENTORY_CACHE["probed_at"] = 0.0


def test_successful_cli_actions_trigger_inventory_refresh_window() -> None:
    source = (bridge.Path(bridge.__file__)).read_text(encoding="utf-8")
    action_guard = 'tool_name in {"install_cli", "cli_auth_start"}'
    invalidation = "_invalidate_cli_inventory_cache(refresh_window_s=180.0)"
    assert action_guard in source
    assert source.index(invalidation) > source.index(action_guard)
