---
tags: [root]
last_updated: 2026-06-09
---

# Database Migration Notes

Audit-compatible explanation of the two non-monotonic items in `database/`.
Captured 2026-05-21 during the empire-wide cleanup pass.

## Numbering gaps

Three slots are deliberately unused: `047`, `035`, `048`.

- **047:** Reserved for a sequence-state extension that ended up folded
  back into 046 during review.
- **035 + 048:** Originally created the `exec_overrides` table and added
  a workspace_label column. Both files were deleted 2026-05-22 along
  with the entire override-approval feature (CC's call — see
  `scripts/state/exec_guard.py` comment). The table was also dropped
  in Supabase. Subsequent migrations have not been renumbered;
  production tracks applied migrations by filename.

**If you need a gap slot:** write `XXX_<descriptive_name>.sql` as a
new migration and apply it forward. Don't backfill.

## Duplicate prefixes at 030 and 031

Two pairs of migrations share a numeric prefix:

| Prefix | Files | Notes |
|---|---|---|
| `030` | `030_bridge_pairings_unique_fingerprint.sql`, `030_outbound_no_active_autocreate.sql` | Both applied to production. Different domains (pairings UNIQUE constraint vs. outbound-table autocreate guard). |
| `031` | `031_onboarding_completed.sql`, `031_pair_attempts_rate_limit.sql` | Both applied. Different domains (onboarding state vs. rate-limit table). |

**Why they exist:** Two parallel feature branches landed migrations that picked the next number from `git log -- database/` at roughly the same time. Both were applied in production via filename order (alphabetical within prefix, which gave a deterministic ordering).

**Why we don't renumber:** Same reason as the 047 gap — production tracks migrations by exact filename. Renaming applied SQL breaks the tracker.

**Going forward:** When picking the next prefix, run `ls database/*.sql | sort -t_ -k1 -n | tail -1` to see the actual last one applied, not just `git status`. The next slot is the value after that, **not** 047.

## Applied ledger — `100_schema_migrations_ledger.sql` (audit Phase 4, 2026-06-09)

The "production tracks by filename" claim above used to be a convention with **no
enforcement**. It's now a real table: `public.schema_migrations` (`filename` PK +
`sha256` + `applied_at` + `applied_by`). `scripts/apply_migration.py`:

- **Before apply:** if the filename is in the ledger with a *different* checksum,
  it refuses unless `--force` (stops a silent re-run of a changed, possibly
  non-idempotent, backfill — there are ~12 such backfills in `database/`).
- **After apply:** upserts the `(filename, sha256)` row.
- **`--status`:** diffs `database/*.sql` vs ledger → applied vs pending.
- **`--backfill-ledger`:** marks every on-disk migration applied
  (`applied_by='mission-remediation-backfill'`). Run ONCE, only when prod is
  confirmed current.

**Full duplicate-prefix set (superset of the 030/031 noted above):** `030`, `031`,
`037`, `057` each appear twice. All historical, all applied, **never renumber** —
the ledger keys on exact filename, so a rename = a re-apply.

**Ordering rule:** lexicographic by filename. New migrations start at the next free
integer **≥ 101** (the ledger is `100`).

### Seeding the ledger on production (one-time, operator)

Only after confirming prod has every migration applied:

```bash
python scripts/apply_migration.py database/100_schema_migrations_ledger.sql --allow-rls
python scripts/apply_migration.py --backfill-ledger
python scripts/apply_migration.py --status      # expect: 89 applied, 0 pending
```

## Cross-references

- [[infra/README]] — deployment-side migration application steps
- [[brain/CAPABILITIES]] — Supabase tooling registry
