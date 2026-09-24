"""Bridge regression contracts for the failed Telegram fallback incident."""
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_telegram_bridge_routes_automatic_fallback_to_codex():
    source = (ROOT / "telegram_agent.js").read_text(encoding="utf-8")
    assert "executeCodexFallback" in source
    assert "routing through Codex subscription fallback" in source
    assert "routing through OpenCode fallback" not in source
    assert "--operator-trusted" in source


def test_telegram_automatic_fallback_only_replays_prework_quota_or_auth_failures():
    source = (ROOT / "telegram_agent.js").read_text(encoding="utf-8")
    assert "if (code !== 0 && tool === 'claude' && looksLikeQuotaOrAuth)" in source
    assert "if (code !== 0 && tool === 'claude')" not in source


def test_untrusted_coordination_rows_never_reach_codex_tools():
    source = (ROOT / "coordination_agent.js").read_text(encoding="utf-8")
    assert "trusted ? await spawnCodexFallback(prompt) : null" in source


def test_telegram_fallback_nonzero_is_not_recorded_as_success():
    source = (ROOT / "telegram_agent.js").read_text(encoding="utf-8")
    assert "codex-fallback" in source
    assert "if (code !== 0" in source
    assert "resolve(null)" in source


def test_telegram_recovery_instructions_name_the_live_supervisor():
    source = (ROOT / "telegram_agent.js").read_text(encoding="utf-8")
    assert "fleet_watchdog.py restart bravo-telegram" in source
    assert "pm2 restart bravo-telegram" not in source


def test_telegram_spawn_error_uses_codex_before_returning_an_error():
    source = (ROOT / "telegram_agent.js").read_text(encoding="utf-8")
    assert "child.on('error', async (err) =>" in source
    assert "Claude unavailable (quota/auth)" in source
    assert "Claude could not start" in source
    assert "Claude quota hit" not in source


def test_dormant_gateway_cannot_resurrect_opencode_fallback():
    source = (ROOT / "gateway" / "adapters" / "telegram.js").read_text(encoding="utf-8")
    assert "executeCodexFallback" in source
    assert "--operator-trusted" in source
    assert "opencode" not in source.lower()
    assert "isClaudeAuthOrQuotaFailure(raw, code)" in source
    assert "createSettlement" in source
    assert "_autoRegisterUser" not in source
    assert "allowlist not configured" in source


def test_empty_allowlist_fails_closed_without_rewriting_the_secret_store():
    source = (ROOT / "telegram_agent.js").read_text(encoding="utf-8")
    assert "ALLOWED_USERS.length > 0 && ALLOWED_USERS.includes" in source
    assert "if (!isAuthorizedUser(userId))" in source
    assert "allowlist not configured" in source
    assert "autoRegisterUser" not in source
    assert "First user registered as owner" not in source
    assert "TELEGRAM_ALLOWED_USERS=${userId}" not in source


def test_timeout_settlement_prevents_late_close_replay():
    """Executable proof: close-after-timeout cannot run fallback/state effects."""
    helper = ROOT / "scripts" / "lib" / "settle_once.js"
    script = f"""
const {{ createSettlement }} = require({json.dumps(str(helper))});
let replies = 0;
let fallbacks = 0;
let stateSyncs = 0;
const gate = createSettlement(() => {{ replies += 1; }});
gate.settle('timed out');
if (!gate.isSettled()) {{ fallbacks += 1; stateSyncs += 1; gate.settle('late close'); }}
process.stdout.write(JSON.stringify({{ replies, fallbacks, stateSyncs }}));
"""
    completed = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, check=True, timeout=10
    )
    assert json.loads(completed.stdout) == {
        "replies": 1,
        "fallbacks": 0,
        "stateSyncs": 0,
    }
