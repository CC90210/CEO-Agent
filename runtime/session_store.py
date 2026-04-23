"""Session store — SQLite FTS5 search across session logs.

Complements brain/STATE.md + memory/SESSION_LOG.md + mem0 + Supabase.
Gives agents durable recall beyond markdown: query-friendly, ranked, fast.

Usage:
    from runtime.session_store import SessionStore
    store = SessionStore()
    store.ingest_session_log()          # scan memory/SESSION_LOG.md
    hits = store.search("stripe", limit=10)
    for h in hits:
        print(h["date"], h["title"], h["snippet"])

CLI:
    python -m runtime.session_store ingest
    python -m runtime.session_store search "stripe"
    python -m runtime.session_store recent --limit 10
    python -m runtime.session_store stats
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Iterator

# Force UTF-8 output on Windows (cp1252 default breaks on any non-ASCII).
if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
MEMORY_DIR = REPO_ROOT / "memory"
DEFAULT_DB = Path(os.path.expanduser("~/.bravo/sessions/bravo.sqlite"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    title       TEXT NOT NULL,
    agent       TEXT,
    source_file TEXT NOT NULL,
    content     TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    UNIQUE(date, title, source_file)
);

CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
    title, agent, content, date UNINDEXED,
    content=sessions, content_rowid=id,
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS sessions_ai AFTER INSERT ON sessions BEGIN
    INSERT INTO sessions_fts(rowid, title, agent, content, date)
    VALUES (new.id, new.title, coalesce(new.agent,''), new.content, new.date);
END;

CREATE TRIGGER IF NOT EXISTS sessions_ad AFTER DELETE ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, title, agent, content, date)
    VALUES('delete', old.id, old.title, coalesce(old.agent,''), old.content, old.date);
END;

CREATE TRIGGER IF NOT EXISTS sessions_au AFTER UPDATE ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, title, agent, content, date)
    VALUES('delete', old.id, old.title, coalesce(old.agent,''), old.content, old.date);
    INSERT INTO sessions_fts(rowid, title, agent, content, date)
    VALUES (new.id, new.title, coalesce(new.agent,''), new.content, new.date);
END;

CREATE INDEX IF NOT EXISTS idx_sessions_date ON sessions(date DESC);
"""

ENTRY_PATTERN = re.compile(r"^### (\d{4}-\d{2}-\d{2}) — (.+?)$", re.MULTILINE)
AGENT_PATTERN = re.compile(r"^\*\*Agent:\*\*\s*(.+?)$", re.MULTILINE)


class SessionStore:
    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def _parse_session_log(self, path: Path) -> Iterator[dict]:
        """Yield {date, title, agent, content} dicts from SESSION_LOG.md."""
        if not path.exists():
            return
        text = path.read_text(encoding="utf-8", errors="ignore")
        matches = list(ENTRY_PATTERN.finditer(text))
        for i, m in enumerate(matches):
            date = m.group(1)
            title = m.group(2).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            agent_m = AGENT_PATTERN.search(body)
            agent = agent_m.group(1).strip() if agent_m else None
            yield {
                "date": date,
                "title": title,
                "agent": agent,
                "content": body,
                "source_file": str(path.relative_to(REPO_ROOT)),
            }

    def ingest_session_log(self, path: Path | None = None) -> int:
        path = path or (MEMORY_DIR / "SESSION_LOG.md")
        count = 0
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        for entry in self._parse_session_log(path):
            try:
                cur = self.conn.execute(
                    "INSERT OR IGNORE INTO sessions "
                    "(date, title, agent, source_file, content, ingested_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (entry["date"], entry["title"], entry["agent"],
                     entry["source_file"], entry["content"], now),
                )
                if cur.rowcount > 0:
                    count += 1
            except sqlite3.Error:
                continue
        self.conn.commit()
        return count

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Full-text ranked search across all ingested sessions."""
        # Escape FTS5 special characters
        safe_query = query.replace('"', '""')
        fts_query = f'"{safe_query}"' if " " in safe_query else safe_query
        rows = self.conn.execute(
            """
            SELECT s.id, s.date, s.title, s.agent, s.source_file,
                   snippet(sessions_fts, 2, '<<', '>>', ' … ', 24) AS snippet,
                   rank
            FROM sessions_fts
            JOIN sessions s ON s.id = sessions_fts.rowid
            WHERE sessions_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def recent(self, limit: int = 10) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, date, title, agent, source_file, "
            "substr(content, 1, 200) AS preview "
            "FROM sessions ORDER BY date DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        total = self.conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        earliest = self.conn.execute(
            "SELECT MIN(date) FROM sessions"
        ).fetchone()[0]
        latest = self.conn.execute(
            "SELECT MAX(date) FROM sessions"
        ).fetchone()[0]
        by_agent = {
            row["agent"] or "unspecified": row["n"]
            for row in self.conn.execute(
                "SELECT COALESCE(agent,'unspecified') AS agent, "
                "COUNT(*) AS n FROM sessions GROUP BY agent ORDER BY n DESC"
            ).fetchall()
        }
        return {
            "db_path": str(self.db_path),
            "total_sessions": total,
            "earliest_date": earliest,
            "latest_date": latest,
            "by_agent": by_agent,
        }


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="runtime.session_store",
        description="Bravo session store — SQLite FTS5 search over session logs",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ingest", help="Scan memory/SESSION_LOG.md into the store")

    p_search = sub.add_parser("search", help="Full-text search")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--json", action="store_true")

    p_recent = sub.add_parser("recent", help="List recent sessions")
    p_recent.add_argument("--limit", type=int, default=10)
    p_recent.add_argument("--json", action="store_true")

    p_stats = sub.add_parser("stats", help="Show store statistics")
    p_stats.add_argument("--json", action="store_true")

    parser.add_argument("--db", default=str(DEFAULT_DB),
                        help=f"SQLite DB path (default: {DEFAULT_DB})")
    args = parser.parse_args(argv)

    store = SessionStore(args.db)
    try:
        if args.cmd == "ingest":
            n = store.ingest_session_log()
            print(f"Ingested {n} new session entries into {store.db_path}")
            return 0
        if args.cmd == "search":
            hits = store.search(args.query, args.limit)
            if args.json:
                print(json.dumps(hits, indent=2))
                return 0
            if not hits:
                print(f"No sessions matched: {args.query!r}")
                return 1
            for h in hits:
                print(f"[{h['date']}] {h['title']}")
                if h.get("agent"):
                    print(f"  agent: {h['agent']}")
                print(f"  {h['snippet']}")
                print()
            return 0
        if args.cmd == "recent":
            rows = store.recent(args.limit)
            if args.json:
                print(json.dumps(rows, indent=2))
                return 0
            for r in rows:
                print(f"[{r['date']}] {r['title']}")
                if r.get("agent"):
                    print(f"  agent: {r['agent']}")
            return 0
        if args.cmd == "stats":
            s = store.stats()
            if args.json:
                print(json.dumps(s, indent=2))
                return 0
            print(f"db: {s['db_path']}")
            print(f"total sessions: {s['total_sessions']}")
            print(f"date range: {s['earliest_date']} -> {s['latest_date']}")
            print("by agent:")
            for agent, n in s["by_agent"].items():
                print(f"  {agent:30s} {n}")
            return 0
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
