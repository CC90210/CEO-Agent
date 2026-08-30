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
from lib.tls_trust import ensure_os_trust  # noqa: E402

# A libsql:// URL is HTTPS underneath. This fleet's AV terminates TLS, which
# breaks certifi's bundle — 33 other tools in scripts/ call this for the same
# reason. Without it, remote Turso fails with CERTIFICATE_VERIFY_FAILED the
# first time anyone connects to the cloud, i.e. the moment Phase 0 lands.
ensure_os_trust()

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


# Per-project env-var pairs, matching what turso_admin `create --write-env`
# writes. "bravo" is the unprefixed canonical pair.
PROJECT_ENV_VARS: dict[str, tuple[str, str]] = {
    "bravo": ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"),
    "breeze": ("BREEZE_TURSO_DATABASE_URL", "BREEZE_TURSO_AUTH_TOKEN"),
    "nostalgic": ("NOSTALGIC_TURSO_DATABASE_URL", "NOSTALGIC_TURSO_AUTH_TOKEN"),
    "propflow": ("PROPFLOW_TURSO_DATABASE_URL", "PROPFLOW_TURSO_AUTH_TOKEN"),
    "oasis": ("OASIS_TURSO_DATABASE_URL", "OASIS_TURSO_AUTH_TOKEN"),
}


def resolve_project_target(project: str) -> tuple[str, str, str]:
    """(url, token, mode) for a named empire project's Turso database."""
    if project not in PROJECT_ENV_VARS:
        raise TursoConfigError(
            f"unknown project {project!r} — known: {', '.join(sorted(PROJECT_ENV_VARS))}")
    url_var, tok_var = PROJECT_ENV_VARS[project]
    env = _load_env()
    url, token = env.get(url_var), env.get(tok_var)
    if not url or not token:
        raise TursoConfigError(
            f"{project}: {url_var} and/or {tok_var} missing from the agents env. "
            f"Provision with: python scripts/integrations/turso_admin.py create "
            f"--all --write-env")
    return url, token, f"remote({url_var})"


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
    #
    # TURSO_API_KEY is excluded for the SAME reason, which the original version
    # missed: it guarded the ig-setter-pro URL and then accepted the
    # ig-setter-pro TOKEN one line later. docs/ENV_KEYS_TEMPLATE.md is explicit
    # that TURSO_API_KEY belongs to that other product.
    #
    # This is not theoretical. On the VPS, TURSO_API_KEY is present and
    # TURSO_AUTH_TOKEN is absent — so setting TURSO_DATABASE_URL there would
    # have authenticated the Bravo harness with another product's credential and
    # reported success. Caught by the VPS agent before the cutover, 2026-08-08.
    for key in ("TURSO_DATABASE_URL", "TURSO_DB_URL"):
        url = e.get(key)
        if url:
            token = e.get("TURSO_AUTH_TOKEN")
            if not token:
                extra = ""
                if e.get("TURSO_API_KEY"):
                    extra = (" TURSO_API_KEY is set but is NOT a substitute — it is "
                             "ig-setter-pro's database token, and using it would point "
                             "this harness at another product's data.")
                raise TursoConfigError(
                    f"{key} is set but TURSO_AUTH_TOKEN is not. A remote libSQL URL "
                    f"cannot authenticate without its own database token.{extra}"
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

# Analysis runs on a PARSE TREE, not regexes. Regex scoping was tried first and
# an adversarial review found two exploitable holes:
#
#   SELECT * FROM main.leads               -> "main" captured as the table name,
#                                             "leads" never seen, query allowed
#   SELECT * FROM leads WHERE tenant_id=?
#     UNION SELECT * FROM leads            -> one scoped arm blessed the whole
#                                             statement; arm two unrestricted
#
# Both silently return other tenants' rows. A security boundary cannot rest on
# pattern-matching SQL, so sqlglot parses the statement and each SELECT/UPDATE/
# DELETE scope is judged on its own: a scope reading a tenant-scoped table must
# itself carry a tenant_id predicate. Union arms, CTEs and subqueries are
# separate scopes. A statement that will not parse is refused, never allowed.
import sqlglot  # noqa: E402
from sqlglot import exp  # noqa: E402

DIALECT = "sqlite"

# The comment/string-literal stripper that used to live here is gone with the
# regex implementation — sqlglot handles comments and literals natively, so
# pre-scrubbing the text would only reintroduce a parallel, weaker parser.


def _parse(sql: str):
    """Parse or refuse. An unparseable statement is never waved through."""
    try:
        tree = sqlglot.parse_one(sql, dialect=DIALECT)
    except Exception as exc:  # noqa: BLE001
        raise UnscopedQueryError(
            f"Could not parse SQL, so tenant scoping cannot be proven — refusing.\n"
            f"Parser error: {exc}\nSQL: {sql[:300]}"
        ) from exc
    if tree is None:
        raise UnscopedQueryError(f"Empty/unparseable SQL — refusing.\nSQL: {sql[:300]}")
    return tree


def _table_name(node: "exp.Table") -> str:
    """Terminal table name, ignoring any schema/catalog qualifier (main.leads -> leads)."""
    return (node.name or "").lower()


def referenced_tables(sql: str) -> set[str]:
    """Every physical table the statement touches, at any depth.

    CTE aliases are excluded: in `WITH x AS (...) SELECT * FROM x`, x is not a
    physical table, and the CTE body is analysed as its own scope.
    """
    tree = _parse(sql)
    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    return {n for t in tree.find_all(exp.Table)
            if (n := _table_name(t)) and n not in cte_names}


def _scope_has_tenant_predicate(scope: "exp.Expression") -> bool:
    """True when THIS scope constrains tenant_id — nested scopes do not count."""
    clauses: list[exp.Expression] = []
    where = scope.args.get("where")
    if where is not None:
        clauses.append(where)
    for join in scope.args.get("joins") or []:
        for key in ("on", "using"):
            val = join.args.get(key)
            if val is None:
                continue
            clauses.extend(val if isinstance(val, list) else [val])

    for clause in clauses:
        for col in clause.find_all(exp.Column):
            if col.name.lower() != TENANT_COLUMN:
                continue
            node = col.parent
            while node is not None and node is not clause.parent:
                if isinstance(node, (exp.EQ, exp.NEQ, exp.In, exp.Is,
                                     exp.GT, exp.LT, exp.GTE, exp.LTE)):
                    return True
                node = node.parent
        # JOIN ... USING (tenant_id) arrives as bare identifiers, not comparisons.
        for ident in clause.find_all(exp.Identifier):
            if ident.name.lower() == TENANT_COLUMN:
                return True
    return False


def _insert_target(node: "exp.Insert") -> tuple[str | None, set[str]]:
    """(table name, column names) for an INSERT."""
    target = node.this
    if target is None:
        return None, set()
    tbl = target if isinstance(target, exp.Table) else target.find(exp.Table)
    cols = {c.name.lower() for c in target.find_all(exp.Column)} if not isinstance(
        target, exp.Table) else set()
    if not cols:
        cols = {i.name.lower() for i in target.find_all(exp.Identifier)}
        if tbl is not None:
            cols.discard(_table_name(tbl))
    return (_table_name(tbl) if tbl is not None else None), cols


def unscoped_tables(sql: str, tenant_tables: frozenset[str]) -> set[str]:
    """Tenant-scoped tables reachable from a scope carrying no tenant predicate.

    An INSERT naming tenant_id in its column list is stamping it — the write-side
    equivalent of a filter.
    """
    tree = _parse(sql)
    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    offenders: set[str] = set()
    insert_targets: set[str] = set()

    for ins in tree.find_all(exp.Insert):
        name, cols = _insert_target(ins)
        if name is None or name not in tenant_tables:
            continue
        insert_targets.add(name)
        if TENANT_COLUMN not in cols:
            offenders.add(name)

    for scope in tree.find_all(exp.Select, exp.Update, exp.Delete):
        if _scope_has_tenant_predicate(scope):
            continue
        for tbl in scope.find_all(exp.Table):
            name = _table_name(tbl)
            if not name or name in cte_names or name not in tenant_tables:
                continue
            # Attribute a table only to its nearest enclosing SELECT, so an
            # unscoped inner subquery is not blamed on its scoped parent (and,
            # crucially, a scoped parent cannot excuse an unscoped child).
            if isinstance(scope, exp.Select) and tbl.parent_select is not scope:
                continue
            if name in insert_targets and isinstance(scope, exp.Select):
                continue  # the INSERT branch above already judged the target
            offenders.add(name)
    return offenders


# NOTE: there is deliberately no `mentions_tenant_filter(sql) -> bool` helper.
# "Does this statement mention a tenant filter anywhere?" is the exact question
# whose answer leaked data — `SELECT ... WHERE tenant_id=? UNION SELECT * FROM
# leads` mentions one. Only `unscoped_tables()` is exported, because it answers
# the question that actually matters: WHICH tables are reachable unprotected.


# ------------------------------------------------------------------- the client

# A plain unquoted SQL identifier. Table and column names in this codebase are
# literals written by us, so anything outside this shape is a caller bug.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def quote_ident(name: str) -> str:
    """Validate a SQL identifier, then return it double-quoted.

    THE canonical identifier guard for the Turso data path. Values are always
    bound (`?`); identifiers cannot be, so table and column names reach the
    statement by interpolation and are the one place injection can enter.

    Lives here rather than in turso_supabase_compat because this module is the
    layer every caller reaches — the compat shim is only ONE of them, and a guard
    that sits in the shim leaves every direct `get_db().insert(...)` unprotected.
    The compat shim delegates here (2026-08-15, point 6 of the 20-point matrix).

    An allowlist, not an escape: a name that is not a plain identifier is refused
    loudly rather than quoted-and-hoped.

    NOTE the deliberate gap: `select(where=..., order_by=..., columns=...)` are
    free-form SQL fragments by design — the documented escape hatch this API
    already exposes to 49 modules — and are NOT validated here. Never build them
    from untrusted input; pass values through `params` instead.
    """
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(
            f"unsafe SQL identifier: {name!r} — must match {_IDENT_RE.pattern}. "
            "Values are bound with ?; only table and column NAMES pass through here."
        )
    return f'"{name}"'


class TursoDB:
    def __init__(self, url: str, auth_token: str | None, mode: str):
        self.url = url
        self.mode = mode
        self._auth_token = auth_token  # kept for auto-reconnect on stale streams
        self._lock = threading.RLock()
        if auth_token:
            self._conn = libsql.connect(database=url, auth_token=auth_token)
        else:
            self._conn = libsql.connect(url)
        self._tenant_tables = self._discover_tenant_tables()
        log.info("Turso connected", mode=mode,
                 tenant_scoped_tables=len(self._tenant_tables))

    # -- schema awareness ---------------------------------------------------
    #
    # THE 38 SECONDS EVERY PROCESS PAID TO CONNECT. The loop below issues one
    # `PRAGMA table_info` per table against a REMOTE database — 206 sequential
    # round trips at ~258 ms each. Measured 2026-08-28: 38 of the 43 seconds
    # each briefing engine spent, and the daily brief fans out ten of them. That
    # is what was rendering "Client health: unavailable" in CC's brief while
    # client_health.py itself was returning `status: ok`.
    #
    # One query replaces all 206: 0.23 s, same 145 tables.
    #
    # BUT THIS SET IS A SECURITY BOUNDARY. `unscoped_tables()` exports it as the
    # tenant-scoping predicate, and an empty or short set reads as "nothing is
    # tenant-scoped" — a data-isolation failure, categorically worse than a slow
    # connect. So the fast path must prove itself: it is used only when it
    # returns a NON-EMPTY set, and any error or empty result falls through to
    # the slow loop rather than being trusted.
    def _discover_tenant_tables(self) -> frozenset[str]:
        """Every table with a tenant_id column, read from the live schema."""
        fast = self._discover_tenant_tables_fast()
        if fast:
            return fast
        return self._discover_tenant_tables_slow()

    def _discover_tenant_tables_fast(self) -> frozenset[str]:
        """One round trip via pragma_table_info as a table-valued function.

        Returns an EMPTY set on any problem — including a libsql build without
        TVF support — so the caller falls back rather than trusting a partial
        answer. Never let this raise: a connect that dies here takes down every
        caller of get_db().
        """
        try:
            rows = self._conn.execute(
                "select m.name from sqlite_master m "
                "join pragma_table_info(m.name) p on p.name = ? "
                "where m.type = 'table' and m.name not like 'sqlite_%'",
                (TENANT_COLUMN,),
            ).fetchall()
        except Exception:  # noqa: BLE001 — any failure means "use the slow path"
            return frozenset()
        return frozenset(name.lower() for (name,) in rows if name not in GLOBAL_TABLES)

    def _discover_tenant_tables_slow(self) -> frozenset[str]:
        """The original per-table PRAGMA walk. Correct, and 165x slower."""
        scoped: set[str] = set()
        rows = self._conn.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
        ).fetchall()
        for (name,) in rows:
            if name in GLOBAL_TABLES:
                continue
            cols = self._conn.execute(f"PRAGMA table_info({quote_ident(name)})").fetchall()
            if any(c[1] == TENANT_COLUMN for c in cols):
                scoped.add(name.lower())
        return frozenset(scoped)

    @property
    def tenant_tables(self) -> frozenset[str]:
        return self._tenant_tables

    def is_tenant_scoped(self, table: str) -> bool:
        return table.lower() in self._tenant_tables

    # An audit line nobody can read audits nothing. This WARNING fired on every
    # deliberate cross-tenant query and became 308,105 of 400,000 sampled lines
    # in state/logs/db_turso.log — 77% of a 190 MB file. The signal it carries
    # is real and must not be dropped, but the thing that made it useless was
    # repetition, not existence: the same handful of (reason, tables) pairs,
    # hundreds of thousands of times.
    #
    # First occurrence of each distinct pair logs in full. After that the pair
    # is counted and re-logged on a widening interval, carrying the running
    # total — so a NEW bypass is still immediately visible, and an existing one
    # is quantified instead of shouted.
    # WHY THIS IS NOT SHARED WITH THE OTHER THREE SUPPRESSORS. As of 2026-08-29
    # this fleet has four: notify.py (persisted, backoff, human-facing alerts),
    # event_router (persisted windows with a rollup, a long-running daemon),
    # outbound_log_post._hint_once (a one-shot bool), and this one. They look
    # like duplication and are not: the distinguishing requirement is LIFETIME.
    #
    # db_turso is imported by hundreds of short-lived scripts, so this counter
    # must stay in-process. Persisting it would put a file write on the hot path
    # of every connect and make every one of those processes contend on one
    # file — which is exactly the multi-writer race that stopped db_turso.log
    # rotating and let it reach 190 MB. A shared abstraction spanning all four
    # would be configured four different ways at four call sites, which is the
    # over-abstracted helper this repo bans, not an improvement.
    #
    # So: if you are adding a FIFTH, copy the shape that matches your lifetime.
    # Do not merge these.
    _unscoped_seen: dict = {}

    def _audit_unscoped(self, touched: list, reason: str | None, sql: str) -> None:
        key = (reason or "(no reason given)", tuple(touched))
        count = self._unscoped_seen.get(key, 0) + 1
        self._unscoped_seen[key] = count
        # 1st, 10th, 100th, 1000th ... — enough to see it is still happening and
        # how fast, without one line per query.
        if count > 1 and count % (10 ** min(len(str(count)) - 1, 4)) != 0:
            return
        log.warn("UNSCOPED QUERY ALLOWED — audit this", tables=list(touched),
                 reason=key[0], occurrences=count, sql=sql[:400])

    # -- the guard ----------------------------------------------------------
    def _enforce_scope(self, sql: str, *, allow_unscoped: bool, reason: str | None) -> None:
        if allow_unscoped:
            # Still parse, so a deliberate bypass is logged with the tables it
            # actually reaches rather than a vague "someone bypassed the guard".
            try:
                touched = sorted(referenced_tables(sql) & self._tenant_tables)
            except UnscopedQueryError:
                touched = ["<unparseable>"]
            if touched:
                self._audit_unscoped(touched, reason, sql)
            return
        offenders = unscoped_tables(sql, self._tenant_tables)
        if not offenders:
            return
        raise UnscopedQueryError(
            f"Tenant-scoped table(s) {sorted(offenders)} are read in a scope with no "
            f"{TENANT_COLUMN} predicate. Supabase RLS used to catch this; Turso "
            f"cannot — the query would return every tenant's rows. Add a "
            f"{TENANT_COLUMN} predicate to THAT scope (each UNION arm, CTE and "
            f"subquery counts separately), or pass allow_unscoped=True with a "
            f"reason if the query is genuinely cross-tenant.\nSQL: {sql[:400]}"
        )

    # -- raw execution ------------------------------------------------------

    # Hrana stream errors that indicate a stale WebSocket connection. Long-running
    # daemons (event-router, bravo-scheduler) hold a connection for hours; Turso's
    # server-side stream expires after an idle period and never comes back. Without
    # this, every query fails with "stream not found" until the process is manually
    # restarted — which is exactly what happened on 2026-08-08 (event-router
    # spamming the same error every 3 seconds for 18 hours).
    _HRANA_RECONNECT_PATTERNS = ("stream not found", "stream_expired", "server_error",
                                 "hrana", "connection closed")

    def _is_hrana_stale(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(p in msg for p in self._HRANA_RECONNECT_PATTERNS)

    def _reconnect(self) -> None:
        """Drop the dead connection and open a fresh one."""
        log.warn("Turso reconnecting — stale Hrana stream detected", mode=self.mode)
        try:
            if hasattr(self._conn, "close"):
                self._conn.close()
        except Exception:
            pass
        url, token = self.url, getattr(self, "_auth_token", None)
        if token:
            self._conn = libsql.connect(database=url, auth_token=token)
        else:
            self._conn = libsql.connect(url)
        log.info("Turso reconnected", mode=self.mode)

    def execute(self, sql: str, params: Sequence[Any] | None = None, *,
                allow_unscoped: bool = False, reason: str | None = None):
        self._enforce_scope(sql, allow_unscoped=allow_unscoped, reason=reason)
        with self._lock:
            try:
                return self._conn.execute(sql, tuple(params or ()))
            except Exception as exc:  # noqa: BLE001
                if self._is_hrana_stale(exc):
                    # Stale stream — reconnect and retry ONCE.
                    try:
                        self._reconnect()
                        return self._conn.execute(sql, tuple(params or ()))
                    except Exception as retry_exc:
                        log.error("Turso execute failed after reconnect",
                                  error=str(retry_exc), sql=sql[:400],
                                  traceback=traceback.format_exc())
                        raise
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

    def executemany(self, sql: str, seq_of_params: Sequence[Sequence[Any]], *,
                    allow_unscoped: bool = False, reason: str | None = None):
        """Batch execute. The scope check runs ONCE on the statement, not per row —
        the SQL is identical for every row, so parsing it 20,000 times would be
        pure waste, but skipping the check entirely would not."""
        self._enforce_scope(sql, allow_unscoped=allow_unscoped, reason=reason)
        if not hasattr(self._conn, "executemany"):
            raise AttributeError("libsql connection has no executemany")
        with self._lock:
            try:
                return self._conn.executemany(sql, list(seq_of_params))
            except Exception as exc:  # noqa: BLE001
                if self._is_hrana_stale(exc):
                    try:
                        self._reconnect()
                        return self._conn.executemany(sql, list(seq_of_params))
                    except Exception as retry_exc:
                        log.error("Turso executemany failed after reconnect",
                                  error=str(retry_exc), sql=sql[:400],
                                  rows=len(seq_of_params), traceback=traceback.format_exc())
                        raise
                log.error("Turso executemany failed", error=str(exc), sql=sql[:400],
                          rows=len(seq_of_params), traceback=traceback.format_exc())
                raise

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
        sql = f"SELECT {columns} FROM {quote_ident(table)}"
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
        col_sql = ", ".join(quote_ident(c) for c in cols)
        sql = f"INSERT INTO {quote_ident(table)} ({col_sql}) VALUES ({placeholders})"
        self.execute(sql, [row[c] for c in cols], allow_unscoped=True,
                     reason="insert stamps tenant_id via values")
        # execute() deliberately leaves the transaction open so a caller can batch.
        # A one-shot helper must not inherit that: without this commit the row is
        # visible to the connection that wrote it and to nothing else, so a
        # same-connection read-back confirms a write that was never durable.
        # claim() has always committed; insert() silently did not, which is the
        # kind of disagreement between neighbours that costs a night of debugging.
        self.commit()

    def claim(self, table: str, *, key: dict[str, Any], set_values: dict[str, Any],
              unclaimed_col: str, tenant_id: str | None = None) -> bool:
        """Compare-and-swap claim. Returns True iff THIS caller won the row.

        Replaces the reserve_send_slot PL/pgSQL RPC. A single conditional UPDATE
        is atomic in SQLite — no BEGIN EXCLUSIVE, no interactive transaction, so
        it behaves identically against a local file and remote Turso over HTTP.

        `set_values` MUST assign a non-NULL token to `unclaimed_col`. Without
        that the UPDATE leaves the row unclaimed, every later worker also wins,
        and the send goes out twice — while the caller is told it holds the slot.
        """
        if not key:
            raise ValueError("claim() requires a non-empty key — an unkeyed CAS "
                             "would claim every unclaimed row in the table.")
        if unclaimed_col not in set_values:
            raise ValueError(
                f"claim() requires set_values to assign {unclaimed_col!r}: that column "
                f"IS the claim marker. Updating other columns leaves the row unclaimed "
                f"and lets a second worker win the same slot."
            )
        if set_values[unclaimed_col] is None:
            raise ValueError(
                f"claim() requires a non-NULL owner token for {unclaimed_col!r} — "
                f"setting it back to NULL re-opens the row to every other worker."
            )
        sets = ", ".join(f"{quote_ident(c)} = ?" for c in set_values)
        args: list[Any] = list(set_values.values())
        conds = [f"{quote_ident(unclaimed_col)} IS NULL"]
        for col, val in key.items():
            conds.append(f"{quote_ident(col)} = ?")
            args.append(val)
        if tenant_id is not None:
            conds.append(f'"{TENANT_COLUMN}" = ?')
            args.append(tenant_id)
        elif self.is_tenant_scoped(table):
            raise UnscopedQueryError(
                f'claim("{table}") requires tenant_id — cross-tenant claims would let '
                f"one tenant's worker take another tenant's row."
            )
        sql = f"UPDATE {quote_ident(table)} SET {sets} WHERE " + " AND ".join(conds)
        cur = self.execute(sql, args, allow_unscoped=True, reason="claim scopes explicitly")
        self.commit()
        changed = getattr(cur, "rowcount", -1)
        if changed is not None and changed >= 0:
            return changed > 0
        # Driver did not report rowcount — read the row back and require the
        # marker to equal OUR token. Comparing against set_values without the
        # non-NULL check above would make None == None report a false win.
        check_conds = " AND ".join(f"{quote_ident(c)} = ?" for c in key)
        check_args = list(key.values())
        if tenant_id is not None:
            check_conds += f' AND "{TENANT_COLUMN}" = ?'
            check_args.append(tenant_id)
        probe = (f"SELECT {quote_ident(unclaimed_col)} AS v "
                 f"FROM {quote_ident(table)} WHERE {check_conds}")
        rows = self.query(probe, check_args, allow_unscoped=True,
                          reason="claim verification read")
        return bool(rows) and rows[0]["v"] == set_values[unclaimed_col]


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
