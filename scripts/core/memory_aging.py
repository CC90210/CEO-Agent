"""
Memory Aging — Confidence Decay and Health Scanner
Implements the exponential decay model defined in brain/BRAIN_LOOP.md.

Decay formula: C(t) = C0 * exp(-lambda * t)
  where t = days since last verification date found in the entry.

Lambda values by category:
  business    (pricing, clients, revenue): 0.02
  technical   (APIs, configs, versions):   0.015
  architectural (decisions, design):        0.005
  identity    (values, soul):              0.000

Usage:
  python scripts/core/memory_aging.py scan    [--json]
  python scripts/core/memory_aging.py stale   [--days 30] [--json]
  python scripts/core/memory_aging.py health  [--json]
  python scripts/core/memory_aging.py archive [--dry-run] [--json]
"""

import argparse
import io
import json
import math
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# Force UTF-8 output on Windows (cp1252 terminal chokes on em-dash, arrows, etc.)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Project root detection
# ---------------------------------------------------------------------------

def _find_project_root() -> Path:
    """Walk up from this script's directory until we find .git or CLAUDE.md."""
    candidate = Path(__file__).resolve().parent
    for _ in range(8):
        if (candidate / ".git").exists() or (candidate / "CLAUDE.md").exists():
            return candidate
        candidate = candidate.parent
    # Fallback: directory containing this script's parent
    return Path(__file__).resolve().parent.parent.parent


ROOT = _find_project_root()
TODAY = date.today()


# ---------------------------------------------------------------------------
# Decay constants (from BRAIN_LOOP.md confidence decay section)
# ---------------------------------------------------------------------------

DECAY_RATES: dict[str, float] = {
    "business":       0.02,
    "technical":      0.015,
    "architectural":  0.005,
    "identity":       0.000,
}

# Files and their primary fact category — used when no category can be inferred
FILE_CATEGORY_DEFAULTS: dict[str, str] = {
    "LONG_TERM.md":  "business",       # mix, but business facts dominate
    "PATTERNS.md":   "architectural",
    "DECISIONS.md":  "architectural",
    "STATE.md":      "business",
    "MISTAKES.md":   "technical",
}

# Section headers in LONG_TERM.md hint at the category
SECTION_CATEGORY_MAP: dict[str, str] = {
    "architecture":   "architectural",
    "business":       "business",
    "technical":      "technical",
    "identity":       "identity",
    "values":         "identity",
    "facts":          "technical",
}

# File line budgets from skills/memory-management/SKILL.md
LINE_BUDGETS: dict[str, int] = {
    "SESSION_LOG.md":  200,
    "ACTIVE_TASKS.md":  50,
    "MISTAKES.md":      30,
    "PATTERNS.md":      30,
}
BRAIN_COMBINED_BUDGET = 2500  # V5.5: 17 agents, 180 skills, CEO OS — structural files are large by design

# Archive retention thresholds
SESSION_LOG_ARCHIVE_DAYS = 14
ACTIVE_TASKS_DONE_DAYS   = 7

# Regex patterns
DATE_PATTERN     = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
# Table row with confidence: | text | 0.85 | ... | YYYY-MM-DD |
TABLE_ROW_CONF   = re.compile(
    r"^\|(.+?)\|\s*(0\.\d+)\s*\|(.+?)\|\s*(\d{4}-\d{2}-\d{2})\s*\|"
)
# Inline confidence tag anywhere in a line: confidence: 0.85 or C=0.90
INLINE_CONF      = re.compile(r"(?:confidence|C)\s*[=:]\s*(0\.\d+)", re.IGNORECASE)
# Entry header (### or ## followed by a date)
ENTRY_HEADER     = re.compile(r"^(#{2,3})\s+(\d{4}-\d{2}-\d{2})\s*[—–-]\s*(.+)$")
# "Last synced:", "Last Verified:", "Updated YYYY-MM-DD"
SYNCED_PATTERN   = re.compile(
    r"(?:last\s+(?:synced|verified|updated)|updated)\s*[:\s]*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
# PROBATIONARY / VALIDATED tag
PROBATIONARY_PAT = re.compile(r"\[PROBATIONARY\]", re.IGNORECASE)
VALIDATED_PAT    = re.compile(r"\[VALIDATED\]",    re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _days_since(d: date) -> int:
    return max(0, (TODAY - d).days)


def _decay(c0: float, lam: float, days: int) -> float:
    return c0 * math.exp(-lam * days)


def _confidence_band(c: float) -> str:
    if c >= 0.8:
        return "HIGH"
    if c >= 0.5:
        return "MEDIUM"
    if c >= 0.2:
        return "LOW"
    return "STALE"


def _infer_category(section_header: str, filename: str) -> str:
    """Return decay category based on current section header and file."""
    h = section_header.lower()
    for keyword, cat in SECTION_CATEGORY_MAP.items():
        if keyword in h:
            return cat
    return FILE_CATEGORY_DEFAULTS.get(filename, "technical")


def _count_lines(path: Path) -> int:
    try:
        return sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
    except OSError:
        return 0


def _fuzzy_title(title: str) -> str:
    """Reduce a title to a normalized key for duplicate detection."""
    # strip punctuation, lowercase, collapse whitespace
    s = re.sub(r"[^\w\s]", "", title.lower())
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# Entry extraction
# ---------------------------------------------------------------------------

class Entry:
    """One logical memory entry extracted from a markdown file."""

    __slots__ = (
        "file", "lineno", "title", "category",
        "confidence_original", "last_date", "days_since",
        "confidence_current", "band", "is_probationary",
    )

    def __init__(
        self,
        file: str,
        lineno: int,
        title: str,
        category: str,
        confidence_original: float,
        last_date: Optional[date],
    ):
        self.file                = file
        self.lineno              = lineno
        self.title               = title
        self.category            = category
        self.confidence_original = confidence_original
        self.last_date           = last_date
        self.days_since          = _days_since(last_date) if last_date else 0
        lam                      = DECAY_RATES[category]
        self.confidence_current  = _decay(confidence_original, lam, self.days_since)
        self.band                = _confidence_band(self.confidence_current)
        self.is_probationary     = False  # set by caller if needed

    def to_dict(self) -> dict:
        return {
            "file":                 self.file,
            "line":                 self.lineno,
            "title":                self.title[:80],
            "category":             self.category,
            "confidence_original":  round(self.confidence_original, 3),
            "confidence_current":   round(self.confidence_current,  3),
            "last_date":            self.last_date.isoformat() if self.last_date else None,
            "days_since":           self.days_since,
            "band":                 self.band,
            "is_probationary":      self.is_probationary,
        }


def _extract_entries_from_file(rel_path: str) -> list[Entry]:
    """
    Parse a memory markdown file and return a list of Entry objects.

    Handles two structures present in the actual files:
      1. Table rows: | Fact text | 0.85 | Source | 2026-03-26 |
      2. Section headers: ### YYYY-MM-DD — Entry title
    """
    full_path = ROOT / rel_path
    if not full_path.exists():
        return []

    filename  = full_path.name
    entries: list[Entry] = []
    current_section = ""

    try:
        lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    for lineno, raw in enumerate(lines, start=1):
        line = raw.strip()

        # Track the active markdown section for category inference
        if line.startswith("## ") and not line.startswith("### "):
            current_section = line.lstrip("#").strip().lower()
            continue

        # --- Pattern 1: Table row with confidence + date ---
        m = TABLE_ROW_CONF.match(line)
        if m:
            fact_text   = m.group(1).strip()
            confidence  = float(m.group(2))
            date_str    = m.group(4)
            last_date   = _parse_date(date_str)
            cat         = _infer_category(current_section, filename)
            e = Entry(
                file=rel_path,
                lineno=lineno,
                title=fact_text[:120],
                category=cat,
                confidence_original=confidence,
                last_date=last_date,
            )
            entries.append(e)
            continue

        # --- Pattern 2: Section entry header ### YYYY-MM-DD — Title ---
        m = ENTRY_HEADER.match(line)
        if m:
            entry_date_str = m.group(2)
            entry_title    = m.group(3).strip()
            last_date      = _parse_date(entry_date_str)
            # Look ahead a few lines for an inline confidence tag
            confidence     = 0.80  # default for dated entries
            for lookahead in lines[lineno : lineno + 6]:
                ic = INLINE_CONF.search(lookahead)
                if ic:
                    confidence = float(ic.group(1))
                    break
            cat = _infer_category(current_section, filename)
            e = Entry(
                file=rel_path,
                lineno=lineno,
                title=entry_title[:120],
                category=cat,
                confidence_original=confidence,
                last_date=last_date,
            )
            # Check for probationary tag
            e.is_probationary = bool(PROBATIONARY_PAT.search(entry_title))
            entries.append(e)
            continue

        # --- Pattern 3: "Last synced: / Updated YYYY-MM-DD" in STATE.md ---
        m2 = SYNCED_PATTERN.search(line)
        if m2 and filename == "STATE.md" and not entries:
            # Create a synthetic entry representing the whole file's freshness
            last_date  = _parse_date(m2.group(1))
            confidence = 0.99
            cat        = FILE_CATEGORY_DEFAULTS.get(filename, "business")
            e = Entry(
                file=rel_path,
                lineno=lineno,
                title=f"{filename} — current state snapshot",
                category=cat,
                confidence_original=confidence,
                last_date=last_date,
            )
            entries.append(e)

    return entries


MEMORY_FILES = [
    "memory/LONG_TERM.md",
    "memory/PATTERNS.md",
    "memory/DECISIONS.md",
    "memory/MISTAKES.md",
    "brain/STATE.md",
]


def _all_entries() -> list[Entry]:
    result = []
    for f in MEMORY_FILES:
        result.extend(_extract_entries_from_file(f))
    return result


# ---------------------------------------------------------------------------
# Command: scan
# ---------------------------------------------------------------------------

def cmd_scan(args: argparse.Namespace) -> None:
    """Print all memory entries with their decayed confidence scores."""
    entries = _all_entries()

    if not entries:
        _out(args, {"error": "No entries found"}, "No entries found in memory files.")
        return

    rows = [e.to_dict() for e in sorted(entries, key=lambda e: e.confidence_current)]

    flagged = [r for r in rows if r["band"] in ("LOW", "STALE")]

    if args.json:
        _print_json({"entries": rows, "flagged_count": len(flagged)})
        return

    # Human-readable table
    print(f"\nMemory Aging Scan — {TODAY.isoformat()}")
    print(f"{'File':<28} {'Line':>5}  {'C0':>5}  {'C(t)':>5}  {'Days':>4}  Band     Title")
    print("-" * 100)
    for r in rows:
        marker = " [!]" if r["band"] in ("LOW", "STALE") else ""
        print(
            f"{r['file']:<28} {r['line']:>5}  "
            f"{r['confidence_original']:>5.2f}  {r['confidence_current']:>5.2f}  "
            f"{r['days_since']:>4}  {r['band']:<8} "
            f"{r['title'][:60]}{marker}"
        )
    print(f"\n{len(flagged)} entries below 0.5 confidence (LOW or STALE).")


# ---------------------------------------------------------------------------
# Command: stale
# ---------------------------------------------------------------------------

def cmd_stale(args: argparse.Namespace) -> None:
    """Find facts not updated in N days."""
    threshold = args.days
    entries   = _all_entries()
    stale     = [e for e in entries if e.days_since >= threshold]
    stale.sort(key=lambda e: e.days_since, reverse=True)

    rows = [e.to_dict() for e in stale]

    if args.json:
        _print_json({"threshold_days": threshold, "stale_count": len(rows), "entries": rows})
        return

    print(f"\nStale Facts (>= {threshold} days since last date) — {TODAY.isoformat()}")
    if not rows:
        print("  None. All entries are within the freshness window.")
        return

    print(f"{'File':<28} {'Line':>5}  {'Days':>5}  {'Last Date':<12}  Title")
    print("-" * 95)
    for r in rows:
        print(
            f"{r['file']:<28} {r['line']:>5}  "
            f"{r['days_since']:>5}  {str(r['last_date']):<12}  "
            f"{r['title'][:60]}"
        )
    print(f"\n{len(rows)} stale entries found.")


# ---------------------------------------------------------------------------
# Command: health
# ---------------------------------------------------------------------------

def cmd_health(args: argparse.Namespace) -> None:
    """Overall memory system health report."""
    entries = _all_entries()

    band_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "STALE": 0}
    for e in entries:
        band_counts[e.band] += 1

    total_age = sum(e.days_since for e in entries)
    avg_age   = round(total_age / len(entries), 1) if entries else 0.0

    # Line budget checks
    budget_violations: list[dict] = []
    for fname, budget in LINE_BUDGETS.items():
        path  = ROOT / "memory" / fname
        count = _count_lines(path)
        if count > budget:
            budget_violations.append({
                "file":   f"memory/{fname}",
                "lines":  count,
                "budget": budget,
                "over_by": count - budget,
            })

    # brain/ combined line count
    brain_files = list((ROOT / "brain").glob("*.md"))
    brain_total = sum(_count_lines(f) for f in brain_files)
    if brain_total > BRAIN_COMBINED_BUDGET:
        budget_violations.append({
            "file":    "brain/ (combined)",
            "lines":   brain_total,
            "budget":  BRAIN_COMBINED_BUDGET,
            "over_by": brain_total - BRAIN_COMBINED_BUDGET,
        })

    # Duplicate detection (fuzzy title match across all entries)
    seen_titles: dict[str, list[str]] = {}
    for e in entries:
        key = _fuzzy_title(e.title)
        if key not in seen_titles:
            seen_titles[key] = []
        seen_titles[key].append(e.file)

    duplicates = [
        {"title": t[:80], "found_in": locs}
        for t, locs in seen_titles.items()
        if len(locs) > 1
    ]

    # Probationary entries
    probationary = [e.to_dict() for e in entries if e.is_probationary]

    health_score = _compute_health_score(band_counts, budget_violations, duplicates)

    report = {
        "date":           TODAY.isoformat(),
        "health_score":   health_score,
        "total_entries":  len(entries),
        "average_age_days": avg_age,
        "confidence_bands": band_counts,
        "budget_violations": budget_violations,
        "duplicate_count":  len(duplicates),
        "duplicates":       duplicates,
        "probationary_count": len(probationary),
        "probationary":     probationary,
    }

    if args.json:
        _print_json(report)
        return

    # Human-readable report
    grade = _health_grade(health_score)
    print(f"\nMemory Health Report — {TODAY.isoformat()}  [{grade}  {health_score}/100]")
    print("=" * 60)
    print(f"  Total entries scanned : {len(entries)}")
    print(f"  Average entry age     : {avg_age} days")
    print()
    print("  Confidence distribution:")
    for band, count in band_counts.items():
        bar = "#" * count
        print(f"    {band:<8} {count:>3}  {bar}")

    print()
    if budget_violations:
        print("  Line budget violations:")
        for v in budget_violations:
            print(f"    {v['file']:<35} {v['lines']} lines  (budget {v['budget']}, over by {v['over_by']})")
    else:
        print("  Line budgets: all within limits.")

    print()
    if duplicates:
        print(f"  Duplicate entries detected: {len(duplicates)}")
        for d in duplicates[:5]:
            print(f"    '{d['title'][:50]}' in: {', '.join(d['found_in'])}")
        if len(duplicates) > 5:
            print(f"    ... and {len(duplicates) - 5} more.")
    else:
        print("  Duplicates: none detected.")

    print()
    if probationary:
        print(f"  Probationary entries (need 3+ sessions to validate): {len(probationary)}")
        for p in probationary[:5]:
            print(f"    {p['file']}:{p['line']}  {p['title'][:60]}")
    else:
        print("  Probationary entries: none.")


def _compute_health_score(
    bands: dict[str, int],
    violations: list[dict],
    duplicates: list[dict],
) -> int:
    score = 100
    score -= bands.get("LOW",   0) * 3
    score -= bands.get("STALE", 0) * 5
    score -= len(violations) * 8
    score -= len(duplicates) * 2
    return max(0, min(100, score))


def _health_grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


# ---------------------------------------------------------------------------
# Command: archive
# ---------------------------------------------------------------------------

def cmd_archive(args: argparse.Namespace) -> None:
    """
    Archive stale/completed entries per memory-management/SKILL.md rules:
      - SESSION_LOG entries older than 14 days → memory/ARCHIVES/sessions-YYYY-MM.md
      - ACTIVE_TASKS [x] items older than 7 days → removed
    """
    dry_run = args.dry_run
    actions: list[dict] = []

    actions.extend(_archive_session_log(dry_run))
    actions.extend(_archive_active_tasks(dry_run))

    if args.json:
        _print_json({"dry_run": dry_run, "actions": actions})
        return

    label = "[DRY RUN] " if dry_run else ""
    print(f"\n{label}Archive — {TODAY.isoformat()}")
    if not actions:
        print("  Nothing to archive. All files within thresholds.")
        return
    for a in actions:
        print(f"  {a['type']:<18} {a.get('file', '')}  {a.get('detail', '')}")
    if dry_run:
        print("\nRun without --dry-run to apply changes.")


def _archive_session_log(dry_run: bool) -> list[dict]:
    """Move SESSION_LOG entries older than SESSION_LOG_ARCHIVE_DAYS to monthly archive."""
    actions: list[dict] = []
    src = ROOT / "memory" / "SESSION_LOG.md"
    if not src.exists():
        return actions

    try:
        text = src.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return actions

    lines       = text.splitlines(keepends=True)
    total_count = sum(1 for _ in lines)

    if total_count <= LINE_BUDGETS["SESSION_LOG.md"]:
        return actions  # Within budget — nothing to do

    # Split on "### YYYY-MM-DD" section headers
    sections: list[tuple[str, list[str]]] = []  # (date_str, lines)
    current_date_str = ""
    current_lines: list[str] = []

    for line in lines:
        m = re.match(r"^### (\d{4}-\d{2}-\d{2})", line)
        if m:
            if current_lines:
                sections.append((current_date_str, current_lines))
            current_date_str = m.group(1)
            current_lines    = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_date_str, current_lines))

    cutoff     = TODAY - timedelta(days=SESSION_LOG_ARCHIVE_DAYS)
    keep: list[tuple[str, list[str]]]    = []
    archive: list[tuple[str, list[str]]] = []

    for date_str, sec_lines in sections:
        d = _parse_date(date_str)
        if d and d < cutoff:
            archive.append((date_str, sec_lines))
        else:
            keep.append((date_str, sec_lines))

    if not archive:
        return actions

    # Group archived sections by YYYY-MM for file naming
    by_month: dict[str, list[str]] = {}
    for date_str, sec_lines in archive:
        month_key = date_str[:7]  # "YYYY-MM"
        by_month.setdefault(month_key, []).extend(sec_lines)

    for month_key, month_lines in by_month.items():
        archive_path = ROOT / "memory" / "ARCHIVES" / f"sessions-{month_key}.md"
        actions.append({
            "type":   "archive_session",
            "file":   str(archive_path.relative_to(ROOT)),
            "detail": f"Moving {len([l for l in month_lines if l.strip().startswith('###')])} session(s) from {month_key}",
        })
        if not dry_run:
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            # Append to existing archive or create
            existing = ""
            if archive_path.exists():
                existing = archive_path.read_text(encoding="utf-8", errors="replace")
            archive_path.write_text(
                existing + "".join(month_lines),
                encoding="utf-8",
            )

    if not dry_run and keep:
        # Rebuild SESSION_LOG.md with only the kept sections
        # Preserve YAML frontmatter and document header (lines before first ### section)
        header_lines: list[str] = []
        for _, sec_lines in sections:
            if not _parse_date(_):
                header_lines = sec_lines
                break

        new_content = "".join(header_lines) + "".join(
            l for _, sec in keep for l in sec
        )
        src.write_text(new_content, encoding="utf-8")

    actions.append({
        "type":   "prune_session_log",
        "file":   "memory/SESSION_LOG.md",
        "detail": f"Kept {len(keep)} recent session(s), archived {len(archive)} old session(s)",
    })
    return actions


def _archive_active_tasks(dry_run: bool) -> list[dict]:
    """Remove [x] (completed) ACTIVE_TASKS entries older than ACTIVE_TASKS_DONE_DAYS."""
    actions: list[dict] = []
    src = ROOT / "memory" / "ACTIVE_TASKS.md"
    if not src.exists():
        return actions

    try:
        lines = src.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    except OSError:
        return actions

    # Count only task items (lines starting with "- [")
    task_items = [l for l in lines if re.match(r"^\s*- \[", l)]
    done_items = [l for l in task_items if re.match(r"^\s*- \[x\]", l, re.IGNORECASE)]

    if len(task_items) <= LINE_BUDGETS["ACTIVE_TASKS.md"] and not done_items:
        return actions

    cutoff = TODAY - timedelta(days=ACTIVE_TASKS_DONE_DAYS)
    removed = 0
    new_lines: list[str] = []

    for line in lines:
        if re.match(r"^\s*- \[x\]", line, re.IGNORECASE):
            # Extract any date in the line
            dates_in_line = DATE_PATTERN.findall(line)
            entry_date    = None
            for ds in reversed(dates_in_line):  # last date = most recent
                entry_date = _parse_date(ds)
                if entry_date:
                    break
            if entry_date and entry_date < cutoff:
                removed += 1
                continue  # drop this line
        new_lines.append(line)

    if removed == 0:
        return actions

    actions.append({
        "type":   "prune_active_tasks",
        "file":   "memory/ACTIVE_TASKS.md",
        "detail": f"Removed {removed} completed task(s) older than {ACTIVE_TASKS_DONE_DAYS} days",
    })

    if not dry_run:
        src.write_text("".join(new_lines), encoding="utf-8")

    return actions


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2, default=str))


def _out(args: argparse.Namespace, data: object, text: str) -> None:
    if args.json:
        _print_json(data)
    else:
        print(text)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memory_aging",
        description="Bravo memory aging — confidence decay, stale detection, health report, archiving.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # scan
    p_scan = sub.add_parser("scan", help="Show all entries with decayed confidence scores")
    p_scan.add_argument("--json", action="store_true", help="Output JSON for agent consumption")

    # stale
    p_stale = sub.add_parser("stale", help="Find facts not updated in N days")
    p_stale.add_argument("--days", type=int, default=30, help="Staleness threshold in days (default: 30)")
    p_stale.add_argument("--json", action="store_true")

    # health
    p_health = sub.add_parser("health", help="Overall memory system health report")
    p_health.add_argument("--json", action="store_true")

    # archive
    p_archive = sub.add_parser("archive", help="Move stale/completed entries to archives")
    p_archive.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    p_archive.add_argument("--json", action="store_true")

    return parser


def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    dispatch = {
        "scan":    cmd_scan,
        "stale":   cmd_stale,
        "health":  cmd_health,
        "archive": cmd_archive,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
