"""V6.0 transactional state manager — single writer for `state/empire_state.db`.

Replaces direct flat-file mutation of:
  - brain/STATE.md (Last Heartbeat block)
  - memory/SESSION_LOG.md (entries)
  - memory/ACTIVE_TASKS.md (programmatic task rows)

Concurrency: SQLite WAL + BEGIN IMMEDIATE + busy_timeout=5000 ms gives
one-writer / many-readers across processes (Bravo + Codex + Atlas + cron).

CLI:
  python scripts/state/state_manager.py heartbeat --agent bravo --status working --focus "..."
  python scripts/state/state_manager.py log --note "..." [--artifacts file1.py,file2.py]
  python scripts/state/state_manager.py task add    --bucket TODAY --title "..."
  python scripts/state/state_manager.py task close  --id 42
  python scripts/state/state_manager.py task list   [--bucket TODAY] [--status open]
  python scripts/state/state_manager.py export
  python scripts/state/state_manager.py export --check       # exits 1 if mirror is stale
  python scripts/state/state_manager.py import-from-files    # one-time bootstrap from existing markdown
  python scripts/state/state_manager.py status               # quick overview
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator, Sequence

# Project root is THREE levels up:
#   scripts/state/state_manager.py → scripts/state → scripts → <repo root>
# The file moved into scripts/state/ during the 2026-05-20 reorg without
# updating these parent counts; the result was that PROJECT_ROOT pointed
# at scripts/, STATE_DIR pointed at scripts/state/ (where the script
# lives, not where the real DB sits).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_DIR = PROJECT_ROOT / "state"
DB_PATH = STATE_DIR / "empire_state.db"
MIGRATIONS_DIR = STATE_DIR / "migrations"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

STATE_MD = PROJECT_ROOT / "brain" / "STATE.md"
SESSION_LOG_MD = PROJECT_ROOT / "memory" / "SESSION_LOG.md"
ACTIVE_TASKS_MD = PROJECT_ROOT / "memory" / "ACTIVE_TASKS.md"

SESSION_LOG_AUTO_BEGIN = "<!-- AUTO-GENERATED-BEGIN: state_manager.py — do not edit between markers -->"
SESSION_LOG_AUTO_END = "<!-- AUTO-GENERATED-END -->"

_FRONTMATTER_RE = re.compile(
    r"\A(?:\ufeff)?---[ \t]*\r?\n.*?^---[ \t]*(?:\r?\n|\Z)",
    re.DOTALL | re.MULTILINE,
)
_AUTO_SECTION_RE = re.compile(
    rf"^{re.escape(SESSION_LOG_AUTO_BEGIN)}[ \t]*\r?\n.*?"
    rf"^{re.escape(SESSION_LOG_AUTO_END)}[ \t]*(?:\r?\n|\Z)",
    re.DOTALL | re.MULTILINE,
)
_DATED_ENTRY_HEADER_RE = re.compile(
    r"^###\s+(\d{4}-\d{2}-\d{2})\s*[—–-]\s*(.*?)\s*$",
)

VALID_AGENTS = {"bravo", "codex", "atlas", "maven", "hermes", "aura", "lex", "cc", "sunbiz", "suga_sean"}
VALID_BUCKETS = {"TODAY", "P0", "P1", "P2", "WARM_LEADS", "ARCHIVE"}
VALID_STATUSES = {"open", "done", "blocked", "archived"}

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _session_id() -> str:
    sid = os.environ.get("BRAVO_SESSION_ID")
    if sid:
        return sid
    return f"auto-{uuid.uuid4().hex[:12]}"


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


# ── DB plumbing ──────────────────────────────────────────────────────────────

def connect(read_only: bool = False) -> sqlite3.Connection:
    _ensure_state_dir()
    if read_only and DB_PATH.exists():
        uri = f"file:{DB_PATH.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0, isolation_level=None)
    else:
        conn = sqlite3.connect(str(DB_PATH), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    if not read_only:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _apply_migrations(conn)
    return conn


def _apply_migrations(conn: sqlite3.Connection) -> None:
    if not MIGRATIONS_DIR.exists():
        return
    for path in sorted(MIGRATIONS_DIR.glob("0*.sql")):
        # *_memory_*.sql migrations (002_memory_index, 003_memory_abstract, …)
        # belong to the FTS5 retrieval DB and are owned/applied by
        # memory_retriever.py — running them here crashes against the state DB
        # (V7.3.0 lesson: 003 assumed 002's tables and broke 4 tests when the
        # old `002_`-only skip let it through).
        if "_memory_" in path.name:
            continue
        sql = path.read_text(encoding="utf-8")
        conn.executescript(sql)


@contextmanager
def transaction(conn: sqlite3.Connection, actor: str, op: str,
                source_script: str | None = None) -> Iterator[sqlite3.Connection]:
    """`BEGIN IMMEDIATE` + auto-rollback + audit-log on commit."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute(
            "INSERT INTO state_transaction(ts, actor, op, table_name, row_pk, diff_json, source_script) "
            "VALUES (?,?,?,?,?,?,?)",
            (_now_iso(), actor, op, "", None, None, source_script or _detect_source()),
        )
        conn.execute("COMMIT")


_STDLIB_HINTS = ("contextlib.py", "runpy.py", "<frozen", "_bootstrap")


def _detect_source() -> str:
    frame = sys._getframe(1) if hasattr(sys, "_getframe") else None
    while frame is not None:
        fname = frame.f_globals.get("__file__")
        if fname:
            if "state_manager" in fname:
                frame = frame.f_back
                continue
            if any(hint in fname for hint in _STDLIB_HINTS):
                frame = frame.f_back
                continue
            return Path(fname).name
        frame = frame.f_back
    return "state_manager.py"


# ── Public API ───────────────────────────────────────────────────────────────

def heartbeat(agent: str, status: str = "working", focus: str | None = None,
              payload: dict | None = None, conn: sqlite3.Connection | None = None) -> None:
    agent = (agent or "bravo").lower().strip()
    if agent not in VALID_AGENTS:
        raise ValueError(f"unknown agent: {agent}")
    own = conn is None
    conn = conn or connect()
    try:
        with transaction(conn, actor=agent, op="heartbeat"):
            row = conn.execute("SELECT tick_count FROM agent_state WHERE agent=?", (agent,)).fetchone()
            tick = (row["tick_count"] + 1) if row else 1
            conn.execute(
                "INSERT INTO agent_state(agent,status,current_focus,last_heartbeat,tick_count,health,payload_json) "
                "VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(agent) DO UPDATE SET "
                "  status=excluded.status,"
                "  current_focus=excluded.current_focus,"
                "  last_heartbeat=excluded.last_heartbeat,"
                "  tick_count=excluded.tick_count,"
                "  health=excluded.health,"
                "  payload_json=excluded.payload_json",
                (agent, status, focus, _now_iso(), tick, "green",
                 json.dumps(payload) if payload else None),
            )
        _mirror_supabase_heartbeat(agent, focus, payload)
    finally:
        if own:
            conn.close()


def _mirror_supabase_heartbeat(agent: str, focus: str | None,
                               payload: dict | None) -> None:
    """Best-effort write to the Supabase `agent_state_snapshot` table.

    Failures never propagate — the local DB is the source of truth; Supabase
    is the cloud mirror for the OASIS dashboard. Called from inside heartbeat()
    so anyone using `state_manager` directly (not just state_sync.py) keeps
    the cloud view current.
    """
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from agent_heartbeat import heartbeat as supa_heartbeat  # type: ignore
        wm: dict = {"last_focus": (focus or "")[:200]}
        if payload:
            wm["payload"] = payload
        supa_heartbeat(agent, working_memory=wm)
    except Exception:
        pass


def append_session_log(note: str, agent: str = "bravo",
                       session_id: str | None = None,
                       artifacts: dict | None = None,
                       conn: sqlite3.Connection | None = None) -> str:
    """Insert a session log row. UNIQUE(session_id, note) gives atomic dedup.

    Returns 'inserted' or 'deduped'.
    """
    agent = (agent or "bravo").lower().strip()
    if agent not in VALID_AGENTS:
        agent = "bravo"
    sid = session_id or _session_id()
    own = conn is None
    conn = conn or connect()
    try:
        with transaction(conn, actor=agent, op="append_session_log"):
            try:
                conn.execute(
                    "INSERT INTO session_log(ts, agent, session_id, note, artifacts_json) "
                    "VALUES (?,?,?,?,?)",
                    (_now_iso(), agent, sid, note,
                     json.dumps(artifacts) if artifacts else None),
                )
                result = "inserted"
            except sqlite3.IntegrityError:
                result = "deduped"
    finally:
        if own:
            conn.close()
    # V6 BUILD 3 — emit a cross-agent event on every NEW session_log row.
    # Best-effort: failures never propagate. Skipped on dedup since the
    # event would also be a duplicate. Event type and source both track the
    # writing agent so SUNBIZ writes emit SUNBIZ_SESSION_LOG_APPENDED, etc.
    if result == "inserted":
        _emit_cross_agent_event(
            f"{agent.upper()}_SESSION_LOG_APPENDED",
            {"agent": agent, "session_id": sid, "note": note[:200]},
            source=agent,
            target=None,  # broadcast — Atlas/Maven/Aura all may want this
            correlation_id=sid,
        )
    return result


def _emit_cross_agent_event(event_type: str, payload: dict,
                            source: str = "bravo",
                            target: str | None = None,
                            correlation_id: str | None = None) -> None:
    """Best-effort wrapper around event_bus.publish — never raises.

    Lazy-imported because event_bus pulls in the supabase client which is
    a heavyweight dep that some scripts running in headless CI shouldn't pay.
    The `source` parameter lets non-Bravo agents (sunbiz, etc.) emit events
    under their own identity rather than masquerading as Bravo.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        # Lazy import: event_bus pulls the heavyweight supabase client and
        # is not needed by callers who only want state-DB operations.
        from event_bus import publish as _bus_publish  # type: ignore[import-not-found]
        _bus_publish(event_type, payload, source=source,
                     target=target, correlation_id=correlation_id)
    except Exception:  # noqa: BLE001
        pass  # publish() already absorbs all errors; this catches import failures


def upsert_task(bucket: str, title: str, owner: str = "bravo",
                priority: int = 100, status: str = "open",
                conn: sqlite3.Connection | None = None) -> int:
    if bucket not in VALID_BUCKETS:
        raise ValueError(f"unknown bucket: {bucket}")
    if status not in VALID_STATUSES:
        raise ValueError(f"unknown status: {status}")
    own = conn is None
    conn = conn or connect()
    try:
        with transaction(conn, actor=owner, op="upsert_task"):
            row = conn.execute(
                "SELECT id FROM active_task WHERE bucket=? AND title=? AND status!='archived'",
                (bucket, title),
            ).fetchone()
            now = _now_iso()
            if row:
                conn.execute(
                    "UPDATE active_task SET updated_at=?, priority=?, status=?, owner=? WHERE id=?",
                    (now, priority, status, owner, row["id"]),
                )
                return row["id"]
            cur = conn.execute(
                "INSERT INTO active_task(created_at, updated_at, bucket, owner, title, status, priority) "
                "VALUES (?,?,?,?,?,?,?)",
                (now, now, bucket, owner, title, status, priority),
            )
            return cur.lastrowid
    finally:
        if own:
            conn.close()



# Override-request surface (create/approve/deny/find/consume/list/cleanup +
# _mirror_override_row helper) was deleted 2026-05-22 along with the
# entire exec_override approval-request system. See scripts/state/exec_guard.py
# for the rationale. The block in exec_guard is still in place — it just
# refuses destructive commands outright rather than creating an approval queue.


def close_task(task_id: int, status: str = "done",
               conn: sqlite3.Connection | None = None) -> bool:
    if status not in VALID_STATUSES:
        raise ValueError(f"unknown status: {status}")
    own = conn is None
    conn = conn or connect()
    try:
        with transaction(conn, actor="bravo", op="close_task"):
            cur = conn.execute(
                "UPDATE active_task SET status=?, updated_at=?, closed_at=? WHERE id=?",
                (status, _now_iso(), _now_iso(), task_id),
            )
            return cur.rowcount > 0
    finally:
        if own:
            conn.close()


# ── Markdown export (read-only mirror for CC and the IDE) ───────────────────

_HEARTBEAT_BLOCK = re.compile(
    r"## Last Heartbeat\n.*?\*Last updated:.*?\*",
    re.DOTALL,
)


def _render_heartbeat_block(agent: str, last_iso: str, focus: str | None,
                            tick: int, status: str) -> str:
    today = last_iso.split("T", 1)[0]
    note = focus or status
    return (
        "## Last Heartbeat\n\n"
        f"- **Date:** {today}\n"
        f"- **Agent:** {agent.upper()} via state_manager.py (tick {tick})\n"
        f"- **Status:** {status}\n"
        f"- **Result:** {note}\n\n"
        f"*Last updated: {today}*"
    )


def _auto_marker_counts(text: str) -> tuple[int, int]:
    begin = len(re.findall(
        rf"(?m)^{re.escape(SESSION_LOG_AUTO_BEGIN)}[ \t]*\r?$", text,
    ))
    end = len(re.findall(
        rf"(?m)^{re.escape(SESSION_LOG_AUTO_END)}[ \t]*\r?$", text,
    ))
    return begin, end


def _without_auto_sections(text: str) -> tuple[str, int]:
    """Remove DB-owned mirror sections before considering Markdown imports.

    Returns the human-authored remainder plus the number of rendered entry
    headings ignored. Unbalanced/nested markers fail closed: guessing which
    side is human-authored is how a mirror becomes a source of truth by accident.
    """
    begin, end = _auto_marker_counts(text)
    sections = list(_AUTO_SECTION_RE.finditer(text))
    if begin != end or len(sections) != begin:
        raise RuntimeError(
            "SESSION_LOG auto-generated markers are unbalanced or nested; "
            "refusing reconciliation"
        )
    ignored = sum(len(_ENTRY_RE.findall(match.group(0))) for match in sections)
    return _AUTO_SECTION_RE.sub("", text), ignored


def _markerless_legacy_body(text: str) -> str:
    """Human-authored body that would be replaced by the first DB export."""
    begin, end = _auto_marker_counts(text)
    if begin != end:
        raise RuntimeError(
            "SESSION_LOG auto-generated markers are unbalanced; refusing reconciliation"
        )
    if begin:
        # Validate nesting/order even though a marked file is not "legacy".
        _without_auto_sections(text)
        return ""
    fm = _FRONTMATTER_RE.match(text)
    return text[fm.end() if fm else 0:]


def _legacy_archive_path(text: str) -> Path | None:
    if not _markerless_legacy_body(text).strip():
        return None
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return SESSION_LOG_MD.parent / "ARCHIVES" / f"session-log-legacy-{digest}.md"


def _archive_markerless_session_log(text: str) -> Path | None:
    """Preserve a markerless SESSION_LOG snapshot before DB-owned replacement.

    The content hash makes retries idempotent. An existing path with different
    content is treated as a collision/corruption and blocks the export.
    """
    archive_path = _legacy_archive_path(text)
    if archive_path is None:
        return None
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with archive_path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(text)
    except FileExistsError:
        existing = archive_path.read_text(encoding="utf-8")
        if existing != text:
            raise RuntimeError(
                f"legacy SESSION_LOG archive hash collision at {archive_path}"
            )
    return archive_path


def _compute_targets(conn: sqlite3.Connection,
                     limit: int = 200) -> dict:
    """Single source of truth for export rendering.

    Computes `before`/`after` content for every mirror file based on current
    DB state, returning everything `export` needs to write AND everything
    `export --check` needs to diff. Eliminates drift between the two paths.
    """
    # ── STATE.md heartbeat block ──
    row = conn.execute(
        "SELECT agent, status, current_focus, last_heartbeat, tick_count "
        "FROM agent_state WHERE agent='bravo'"
    ).fetchone()
    state_block = ""
    if row:
        state_block = _render_heartbeat_block(
            row["agent"], row["last_heartbeat"], row["current_focus"],
            row["tick_count"], row["status"],
        )
    state_before = STATE_MD.read_text(encoding="utf-8") if STATE_MD.exists() else ""
    if state_block and _HEARTBEAT_BLOCK.search(state_before):
        state_after = _HEARTBEAT_BLOCK.sub(lambda _m: state_block, state_before)
    elif state_block:
        state_after = state_before.rstrip() + "\n\n" + state_block + "\n"
    else:
        state_after = state_before

    # ── SESSION_LOG.md auto-generated section ──
    log_rows = conn.execute(
        "SELECT ts, agent, note FROM session_log ORDER BY ts DESC LIMIT ?",
        (limit,),
    ).fetchall()
    rendered_entries = _render_session_log_entries(log_rows)
    log_body = (
        f"{SESSION_LOG_AUTO_BEGIN}\n"
        f"<!-- regenerated by state_manager.py — last {len(log_rows)} entries from empire_state.db -->\n\n"
        f"{rendered_entries}\n\n"
        f"{SESSION_LOG_AUTO_END}"
    )
    log_before = SESSION_LOG_MD.read_text(encoding="utf-8") if SESSION_LOG_MD.exists() else ""
    begin_markers, end_markers = _auto_marker_counts(log_before)
    _without_auto_sections(log_before)  # marker-integrity validation
    if begin_markers > 1:
        raise RuntimeError(
            "SESSION_LOG contains multiple auto-generated sections; refusing export"
        )
    legacy_archive = _legacy_archive_path(log_before)
    if begin_markers == 1 and end_markers == 1:
        log_after = re.sub(
            re.escape(SESSION_LOG_AUTO_BEGIN) + r".*?" + re.escape(SESSION_LOG_AUTO_END),
            lambda _m: log_body,
            log_before,
            count=1,
            flags=re.DOTALL,
        )
    else:
        fm_match = _FRONTMATTER_RE.match(log_before)
        frontmatter = (
            fm_match.group(0).rstrip("\r\n") + "\n\n"
            if fm_match else "---\ntags: [daily]\n---\n\n"
        )
        log_after = frontmatter + log_body + "\n"

    return {
        "state_md": {"before": state_before, "after": state_after, "block": state_block},
        "session_log_md": {
            "before": log_before,
            "after": log_after,
            "rows": len(log_rows),
            "markerless_legacy": legacy_archive is not None,
            "legacy_archive_path": str(legacy_archive) if legacy_archive else None,
        },
    }


def _render_session_log_entries(rows: Sequence[sqlite3.Row]) -> str:
    parts: list[str] = []
    for row in rows:
        date = row["ts"].split("T", 1)[0]
        agent = (row["agent"] or "bravo").upper()
        body = row["note"].strip()
        if body.startswith("### "):
            parts.append(body)
        else:
            parts.append(f"### {date} — {agent} state_manager\n**Agent:** {agent}\n**Note:** {body}")
    return "\n\n".join(parts)


def export_state_md(conn: sqlite3.Connection | None = None) -> str:
    """Update only the `## Last Heartbeat` block of brain/STATE.md."""
    own = conn is None
    conn = conn or connect(read_only=True)
    try:
        targets = _compute_targets(conn)
        state = targets["state_md"]
        if state["after"] != state["before"] and state["after"]:
            STATE_MD.parent.mkdir(parents=True, exist_ok=True)
            STATE_MD.write_text(state["after"], encoding="utf-8")
        return state["block"]
    finally:
        if own:
            conn.close()


def export_session_log_md(conn: sqlite3.Connection | None = None,
                          limit: int = 200) -> bool:
    """Rebuild the DB-owned section without discarding markerless history."""
    own = conn is None
    conn = conn or connect(read_only=True)
    try:
        targets = _compute_targets(conn, limit=limit)
        log = targets["session_log_md"]
        if log["after"] != log["before"]:
            current = SESSION_LOG_MD.read_text(encoding="utf-8") if SESSION_LOG_MD.exists() else ""
            if current != log["before"]:
                raise RuntimeError(
                    "SESSION_LOG changed during reconciliation; refusing to overwrite it"
                )
            _archive_markerless_session_log(log["before"])
            SESSION_LOG_MD.parent.mkdir(parents=True, exist_ok=True)
            SESSION_LOG_MD.write_text(log["after"], encoding="utf-8")
            return True
        return False
    finally:
        if own:
            conn.close()


def export_markdown(conn: sqlite3.Connection | None = None,
                    skip_import: bool = False) -> dict:
    """Run all exports. Returns a summary dict for logging.

    By default we first absorb any flat-file entries the DB does not yet
    know about (idempotent via UNIQUE(session_id, note)). This protects
    `mode=off` writes from being clobbered when shadow-mode `export` runs.
    Pass `skip_import=True` only if you have just imported in this process.
    """
    own = conn is None
    conn = conn or connect()
    try:
        imported = 0
        if not skip_import:
            imported = import_from_files(conn).get("imported_session_entries", 0)
        log_before = SESSION_LOG_MD.read_text(encoding="utf-8") if SESSION_LOG_MD.exists() else ""
        legacy_archive = _legacy_archive_path(log_before)
        block = export_state_md(conn)
        log_changed = export_session_log_md(conn)
        return {
            "absorbed_flat_file_entries": imported,
            "state_heartbeat_block_chars": len(block),
            "session_log_changed": log_changed,
            "legacy_session_log_archive": str(legacy_archive) if legacy_archive else None,
        }
    finally:
        if own:
            conn.close()


# ── Bootstrap import (one-time migration of existing markdown into DB) ──────

_ENTRY_RE = re.compile(r"^### (.+?)$", re.MULTILINE)


def _session_import_record(block: str) -> dict[str, str | bool]:
    """Normalize a Markdown entry for semantic import/deduplication."""
    first_line = block.split("\n", 1)[0]
    header = _DATED_ENTRY_HEADER_RE.match(first_line)
    date_str = header.group(1) if header else _today()
    label = header.group(2).strip().lower() if header else ""

    agent_match = re.search(
        r"(?m)^\*\*Agent:\*\*[ \t]*([A-Za-z0-9_-]+)", block,
    )
    agent = agent_match.group(1).lower() if agent_match else "bravo"
    if agent not in VALID_AGENTS:
        agent = "bravo"

    standard = label == "auto-sync" or label.endswith(" state_manager")
    note = block.strip()
    if standard:
        note_match = re.search(r"(?ms)^\*\*Note:\*\*[ \t]*(.*)\Z", block)
        if note_match and note_match.group(1).strip():
            note = note_match.group(1).strip()
        else:
            standard = False

    return {
        "date": date_str,
        "agent": agent,
        "note": note,
        "standard": standard,
    }


def _session_semantic_exists(conn: sqlite3.Connection, record: dict[str, str | bool],
                             original_block: str) -> bool:
    """Whether the date/agent/note meaning is already represented in the DB."""
    date_str = str(record["date"])
    agent = str(record["agent"])
    note = str(record["note"]).strip()
    original = original_block.strip()
    rows = conn.execute(
        "SELECT agent, note FROM session_log WHERE substr(ts,1,10)=?",
        (date_str,),
    ).fetchall()
    for row in rows:
        existing_note = (row["note"] or "").strip()
        if existing_note == original:
            return True
        if (row["agent"] or "").lower() == agent and existing_note == note:
            return True
    return False


def _empty_import_result() -> dict[str, int]:
    return {
        "candidate_session_entries": 0,
        "imported_session_entries": 0,
        "semantic_duplicates_skipped": 0,
        "standard_entries_normalized": 0,
        "auto_generated_entries_ignored": 0,
    }


def import_from_files(conn: sqlite3.Connection | None = None) -> dict:
    """Idempotent import of existing SESSION_LOG.md entries into the DB.

    Human-authored `### …` blocks become session_log rows. Content inside the
    DB-owned AUTO markers is never imported. Standard state_sync/state_manager
    blocks normalize to their underlying note so a shadow-mode raw DB row and
    its Markdown rendering do not become two semantic sessions.
    """
    own = conn is None
    conn = conn or connect()
    try:
        if not SESSION_LOG_MD.exists():
            return _empty_import_result()

        text = SESSION_LOG_MD.read_text(encoding="utf-8")
        stripped, auto_ignored = _without_auto_sections(text)
        fm_match = _FRONTMATTER_RE.match(stripped)
        if fm_match:
            stripped = stripped[fm_match.end():]

        # Split into blocks, each starting with `### `.
        positions = [m.start() for m in _ENTRY_RE.finditer(stripped)]
        if not positions:
            result = _empty_import_result()
            result["auto_generated_entries_ignored"] = auto_ignored
            return result
        blocks: list[str] = []
        for i, pos in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(stripped)
            block = stripped[pos:end].strip()
            if block:
                blocks.append(block)

        imported = 0
        semantic_duplicates = 0
        normalized = 0
        with transaction(conn, actor="cc", op="import_from_files"):
            for block in blocks:
                record = _session_import_record(block)
                if _session_semantic_exists(conn, record, block):
                    semantic_duplicates += 1
                    continue
                date_str = str(record["date"])
                agent = str(record["agent"])
                note = str(record["note"])
                if bool(record["standard"]):
                    normalized += 1
                ts = f"{date_str}T12:00:00+00:00"
                # Stable semantic identity keeps retries/races idempotent.
                identity = f"{date_str}\0{agent}\0{note}"
                content_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
                session_id = f"import-{content_hash}"
                try:
                    conn.execute(
                        "INSERT INTO session_log(ts, agent, session_id, note, artifacts_json) "
                        "VALUES (?,?,?,?,?)",
                        (ts, agent, session_id, note, None),
                    )
                    imported += 1
                except sqlite3.IntegrityError:
                    semantic_duplicates += 1
        return {
            "candidate_session_entries": len(blocks),
            "imported_session_entries": imported,
            "semantic_duplicates_skipped": semantic_duplicates,
            "standard_entries_normalized": normalized,
            "auto_generated_entries_ignored": auto_ignored,
        }
    finally:
        if own:
            conn.close()


def status() -> dict:
    """Quick read-only summary for monitoring.

    Single source of truth consumed by:
      - `state_manager.py status` CLI
      - `scripts/state/state_api.py` /status endpoint (dashboard)
      - any future caller that wants V6.0 DB health at a glance.

    Anything dashboard-shaped should land here, not in state_api.
    """
    if not DB_PATH.exists():
        return {"db": "missing", "path": str(DB_PATH), "exists": False}
    conn = connect(read_only=True)
    try:
        agents = conn.execute(
            "SELECT agent, status, current_focus, last_heartbeat, tick_count, "
            "       health, payload_json FROM agent_state ORDER BY last_heartbeat DESC"
        ).fetchall()
        log_count = conn.execute("SELECT COUNT(*) AS c FROM session_log").fetchone()["c"]
        tx_count = conn.execute("SELECT COUNT(*) AS c FROM state_transaction").fetchone()["c"]
        task_count = conn.execute(
            "SELECT bucket, COUNT(*) AS c FROM active_task WHERE status='open' GROUP BY bucket"
        ).fetchall()
        last_log = conn.execute(
            "SELECT ts, agent, substr(note,1,160) AS note FROM session_log ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        last_tx = conn.execute(
            "SELECT ts, actor, op, source_script FROM state_transaction ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        try:
            size_kb = round(DB_PATH.stat().st_size / 1024, 1)
        except OSError:
            size_kb = None
        return {
            "db": str(DB_PATH),
            "exists": True,
            "size_kb": size_kb,
            "agents": [dict(a) for a in agents],
            "session_log_count": log_count,
            "transaction_count": tx_count,
            "open_tasks_by_bucket": {row["bucket"]: row["c"] for row in task_count},
            "last_session_log": dict(last_log) if last_log else None,
            "last_transaction": dict(last_tx) if last_tx else None,
        }
    finally:
        conn.close()


def export_check() -> dict:
    """Dry-run: report what export_markdown WOULD do without writing.

    Uses the same `_compute_targets` path that `export_markdown` consumes,
    so check and write can never disagree.
    """
    conn = connect(read_only=True)
    try:
        targets = _compute_targets(conn)
        return {
            "state_md_drift": targets["state_md"]["before"] != targets["state_md"]["after"],
            "session_log_md_drift": targets["session_log_md"]["before"] != targets["session_log_md"]["after"],
            "session_log_db_rows": targets["session_log_md"]["rows"],
            "session_log_markerless_legacy": targets["session_log_md"]["markerless_legacy"],
            "session_log_legacy_archive": targets["session_log_md"]["legacy_archive_path"],
        }
    finally:
        conn.close()


# ── CLI ─────────────────────────────────────────────────────────────────────

def _cmd_heartbeat(args) -> int:
    heartbeat(args.agent, args.status, args.focus,
              json.loads(args.payload) if args.payload else None)
    if args.export:
        export_markdown()
    print(json.dumps({"ok": True, "agent": args.agent, "status": args.status}, indent=2))
    return 0


def _cmd_log(args) -> int:
    artifacts = None
    if args.artifacts:
        artifacts = {"files_touched": [s.strip() for s in args.artifacts.split(",") if s.strip()]}
    result = append_session_log(args.note, args.agent, args.session_id, artifacts)
    if args.export:
        export_markdown()
    print(json.dumps({"ok": True, "result": result, "note": args.note[:80]}, indent=2))
    return 0


def _cmd_task(args) -> int:
    if args.task_action == "add":
        task_id = upsert_task(args.bucket, args.title, args.owner, args.priority, "open")
        print(json.dumps({"ok": True, "id": task_id, "bucket": args.bucket}, indent=2))
        return 0
    if args.task_action == "close":
        ok = close_task(args.id, args.status)
        print(json.dumps({"ok": ok, "id": args.id, "status": args.status}, indent=2))
        return 0 if ok else 1
    if args.task_action == "list":
        conn = connect(read_only=True)
        try:
            sql = "SELECT id, bucket, owner, title, status, priority, updated_at FROM active_task WHERE 1=1"
            params: list = []
            if args.bucket:
                sql += " AND bucket=?"
                params.append(args.bucket)
            if args.status:
                sql += " AND status=?"
                params.append(args.status)
            sql += " ORDER BY priority ASC, updated_at DESC"
            rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
            print(json.dumps(rows, indent=2))
            return 0
        finally:
            conn.close()
    return 2


def _cmd_export(args) -> int:
    if args.check:
        result = export_check()
        print(json.dumps(result, indent=2))
        return 1 if (result["state_md_drift"] or result["session_log_md_drift"]) else 0
    result = export_markdown()
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


def _cmd_import(args) -> int:
    result = import_from_files()
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


def _cmd_status(args) -> int:
    print(json.dumps(status(), indent=2, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V6.0 transactional state manager")
    sub = p.add_subparsers(dest="command", required=True)

    hb = sub.add_parser("heartbeat", help="Update an agent's heartbeat row")
    hb.add_argument("--agent", default="bravo", choices=sorted(VALID_AGENTS))
    hb.add_argument("--status", default="working")
    hb.add_argument("--focus", default=None)
    hb.add_argument("--payload", default=None, help="JSON blob")
    hb.add_argument("--export", action="store_true", help="Regenerate markdown mirrors after write")
    hb.set_defaults(func=_cmd_heartbeat)

    lg = sub.add_parser("log", help="Append a session-log entry")
    lg.add_argument("--note", "-n", required=True)
    lg.add_argument("--agent", default="bravo", choices=sorted(VALID_AGENTS))
    lg.add_argument("--session-id", default=None)
    lg.add_argument("--artifacts", default=None, help="comma-separated file list")
    lg.add_argument("--export", action="store_true")
    lg.set_defaults(func=_cmd_log)

    tk = sub.add_parser("task", help="Manage active_task rows")
    tk_sub = tk.add_subparsers(dest="task_action", required=True)
    tk_add = tk_sub.add_parser("add")
    tk_add.add_argument("--bucket", required=True, choices=sorted(VALID_BUCKETS))
    tk_add.add_argument("--title", required=True)
    tk_add.add_argument("--owner", default="bravo")
    tk_add.add_argument("--priority", type=int, default=100)
    tk_close = tk_sub.add_parser("close")
    tk_close.add_argument("--id", type=int, required=True)
    tk_close.add_argument("--status", default="done", choices=sorted(VALID_STATUSES))
    tk_list = tk_sub.add_parser("list")
    tk_list.add_argument("--bucket", default=None, choices=sorted(VALID_BUCKETS))
    tk_list.add_argument("--status", default=None, choices=sorted(VALID_STATUSES))
    tk.set_defaults(func=_cmd_task)

    ex = sub.add_parser("export", help="Regenerate markdown mirrors")
    ex.add_argument("--check", action="store_true", help="Dry run; exit 1 if drift detected")
    ex.set_defaults(func=_cmd_export)

    im = sub.add_parser("import-from-files", help="One-time bootstrap from existing markdown")
    im.set_defaults(func=_cmd_import)

    st = sub.add_parser("status", help="Quick read-only overview")
    st.set_defaults(func=_cmd_status)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
