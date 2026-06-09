-- 100_schema_migrations_ledger.sql
-- Audit Phase 4 (2026-06-09): a per-file applied ledger so no migration is ever
-- blindly re-run. 88 historical migrations had duplicate numeric prefixes
-- (030/031/037/057) and NO record of what was applied — one re-run of a
-- non-idempotent backfill could corrupt live data. This ledger fixes that:
-- scripts/apply_migration.py checks it before applying and records after.
--
-- Idempotent: safe to run repeatedly (create table if not exists; policy guarded).
-- RLS posture matches the internal-table convention (see 094_email_suppressions.sql):
-- service_role full access, no anon/authenticated policy. This is an ops table,
-- not tenant-scoped — only the migration runner (service role) touches it.

create table if not exists public.schema_migrations (
    filename    text primary key,
    sha256      text not null,
    applied_at  timestamptz not null default now(),
    applied_by  text
);

alter table public.schema_migrations enable row level security;

-- Guarded CREATE POLICY (Postgres has no CREATE POLICY IF NOT EXISTS, and this
-- repo's apply_migration.py blocks DROP POLICY). The DO block makes re-runs safe.
do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'schema_migrations'
          and policyname = 'schema_migrations_service_all'
    ) then
        create policy schema_migrations_service_all
            on public.schema_migrations
            for all to service_role
            using (true) with check (true);
    end if;
end $$;

comment on table public.schema_migrations is
    'Per-file migration ledger (audit Phase 4, 2026-06-09). filename = database/<name>.sql, '
    'sha256 = content hash at apply time. apply_migration.py warns + requires --force if a '
    'filename re-applies with a changed checksum. Ordering is lexicographic by filename; '
    'duplicate numeric prefixes (030/031/037/057) are historical and harmless under that order.';
