---
name: turso-patterns
description: Use when working on the Supabase → Turso (libSQL) migration — transpiling schema, porting RPCs/views, flipping an app's backend, or verifying a migrated database. Encodes the failures this migration actually hit.
tags: [turso, libsql, migration, database, sqlite, supabase]
triggers: [turso, libsql, turso migration, supabase to turso, transpile schema, port rpc, turso verify, sqlite migration]
---

# Turso / libSQL patterns

Five isolated Turso databases replace five Supabase projects: `bravo`, `breeze`,
`propflow`, `oasis`, `nostalgic`. **Supabase stays live and paid until the last
app is cut over** — every change must leave it working.

Related: [[skills/supabase-patterns/SKILL]] (still current — Supabase is not
retired), [[CONTEXT]], [[brain/APP_REGISTRY]].

## The one rule that would have prevented most of this

**Verify by EXECUTING, never by counting.** `--verify` used to compare the number
of emitted `CREATE TABLE` strings against the live table count, and reported PASS
while a `char_length()` inside a CHECK was killing an entire table at apply time.
Counting proves the transpiler produced text. Only execution proves the text is a
schema.

Corollary: `CREATE VIEW` does **not** resolve function names. A view calling
`GREATEST()` creates cleanly and explodes only when something SELECTs it — which
is how a broken `merchant_advance_summary` reached a live database. The verifier
now SELECTs from every view.

```bash
python scripts/core/turso_schema_transpiler.py --project <p> --verify   # applies + selects
python scripts/apply_turso_migration.py --test-mode                      # 1 db PER project
```

`--test-mode` gets one throwaway db per project on purpose. Sharing one let
bravo's `profiles` satisfy `IF NOT EXISTS` for oasis' and propflow's
differently-shaped `profiles` — false failures, and worse, a table that genuinely
failed to create could be masked by another project's same-named table.

## Object classes that are easy to miss entirely

Tables and indexes are the obvious ones. These were each missed once:

| Class | What went wrong | Status |
|---|---|---|
| **UNIQUE indexes** | 20 dropped as "non-portable" — they are integrity CONSTRAINTS, and SQLite has expression (3.9+) and partial (3.8+) indexes | fixed + restored |
| **CHECK constraints** | all 226 dropped, incl. breeze money guards. SQLite enforces them natively, but they must be inside `CREATE TABLE` — there is no `ADD CONSTRAINT` | fixed |
| **VIEWS** | all 9 never introspected. On flipped apps every SELECT returned "no such table" | 8 ported, `merchant_summary` open |
| **GENERATED columns** | 2 emitted as plain writable columns. `draws.net_deposit_cents` is merchant money and no app code writes it | fixed + tables rebuilt |
| **SERIAL defaults** | `nextval()` dropped — harmless, because `"id" INTEGER PRIMARY KEY` IS SQLite's auto-assigning rowid alias | verified benign |
| **Triggers** | 123 not transpiled; 3 are security-shaped | OPEN — DAL's job |

Re-run the census when touching the transpiler: `relkind` counts plus generated /
identity / serial / domains / composite types / partitioned / exclusion
constraints / extensions / cross-schema FK targets.

## Expression translation

Never strip Postgres casts with a character class that matches spaces.
`::[a-z_ ]+` ran straight through the next keyword:

```
"entry_type = 'commission'::text AND c.status <> 'voided'"
   ->  "'commission'.status <> 'voided'"        -- the AND-guard silently DELETED
```

In `iso_clawback_candidates` that guard is what excludes voided commissions from
clawback. It failed loudly here; the same bug producing *valid* SQL is a silent
money bug. Use the explicit type alternation (`_PG_CAST`).

| Postgres | libSQL | note |
|---|---|---|
| `char_length(x)` | `length(x)` | inside a CHECK, the bad form kills the whole table |
| `GREATEST/LEAST` | `max(a,b)` / `min(a,b)` | multi-arg forms; fails at SELECT, not CREATE |
| `x ~~ y` / `!~~` | `LIKE` / `NOT LIKE` | `~` (regex) has no equivalent — reject |
| `EXTRACT(epoch FROM ts)` | `unixepoch(ts,'subsec')` | NOT julianday arithmetic — it is a double and lands ~11µs off, which matters when the column is a sort key |
| `EXTRACT(epoch FROM a - b)` | `(julianday(a)-julianday(b))*86400.0` | difference, fine as a double |
| `EXTRACT(day FROM now()-x)` | `CAST((julianday('now')-julianday(x)) AS INTEGER)` | both truncate toward zero |
| `ts + make_interval(days=>n)` | `datetime(ts,'+'\|\|n\|\|' days')` | |
| `= ANY(ARRAY[...])` | `IN (...)` | rewrite BEFORE stripping casts |
| `NULLS FIRST/LAST` | strip | SQLite rejects it in index defs |
| `NULLS NOT DISTINCT` (PG15) | COALESCE keys to a sentinel | SQLite treats NULLs as distinct, so duplicate suppression rows slip through |
| `DISTINCT ON` | — | no equivalent; reject and report |

libSQL is SQLite 3.45: `FILTER (WHERE ...)`, window functions and `->>`/`->` all
work verbatim. Do not "port" them.

When rejecting, record it (`lossy.VIEWS_LOST`, `UNIQUE_CONSTRAINTS_LOST`,
`GENERATED_COLUMNS_LOST`) — silent loss is the failure mode.

## Verifying a migration

Row counts are not correctness. Compare VALUES, as a **multiset** — Postgres
orders NULLs last on ASC and SQLite orders them first, so a positional compare
reports ordering as corruption. Normalize the documented mappings first
(bool→INTEGER, jsonb→TEXT, timestamptz→ISO-8601 with `T`) or real findings drown
in noise.

When a diff appears, prove which kind it is before reporting:
- **ETL lag** — the differing ids are absent from the Turso base table entirely
  (Supabase is still the live write target for anything not yet flipped)
- **Semantic** — the ids exist on both sides and the view disagrees

## Flipping an app

**THREE flags, not one.** `EMPIRE_DATA_BACKEND=turso_cloud` switches only the
server data plane. Auth and the `/api/data/bridge` + `/api/data/rpc` routes gate
on `EMPIRE_AUTH_BACKEND=turso` **and** `AUTH_SESSION_SECRET`, and 404 without
them. Setting one gives Turso data with Supabase auth and no browser bridge.

Push credentials with `python scripts/integrations/vercel_turso_sync.py --project
<slug> --db <key>` — if a project already carries a `TURSO_DATABASE_URL` this
tool never wrote, its provenance is unknown and it may point at the wrong
database. Pushing from here is what makes the target verifiable.

**Native bindings break client bundles.** `@supabase/supabase-js` is isomorphic,
so a client component transitively importing the service-role client bundled
without complaint. `@libsql/client` is native, so the same edge is a hard build
error. Turbopack traces BOTH sides of a `typeof window` branch, including
`await import(...)` — a runtime guard does not keep it out of the graph. Split
the module and mark the server half `import "server-only"`. Verify:

```bash
grep -rl "libsql\|hrana\|SERVICE_ROLE" .next/static/chunks/   # must be empty
```

**Do not probe a Vercel preview for API behavior.** Deployment protection answers
POSTs to API routes with an SSO challenge, so a 401 tells you nothing about your
code. Run the production build locally against the real database instead.

**Prove the tenant boundary before any flip** —
`realestate-App/scripts/verify_tenant_isolation.py`. RLS is gone; a route
enforces it now. Send the bridge's real wire shape (`{method, args}` plus
`action`) — a malformed request 400s and proves nothing.

## Rollback

Unset `EMPIRE_DATA_BACKEND` (and `EMPIRE_AUTH_BACKEND`) → the app is back on
Supabase immediately. That fallback is the reason Supabase must stay paid until
the last app is verified.
