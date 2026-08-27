-- bravo__014 — pin a cron job to one machine, so two machines cannot both run it.
--
-- WHY NOW
-- -------
-- `cron_jobs` is a SHARED Turso registry and carries 38 seeded jobs. Nothing in
-- it records WHICH machine is responsible for a job. That was harmless while CC's
-- Windows box was the only seeder — brain/CROSS_MACHINE_SYNC.md handles CC's own
-- Windows+Mac pair by the blunt rule "only Windows runs daemons".
--
-- It stops being harmless the moment APEX's machine seeds the same registry.
-- `cron_engine.py seed` is idempotent by NAME, so Adon seeding would not create
-- duplicate rows — but both engines would then poll the same rows and both would
-- fire them. For a digest that means two digests; for anything in the send path
-- it means the recipient gets it twice. Double-sending is not recoverable by
-- retry logic, so this lands BEFORE Adon's machine is wired, not after.
--
-- SEMANTICS — deliberately backwards-compatible
-- ---------------------------------------------
--   owner_machine IS NULL   -> unpinned; any engine may run it (every existing
--                              row, so today's behaviour is preserved exactly)
--   owner_machine = 'CCPC'  -> only the engine on that hostname runs it; every
--                              other engine skips it and says so
--
-- Nullable ON PURPOSE. A NOT NULL column would need a DEFAULT on a populated
-- table (see reference_sqlite_alter_add_notnull_check), and picking a default
-- hostname would silently pin 38 existing jobs to whichever machine happened to
-- apply the migration.

ALTER TABLE "cron_jobs" ADD COLUMN "owner_machine" TEXT;

CREATE INDEX IF NOT EXISTS idx_cron_jobs_owner_machine
  ON "cron_jobs"(owner_machine, is_active);
