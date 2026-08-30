"""
cron_dispatcher.py — Execute allowlisted script-backed cron jobs.

`cron_engine.py` is the registry. This script is the runner surface n8n (or
Windows Task Scheduler / systemd / PM2) can call safely:

  python scripts/core/cron_dispatcher.py due --execute
  python scripts/core/cron_dispatcher.py run <cron_job_uuid>

Only the small cross-repo allowlist below executes here. Empire `script_run`
jobs are owned by scripts/scheduler.py; unknown types remain registry-only and
must be handled by their declared runner. Both Python runners use the canonical
action_config `timeout` key (`timeout_seconds` remains a compatibility alias).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cron_engine import _next_run_approx, fmt_date, get_client, load_env
from _subprocess_helpers import WINDOWLESS_FLAGS

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
KNOWN_ROOTS = [
    REPO_ROOT,
    REPO_ROOT.parent / "CMO-Agent",
    REPO_ROOT.parent / "APPS" / "CFO-Agent",
]

ALLOWLISTED_SCRIPT_ACTIONS = {
    "atlas_pulse_publish",
    "maven_token_check",
    "maven_content_audit",
}

DEFAULT_ARGS = {
    "atlas_pulse_publish": ["auto"],
    "maven_token_check": ["--notify"],
    "maven_content_audit": ["--json"],
}


def _resolve_known(path_value: str, base: Path = REPO_ROOT) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = base / path
    resolved = path.resolve()
    for root in KNOWN_ROOTS:
        try:
            resolved.relative_to(root.resolve())
            return resolved
        except ValueError:
            continue
    raise ValueError(f"Refusing path outside known agent roots: {path_value}")


def _job_command(job: dict[str, Any]) -> tuple[list[str], Path]:
    action_type = job.get("action_type")
    if action_type not in ALLOWLISTED_SCRIPT_ACTIONS:
        raise ValueError(f"Action type is not script-dispatch allowlisted: {action_type}")
    config = job.get("action_config") or {}
    if not isinstance(config, dict):
        raise ValueError("action_config must be an object")
    script = config.get("script")
    if not script:
        raise ValueError("action_config.script is required")

    cwd = _resolve_known(config["cwd"]) if config.get("cwd") else None
    script_path = _resolve_known(script)
    if not script_path.exists():
        raise FileNotFoundError(f"Script does not exist: {script_path}")
    if script_path.suffix.lower() != ".py":
        raise ValueError(f"Only Python scripts are supported: {script_path}")

    args = config.get("args")
    if args is None:
        args = DEFAULT_ARGS.get(action_type, [])
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise ValueError("action_config.args must be a list of strings")

    workdir = cwd or script_path.parent.parent
    return [sys.executable, str(script_path), *args], workdir


def _update_run_state(client, job: dict[str, Any], ok: bool, result: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    updates: dict[str, Any] = {
        "last_run_at": now,
        "run_count": (job.get("run_count") or 0) + 1,
        "last_result": result[:500],
    }
    next_run = _next_run_approx(job.get("schedule", ""))
    if next_run:
        updates["next_run_at"] = next_run
    if not ok:
        updates["last_error_at"] = now
    client.table("cron_jobs").update(updates).eq("id", job["id"]).execute()


def execute_job(client, job: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    cmd, cwd = _job_command(job)
    payload = {
        "id": job.get("id"),
        "name": job.get("name"),
        "action_type": job.get("action_type"),
        "cmd": cmd,
        "cwd": str(cwd),
        "dry_run": dry_run,
    }
    if dry_run:
        return {**payload, "ok": True, "result": "dry_run"}

    env = os.environ.copy()
    env.update(load_env())
    config = job.get("action_config") or {}
    timeout = int(config.get("timeout", config.get("timeout_seconds", 300)))
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        creationflags=WINDOWLESS_FLAGS,
    )
    output = (proc.stdout or "").strip()
    error = (proc.stderr or "").strip()
    ok = proc.returncode == 0
    result = "ok" if ok else f"failed:{proc.returncode}"
    # What the job actually REPORTED, not just whether it exited 0 (2026-08-29).
    # This path stored a bare "ok" and discarded stdout, so a job triggered by
    # hand — the debugging path, where you most need to know what happened —
    # overwrote cron_jobs.last_result with strictly less information than the
    # scheduler had written on its previous scheduled run.
    #
    # Reuses scheduler.summarize_stdout rather than re-deriving a summary: two
    # dispatch paths storing one column in two shapes is how last_result became
    # unreadable in the first place. Lazy import — scheduler is a heavy module
    # and this is the only line here that needs it.
    if ok and output:
        try:
            from scheduler import summarize_stdout  # noqa: PLC0415
            summary = summarize_stdout(output)
            if summary and summary != "ok":
                result = f"ok: {summary}"
        except Exception:  # noqa: BLE001 - never fail a dispatch over a summary
            pass
    if error:
        result += f" stderr={error[:220]}"
    _update_run_state(client, job, ok, result)
    return {
        **payload,
        "ok": ok,
        "returncode": proc.returncode,
        "stdout": output[-4000:],
        "stderr": error[-4000:],
        "result": result,
    }


def _fetch_job(client, job_id: str) -> dict[str, Any]:
    result = client.table("cron_jobs").select("*").eq("id", job_id).execute()
    if not result.data:
        raise ValueError(f"Cron job not found: {job_id}")
    return result.data[0]


def _fetch_due(client, limit: int) -> list[dict[str, Any]]:
    now_iso = datetime.now(timezone.utc).isoformat()
    result = (
        client.table("cron_jobs")
        .select("*")
        .eq("is_active", True)
        .lte("next_run_at", now_iso)
        .not_.is_("next_run_at", "null")
        .order("next_run_at", desc=False)
        .limit(limit)
        .execute()
    )
    return result.data or []


def _print_result(result: dict[str, Any]) -> None:
    mark = "OK" if result.get("ok") else "FAIL"
    print(f"[{mark}] {result.get('name')} ({result.get('action_type')})")
    print(f"  cwd: {result.get('cwd')}")
    print(f"  cmd: {' '.join(result.get('cmd', []))}")
    if result.get("stdout"):
        print("  stdout:")
        print(result["stdout"])
    if result.get("stderr"):
        print("  stderr:")
        print(result["stderr"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute allowlisted script-backed cron jobs.")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    pr = sub.add_parser("run", help="Execute one cron job by UUID")
    pr.add_argument("job_id")
    pr.add_argument("--dry-run", action="store_true")
    pr.add_argument("--json", action="store_true")

    pd = sub.add_parser("due", help="List or execute due allowlisted jobs")
    pd.add_argument("--execute", action="store_true")
    pd.add_argument("--limit", type=int, default=10)
    pd.add_argument("--dry-run", action="store_true")
    pd.add_argument("--json", action="store_true")

    args = parser.parse_args()
    client = get_client(load_env())

    if args.command == "run":
        result = execute_job(client, _fetch_job(client, args.job_id), dry_run=args.dry_run)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            _print_result(result)
        sys.exit(0 if result.get("ok") else 1)

    jobs = _fetch_due(client, args.limit)
    if not args.execute:
        payload = [
            {
                "id": j.get("id"),
                "name": j.get("name"),
                "action_type": j.get("action_type"),
                "next_run_at": j.get("next_run_at"),
                "dispatchable": j.get("action_type") in ALLOWLISTED_SCRIPT_ACTIONS,
            }
            for j in jobs
        ]
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            for item in payload:
                flag = "dispatchable" if item["dispatchable"] else "registry-only"
                print(f"{fmt_date(item['next_run_at'])}  {item['id']}  {item['name']}  [{flag}]")
        return

    results = []
    for job in jobs:
        if job.get("action_type") not in ALLOWLISTED_SCRIPT_ACTIONS:
            results.append({"id": job.get("id"), "name": job.get("name"), "ok": False, "result": "registry-only"})
            continue
        results.append(execute_job(client, job, dry_run=args.dry_run))
    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        for result in results:
            _print_result(result)
    if any(not r.get("ok") for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
