"""Sanity checks on the warm-pool module that don't require spawning
a real claude subprocess. Anything heavier (send_turn round-trip)
belongs in an integration test, not a smoke suite."""

from bravo_cli import warm_claude_pool as wp


def test_prewarm_prompt_is_explicit_about_origin():
    """The prewarm prompt must clearly mark itself as a runtime ping
    so the agent ignores it in the conversation history. The
    [OASIS_RUNTIME_PREWARM] tag is the load-bearing signal — without it,
    claude treats the prewarm as the user's first question."""
    p = wp._PREWARM_PROMPT
    assert "[OASIS_RUNTIME_PREWARM]" in p, "prewarm prompt must carry the runtime tag"
    assert "ignore" in p.lower(), "prompt must instruct the agent to ignore the exchange"
    assert "user did not send this" in p.lower() or "not a user request" in p.lower(), \
        "prompt must disclaim the user origin so the model doesn't surface it"


def test_pool_module_exposes_lifecycle_functions():
    """The bridge_chat_server imports these by name. Renaming any of
    them silently is the kind of regression a smoke test catches."""
    for name in ("use_or_create", "kill_for_session", "prewarm",
                 "pool_status"):
        assert hasattr(wp, name), f"warm_claude_pool missing public function {name!r}"


def test_warmclaudeprocess_exists():
    cls = getattr(wp, "WarmClaudeProcess", None)
    assert cls is not None
    for method in ("send_turn", "is_alive", "kill"):
        assert callable(getattr(cls, method, None)), \
            f"WarmClaudeProcess missing {method}()"
