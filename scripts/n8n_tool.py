"""
n8n CLI Tool — Full Workflow Management via REST API
Replaces the broken n8n MCP management tools with direct API access.
All credentials loaded from .env.agents (never hardcoded).

Usage (from any agent via terminal):
  python scripts/n8n_tool.py list                          # List all workflows
  python scripts/n8n_tool.py get <id>                      # Get workflow details
  python scripts/n8n_tool.py create <json_file_or_string>  # Create workflow from JSON
  python scripts/n8n_tool.py update <id> <json>            # Update workflow
  python scripts/n8n_tool.py activate <id>                 # Activate workflow
  python scripts/n8n_tool.py deactivate <id>               # Deactivate workflow
  python scripts/n8n_tool.py delete <id>                   # Delete workflow
  python scripts/n8n_tool.py execute <id> [--data '{}']    # Execute/test workflow
  python scripts/n8n_tool.py executions <id> [--limit 5]   # View execution history
  python scripts/n8n_tool.py export <id> [--output file]   # Export workflow JSON
  python scripts/n8n_tool.py import <json_file>            # Import workflow from file

Flags:
  --json    Output raw JSON for agent consumption
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode


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


class N8nClient:
    """n8n REST API client."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _request(self, method: str, path: str, data=None, params=None) -> dict:
        """Make authenticated API request."""
        url = f"{self.base_url}/api/v1{path}"
        if params:
            url += "?" + urlencode(params)

        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")

        req = Request(url, data=body, method=method)
        req.add_header("X-N8N-API-KEY", self.api_key)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        try:
            # Timeout is mandatory — without it a hung n8n instance can freeze
            # any cron job calling this tool indefinitely. 30s matches other
            # CLI tools in scripts/.
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            try:
                error_json = json.loads(error_body)
                msg = error_json.get("message", error_body)
            except json.JSONDecodeError:
                msg = error_body
            print(f"ERROR: n8n API {e.code}: {msg}", file=sys.stderr)
            sys.exit(1)
        except URLError as e:
            print(f"ERROR: Connection failed: {e.reason}", file=sys.stderr)
            sys.exit(1)

    # --- Workflow CRUD ---

    def list_workflows(self, limit=200, active_only=False):
        """List all workflows."""
        params = {"limit": limit}
        if active_only:
            params["active"] = "true"
        return self._request("GET", "/workflows", params=params)

    def get_workflow(self, workflow_id: str):
        """Get full workflow details including nodes and connections."""
        return self._request("GET", f"/workflows/{workflow_id}")

    def create_workflow(self, workflow_data: dict):
        """Create a new workflow."""
        return self._request("POST", "/workflows", data=workflow_data)

    def update_workflow(self, workflow_id: str, workflow_data: dict):
        """Update an existing workflow."""
        return self._request("PUT", f"/workflows/{workflow_id}", data=workflow_data)

    def delete_workflow(self, workflow_id: str):
        """Delete a workflow."""
        return self._request("DELETE", f"/workflows/{workflow_id}")

    def activate_workflow(self, workflow_id: str):
        """Activate a workflow."""
        return self._request("PATCH", f"/workflows/{workflow_id}", data={"active": True})

    def deactivate_workflow(self, workflow_id: str):
        """Deactivate a workflow."""
        return self._request("PATCH", f"/workflows/{workflow_id}", data={"active": False})

    # --- Execution ---

    def execute_workflow(self, workflow_id: str, data=None):
        """Execute a workflow (test run)."""
        payload = {}
        if data:
            payload = data
        # Use the webhook/test endpoint for execution
        return self._request("POST", f"/workflows/{workflow_id}/run", data=payload)

    def get_executions(self, workflow_id: str = None, limit=10, status=None):
        """Get execution history."""
        params = {"limit": limit}
        if workflow_id:
            params["workflowId"] = workflow_id
        if status:
            params["status"] = status
        return self._request("GET", "/executions", params=params)

    # --- Credentials ---

    def list_credentials(self):
        """List available credentials (names only, no secrets)."""
        return self._request("GET", "/credentials")


# --- CLI Commands ---

def cmd_list(client, args):
    """List all workflows."""
    result = client.list_workflows(active_only=args.active)
    workflows = result.get("data", [])

    if args.output_json:
        print(json.dumps(workflows, indent=2))
        return

    if not workflows:
        print("No workflows found.")
        return

    # Summary table
    active_count = sum(1 for w in workflows if w.get("active"))
    print(f"\n  n8n Workflows: {len(workflows)} total, {active_count} active\n")
    print(f"  {'ID':<24} {'Active':>6}  {'Name'}")
    print(f"  {'-' * 24} {'-' * 6}  {'-' * 40}")
    for w in sorted(workflows, key=lambda x: x.get("active", False), reverse=True):
        status = " ON" if w.get("active") else "  -"
        print(f"  {w['id']:<24} {status:>6}  {w['name']}")


def cmd_get(client, args):
    """Get workflow details."""
    wf = client.get_workflow(args.workflow_id)

    if args.output_json:
        print(json.dumps(wf, indent=2))
        return

    nodes = wf.get("nodes", [])
    print(f"\n  Workflow: {wf.get('name', 'Unknown')}")
    print(f"  ID:      {wf.get('id')}")
    print(f"  Active:  {wf.get('active', False)}")
    print(f"  Created: {wf.get('createdAt', 'Unknown')}")
    print(f"  Updated: {wf.get('updatedAt', 'Unknown')}")
    print(f"\n  Nodes ({len(nodes)}):")
    for node in nodes:
        node_type = node.get("type", "unknown").split(".")[-1]
        print(f"    • {node.get('name', 'Unnamed')} ({node_type})")

    connections = wf.get("connections", {})
    if connections:
        print(f"\n  Connections:")
        for source, targets in connections.items():
            for conn_type, conns in targets.items():
                for conn_list in conns:
                    for conn in conn_list if isinstance(conn_list, list) else [conn_list]:
                        if isinstance(conn, dict):
                            print(f"    {source} → {conn.get('node', '?')}")


def cmd_create(client, args):
    """Create a workflow from JSON string or file."""
    source = args.source

    # Try as file path first
    source_path = Path(source)
    if source_path.exists():
        with open(source_path, "r", encoding="utf-8") as f:
            workflow_data = json.load(f)
    else:
        # Try as JSON string
        try:
            workflow_data = json.loads(source)
        except json.JSONDecodeError:
            print(f"ERROR: '{source}' is not a valid file path or JSON string", file=sys.stderr)
            sys.exit(1)

    result = client.create_workflow(workflow_data)

    if args.output_json:
        print(json.dumps(result, indent=2))
        return

    print(f"\n  Workflow created successfully!")
    print(f"  ID:   {result.get('id')}")
    print(f"  Name: {result.get('name')}")
    print(f"  Nodes: {len(result.get('nodes', []))}")
    print(f"\n  Note: Workflow created as INACTIVE. Use 'activate {result.get('id')}' to enable.")


def cmd_update(client, args):
    """Update a workflow."""
    try:
        update_data = json.loads(args.data)
    except json.JSONDecodeError:
        # Try as file
        path = Path(args.data)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                update_data = json.load(f)
        else:
            print(f"ERROR: '{args.data}' is not valid JSON or file path", file=sys.stderr)
            sys.exit(1)

    result = client.update_workflow(args.workflow_id, update_data)

    if args.output_json:
        print(json.dumps(result, indent=2))
        return

    print(f"\n  Workflow '{result.get('name')}' updated successfully.")


def cmd_activate(client, args):
    """Activate a workflow."""
    result = client.activate_workflow(args.workflow_id)
    if args.output_json:
        print(json.dumps(result, indent=2))
        return
    print(f"\n  Workflow '{result.get('name')}' activated.")


def cmd_deactivate(client, args):
    """Deactivate a workflow."""
    result = client.deactivate_workflow(args.workflow_id)
    if args.output_json:
        print(json.dumps(result, indent=2))
        return
    print(f"\n  Workflow '{result.get('name')}' deactivated.")


def cmd_delete(client, args):
    """Delete a workflow."""
    if not args.force:
        wf = client.get_workflow(args.workflow_id)
        print(f"\n  About to DELETE: {wf.get('name')} ({args.workflow_id})")
        confirm = input("  Type 'yes' to confirm: ")
        if confirm.lower() != "yes":
            print("  Cancelled.")
            return

    client.delete_workflow(args.workflow_id)
    print(f"\n  Workflow {args.workflow_id} deleted.")


def cmd_execute(client, args):
    """Execute a workflow."""
    data = None
    if args.data:
        try:
            data = json.loads(args.data)
        except json.JSONDecodeError:
            print(f"ERROR: Invalid JSON data", file=sys.stderr)
            sys.exit(1)

    result = client.execute_workflow(args.workflow_id, data)

    if args.output_json:
        print(json.dumps(result, indent=2))
        return

    print(f"\n  Workflow executed.")
    if isinstance(result, dict):
        print(f"  Status: {result.get('status', 'unknown')}")
        if result.get("data"):
            print(f"  Output: {json.dumps(result['data'], indent=2)[:500]}")


def cmd_executions(client, args):
    """View execution history."""
    result = client.get_executions(
        workflow_id=args.workflow_id,
        limit=args.limit,
        status=args.status
    )
    executions = result.get("data", [])

    if args.output_json:
        print(json.dumps(executions, indent=2))
        return

    if not executions:
        print("  No executions found.")
        return

    print(f"\n  Executions for workflow {args.workflow_id or 'all'}:\n")
    for ex in executions:
        status = ex.get("status", "?")
        started = ex.get("startedAt", "?")[:19]
        wf_name = ex.get("workflowData", {}).get("name", "?") if not args.workflow_id else ""
        print(f"  {ex.get('id', '?'):>6}  {status:<10}  {started}  {wf_name}")


def cmd_export(client, args):
    """Export workflow as JSON file."""
    wf = client.get_workflow(args.workflow_id)

    if args.output:
        output_path = Path(args.output)
    else:
        safe_name = wf.get("name", "workflow").replace(" ", "_").lower()
        output_path = Path(f"{safe_name}_{args.workflow_id}.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, indent=2)

    print(f"\n  Exported to: {output_path}")


def cmd_import(client, args):
    """Import workflow from JSON file."""
    path = Path(args.file)
    if not path.exists():
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        workflow_data = json.load(f)

    # Remove fields that would conflict with creation
    for field in ["id", "createdAt", "updatedAt", "versionId"]:
        workflow_data.pop(field, None)

    result = client.create_workflow(workflow_data)

    if args.output_json:
        print(json.dumps(result, indent=2))
        return

    print(f"\n  Imported successfully!")
    print(f"  ID:    {result.get('id')}")
    print(f"  Name:  {result.get('name')}")
    print(f"  Nodes: {len(result.get('nodes', []))}")


def cmd_credentials(client, args):
    """List available credentials."""
    result = client.list_credentials()
    creds = result.get("data", [])

    if args.output_json:
        print(json.dumps(creds, indent=2))
        return

    if not creds:
        print("  No credentials found.")
        return

    print(f"\n  Credentials ({len(creds)}):\n")
    for c in creds:
        print(f"  {c.get('id', '?'):>4}  {c.get('type', '?'):<30}  {c.get('name', '?')}")


def main():
    env = load_env()

    api_url = env.get("N8N_API_URL")
    api_key = env.get("N8N_API_KEY")

    if not api_url or not api_key:
        print("ERROR: N8N_API_URL and N8N_API_KEY must be set in .env.agents", file=sys.stderr)
        sys.exit(1)

    # Parent parser for shared flags
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--json", dest="output_json", action="store_true",
                        help="Output raw JSON for agent consumption")

    parser = argparse.ArgumentParser(
        description="n8n CLI Tool — Full workflow management via REST API",
        parents=[parent]
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # list
    p_list = subparsers.add_parser("list", parents=[parent], help="List all workflows")
    p_list.add_argument("--active", action="store_true", help="Show only active workflows")

    # get
    p_get = subparsers.add_parser("get", parents=[parent], help="Get workflow details")
    p_get.add_argument("workflow_id", help="Workflow ID")

    # create
    p_create = subparsers.add_parser("create", parents=[parent], help="Create workflow from JSON")
    p_create.add_argument("source", help="JSON file path or JSON string")

    # update
    p_update = subparsers.add_parser("update", parents=[parent], help="Update workflow")
    p_update.add_argument("workflow_id", help="Workflow ID")
    p_update.add_argument("data", help="JSON file path or JSON string with updates")

    # activate
    p_act = subparsers.add_parser("activate", parents=[parent], help="Activate workflow")
    p_act.add_argument("workflow_id", help="Workflow ID")

    # deactivate
    p_deact = subparsers.add_parser("deactivate", parents=[parent], help="Deactivate workflow")
    p_deact.add_argument("workflow_id", help="Workflow ID")

    # delete
    p_del = subparsers.add_parser("delete", parents=[parent], help="Delete workflow")
    p_del.add_argument("workflow_id", help="Workflow ID")
    p_del.add_argument("--force", action="store_true", help="Skip confirmation")

    # execute
    p_exec = subparsers.add_parser("execute", parents=[parent], help="Execute workflow")
    p_exec.add_argument("workflow_id", help="Workflow ID")
    p_exec.add_argument("--data", help="JSON input data")

    # executions
    p_execs = subparsers.add_parser("executions", parents=[parent], help="View execution history")
    p_execs.add_argument("workflow_id", nargs="?", help="Workflow ID (optional)")
    p_execs.add_argument("--limit", type=int, default=10, help="Max results")
    p_execs.add_argument("--status", help="Filter by status (success, error, waiting)")

    # export
    p_export = subparsers.add_parser("export", parents=[parent], help="Export workflow to JSON file")
    p_export.add_argument("workflow_id", help="Workflow ID")
    p_export.add_argument("--output", "-o", help="Output file path")

    # import
    p_import = subparsers.add_parser("import", parents=[parent], help="Import workflow from JSON file")
    p_import.add_argument("file", help="JSON file path")

    # credentials
    p_creds = subparsers.add_parser("credentials", parents=[parent], help="List credentials")

    # V2 2026-04-11: pre-scan argv for --json BEFORE subcommand so that
    # `python n8n_tool.py --json list` behaves identically to
    # `python n8n_tool.py list --json`. Same bug class as revenue_engine.py:
    # argparse subparser inheritance silently clobbers the top-level flag.
    _pre_json = "--json" in sys.argv[1:]

    args = parser.parse_args()
    if _pre_json:
        args.output_json = True

    if not args.command:
        parser.print_help()
        sys.exit(0)

    client = N8nClient(api_url, api_key)

    commands = {
        "list": cmd_list,
        "get": cmd_get,
        "create": cmd_create,
        "update": cmd_update,
        "activate": cmd_activate,
        "deactivate": cmd_deactivate,
        "delete": cmd_delete,
        "execute": cmd_execute,
        "executions": cmd_executions,
        "export": cmd_export,
        "import": cmd_import,
        "credentials": cmd_credentials,
    }

    cmd_fn = commands.get(args.command)
    if cmd_fn:
        cmd_fn(client, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
