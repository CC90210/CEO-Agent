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


# ── Codex adversarial audit, 2026-08-04 ───────────────────────────────────

def test_failure_detail_survives_a_counts_headline():
    """Codex [high]: the scalar fallback was gated on `not counts`, so a payload
    with both counts AND an error rendered as counts only — strictly less
    informative than the raw prefix it replaced."""
    payload = json.dumps({
        "status": "partial_failure",
        "processed": 10,
        "failed": 1,
        "error": "database write rejected",
    })
    out = sch.humanize_job_result("Nightly Sync", payload)
    assert "10 processed" in out and "1 failed" in out
    assert "database write rejected" in out, f"error text dropped:\n{out}"
    assert "partial_failure" in out, f"non-benign status dropped:\n{out}"


def test_benign_status_does_not_add_noise():
    """The counterpart: don't paste 'status: ok' onto every healthy alert."""
    out = sch.humanize_job_result("Sweep", json.dumps({"status": "ok", "sent": 2}))
    assert "status:" not in out
    assert "2 sent" in out


def test_nested_error_dict_is_flattened_not_dropped():
    out = sch.humanize_job_result("Job", json.dumps({
        "synced": 3, "errors": {"row_7": "constraint violation", "row_9": "timeout"}}))
    assert "constraint violation" in out
    assert "{" not in out


def test_pathological_payload_cannot_abort_the_scheduler_loop():
    """Codex [medium]: json.loads on deeply nested input raises RecursionError,
    which is NOT a ValueError. Formatting runs inside check_and_run_due_jobs
    outside any per-job try, so an unhandled raise there would skip every
    remaining due job that tick."""
    bomb = "[" * 20000 + "]" * 20000
    out = sch.humanize_job_result("Evil Job", bomb)          # must not raise
    assert out.startswith("Evil Job — ")
    assert len(out) < 400


def test_huge_and_unicode_payloads_stay_bounded():
    big = json.dumps({"unread_count": 500,
                      "emails": [{"from": f"ünïcøde{i}@例え.jp", "subject": "件名 " * 50}
                                 for i in range(500)]})
    out = sch.humanize_job_result("Inbound Email Sweep", big)
    assert len(out) < 900, "unbounded output would be truncated by Telegram anyway"
    assert "…and 497 more" in out


def test_none_and_nested_items_do_not_crash():
    out = sch.humanize_job_result("Job", json.dumps({
        "items": [None, {"from": None, "subject": None}, {"nested": {"a": 1}}]}))
    assert isinstance(out, str) and out


def test_refusal_is_distinguishable_from_a_delivery_failure(monkeypatch):
    """Codex [medium]: notify() returns False for six different reasons. A
    caller retrying on False must not retry a programmer error."""
    monkeypatch.setattr(nf, "_notify_disabled", lambda: False)
    assert nf.notify("--help", category="system", force=True) is False
    assert nf.LAST_REFUSED is True
    assert nf.LAST_SUPPRESSED is False


def test_a_real_send_path_clears_the_refused_flag(monkeypatch):
    monkeypatch.setattr(nf, "_notify_disabled", lambda: True)  # no real send
    nf.LAST_REFUSED = True
    nf.notify("Inbound sweep: 2 unread", category="email")
    assert nf.LAST_REFUSED is False, "stale refusal flag would mislead the next caller"


# ── Turnkey pass, 2026-08-04: delivery, classification, failure detail ────

def test_hostile_subject_cannot_break_html_delivery():
    """The send sets parse_mode=HTML. An inbound subject containing a tag made
    Telegram answer 400 "can't parse entities" — the alert was generated,
    logged as attempted, and never delivered. Silent loss on the lead channel."""
    body = sch.humanize_job_result("Inbound Email Sweep", json.dumps({
        "unread_count": 1,
        "emails": [{"from": "a@b.com",
                    "subject": "Re: <urgent> invoice & payment <b>overdue</b>"}],
    }, indent=2))
    assert "<" in body and "&" in body          # the renderer passes content through
    safe = nf._escape_html(body)
    assert "<" not in safe and ">" not in safe
    assert "&lt;urgent&gt;" in safe
    assert "&amp;" in safe
    # Readability is not sacrificed: apostrophes/quotes stay literal.
    assert nf._escape_html("CC's \"report\"") == "CC's \"report\""


def test_truncation_never_splits_an_html_entity():
    text = "x" * 4090 + "&amp;tail"
    out = nf._truncate_escaped(text, 4096)
    assert len(out) <= 4096
    assert not out.rstrip(".").endswith("&am")
    assert "&" not in out.rstrip(".")[-4:] or ";" in out.rstrip(".")[-6:]


def test_short_messages_are_not_truncated():
    assert nf._truncate_escaped("hello", 4096) == "hello"


@pytest.mark.parametrize("subject", [
    "Your payment FAILED to process",
    "ERROR: action required on your account",
    "URGENT: transfer FAILED",
])
def test_email_subject_mentioning_failure_is_not_a_job_failure(subject):
    """The real bug: is_error substring-scanned the whole payload, including
    inbound email subjects, so a prospect's wording marked a healthy sweep as
    failed and fed the consecutive-failure escalation ladder."""
    payload = json.dumps({"status": "checked", "unread_count": 1,
                          "emails": [{"from": "p@co.com", "subject": subject}]})
    assert sch._looks_like_failure(payload) is False, subject


def test_genuine_job_failures_are_still_detected():
    for payload in (
        json.dumps({"status": "failed", "processed": 0}),
        json.dumps({"status": "ok", "error": "connection refused"}),
        json.dumps({"ok": False}),
        json.dumps({"result": "FAILED to connect to Supabase"}),
        "Traceback: ERROR connecting",                       # plain text unchanged
        json.dumps({"errors": ["row 7 rejected"]}),
    ):
        assert sch._looks_like_failure(payload) is True, payload


def test_warnings_are_reported_but_do_not_escalate():
    """A warning belongs in the message, not on the failure ladder."""
    payload = json.dumps({"synced": 5, "warning": "3 rows skipped"})
    assert sch._looks_like_failure(payload) is False
    assert "3 rows skipped" in sch.humanize_job_result("Sync", payload)


def test_zero_count_ticks_are_recognised_in_any_json_spelling():
    """The literal probes only matched '"unread_count": 0'. Compact and
    reordered spellings slipped through and notified CC about nothing."""
    for payload in ('{"unread_count":0,"status":"checked"}',
                    '{"status":"checked", "unread_count" : 0}',
                    json.dumps({"status": "checked", "unread_count": 0}, indent=2)):
        assert sch._is_nothing_happened(payload) is True, payload


def test_a_tick_with_actual_content_is_never_called_routine():
    assert sch._is_nothing_happened(SWEEP_RESULT) is False
    assert sch._is_nothing_happened(json.dumps({"unread_count": 0,
                                                "emails": [{"from": "a@b.c"}]})) is False
    assert sch._is_nothing_happened(json.dumps({"unread_count": 0,
                                                "error": "imap timeout"})) is False


def test_failure_alerts_render_the_cause_not_a_json_dump():
    """The error path was the last place shipping raw [:200] JSON — and it is
    the message CC reads at 2am. notify_error() prepends "<job> error:", so the
    detail must not repeat the job name."""
    payload = json.dumps({"status": "failed", "processed": 4, "failed": 3,
                          "error": "Supabase connection refused after 3 retries"},
                         indent=2)
    rendered = sch.humanize_job_result("Stripe Revenue Sync", payload)
    detail = (rendered.split(" — ", 1)[-1]
              if " — " in rendered.split("\n")[0] else rendered)
    assert not detail.startswith("Stripe Revenue Sync"), "job name would be doubled"
    assert "Supabase connection refused after 3 retries" in detail
    assert "{" not in detail and '"' not in detail


def test_a_cause_beyond_200_chars_is_kept_that_is_the_whole_point():
    """Honest discrimination. On a SMALL payload the old [:200] slice happened
    to include the error too — the first version of the test above asserted
    otherwise and was simply wrong. The failure mode is real but needs a payload
    where the cause sits past the cut, which is the common shape: counts and
    items first, diagnosis last."""
    payload = json.dumps({
        "status": "failed",
        "processed": 40,
        "rows": [{"id": f"row-{i}", "state": "rejected"} for i in range(6)],
        "error": "Supabase connection refused after 3 retries",
    }, indent=2)
    assert "Supabase connection refused" not in payload[:200], "fixture must exercise the cut"
    rendered = sch.humanize_job_result("Stripe Revenue Sync", payload)
    assert "Supabase connection refused after 3 retries" in rendered


# ── Codex round 2 on the turnkey pass, 2026-08-04 ─────────────────────────

@pytest.mark.parametrize("payload,why", [
    ('["ERROR: database unavailable"]', "JSON list payload"),
    ('{"result": {"error": "connection refused"}}', "nested error dict"),
    ('{"stage": {"stderr": "FAILED to bind port"}}', "nested stderr text"),
    ('{"rows": [{"id": 7, "error": "constraint violation"}]}', "explicit error inside an item"),
])
def test_failures_are_found_however_they_are_nested(payload, why):
    """Codex [high]: the first classifier returned False for any non-dict and
    only read top-level scalars, so these went from 'failure' under the old
    substring check to SILENCE. Turning a broken job into silence is worse than
    the false alarm it replaced."""
    assert sch._looks_like_failure(payload) is True, why


@pytest.mark.parametrize("subject", [
    "Your payment FAILED to process",
    "ERROR: action required",
])
def test_untrusted_item_text_still_does_not_escalate(subject):
    """The recursion must not undo the false-alarm fix: free text inside an
    item list is a stranger's wording, not our job status."""
    payload = json.dumps({"status": "checked", "unread_count": 1,
                          "emails": [{"from": "p@co.com", "subject": subject}]})
    assert sch._looks_like_failure(payload) is False, subject


def test_agent_metadata_cannot_break_delivery():
    """Codex [high]: only the body was escaped; the misroute marker
    interpolates a caller-supplied agent name into the prefix."""
    composed = f"System  ·  [for ops<&> — bridge not configured]\nbody\n\n9:00 AM"
    safe = nf._escape_html(composed)
    assert "<" not in safe and ">" not in safe
    assert "ops&lt;&amp;&gt;" in safe


def test_meaningful_zero_count_tick_is_not_suppressed():
    """Codex [medium]: counts can all be zero and the tick still matter."""
    assert sch._is_nothing_happened(json.dumps({
        "unread_count": 0, "status": "changed",
        "message": "OAuth token refreshed"})) is False
    assert sch._is_nothing_happened(json.dumps({
        "unread_count": 0, "warning": "credential expires in 3 days"})) is False
    # ...but a genuine no-op still is.
    assert sch._is_nothing_happened(json.dumps({
        "unread_count": 0, "status": "checked"})) is True


def test_job_name_containing_an_em_dash_is_stripped_correctly():
    """Codex [medium]: splitting on the first em dash corrupts the detail when
    the job name has one, and doubles the name when there is no separator."""
    job = "Sync — Stripe"
    payload = json.dumps({"status": "failed", "error": "connection refused"})
    rendered = sch.humanize_job_result(job, payload)
    headline = f"{job} — "
    detail = rendered[len(headline):] if rendered.startswith(headline) else rendered
    assert detail.startswith("failed") or "connection refused" in detail
    assert "Stripe" not in detail.split("\n")[0], "split landed inside the job name"
    assert not detail.startswith("— ")


def test_escaping_happens_exactly_once_in_the_fleet():
    """Self-review 2026-08-04. Three callers (cron_health_check, daily_brief,
    email_engine) each defended themselves with html.escape because notify()
    did not. Moving the escape to the chokepoint made those double-encode —
    CC would have seen a literal "&lt;module&gt;" in cron-failure alerts.
    Escaping is now the chokepoint's job alone; this test fails if a caller
    re-adds its own."""
    import re as _re
    offenders = []
    for rel in ("core/cron_health_check.py", "daily_brief.py",
                "integrations/email_engine.py", "funnel_nurture.py"):
        src = (SCRIPTS / rel).read_text(encoding="utf-8", errors="replace")
        # An escape call on a line, not inside a comment.
        for i, line in enumerate(src.splitlines(), 1):
            if _re.search(r"(?<!\w)(_?html)\.escape\(", line) and not line.lstrip().startswith("#"):
                offenders.append(f"{rel}:{i}")
    assert not offenders, (
        "these pre-escape and will double-encode through notify(): " + ", ".join(offenders))


def test_double_escaping_is_what_we_avoided():
    """Discrimination: prove the failure mode is real, not hypothetical."""
    import html as _h
    traceback_line = 'File "<module>", line 3 & failing'
    doubled = nf._escape_html(_h.escape(traceback_line, quote=False))
    assert "&amp;lt;module&amp;gt;" in doubled       # what CC would have seen
    single = nf._escape_html(traceback_line)
    assert single == 'File "&lt;module&gt;", line 3 &amp; failing'


def test_funnel_fallback_sends_plain_text():
    """The raw-HTTP safety net must not set parse_mode — it runs precisely when
    notify() (and its escaping) is unavailable."""
    src = (SCRIPTS / "funnel_nurture.py").read_text(encoding="utf-8", errors="replace")
    fallback = src.split("Fallback: original raw HTTP path", 1)[-1]
    code = [ln for ln in fallback.splitlines() if not ln.lstrip().startswith("#")]
    assert not any("parse_mode" in ln for ln in code), \
        "fallback would break on lead-typed '<'"


def test_retry_scheduling_uses_the_same_classifier_as_alerting():
    """Found by the 2026-08-04 live audit. There were TWO substring error checks
    in scheduler.py; the first pass only fixed the alerting one. The other drives
    fail_count, the 5-minute retry, and the give-up-after-5 logic — so an email
    whose SUBJECT said "FAILED" made a healthy sweep burn its retry budget and
    corrupt its own failure counter. Both must use one classifier."""
    import inspect
    src = inspect.getsource(sch.check_and_run_due_jobs)
    assert 'result_is_error = _looks_like_failure(' in src
    # No bare substring classification anywhere in the scheduling loop.
    offenders = [ln.strip() for ln in src.splitlines()
                 if ('"ERROR" in' in ln or '"FAILED" in' in ln)
                 and not ln.lstrip().startswith("#")]
    assert not offenders, f"substring error-classification still live: {offenders}"


@pytest.mark.parametrize("payload,why", [
    ('{"results":[{"status":"FAILED"}]}', "nested status inside an item list"),
    ('{"rows":[{"ok":false}]}', "ok=false inside an item list"),
    ('{"items":[{"success":false}]}', "success=false inside an item list"),
    ('{"report":[{"stage":{"status":"error"}}]}', "status nested two deep"),
])
def test_structured_failure_indicators_count_even_inside_item_lists(payload, why):
    """Codex [high], 2026-08-04. The `trusted` flag correctly suppresses the
    free-text substring heuristic inside item lists (a stranger's email subject
    is not our job status) — but I also suppressed the STRUCTURED indicators,
    which ARE our schema wherever they appear. {"results":[{"status":"FAILED"}]}
    was caught by the old substring check and silently stopped being caught, so
    a genuinely failing job stopped retrying and reset its own fail_count.

    This is behavioural, not a source-string grep — the earlier test could not
    have caught it."""
    assert sch._looks_like_failure(payload) is True, why


def test_untrusted_free_text_still_does_not_escalate_after_that_fix():
    """The counterpart: restoring structured detection must not resurrect the
    false alarm. A subject line is still not a job status."""
    payload = json.dumps({"status": "checked", "unread_count": 1, "emails": [
        {"from": "p@co.com", "subject": "Your payment FAILED to process"}]})
    assert sch._looks_like_failure(payload) is False


def test_booleans_are_not_rendered_as_counts():
    """bool is a subclass of int — {"sent": True} must not render "True sent"."""
    out = sch.humanize_job_result("Some Job", json.dumps({"sent": True, "status": "done"}))
    assert "True sent" not in out
