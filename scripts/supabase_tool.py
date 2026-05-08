"""
Supabase SDK Integration — Universal Agent Tool
Replaces the broken Supabase MCP server with direct Python SDK access.
All credentials loaded from .env.agents (never hardcoded).

Usage (from any agent via terminal):
  python scripts/supabase_tool.py list-tables [--project bravo|oasis|nostalgic]
  python scripts/supabase_tool.py query "SELECT * FROM agent_state LIMIT 5" [--project bravo]
  python scripts/supabase_tool.py insert <table> '{"key": "value"}' [--project bravo]
  python scripts/supabase_tool.py update <table> '{"key": "value"}' --match '{"id": "123"}' [--project bravo]
  python scripts/supabase_tool.py delete <table> --match '{"id": "123"}' [--project bravo]
  python scripts/supabase_tool.py rpc <function_name> '{"arg": "value"}' [--project bravo]
  python scripts/supabase_tool.py list-projects
"""

import argparse
import json
import os
import sys
from pathlib import Path

def load_env():
    """Load .env.agents from project root."""
    env_path = Path(__file__).resolve().parent.parent / ".env.agents"
    if not env_path.exists():
        print(f"ERROR: {env_path} not found", file=sys.stderr)
        sys.exit(1)
    
    env_vars = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars

# Project configuration mapping
PROJECTS = {
    "bravo": {
        "url_key": "BRAVO_SUPABASE_URL",
        "key_key": "BRAVO_SUPABASE_SERVICE_ROLE_KEY",
        "description": "Bravo — Agent intelligence database"
    },
    "oasis": {
        "url_key": "OASIS_SUPABASE_URL",
        "key_key": "OASIS_SUPABASE_SERVICE_ROLE_KEY",
        "description": "OASIS AI Platform"
    },
    "nostalgic": {
        "url_key": "NOSTALGIC_SUPABASE_URL",
        "key_key": "NOSTALGIC_SUPABASE_SERVICE_ROLE_KEY",
        "description": "Nostalgic Requests"
    }
}

_PINGED_SUPABASE = False


def _ping_supabase_health(client, project: str, ok: bool) -> None:
    """Bump integrations_health for the supabase service. Once-per-process.

    Pass the live `client` so integration_health doesn't have to construct
    its own from os.environ — supabase_tool.load_env() returns a dict
    without pushing values to os.environ, so ping() would fail to find
    BRAVO_SUPABASE_URL otherwise.
    """
    global _PINGED_SUPABASE
    if _PINGED_SUPABASE and ok:
        return
    try:
        from integration_health import ping  # type: ignore
        ok_call = ping(
            f"supabase_{project}" if project != "bravo" else "supabase",
            status="healthy" if ok else "degraded",
            client=client,
        )
        if ok and ok_call:
            _PINGED_SUPABASE = True
    except Exception:
        pass


def get_client(env_vars, project="bravo"):
    """Create a Supabase client for the specified project."""
    from supabase import create_client

    config = PROJECTS.get(project)
    if not config:
        print(f"ERROR: Unknown project '{project}'. Options: {list(PROJECTS.keys())}", file=sys.stderr)
        sys.exit(1)

    url = env_vars.get(config["url_key"])
    key = env_vars.get(config["key_key"])

    if not url or not key:
        print(f"ERROR: Missing credentials for project '{project}' in .env.agents", file=sys.stderr)
        print(f"  Need: {config['url_key']} and {config['key_key']}", file=sys.stderr)
        sys.exit(1)

    client = create_client(url, key)
    # Best-effort health ping — flips /integrations green when this CLI
    # successfully connects. Silent on failure. Pass client so the ping
    # helper doesn't try to construct one from os.environ (load_env
    # returns a dict but doesn't push to os.environ).
    _ping_supabase_health(client, project, ok=True)
    return client


def cmd_list_tables(client, args):
    """List all tables in the project's public schema."""
    import requests as req
    
    # Method 1: Use the Supabase REST API directly — the OpenAPI spec lists all tables
    try:
        # Get the Supabase URL from the client
        url = client.supabase_url if hasattr(client, 'supabase_url') else client._client.base_url
        key = client.supabase_key if hasattr(client, 'supabase_key') else None
        
        # Try the REST root which returns OpenAPI schema with all table paths
        resp = req.get(
            f"{url}/rest/v1/",
            headers={"apikey": key or "", "Authorization": f"Bearer {key or ''}"},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            if "paths" in data:
                tables = [path.strip("/") for path in data["paths"].keys() if path != "/"]
                if tables:
                    print(f"Found {len(tables)} tables in public schema:")
                    for t in sorted(tables):
                        print(f"  - {t}")
                    return
    except Exception:
        pass
    
    # Method 2: Try RPC function if user has created one
    try:
        result = client.rpc("get_tables", {}).execute()
        if result.data:
            tables = [row.get("table_name", row) if isinstance(row, dict) else row for row in result.data]
            print(f"Found {len(tables)} tables:")
            for t in sorted(tables):
                print(f"  - {t}")
            return
    except Exception:
        pass
    
    # Method 3: Try common table names
    common_tables = ["users", "profiles", "agent_state", "session_logs", "tasks", "customers", "orders"]
    found = []
    for table in common_tables:
        try:
            result = client.table(table).select("*", count="exact").limit(0).execute()
            found.append(f"{table} ({result.count or '?'} rows)")
        except Exception:
            pass
    
    if found:
        print(f"Found {len(found)} tables (via probing):")
        for t in found:
            print(f"  - {t}")
    else:
        print("NOTE: Could not discover tables. Create this SQL function in Supabase to enable:")
        print("""
  CREATE OR REPLACE FUNCTION get_tables()
  RETURNS TABLE(table_name text) AS $$
    SELECT tablename::text FROM pg_tables WHERE schemaname = 'public';
  $$ LANGUAGE sql SECURITY DEFINER;
        """)


def cmd_query(client, args):
    """Execute a raw SQL query via RPC."""
    sql = args.sql
    
    # Try using a query_sql RPC function first
    try:
        result = client.rpc("query_sql", {"sql_query": sql}).execute()
        print(json.dumps(result.data, indent=2))
        return
    except Exception:
        pass
    
    # If no RPC function, try fetching from a table directly
    # Parse simple SELECT statements
    if sql.strip().upper().startswith("SELECT"):
        # Try to extract table name for simple queries
        import re
        match = re.search(r'FROM\s+(\w+)', sql, re.IGNORECASE)
        if match:
            table = match.group(1)
            try:
                # Try a simple select with limit
                limit_match = re.search(r'LIMIT\s+(\d+)', sql, re.IGNORECASE)
                limit = int(limit_match.group(1)) if limit_match else 100
                
                result = client.table(table).select("*").limit(limit).execute()
                print(json.dumps(result.data, indent=2, default=str))
                return
            except Exception as e:
                print(f"PostgREST query failed: {e}", file=sys.stderr)
    
    print("NOTE: Raw SQL requires an RPC function. Create one in Supabase:")
    print("""
  CREATE OR REPLACE FUNCTION query_sql(sql_query text)
  RETURNS json AS $$
  DECLARE result json;
  BEGIN
    EXECUTE sql_query INTO result;
    RETURN result;
  END;
  $$ LANGUAGE plpgsql SECURITY DEFINER;
    """)
    print(f"\nFor simple queries, try table operations directly:")
    print(f"  python scripts/supabase_tool.py select <table_name> [--limit 10]")


def cmd_select(client, args):
    """Select rows from a table."""
    query = client.table(args.table).select(args.columns or "*")
    
    if args.eq:
        filters = json.loads(args.eq)
        for k, v in filters.items():
            query = query.eq(k, v)
    
    if args.limit:
        query = query.limit(args.limit)
    
    if args.order:
        query = query.order(args.order, desc=args.desc)
    
    result = query.execute()
    print(json.dumps(result.data, indent=2, default=str))
    print(f"\n--- {len(result.data)} rows returned ---")


def _preview_match(client, table: str, match_filter: dict, limit: int = 10):
    """For update/delete dry-run: read the rows that match the filter and print them."""
    try:
        q = client.table(table).select("*")
        for k, v in match_filter.items():
            q = q.eq(k, v)
        rows = q.limit(limit).execute().data
    except Exception as exc:
        print(f"[dry-run] match preview failed: {exc}")
        return
    print(f"[dry-run] {len(rows)} row(s) match the filter (showing up to {limit}):")
    print(json.dumps(rows, indent=2, default=str))


def cmd_insert(client, args):
    """Insert a row into a table."""
    data = json.loads(args.data)
    if getattr(args, "dry_run", False):
        print(f"[dry-run] INSERT NOT executed. Would insert into '{args.table}':")
        print(json.dumps(data, indent=2, default=str))
        print("\nRe-run without --dry-run to apply.")
        return
    result = client.table(args.table).insert(data).execute()
    print(json.dumps(result.data, indent=2, default=str))
    print(f"\n--- Inserted {len(result.data)} row(s) ---")


def cmd_update(client, args):
    """Update rows in a table."""
    data = json.loads(args.data)
    match_filter = json.loads(args.match)

    if getattr(args, "dry_run", False):
        print(f"[dry-run] UPDATE NOT executed. Would set on '{args.table}':")
        print(json.dumps(data, indent=2, default=str))
        print(f"\nMatching: {json.dumps(match_filter, default=str)}")
        _preview_match(client, args.table, match_filter)
        print("\nRe-run without --dry-run to apply.")
        return

    query = client.table(args.table).update(data)
    for k, v in match_filter.items():
        query = query.eq(k, v)

    result = query.execute()
    print(json.dumps(result.data, indent=2, default=str))
    print(f"\n--- Updated {len(result.data)} row(s) ---")


def cmd_delete(client, args):
    """Delete rows from a table."""
    match_filter = json.loads(args.match)

    if getattr(args, "dry_run", False):
        print(f"[dry-run] DELETE NOT executed on '{args.table}'.")
        print(f"Matching: {json.dumps(match_filter, default=str)}")
        _preview_match(client, args.table, match_filter)
        print("\nRe-run without --dry-run to apply.")
        return

    query = client.table(args.table).delete()
    for k, v in match_filter.items():
        query = query.eq(k, v)

    result = query.execute()
    print(json.dumps(result.data, indent=2, default=str))
    print(f"\n--- Deleted {len(result.data)} row(s) ---")


def cmd_upsert(client, args):
    """Upsert (insert or update) a row into a table."""
    data = json.loads(args.data)
    if getattr(args, "dry_run", False):
        print(f"[dry-run] UPSERT NOT executed. Would upsert into '{args.table}':")
        print(json.dumps(data, indent=2, default=str))
        print("\nRe-run without --dry-run to apply.")
        return
    result = client.table(args.table).upsert(data).execute()
    print(json.dumps(result.data, indent=2, default=str))
    print(f"\n--- Upserted {len(result.data)} row(s) ---")


def cmd_rpc(client, args):
    """Call a Supabase Edge Function / database RPC."""
    params = json.loads(args.params) if args.params else {}
    result = client.rpc(args.function_name, params).execute()
    print(json.dumps(result.data, indent=2, default=str))


def cmd_list_projects(env_vars, args):
    """List all configured Supabase projects."""
    print("Configured Supabase Projects:\n")
    for name, config in PROJECTS.items():
        url = env_vars.get(config["url_key"], "NOT SET")
        has_key = "✅" if env_vars.get(config["key_key"]) else "❌"
        print(f"  [{name}] {config['description']}")
        print(f"    URL: {url}")
        print(f"    Service Role Key: {has_key}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Supabase SDK Tool — Universal agent database access",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list-projects
  %(prog)s select agent_state --limit 5
  %(prog)s select agent_state --eq '{"agent_name": "bravo"}'
  %(prog)s insert session_logs '{"session_id": "s1", "summary": "test"}'
  %(prog)s update agent_state '{"status": "active"}' --match '{"id": "1"}'
  %(prog)s delete session_logs --match '{"session_id": "s1"}'
  %(prog)s upsert agent_state '{"id": "1", "status": "idle"}'
  %(prog)s rpc get_tables
  %(prog)s query "SELECT * FROM agent_state"
  %(prog)s list-tables
  %(prog)s select users --project oasis --limit 10
        """
    )
    
    # Parent parser for shared --project flag
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("--project", "-p", default="bravo", choices=list(PROJECTS.keys()),
                               help="Supabase project to use (default: bravo)")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # list-projects
    subparsers.add_parser("list-projects", help="List configured Supabase projects")
    
    # list-tables
    subparsers.add_parser("list-tables", parents=[parent_parser], help="List tables in public schema")
    
    # query
    p_query = subparsers.add_parser("query", parents=[parent_parser], help="Execute SQL query (requires RPC function)")
    p_query.add_argument("sql", help="SQL query string")
    
    # select
    p_select = subparsers.add_parser("select", parents=[parent_parser], help="Select rows from a table")
    p_select.add_argument("table", help="Table name")
    p_select.add_argument("--columns", "-c", default="*", help="Columns to select (default: *)")
    p_select.add_argument("--eq", help="Equality filter as JSON: '{\"col\": \"val\"}'")
    p_select.add_argument("--limit", "-l", type=int, default=100, help="Row limit (default: 100)")
    p_select.add_argument("--order", "-o", help="Column to order by")
    p_select.add_argument("--desc", action="store_true", help="Order descending")
    
    # insert
    p_insert = subparsers.add_parser("insert", parents=[parent_parser], help="Insert a row")
    p_insert.add_argument("table", help="Table name")
    p_insert.add_argument("data", help="JSON data to insert")
    p_insert.add_argument("--dry-run", action="store_true",
                          help="Print the would-be insert without executing it")
    
    # update
    p_update = subparsers.add_parser("update", parents=[parent_parser], help="Update rows")
    p_update.add_argument("table", help="Table name")
    p_update.add_argument("data", help="JSON data to set")
    p_update.add_argument("--match", required=True, help="Match filter as JSON")
    p_update.add_argument("--dry-run", action="store_true",
                          help="Print matching rows + intended set without applying")
    
    # delete
    p_delete = subparsers.add_parser("delete", parents=[parent_parser], help="Delete rows")
    p_delete.add_argument("table", help="Table name")
    p_delete.add_argument("--match", required=True, help="Match filter as JSON")
    p_delete.add_argument("--dry-run", action="store_true",
                          help="Print matching rows that would be deleted without deleting")
    
    # upsert
    p_upsert = subparsers.add_parser("upsert", parents=[parent_parser], help="Upsert a row")
    p_upsert.add_argument("table", help="Table name")
    p_upsert.add_argument("data", help="JSON data to upsert")
    p_upsert.add_argument("--dry-run", action="store_true",
                          help="Print the would-be upsert without executing it")
    
    # rpc
    p_rpc = subparsers.add_parser("rpc", parents=[parent_parser], help="Call an RPC/Edge Function")
    p_rpc.add_argument("function_name", help="Function name")
    p_rpc.add_argument("params", nargs="?", default="{}", help="JSON parameters")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    env_vars = load_env()
    
    if args.command == "list-projects":
        cmd_list_projects(env_vars, args)
        return
    
    client = get_client(env_vars, args.project)
    
    commands = {
        "list-tables": cmd_list_tables,
        "query": cmd_query,
        "select": cmd_select,
        "insert": cmd_insert,
        "update": cmd_update,
        "delete": cmd_delete,
        "upsert": cmd_upsert,
        "rpc": cmd_rpc,
    }
    
    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(client, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
