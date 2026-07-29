-- 105_cron_jobs_fail_count.sql
-- 2026-07-29 — add the fail_count column scheduler.py has been writing to since
-- 2026-04-11 against a column that never existed.
--
-- WHAT WAS BROKEN
-- scheduler.py check_and_run_due_jobs() maintains a consecutive-failure counter
-- to (a) retry a failed job in 5 minutes instead of waiting for its next slot,
-- and (b) give up after 5 attempts. It writes that counter with:
--
--     try:    update({**payload, "fail_count": fail_count})
--     except: update(payload)          # "column doesn't exist yet" fallback
--
-- The column genuinely did not exist, so EVERY write took the fallback and
-- fail_count was never persisted. On the next tick the code re-read
-- job.get("fail_count") -> None -> 0, so:
--   * every failure logged "attempt 1/5" forever — the give-up branch was
--     unreachable, and a broken job retried every 5 minutes indefinitely
--     (Inbound Email Sweep reached run_count 1410 this way);
--   * no repeat-failure alerting was possible, because nothing could observe
--     that a job had failed twice in a row.
--
-- Verified live 2026-07-29 via PostgREST:
--   {'message': 'column cron_jobs.fail_count does not exist', 'code': '42703'}
--
-- Safe to re-run. NOT NULL DEFAULT 0 so existing rows backfill to a clean state
-- and the scheduler's `(job.get("fail_count") or 0)` read keeps working.

ALTER TABLE public.cron_jobs
    ADD COLUMN IF NOT EXISTS fail_count integer NOT NULL DEFAULT 0;

COMMENT ON COLUMN public.cron_jobs.fail_count IS
    'Consecutive failed runs. Incremented by scheduler.py on an ERROR/FAILED '
    'result, reset to 0 on success or after the retry budget is exhausted. '
    'Drives 5-minute retry backoff and the repeat-failure Telegram escalation.';

-- Partial index: the escalation path only ever asks "which jobs are currently
-- failing?", which is a tiny slice of the table.
CREATE INDEX IF NOT EXISTS cron_jobs_failing_idx
    ON public.cron_jobs (fail_count)
    WHERE fail_count > 0;
