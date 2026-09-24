"""The Node bridge heartbeat must reflect real Telegram API reachability."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_both_bridges_publish_and_mark_polling_failures():
    helper = (ROOT / "scripts" / "lib" / "telegram_transport_health.js")
    assert helper.is_file()
    source = helper.read_text(encoding="utf-8")
    assert "bot.getMe()" in source
    assert "checked_at" in source

    telegram = (ROOT / "telegram_agent.js").read_text(encoding="utf-8")
    coordination = (ROOT / "coordination_agent.js").read_text(encoding="utf-8")
    for bridge in (telegram, coordination):
        assert "createTelegramTransportHealth" in bridge
        assert "transportHealth.markFailure" in bridge
        assert "transportHealth.start" in bridge


def test_coordination_conflict_recovery_cannot_clear_a_newer_failure():
    coordination = (ROOT / "coordination_agent.js").read_text(encoding="utf-8")
    assert "const conflictCountAtResume = pollConflicts" in coordination
    assert "if (pollConflicts === conflictCountAtResume)" in coordination
    conflict_handler = coordination.split("bot.on('polling_error'", 1)[1]
    before_increment = conflict_handler.split("pollConflicts++", 1)[0]
    assert "clearTimeout(lastConflictResolvedCheck)" in before_increment
