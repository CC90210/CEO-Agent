#!/usr/bin/env python
"""Audit tenant-scoped Supabase tables for basic RLS coverage.

Checks every public table with a tenant_id column and fails if row level
security is disabled or the table has zero policies. This is intentionally
read-only; it uses the same Supabase Management API helper as apply_migration.py
so it can inspect pg_catalog without requiring a raw database password.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from apply_migration import extract_project_ref, load_env, run_query_via_management_api  # noqa: E402


PROJECT_URL_KEYS = {
    "bravo": "BRAVO_SUPABASE_URL",
    "oasis": "OASIS_SUPABASE_URL",
    "nostalgic": "NOSTALGIC_SUPABASE_URL",
}

RLS_AUDIT_SQL = """
with tenant_tables as (
  select
    c.oid,
    n.nspname as schema_name,
    c.relname as table_name,
    c.relrowsecurity as rls_enabled
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  join information_schema.columns col
    on col.table_schema = n.nspname
   and col.table_name = c.relname
   and col.column_name = 'tenant_id'
  where n.nspname = 'public'
    and c.relkind in ('r', 'p')
)
select
  schema_name,
  table_name,
  rls_enabled,
  count(p.polname)::int as policy_count,
  coalesce(
    array_agg(p.polname order by p.polname) filter (where p.polname is not null),
    '{}'::name[]
  ) as policies
from tenant_tables t
left join pg_policy p on p.polrelid = t.oid
group by schema_name, table_name, rls_enabled
order by table_name;
"""


def load_rows(project: str) -> list[dict[str, Any]]:
    env = load_env()
    url_key = PROJECT_URL_KEYS[project]
    url = env.get(url_key)
    if not url:
        raise RuntimeError(f"Missing {url_key} in .env.agents")
    ref = extract_project_ref(url)
    ok, body = run_query_via_management_api(
        env.get("SUPABASE_ACCESS_TOKEN", ""),
        ref,
        RLS_AUDIT_SQL,
    )
    if not ok:
        raise RuntimeError(body)
    parsed = json.loads(body)
    if not isinstance(parsed, list):
        raise RuntimeError(f"Unexpected Management API response: {parsed!r}")
    return [row for row in parsed if isinstance(row, dict)]


def find_gaps(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for row in rows:
        policy_count = int(row.get("policy_count") or 0)
        if not row.get("rls_enabled") or policy_count <= 0:
            gaps.append(row)
    return gaps


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit tenant_id tables for RLS + policies")
    parser.add_argument("--project", choices=sorted(PROJECT_URL_KEYS), default="bravo")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    try:
      rows = load_rows(args.project)
    except Exception as exc:  # noqa: BLE001
      if args.json:
          print(json.dumps({"ok": False, "error": str(exc)}))
      else:
          print(f"RLS audit failed: {exc}", file=sys.stderr)
      return 2

    gaps = find_gaps(rows)
    payload = {
        "ok": not gaps,
        "project": args.project,
        "checked": len(rows),
        "gaps": gaps,
    }
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(f"Checked {len(rows)} tenant-scoped tables in {args.project}.")
        if gaps:
            print("RLS gaps:")
            for gap in gaps:
                state = "RLS off" if not gap.get("rls_enabled") else "no policies"
                print(f"  - {gap.get('schema_name')}.{gap.get('table_name')}: {state}")
        else:
            print("All tenant-scoped tables have RLS enabled and at least one policy.")
    return 1 if gaps else 0


if __name__ == "__main__":
    raise SystemExit(main())
