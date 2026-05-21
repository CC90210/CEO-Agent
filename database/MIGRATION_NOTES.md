# Database Migration Notes

Audit-compatible explanation of the two non-monotonic items in `database/`.
Captured 2026-05-21 during the empire-wide cleanup pass.

## Numbering gap at 047

There is no `database/047_*.sql`. The numbers jump from `046_sequence_state_atomic_claim.sql` straight to `048_exec_overrides_workspace_label.sql`.

**Why:** Slot 047 was reserved for a sequence-state extension that ended up folded back into 046 during review. The gap is intentional — do NOT renumber subsequent migrations to close it. Production tracks applied migrations by filename, and renaming applied migrations breaks the tracking table.

**If you need slot 047:** write `047_<descriptive_name>.sql` as a new migration and apply it forward. Don't backfill.

## Duplicate prefixes at 030 and 031

Two pairs of migrations share a numeric prefix:

| Prefix | Files | Notes |
|---|---|---|
| `030` | `030_bridge_pairings_unique_fingerprint.sql`, `030_outbound_no_active_autocreate.sql` | Both applied to production. Different domains (pairings UNIQUE constraint vs. outbound-table autocreate guard). |
| `031` | `031_onboarding_completed.sql`, `031_pair_attempts_rate_limit.sql` | Both applied. Different domains (onboarding state vs. rate-limit table). |

**Why they exist:** Two parallel feature branches landed migrations that picked the next number from `git log -- database/` at roughly the same time. Both were applied in production via filename order (alphabetical within prefix, which gave a deterministic ordering).

**Why we don't renumber:** Same reason as the 047 gap — production tracks migrations by exact filename. Renaming applied SQL breaks the tracker.

**Going forward:** When picking the next prefix, run `ls database/*.sql | sort -t_ -k1 -n | tail -1` to see the actual last one applied, not just `git status`. The next slot is the value after that, **not** 047.

## Cross-references

- [[infra/README]] — deployment-side migration application steps
- [[brain/CAPABILITIES]] — Supabase tooling registry
