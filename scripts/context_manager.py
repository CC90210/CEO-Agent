"""
Context Manager — SESSION_LOG compaction, tiered context loading, and MCP/CLI health checks.

Inspired by Claude Code's internal context management:
  - Transcript compaction: Claude Code compacts after ~12 turns, keeping the last 8.
    We mirror this for SESSION_LOG.md — archive old entries, keep N recent ones.
  - Simple Mode / Tiered Loading: Claude Code loads minimal context for simple queries
    and expands progressively for complex work. We calculate which brain/memory files
    are actually needed for a given query.
  - Deferred Init: Claude Code delays expensive MCP server initialization until the
    server is actually needed. Our health check tells you what's available before
    anything is loaded.

Usage:
  python scripts/context_manager.py compact [--keep 10] [--dry-run]
  python scripts/context_manager.py status
  python scripts/context_manager.py tier "<query string>"
  python scripts/context_manager.py health
  python scripts/context_manager.py health --json

Flags:
  --json      Output raw JSON for agent consumption
  --dry-run   Preview compaction without writing any files
"""

import argparse
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Force UTF-8 output on Windows (avoids cp1252 failures with arrow/dash characters)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Project root detection
# ---------------------------------------------------------------------------

def find_project_root() -> Path:
    """Walk up from this script's location until we find a .git directory."""
    candidate = Path(__file__).resolve().parent
    for _ in range(10):
        if (candidate / ".git").exists():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    # Fallback: two levels up from scripts/
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = find_project_root()
SESSION_LOG = PROJECT_ROOT / "memory" / "SESSION_LOG.md"
ARCHIVES_DIR = PROJECT_ROOT / "memory" / "ARCHIVES"


# ---------------------------------------------------------------------------
# .env.agents loader (matches pattern used by all other CLI tools)
# ---------------------------------------------------------------------------

def load_env() -> dict:
    """Load .env.agents from project root. Never raises — returns empty dict on miss."""
    env_path = PROJECT_ROOT / ".env.agents"
    env_vars: dict = {}
    if not env_path.exists():
        return env_vars
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip()
    except OSError:
        pass

    # Also attempt python-dotenv for richer .env support
    try:
        from dotenv import dotenv_values  # type: ignore
        dotenv_parsed = dotenv_values(env_path)
        for k, v in dotenv_parsed.items():
            if k and v is not None:
                env_vars.setdefault(k, v)
    except ImportError:
        pass  # python-dotenv not installed — manual parse already done above

    return env_vars


# ---------------------------------------------------------------------------
# SESSION_LOG entry parsing
# ---------------------------------------------------------------------------

def parse_entries(text: str) -> list[dict]:
    """
    Split SESSION_LOG.md into individual entries.
    Each entry starts with a '### ' header line.
    Returns list of dicts: {header, date, body, full_text}.
    """
    lines = text.splitlines(keepends=True)
    entries: list[dict] = []
    current_header: str | None = None
    current_lines: list[str] = []
    preamble_lines: list[str] = []
    in_entries = False

    for line in lines:
        if line.startswith("### "):
            if not in_entries:
                in_entries = True
            if current_header is not None:
                entries.append(_build_entry(current_header, current_lines))
            current_header = line.rstrip("\n")
            current_lines = [line]
        else:
            if in_entries:
                current_lines.append(line)
            else:
                preamble_lines.append(line)

    if current_header is not None:
        entries.append(_build_entry(current_header, current_lines))

    return entries, "".join(preamble_lines)


def _build_entry(header: str, lines: list[str]) -> dict:
    """Parse a single entry's header to extract its date."""
    # Header format: ### YYYY-MM-DD — Description
    date_str = None
    parts = header.lstrip("#").strip()
    # Take the first token that looks like a date
    for token in parts.split():
        token = token.rstrip("—").strip()
        try:
            datetime.strptime(token, "%Y-%m-%d")
            date_str = token
            break
        except ValueError:
            continue

    return {
        "header": header,
        "date": date_str,
        "full_text": "".join(lines),
    }


# ---------------------------------------------------------------------------
# Feature 1: Transcript Compaction
# ---------------------------------------------------------------------------

def cmd_compact(args) -> int:
    """Archive old SESSION_LOG entries, keep the N most recent."""
    keep: int = args.keep
    dry_run: bool = args.dry_run
    as_json: bool = args.json

    if not SESSION_LOG.exists():
        _emit({"error": f"SESSION_LOG not found at {SESSION_LOG}"}, as_json,
              f"ERROR: SESSION_LOG not found at {SESSION_LOG}")
        return 1

    raw = SESSION_LOG.read_text(encoding="utf-8")
    entries, preamble = parse_entries(raw)
    total = len(entries)

    if total <= keep:
        _emit(
            {"status": "no_action", "total_entries": total, "keep": keep,
             "message": f"Only {total} entries present — nothing to compact (threshold: {keep})."},
            as_json,
            f"No compaction needed. {total} entries present, threshold is {keep}.",
        )
        return 0

    to_archive = entries[: total - keep]
    to_keep = entries[total - keep :]

    # Determine archive filename from the oldest entry being archived
    archive_month = _resolve_archive_month(to_archive)
    archive_path = ARCHIVES_DIR / f"sessions-{archive_month}.md"

    result = {
        "total_entries": total,
        "keep": keep,
        "archiving": len(to_archive),
        "archive_file": str(archive_path),
        "kept_entries": [e["header"] for e in to_keep],
        "archived_entries": [e["header"] for e in to_archive],
        "dry_run": dry_run,
    }

    if dry_run:
        _emit(
            {**result, "status": "dry_run"},
            as_json,
            _compact_dry_run_summary(result),
        )
        return 0

    # Write archive
    ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
    archive_content = _build_archive_content(to_archive, archive_path)
    with open(archive_path, "a", encoding="utf-8") as f:
        f.write(archive_content)

    # Rewrite SESSION_LOG with preamble + kept entries
    new_content = preamble
    for entry in to_keep:
        new_content += entry["full_text"]
        if not new_content.endswith("\n"):
            new_content += "\n"

    SESSION_LOG.write_text(new_content, encoding="utf-8")

    _emit(
        {**result, "status": "compacted"},
        as_json,
        (
            f"Compacted: archived {len(to_archive)} entries to {archive_path.name}, "
            f"kept {len(to_keep)} entries in SESSION_LOG.md."
        ),
    )
    return 0


def _resolve_archive_month(entries: list[dict]) -> str:
    """Return YYYY-MM for the archive file based on the entries being archived."""
    for entry in entries:
        if entry["date"]:
            try:
                dt = datetime.strptime(entry["date"], "%Y-%m-%d")
                return dt.strftime("%Y-%m")
            except ValueError:
                pass
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _build_archive_content(entries: list[dict], archive_path: Path) -> str:
    """Build the text block to append to the archive file."""
    header = ""
    if not archive_path.exists():
        month_label = archive_path.stem.replace("sessions-", "")
        header = f"# Session Archive — {month_label}\n\n"
    return header + "".join(e["full_text"] for e in entries)


def _compact_dry_run_summary(result: dict) -> str:
    lines = [
        f"DRY RUN — no files written.",
        f"  Total entries : {result['total_entries']}",
        f"  Would archive : {result['archiving']} entries → {Path(result['archive_file']).name}",
        f"  Would keep    : {result['keep']} entries in SESSION_LOG.md",
        "",
        "Entries that would be archived:",
    ]
    for h in result["archived_entries"]:
        lines.append(f"  {h.strip()}")
    lines.append("")
    lines.append("Entries that would be kept:")
    for h in result["kept_entries"]:
        lines.append(f"  {h.strip()}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Feature 1b: Status
# ---------------------------------------------------------------------------

def cmd_status(args) -> int:
    """Report SESSION_LOG current state and recommended action."""
    as_json: bool = args.json

    if not SESSION_LOG.exists():
        _emit({"error": f"SESSION_LOG not found at {SESSION_LOG}"}, as_json,
              f"ERROR: SESSION_LOG not found at {SESSION_LOG}")
        return 1

    raw = SESSION_LOG.read_text(encoding="utf-8")
    entries, _ = parse_entries(raw)
    line_count = len(raw.splitlines())
    total_entries = len(entries)

    oldest_date = None
    newest_date = None
    for entry in entries:
        if entry["date"]:
            if oldest_date is None or entry["date"] < oldest_date:
                oldest_date = entry["date"]
            if newest_date is None or entry["date"] > newest_date:
                newest_date = entry["date"]

    # Recommendations matching memory-management skill thresholds
    if line_count > 200:
        recommendation = "COMPACT NOW — over 200-line threshold. Run: python scripts/context_manager.py compact"
    elif total_entries > 15:
        recommendation = "COMPACT SOON — entry count is high. Consider running compact to keep context lean."
    else:
        recommendation = "HEALTHY — no action needed."

    result = {
        "file": str(SESSION_LOG),
        "line_count": line_count,
        "entry_count": total_entries,
        "oldest_entry": oldest_date,
        "newest_entry": newest_date,
        "line_threshold": 200,
        "recommendation": recommendation,
    }

    _emit(
        result,
        as_json,
        (
            f"SESSION_LOG Status\n"
            f"  File        : {SESSION_LOG}\n"
            f"  Lines       : {line_count} / 200 threshold\n"
            f"  Entries     : {total_entries}\n"
            f"  Oldest      : {oldest_date or 'unknown'}\n"
            f"  Newest      : {newest_date or 'unknown'}\n"
            f"  Action      : {recommendation}"
        ),
    )
    return 0


# ---------------------------------------------------------------------------
# Feature 2: Tiered context loading calculator
# ---------------------------------------------------------------------------

# Actual line counts for each tier (measured 2026-03-31)
TIER_FILES = {
    1: {
        "files": ["brain/STATE.md", "memory/ACTIVE_TASKS.md"],
        "approx_lines": 185,
        "description": "Minimal — status checks and quick lookups",
    },
    2: {
        "files": [
            "brain/STATE.md",
            "memory/ACTIVE_TASKS.md",
            "brain/AGENTS.md",
            "brain/CAPABILITIES.md",
        ],
        "approx_lines": 789,
        "description": "Standard — feature work, bug fixes, moderate tasks",
    },
    3: {
        "files": [
            "brain/STATE.md",
            "memory/ACTIVE_TASKS.md",
            "brain/AGENTS.md",
            "brain/CAPABILITIES.md",
            "brain/SOUL.md",
            "brain/USER.md",
            "brain/BRAIN_LOOP.md",
            "memory/LONG_TERM.md",
            "memory/PATTERNS.md",
            "memory/MISTAKES.md",
            "memory/SESSION_LOG.md",
        ],
        "approx_lines": 1275,
        "description": "Full — architecture, system redesign, complex multi-file tasks",
    },
}

# Token cost estimation (approx 3 tokens per line of markdown, priced at Claude Opus input rate)
# Opus 4.6: $15/MTok input. Mythos (when available): expected similar or lower per-token.
COST_PER_TOKEN_USD = 15.0 / 1_000_000  # $0.000015 per token
TOKENS_PER_LINE = 3  # Conservative estimate for markdown

def estimate_tier_cost(tier: int) -> dict:
    """Estimate token count and USD cost for a context tier load."""
    info = TIER_FILES[tier]
    est_tokens = info["approx_lines"] * TOKENS_PER_LINE
    est_cost = est_tokens * COST_PER_TOKEN_USD
    return {
        "tier": tier,
        "est_tokens": est_tokens,
        "est_cost_usd": round(est_cost, 6),
        "files": len(info["files"]),
        "approx_lines": info["approx_lines"],
    }


# Keywords that signal each tier. Checked in order from T3 → T1 so higher tiers win.
TIER_KEYWORDS = {
    3: [
        "redesign", "architecture", "refactor", "overhaul", "migrate", "migration",
        "schema", "system design", "spar c", "sparc", "multi-file", "cross-cutting",
        "strategic", "quarterly", "planning", "retro", "roadmap", "scale",
    ],
    2: [
        "build", "implement", "fix", "debug", "create", "add feature", "update",
        "deploy", "ship", "integrate", "test", "endpoint", "route", "component",
        "workflow", "automation", "client", "proposal",
    ],
    1: [
        "status", "check", "what", "show", "list", "how many", "current", "is",
        "health", "balance", "count", "report", "summary",
    ],
}


def classify_tier(query: str) -> int:
    """Return the recommended context tier (1, 2, or 3) for a given query."""
    q = query.lower()
    # Evaluate highest-signal tier first
    for tier in (3, 2, 1):
        for kw in TIER_KEYWORDS[tier]:
            if kw in q:
                return tier
    # Default to tier 2 when uncertain — standard work is the most common case
    return 2


def cmd_tier(args) -> int:
    """Recommend which brain/memory files to load for the given query."""
    query: str = args.query
    as_json: bool = args.json

    tier = classify_tier(query)
    info = TIER_FILES[tier]

    matched_keywords = []
    q = query.lower()
    for kw in TIER_KEYWORDS[tier]:
        if kw in q:
            matched_keywords.append(kw)

    cost = estimate_tier_cost(tier)

    result = {
        "query": query,
        "recommended_tier": tier,
        "description": info["description"],
        "approx_lines": info["approx_lines"],
        "est_tokens": cost["est_tokens"],
        "est_cost_usd": cost["est_cost_usd"],
        "files_to_load": info["files"],
        "matched_keywords": matched_keywords,
        "tier_rationale": {
            1: "Minimal context — status/lookup queries need almost nothing.",
            2: "Standard context — active task and agent routing are enough.",
            3: "Full context — architecture work benefits from all memory layers.",
        }[tier],
    }

    _emit(
        result,
        as_json,
        (
            f"Tier {tier} — {info['description']}\n"
            f"  Approx lines : {info['approx_lines']}\n"
            f"  Est. tokens  : {cost['est_tokens']:,}\n"
            f"  Est. cost    : ${cost['est_cost_usd']:.6f}\n"
            f"  Matched on   : {', '.join(matched_keywords) if matched_keywords else 'default'}\n"
            f"\n  Files to load:\n"
            + "\n".join(f"    {f}" for f in info["files"])
        ),
    )
    return 0


# ---------------------------------------------------------------------------
# Feature 3: Deferred Init Health Check
# ---------------------------------------------------------------------------

MCP_CHECKS = {
    "playwright": {
        "description": "Browser automation (Playwright MCP)",
        "check": "npm_package",
        "package": "@playwright/mcp",
    },
    "context7": {
        "description": "Library docs (Context7 MCP)",
        "check": "npm_package",
        "package": "@upstash/context7-mcp",
    },
    "memory": {
        "description": "Knowledge graph (Memory MCP)",
        "check": "npm_package",
        "package": "@modelcontextprotocol/server-memory",
    },
    "sequential-thinking": {
        "description": "Structured reasoning (Sequential Thinking MCP)",
        "check": "npm_package",
        "package": "@modelcontextprotocol/server-sequential-thinking",
    },
}

CLI_CHECKS = {
    "n8n_tool": {
        "description": "n8n workflow management",
        "check": "python_script",
        "script": "scripts/n8n_tool.py",
        "env_key": "N8N_API_KEY",
    },
    "late_tool": {
        "description": "Social media publishing (Zernio/Late)",
        "check": "python_script",
        "script": "scripts/late_tool.py",
        "env_key": "LATE_API_KEY",
    },
    "supabase_tool": {
        "description": "Database access (Supabase)",
        "check": "python_script",
        "script": "scripts/supabase_tool.py",
        "env_key": "BRAVO_SUPABASE_SERVICE_ROLE_KEY",
    },
    "stripe_tool": {
        "description": "Payments (Stripe)",
        "check": "python_script",
        "script": "scripts/stripe_tool.py",
        "env_key": "STRIPE_SECRET_KEY",
    },
    "google_tool": {
        "description": "Gmail, Calendar, Drive",
        "check": "python_script",
        "script": "scripts/google_tool.py",
        "env_key": "GMAIL_USER",
    },
}


def check_npm_package(package: str) -> tuple[bool, str]:
    """Return (available, version_or_reason) for a global npm package."""
    # Try both 'npm' and the Windows-native path fallback
    npm_candidates = ["npm"]
    # On Windows, npm may be absent from bash PATH but present in the node install
    node_appdata = os.environ.get("APPDATA", "")
    if node_appdata:
        npm_candidates.append(str(Path(node_appdata).parent / "Roaming" / "npm" / "npm.cmd"))

    for npm_cmd in npm_candidates:
        try:
            result = subprocess.run(
                [npm_cmd, "list", "-g", "--depth=0", "--json"],
                capture_output=True, text=True, timeout=15,
                shell=(npm_cmd.endswith(".cmd")),
            )
            data = json.loads(result.stdout or "{}")
            deps = data.get("dependencies", {})
            if package in deps:
                version = deps[package].get("version", "unknown")
                return True, version
            # npm ran but package not found
            return False, "not installed globally"
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            return False, "npm check timed out"
        except json.JSONDecodeError:
            return False, "npm output unparseable"

    return False, "npm not found on PATH"


def check_python_script(script_relative: str, env_key: str, env_vars: dict) -> tuple[bool, str]:
    """Return (available, reason) for a CLI script."""
    script_path = PROJECT_ROOT / script_relative
    if not script_path.exists():
        return False, f"script not found at {script_path}"
    if env_key and not env_vars.get(env_key):
        return False, f"credential {env_key} missing from .env.agents"
    return True, "ready"


def cmd_health(args) -> int:
    """Report MCP server availability and CLI tool readiness. Does not load anything."""
    as_json: bool = args.json
    env_vars = load_env()

    mcp_results: dict = {}
    for name, cfg in MCP_CHECKS.items():
        available, detail = check_npm_package(cfg["package"])
        mcp_results[name] = {
            "description": cfg["description"],
            "available": available,
            "detail": detail,
        }

    cli_results: dict = {}
    for name, cfg in CLI_CHECKS.items():
        available, detail = check_python_script(
            cfg["script"], cfg.get("env_key", ""), env_vars
        )
        cli_results[name] = {
            "description": cfg["description"],
            "available": available,
            "detail": detail,
        }

    mcp_ok = sum(1 for v in mcp_results.values() if v["available"])
    cli_ok = sum(1 for v in cli_results.values() if v["available"])

    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "mcp_servers": mcp_results,
        "cli_tools": cli_results,
        "summary": {
            "mcp_available": mcp_ok,
            "mcp_total": len(mcp_results),
            "cli_available": cli_ok,
            "cli_total": len(cli_results),
        },
    }

    _emit(result, as_json, _health_human_summary(result))
    return 0


def _health_human_summary(result: dict) -> str:
    s = result["summary"]
    lines = [
        f"Health Check — {result['checked_at']}",
        "",
        f"MCP Servers ({s['mcp_available']}/{s['mcp_total']} available):",
    ]
    for name, info in result["mcp_servers"].items():
        icon = "OK" if info["available"] else "--"
        lines.append(f"  [{icon}] {name:25s} {info['description']} ({info['detail']})")

    lines.append("")
    lines.append(f"CLI Tools ({s['cli_available']}/{s['cli_total']} available):")
    for name, info in result["cli_tools"].items():
        icon = "OK" if info["available"] else "--"
        lines.append(f"  [{icon}] {name:25s} {info['description']} ({info['detail']})")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _emit(data: dict, as_json: bool, human_text: str) -> None:
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(human_text)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context_manager",
        description=(
            "SESSION_LOG compaction, tiered context loading, and MCP/CLI health checks. "
            "Inspired by Claude Code's internal transcript compaction and deferred init patterns."
        ),
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # compact
    p_compact = sub.add_parser(
        "compact",
        help="Archive old SESSION_LOG entries, keep the N most recent.",
    )
    p_compact.add_argument(
        "--keep", type=int, default=10,
        help="Number of recent entries to keep in SESSION_LOG.md (default: 10).",
    )
    p_compact.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be archived without writing any files.",
    )
    p_compact.add_argument("--json", action="store_true", help="Output JSON.")
    p_compact.set_defaults(func=cmd_compact)

    # status
    p_status = sub.add_parser(
        "status",
        help="Show SESSION_LOG line count, entry count, and recommended action.",
    )
    p_status.add_argument("--json", action="store_true", help="Output JSON.")
    p_status.set_defaults(func=cmd_status)

    # tier
    p_tier = sub.add_parser(
        "tier",
        help="Recommend which brain/memory files to load for a given query.",
    )
    p_tier.add_argument("query", help="The query or task description to classify.")
    p_tier.add_argument("--json", action="store_true", help="Output JSON.")
    p_tier.set_defaults(func=cmd_tier)

    # health
    p_health = sub.add_parser(
        "health",
        help="Check which MCP servers are installed and which CLI tools are ready.",
    )
    p_health.add_argument("--json", action="store_true", help="Output JSON.")
    p_health.set_defaults(func=cmd_health)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
