"""libSQL / Turso data-access layer — with mandatory tenant scoping.

WHY THIS FILE IS THE WHOLE MIGRATION. Supabase enforced tenant isolation with
858 Row Level Security policies evaluated by Postgres itself. libSQL/SQLite has
no RLS. If the application forgets a `WHERE tenant_id = ?` even once, the query
silently returns every tenant's rows — no error, no warning, just a cross-tenant
leak that looks like a successful read. That failure mode already cost this
system once (supabase_tool.py:297 records the 2026-06-11 cross-tenant leak that
followed a *silent fallback*).

So the guard here is not advisory. Every table carrying a `tenant_id` column is
registered as tenant-scoped at connect time by reading the live schema. Any read
or write against such a table that does not constrain `tenant_id` raises
`UnscopedQueryError`. It fails closed, loudly, with the offending SQL in the
message. Bypassing it requires passing `allow_unscoped=True` explicitly, which
is logged at WARNING with a stack-identifying reason — so a bypass is a decision
someone made on purpose and can be found in the audit log, not an accident.

CONNECTION MODES (first match wins):
  TURSO_DATABASE_URL + TURSO_AUTH_TOKEN   remote Turso Cloud   (canonical)
  TURSO_DB_URL       + TURSO_AUTH_TOKEN   remote               (legacy — oasis-command-center)
  TURSO_DATA_BASE_URL+ TURSO_AUTH_TOKEN   remote               (legacy — agents env typo)
  TURSO_DB_PATH                           local libSQL file    (offline / tests)

Credentials load through lib.secret_loader — never read the agents env directly.

USAGE
    from lib.db_turso import get_db, UnscopedQueryError

    db = get_db()
    rows = db.select("leads", tenant_id=TENANT, where="status = ?", params=["warm"])
    db.insert("leads", {"email": "a@b.com", "status": "cold"}, tenant_id=TENANT)
    claimed = db.claim("scheduled_sends", key={"id": sid},
                       set_values={"claimed_by": worker}, unclaimed_col="claimed_by")

`claim()` is the compare-and-swap primitive that replaces the reserve_send_slot
PL/pgSQL RPC — a single UPDATE ... WHERE col IS NULL, atomic in SQLite without
an interactive transaction (which is not reliable over remote HTTP).
"""
from __future__ import annotations

import os
import re
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, Sequence

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.structured_log import get_logger  # noqa: E402

log = get_logger("db_turso")

try:
    import libsql
except ImportError:  # pragma: no cover - install-time failure must be loud
    raise ImportError(
        "The 'libsql' package is required for the Turso backend. Install it with:\n"
        "    python -m pip install libsql"
    ) from None

TENANT_COLUMN = "tenant_id"

# Tables that legitimately hold no tenant_id and are global by design. Kept
# explicit so a *missing* tenant_id column is a deliberate registration, not an
# oversight that silently disables the guard.
GLOBAL_TABLES = frozenset({
    "schema_migrations",
    "schema_version",
})


class UnscopedQueryError(RuntimeError):
    """Raised when a query touches a tenant-scoped table without a tenant filter."""


class TursoConfigError(RuntimeError):
    """Raised when no usable Turso connection target is configured."""


def _load_env() -> dict:
    try:
        from lib.secret_loader import load_env  # noqa: PLC0415
        return load_env()
    except Exception as exc:  # noqa: BLE001 - surface, never swallow
        log.error("secret_loader failed", error=str(exc), traceback=traceback.format_exc())
        raise


def resolve_target(env: dict | None = None) -> tuple[str, str | None, str]:
    """Return (url, auth_token, mode). Raises TursoConfigError if unconfigured.

    `env=None` means "load the real agents env"; `env={}` means "nothing is
    configured" and must raise. Those are different questions, so the check is
    `is not None` — `env or _load_env()` would treat an empty dict as falsy and
    silently connect to the live database during a test that was asserting the
    unconfigured path. (Same trap as scripts/integrations/send_gateway.py's
    None-sentinel incident: a falsy value colliding with a real signal.)
    """
    e = dict(env if env is not None else _load_env())
    if env is None:
        e.update({k: v for k, v in os.environ.items() if k.startswith("TURSO_")})

    # NOTE: TURSO_DATA_BASE_URL is deliberately NOT in this chain. That key
    # exists in the agents env and points at the ig-setter-pro database — an
    # unrelated product. Including it as a fallback would have silently pointed
    # the Bravo harness at IG Setter's data. Callers who really want it must set
    # TURSO_DATABASE_URL explicitly.
    for key in ("TURSO_DATABASE_URL", "TURSO_DB_URL"):
        url = e.get(key)
        if url:
            token = e.get("TURSO_AUTH_TOKEN") or e.get("TURSO_API_KEY")
            if not token:
                raise TursoConfigError(
                    f"{key} is set but neither TURSO_AUTH_TOKEN nor TURSO_API_KEY is. "
                    "A remote libSQL URL cannot authenticate without a database token."
                )
            return url, token, f"remote({key})"

    path = e.get("TURSO_DB_PATH")
    if path:
        return path, None, "local(TURSO_DB_PATH)"

    raise TursoConfigError(
        "No Turso target configured. Set TURSO_DATABASE_URL + TURSO_AUTH_TOKEN "
        "(remote) or TURSO_DB_PATH (local file) in the agents env."
    )


# --------------------------------------------------------------- SQL inspection

_TABLE_REF = re.compile(
    r"\b(?:from|join|into|update)\s+[\"'`\[]?([a-zA-Z_][a-zA-Z0-9_]*)[\"'`\]]?",
    re.IGNORECASE,
)
_DELETE_FROM = re.compile(r"\bdelete\s+from\s+[\"'`\[]?([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)
_STRING_LIT = re.compile(r"'(?:[^']|'')*'")
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_noise(sql: str) -> str:
    s = _BLOCK_COMMENT.sub(" ", sql)
    s = _LINE_COMMENT.sub(" ", s)
    return _STRING_LIT.sub("''", s)


def referenced_tables(sql: str) -> set[str]:
    """Best-effort set of table names a statement touches."""
    stripped = _strip_noise(sql)
    names = set(_TABLE_REF.findall(stripped)) | set(_DELETE_FROM.findall(stripped))
    return {n.lower() for n in names}


def mentions_tenant_filter(sql: str) -> bool:
    """True when the statement constrains or supplies tenant_id."""
    return TENANT_COLUMN in _strip_noise(sql).lower()


# ------------------------------------------------------------------- the client

class TursoDB:
    def __init__(self, url: str, auth_token: str | None, mode: str):
        self.url = url
        self.mode = mode
        self._lock = threading.RLock()
        if auth_token:
            self._conn = libsql.connect(database=url, auth_token=auth_token)
        else:
            self._conn = libsql.connect(url)
        self._tenant_tables = self._discover_tenant_tables()
        log.info("Turso connected", mode=mode,
                 tenant_scoped_tables=len(self._tenant_tables))

    # -- schema awareness ---------------------------------------------------
    def _discover_tenant_tables(self) -> frozenset[str]:
        """Every table with a tenant_id column, read from the live schema."""
        scoped: set[str] = set()
        rows = self._conn.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
        ).fetchall()
        for (name,) in rows:
            if name in GLOBAL_TABLES:
                continue
            cols = self._conn.execute(f'PRAGMA table_info("{name}")').fetchall()
            if any(c[1] == TENANT_COLUMN for c in cols):
                scoped.add(name.lower())
        return frozenset(scoped)

    @property
    def tenant_tables(self) -> frozenset[str]:
        return self._tenant_tables

    def is_tenant_scoped(self, table: str) -> bool:
        return table.lower() in self._tenant_tables

    # -- the guard ----------------------------------------------------------
    def _enforce_scope(self, sql: str, *, allow_unscoped: bool, reason: str | None) -> None:
        touched = referenced_tables(sql) & self._tenant_tables
        if not touched:
            return
        if mentions_tenant_filter(sql):
            return
        if allow_unscoped:
            log.warn("UNSCOPED QUERY ALLOWED — audit this",
                     tables=sorted(touched), reason=reason or "(no reason given)",
                     sql=sql[:400])
            return
        raise UnscopedQueryError(
            f"Query touches tenant-scoped table(s) {sorted(touched)} without a "
            f"{TENANT_COLUMN} filter. Supabase RLS used to catch this; Turso "
            f"cannot. Add a {TENANT_COLUMN} predicate, or pass "
            f"allow_unscoped=True with a reason if the query is genuinely "
            f"cross-tenant.\nSQL: {sql[:400]}"
        )

    # -- raw execution ------------------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] | None = None, *,
                allow_unscoped: bool = False, reason: str | None = None):
        self._enforce_scope(sql, allow_unscoped=allow_unscoped, reason=reason)
        with self._lock:
            try:
                return self._conn.execute(sql, tuple(params or ()))
            except Exception as exc:  # noqa: BLE001 - log the real cause, then re-raise
                log.error("Turso execute failed", error=str(exc), sql=sql[:400],
                          traceback=traceback.format_exc())
                raise

    def query(self, sql: str, params: Sequence[Any] | None = None, *,
              allow_unscoped: bool = False, reason: str | None = None) -> list[dict]:
        cur = self.execute(sql, params, allow_unscoped=allow_unscoped, reason=reason)
        rows = cur.fetchall()
        desc = getattr(cur, "description", None)
        if not desc:
            return [dict(enumerate(r)) for r in rows]
        cols = [d[0] for d in desc]
        return [dict(zip(cols, r)) for r in rows]

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    # -- structured helpers -------------------------------------------------
    def select(self, table: str, *, tenant_id: str | None = None, columns: str = "*",
               where: str | None = None, params: Sequence[Any] | None = None,
               order_by: str | None = None, limit: int | None = None,
               allow_unscoped: bool = False, reason: str | None = None) -> list[dict]:
        clauses: list[str] = []
        args: list[Any] = []
        if tenant_id is not None:
            clauses.append(f'"{TENANT_COLUMN}" = ?')
            args.append(tenant_id)
        elif self.is_tenant_scoped(table) and not allow_unscoped:
            raise UnscopedQueryError(
                f'select("{table}") requires tenant_id — "{table}" carries a '
                f"{TENANT_COLUMN} column. Pass tenant_id=..., or allow_unscoped=True "
                f"with a reason for a deliberate cross-tenant read."
            )
        if where:
            clauses.append(f"({where})")
            args.extend(params or ())
        sql = f'SELECT {columns} FROM "{table}"'
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        return self.query(sql, args, allow_unscoped=allow_unscoped, reason=reason)

    def insert(self, table: str, values: dict[str, Any], *,
               tenant_id: str | None = None, allow_unscoped: bool = False,
               reason: str | None = None) -> None:
        row = dict(values)
        if self.is_tenant_scoped(table):
            if tenant_id is not None:
                row[TENANT_COLUMN] = tenant_id
            elif row.get(TENANT_COLUMN) in (None, ""):
                if not allow_unscoped:
                    raise UnscopedQueryError(
                        f'insert into "{table}" must stamp {TENANT_COLUMN}. An unstamped '
                        f"row is invisible to every tenant-scoped read and effectively "
                        f"orphaned."
                    )
                log.warn("UNSTAMPED INSERT ALLOWED — audit this", table=table,
                         reason=reason or "(no reason given)")
        cols = list(row)
        placeholders = ", ".join("?" for _ in cols)
        col_sql = ", ".join(f'"{c}"' for c in cols)
        sql = f'INSERT INTO "{table}" ({col_sql}) VALUES ({placeholders})'
        self.execute(sql, [row[c] for c in cols], allow_unscoped=True,
                     reason="insert stamps tenant_id via values")

    def claim(self, table: str, *, key: dict[str, Any], set_values: dict[str, Any],
              unclaimed_col: str, tenant_id: str | None = None) -> bool:
        """Compare-and-swap claim. Returns True iff THIS caller won the row.

        Replaces the reserve_send_slot PL/pgSQL RPC. A single conditional UPDATE
        is atomic in SQLite — no BEGIN EXCLUSIVE, no interactive transaction, so
        it behaves identically against a local file and remote Turso over HTTP.
        """
        sets = ", ".join(f'"{c}" = ?' for c in set_values)
        args: list[Any] = list(set_values.values())
        conds = [f'"{unclaimed_col}" IS NULL']
        for col, val in key.items():
            conds.append(f'"{col}" = ?')
            args.append(val)
        if tenant_id is not None:
            conds.append(f'"{TENANT_COLUMN}" = ?')
            args.append(tenant_id)
        elif self.is_tenant_scoped(table):
            raise UnscopedQueryError(
                f'claim("{table}") requires tenant_id — cross-tenant claims would let '
                f"one tenant's worker take another tenant's row."
            )
        sql = f'UPDATE "{table}" SET {sets} WHERE ' + " AND ".join(conds)
        cur = self.execute(sql, args, allow_unscoped=True, reason="claim scopes explicitly")
        self.commit()
        changed = getattr(cur, "rowcount", -1)
        if changed is None or changed < 0:
            # Driver did not report rowcount — verify by reading the row back.
            check_conds = " AND ".join(f'"{c}" = ?' for c in key)
            check_args = list(key.values())
            probe = f'SELECT "{unclaimed_col}" AS v FROM "{table}" WHERE {check_conds}'
            rows = self.query(probe, check_args, allow_unscoped=True,
                              reason="claim verification read")
            return bool(rows) and rows[0]["v"] == set_values.get(unclaimed_col)
        return changed > 0


_INSTANCE: TursoDB | None = None
_INSTANCE_LOCK = threading.Lock()


def get_db(*, force_new: bool = False) -> TursoDB:
    """Process-cached TursoDB. Raises TursoConfigError when unconfigured."""
    global _INSTANCE
    if _INSTANCE is not None and not force_new:
        return _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None or force_new:
            url, token, mode = resolve_target()
            _INSTANCE = TursoDB(url, token, mode)
    return _INSTANCE


def reset_cache() -> None:
    """Test hook — drop the cached connection."""
    global _INSTANCE
    _INSTANCE = None
