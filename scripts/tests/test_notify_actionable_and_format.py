"""Two defects CC hit on 2026-08-04, both about notifications that waste his attention.

1. `python scripts/notify.py --help` BROADCAST the literal string "--help" to his
   phone. notify.py had no argument parser: anything that wasn't exactly
   --test/--group fell through to `" ".join(argv)` and was force-sent past the
   category block. He got a message from Bravo saying "--help" and no way to
   tell what it wanted.

2. Cron results went to Telegram as `f"{job_name}: {result_msg[:200]}"` — raw
   JSON sliced mid-value, so the Inbound Email Sweep alert ended in the middle
   of a DMARC Report-ID.

Run: python -m pytest scripts/tests/test_notify_actionable_and_format.py -q
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import notify as nf  # noqa: E402
import scheduler as sch  # noqa: E402


# ── 1. The CLI must never send a flag ──────────────────────────────────────

def _run_cli(*args: str) -> subprocess.CompletedProcess:
    """Invoke the real CLI. NOTIFY_DISABLED=1 makes a send a no-op, so if the
    argument handling regressed this fails on exit code / output, never by
    actually paging CC."""
    import os
    env = {**os.environ, "NOTIFY_DISABLED": "1"}
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "notify.py"), *args],
        capture_output=True, text=True, env=env, timeout=120,
    )


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_prints_usage_and_sends_nothing(flag):
    proc = _run_cli(flag)
    assert proc.returncode == 0
    assert "usage: notify.py" in proc.stdout
    # The regression: the CLI reporting a send at all on --help.
    assert "Sent:" not in proc.stdout


@pytest.mark.parametrize("flag", ["--dry-run", "--verison", "--force"])
def test_unknown_flag_is_an_error_not_a_message(flag):
    proc = _run_cli(flag)
    assert proc.returncode == 2, f"{flag} should be rejected, not sent"
    assert "unknown option" in proc.stderr
    assert "Sent:" not in proc.stdout


def test_no_args_refuses_instead_of_sending_a_contentless_ping():
    proc = _run_cli()
    assert proc.returncode == 2
    assert "nothing to send" in proc.stderr
    assert "Sent:" not in proc.stdout


def test_a_real_message_still_reaches_the_send_path():
    """Guard against over-correcting: normal usage must be unaffected."""
    proc = _run_cli("Funnel lead from oasisai.work needs review")
    assert proc.returncode in (0, 1)  # 1 = disabled/no-send, not an arg error
    assert "Sent:" in proc.stdout
    assert "unknown option" not in proc.stderr


# ── 2. The chokepoint guard, for every non-CLI caller ──────────────────────

@pytest.mark.parametrize("bad", ["--help", "-h", "--group", "", "   ", "\n"])
def test_non_actionable_payloads_are_refused(bad):
    assert nf._is_actionable(bad) is False


@pytest.mark.parametrize("good", [
    "Inbound sweep found 3 unread",
    "--group lane resolved no chat id — check GROUP_TELEGRAM_CHAT_ID",  # flag + words
    "OK",
    "cron: Daily Brief failed 2x consecutively",
])
def test_real_alerts_are_not_refused(good):
    assert nf._is_actionable(good) is True


def test_notify_refuses_a_bare_flag_even_when_forced(monkeypatch, capsys):
    """force=True bypasses category muting — it must NOT bypass this."""
    monkeypatch.setattr(nf, "_notify_disabled", lambda: False)
    sent = []
    monkeypatch.setattr(nf, "_send_telegram", lambda *a, **k: sent.append(a) or True,
                        raising=False)
    assert nf.notify("--help", category="system", force=True) is False
    assert sent == []
    assert "non-actionable" in capsys.readouterr().err


# ── 3. Cron results must read like English, not like a JSON dump ───────────

# Verbatim from CC's screenshot, 2026-08-04 06:30. indent=2 matters: the
# pretty-printed form is what the job actually emits, and it is why the 200-char
# slice landed in the middle of the Report-ID rather than past it.
SWEEP_RESULT = json.dumps({
    "status": "checked",
    "unread_count": 1,
    "emails": [{
        "from": "noreply-dmarc-support@google.com",
        "subject": ("Report domain: oasisai.work Submitter: google.com "
                    "Report-ID: 12178238882037592739"),
    }],
}, indent=2)


def test_the_screenshotted_message_is_now_readable():
    out = sch.humanize_job_result("Inbound Email Sweep", SWEEP_RESULT)
    # No JSON punctuation anywhere.
    for ch in ('{', '}', '[', ']', '"'):
        assert ch not in out, f"raw JSON char {ch!r} still reaching Telegram:\n{out}"
    assert out.startswith("Inbound Email Sweep — 1 unread")
    assert "noreply-dmarc-support@google.com" in out
    # The old 200-char slice cut the Report-ID in half at "12178".
    assert "12178238882037592739" in out


def test_old_format_would_fail_these_assertions():
    """The assertions discriminate — they reject the pre-fix rendering."""
    old = f"Inbound Email Sweep: {SWEEP_RESULT[:200]}"
    assert "{" in old and '"' in old
    assert "12178238882037592739" not in old  # truncated mid-ID, the actual complaint


def test_clip_prefers_a_word_boundary():
    """Self-review 2026-08-04: the first version of this test contained
    `assert " " not in out[-2:-1] or True` — vacuously true, it could never
    fail. Asserting the real contract instead."""
    out = sch._clip("Report-ID: 12178238882037592739 trailing words here", 30)
    assert out.endswith("…")
    body = out.rstrip("…")
    # Every retained token is whole: the clipped text is a word-prefix of the input.
    assert "Report-ID: 12178238882037592739".startswith(body)
    assert not body.endswith(" ")


def test_clip_falls_back_to_a_hard_cut_for_one_oversized_token():
    """Honest contract: a single token longer than the limit has no boundary to
    cut on, so it IS cut mid-token. Documented rather than pretended away."""
    out = sch._clip("12178238882037592739xxxxx", 10)
    assert out == "1217823888…"


def test_clip_leaves_short_text_untouched():
    assert sch._clip("3 unread", 50) == "3 unread"


def test_plain_text_result_passes_through_unmangled():
    out = sch.humanize_job_result("Pulse Autorefresh", "published 3 items")
    assert out == "Pulse Autorefresh — published 3 items"


def test_unknown_json_shape_still_avoids_raw_braces():
    out = sch.humanize_job_result("Weird Job", json.dumps({"alpha": "one", "beta": 2}))
    assert "{" not in out and '"' not in out
    assert "alpha" in out


def test_long_item_lists_are_summarised_not_dumped():
    payload = json.dumps({
        "unread_count": 9,
        "emails": [{"from": f"s{i}@x.com", "subject": f"subject {i}"} for i in range(9)],
    })
    out = sch.humanize_job_result("Inbound Email Sweep", payload)
    assert "…and 6 more" in out
    assert out.count("•") == 4  # 3 items + the overflow line
    assert len(out) < 700


def test_empty_result_says_so():
    assert sch.humanize_job_result("Some Job", "") == "Some Job — ran, no output"


def test_two_different_sweeps_produce_different_text_so_dedup_cannot_eat_one():
    """Self-review catch, 2026-08-04.

    The first version of this fix passed dedup_key=f"job_result:{job_name}" to
    notify(). That pins suppression to the JOB, so the 06:30 sweep reporting a
    DMARC report would have silently swallowed the 06:35 sweep reporting a real
    prospect for the full 1h NOTIFY_DEDUP_WINDOW_SEC — on the inbound lead
    channel. Identity must stay the rendered text, which only collapses genuine
    repeats. This test fails if anyone reintroduces a constant dedup identity.
    """
    first = sch.humanize_job_result("Inbound Email Sweep", SWEEP_RESULT)
    second = sch.humanize_job_result("Inbound Email Sweep", json.dumps({
        "status": "checked",
        "unread_count": 1,
        "emails": [{"from": "prospect@realcompany.com",
                    "subject": "Interested in your automation service"}],
    }, indent=2))
    assert first != second, "distinct inbound mail must render distinctly"
    assert "prospect@realcompany.com" in second

    # And the scheduler must not hand notify() a constant identity for results.
    import inspect
    src = inspect.getsource(sch.check_and_run_due_jobs)
    assert "dedup_key=f\"job_result:" not in src, (
        "a constant dedup_key on job RESULTS suppresses real new content")


def test_booleans_are_not_rendered_as_counts():
    """bool is a subclass of int — {"sent": True} must not render "True sent"."""
    out = sch.humanize_job_result("Some Job", json.dumps({"sent": True, "status": "done"}))
    assert "True sent" not in out
