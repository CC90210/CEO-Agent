"""Reap duplicate MCP server processes from leaked editor sessions.

Multiple AI editors (Claude Code, Antigravity, Cursor, Gemini CLI) each spawn
their own MCP server set on launch. When a host exits, its MCPs are not
always reaped — they become orphans, holding RAM forever.

For each known MCP signature, this script keeps the N newest processes and
terminates the older duplicates. The "newest = mine" heuristic is safe because
the currently active editor session is also the most recent MCP-spawner.

Usage:
    python scripts/reap_orphan_mcps.py                # dry-run, keep 2 newest
    python scripts/reap_orphan_mcps.py --keep 4       # keep more per signature
    python scripts/reap_orphan_mcps.py --apply        # actually terminate
    python scripts/reap_orphan_mcps.py --json         # machine-readable
"""
import argparse
import json
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000

MCP_SIGNATURES = (
    "context7-mcp",
    "server-memory",
    "sequential-thinking",
    "playwright/mcp",
    "@playwright\\mcp",
    "supabase/mcp-server",
    "@supabase\\mcp-server",
    "supergateway",
    "claude-mem",
    "late-mcp",
    "chroma-mcp",
    "firecrawl-mcp",
    "obsidian-mcp",
    "knowledge-graph",
)


def _powershell_json(ps_script: str, timeout: int = 30) -> list:
    """Run a PowerShell command that emits JSON, return list of dicts."""
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
        capture_output=True, text=True, timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
        startupinfo=si,
    )
    if r.returncode != 0:
        sys.stderr.write(f"PowerShell query failed: {r.stderr}\n")
        sys.exit(2)
    if not r.stdout.strip():
        return []
    data = json.loads(r.stdout)
    return [data] if isinstance(data, dict) else data


def query_mcps() -> list[dict]:
    """Return list of MCP-server processes with PID, command line, and start time.

    Single PowerShell call instead of two — `Win32_Process` exposes both
    CommandLine and CreationDate in the same query.
    """
    ps = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId, Name, CommandLine, CreationDate | "
        "ConvertTo-Json -Compress -Depth 2"
    )
    procs = _powershell_json(ps)
    out = []
    for p in procs:
        cmd = p.get("CommandLine") or ""
        sig = next((s for s in MCP_SIGNATURES if s in cmd), None)
        if not sig:
            continue
        cd = p.get("CreationDate")
        # CIM emits a wrapped {"DateTime": "..."} on some PowerShell versions
        started = cd["DateTime"] if isinstance(cd, dict) and "DateTime" in cd else str(cd or "")
        out.append({
            "pid": int(p["ProcessId"]),
            "name": (p.get("Name") or "").strip(),
            "cmdline": cmd,
            "signature": sig,
            "started": started,
        })
    return out


def classify_mcps(mcps: list[dict], keep_n: int = 2) -> dict:
    """Per MCP signature, keep the N newest; older ones are orphans."""
    grouped: dict[str, list[dict]] = {}
    for m in mcps:
        grouped.setdefault(m["signature"], []).append(m)

    orphans = []
    live = []
    for sig, group in grouped.items():
        group.sort(key=lambda m: m["started"], reverse=True)  # newest first
        for i, m in enumerate(group):
            if i < keep_n:
                live.append(m)
            else:
                orphans.append({**m, "reason": f"older duplicate (rank {i+1} of {len(group)} for {sig})"})

    return {"orphans": orphans, "live": live, "total_mcps": len(mcps), "keep_n": keep_n}


def kill_pid(pid: int) -> tuple[bool, str]:
    """Terminate a process by PID. Returns (success, message)."""
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        # taskkill is the most reliable Windows option
        result = subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True, text=True, timeout=10,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=si,
        )
        if result.returncode == 0:
            return True, "terminated"
        return False, result.stderr.strip() or result.stdout.strip()
    except Exception as exc:
        return False, str(exc)


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="actually terminate orphans")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--keep", type=int, default=2, help="MCPs to keep per signature (default 2)")
    args = parser.parse_args(argv)

    mcps = query_mcps()
    result = classify_mcps(mcps, keep_n=args.keep)

    summary = {
        "total_mcps": result["total_mcps"],
        "orphans": len(result["orphans"]),
        "live": len(result["live"]),
        "applied": False,
        "killed": [],
        "failed": [],
    }

    if args.apply and result["orphans"]:
        for o in result["orphans"]:
            ok, msg = kill_pid(o["pid"])
            entry = {"pid": o["pid"], "signature": o["signature"], "msg": msg}
            if ok:
                summary["killed"].append(entry)
            else:
                summary["failed"].append(entry)
        summary["applied"] = True

    if args.json:
        print(json.dumps({**summary, "orphans_detail": result["orphans"]}, indent=2))
        return 0 if not summary["failed"] else 1

    # Human report
    print(f"Total MCP procs: {result['total_mcps']}")
    print(f"  Keeping (newest {args.keep} per signature):  {len(result['live'])}")
    print(f"  Orphans (older duplicates):                  {len(result['orphans'])}")
    print()
    if result["orphans"]:
        print("Orphans:")
        for o in result["orphans"]:
            print(f"  PID {o['pid']:>6}  {o['signature']:<22}  reason: {o['reason']}")
    if not args.apply and result["orphans"]:
        print()
        print(f"Re-run with --apply to terminate {len(result['orphans'])} orphan(s).")
    elif args.apply:
        print()
        print(f"Killed {len(summary['killed'])} | Failed {len(summary['failed'])}")
        for f in summary["failed"]:
            print(f"  FAIL PID {f['pid']}: {f['msg']}")
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
