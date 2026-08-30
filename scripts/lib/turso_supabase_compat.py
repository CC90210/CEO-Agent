"""supabase-py–compatible client over Turso — the harness data-plane switch.

WHY. 49 modules in scripts/ call `supabase.create_client(...)` and speak the
postgrest-py builder dialect (`.table().select().eq()....execute().data`), plus
27 `.rpc(...)` call sites against 12 PL/pgSQL functions. Rewriting every module
is weeks of churn on production automations; giving them a byte-compatible
client over Turso means ZERO call-site changes. sitecustomize.py patches
`supabase.create_client` to return this class when EMPIRE_DATA_BACKEND=
turso_cloud — one env var flips the whole harness, deleting it flips it back.

WHAT IS FAITHFUL:
  .table(name)  select/insert/update/upsert/delete
                eq neq gt gte lt lte like ilike is_ in_ contains or_ filter match
                order limit range single maybe_single execute -> resp.data/.count
  .rpc(name)    dispatched to PYTHON ports of the PL/pgSQL sources (extracted to
                database/rpc_sources/ and ported line-by-line below); unknown
                RPCs raise loudly — never a silent no-op.

  .storage      backed by Cloudflare R2 (lib/r2_storage.py), keys shaped
                `<supabase-bucket>/<path>` — the same convention
                etl_storage_to_r2.py uploaded with and lib/r2-storage.ts writes
                with in the Next.js repos. Reads RAISE on a miss, matching
                supabase-py, so a missing attachment can never become an empty one.

WHAT IS NOT PROVIDED: .auth raises with guidance (auth flows are the apps'
concern; harness code never used them). Realtime channels likewise.

GUARD POSTURE. Calls run through lib.db_turso with allow_unscoped=True and an
audit reason naming the calling module: the harness is CC's single-operator
infra whose queries already carry their own tenant predicates where relevant
(e.g. the event bus is deliberately cross-tenant). Every unscoped statement
still lands in the audit log — permissive-but-audited, vs the strict fail-closed
guard the multi-tenant web apps keep.
"""
from __future__ import annotations

import inspect
import json
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.db_turso import (  # noqa: E402
    TursoDB,
    quote_ident,
    resolve_project_target,
)
from lib.r2_storage import storage_surface as r2_storage_surface  # noqa: E402
from lib.structured_log import get_logger  # noqa: E402

log = get_logger("turso_supabase_compat")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "+00:00")


def _caller() -> str:
    """Best-effort name of the harness module driving this query (audit trail)."""
    for frame in inspect.stack()[2:8]:
        f = frame.filename.replace("\\", "/")
        if "/scripts/" in f and "turso_supabase_compat" not in f and "sitecustomize" not in f:
            return f.rsplit("/scripts/", 1)[-1]
    return "unknown"


def _to_sql(v: Any) -> Any:
    if v is None or isinstance(v, (int, float, str)):
        return v
    if isinstance(v, bool):  # unreachable after int check on CPython; kept for clarity
        return 1 if v else 0
    if isinstance(v, (dict, list)):
        return json.dumps(v, separators=(",", ":"))
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


def _from_sql(v: Any) -> Any:
    if isinstance(v, str) and v[:1] in ("{", "["):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def _row_out(row: dict) -> dict:
    return {k: _from_sql(v) for k, v in row.items()}


class CompatError(Exception):
    pass


OPS = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}

# (table, sorted columns) -> the index's exact expression list, or None when the
# caller's bare column list is already correct. Populated lazily from
# sqlite_master; see CompatQuery._resolve_conflict_target.
_CONFLICT_TARGET_CACHE: dict[tuple[str, tuple[str, ...]], str | None] = {}


class _CompatNot:
    """Negation proxy returned by ``CompatQuery.not_``.

    Mirrors the postgrest-py pattern: ``query.not_.is_("col", "null")``
    negates the next filter and returns the original CompatQuery so further
    chaining (.order, .limit, .execute, more filters) keeps working.

    Only filter-like methods are proxied; structural calls (select, order,
    limit, execute) are intentionally missing — calling them on a negation
    proxy is a usage error, and an AttributeError there is the right signal.
    """

    def __init__(self, parent: "CompatQuery"):
        self._parent = parent

    def _neg(self, col: str, op: str, value):
        """Build the filter on a scratch query, wrap it in NOT, append to parent."""
        inner = CompatQuery(self._parent._db, self._parent._table)._op(col, op, value)
        sql, args = inner._conds[-1]
        self._parent._conds.append((f"NOT ({sql})", args))
        return self._parent

    def is_(self, c, v):   return self._neg(c, "is", v)      # noqa: E704
    def in_(self, c, v):   return self._neg(c, "in", v)      # noqa: E704
    def eq(self, c, v):    return self._neg(c, "eq", v)      # noqa: E704
    def neq(self, c, v):   return self._neg(c, "neq", v)     # noqa: E704
    def gt(self, c, v):    return self._neg(c, "gt", v)      # noqa: E704
    def gte(self, c, v):   return self._neg(c, "gte", v)     # noqa: E704
    def lt(self, c, v):    return self._neg(c, "lt", v)      # noqa: E704
    def lte(self, c, v):   return self._neg(c, "lte", v)     # noqa: E704
    def like(self, c, v):  return self._neg(c, "like", v)    # noqa: E704
    def ilike(self, c, v): return self._neg(c, "ilike", v)   # noqa: E704
    def contains(self, c, v): return self._neg(c, "cs", v)   # noqa: E704


class CompatQuery:
    """postgrest-py builder over TursoDB. Terminal call is .execute()."""

    def __init__(self, db: TursoDB, table: str):
        self._db = db
        # Validate once here so every downstream f-string that interpolates
        # `self._table` (SELECT/INSERT/UPDATE/DELETE/count) is safe by
        # construction rather than each needing its own guard.
        self._ident(table)
        self._table = table
        self._mode = "select"
        self._cols = "*"
        self._conds: list[tuple[str, list[Any]]] = []
        self._order: list[str] = []
        self._limit: int | None = None
        self._offset: int | None = None
        self._single: str | None = None
        self._count: str | None = None
        self._payload: list[dict] | None = None
        self._on_conflict: str | None = None

    # -- verbs
    def select(self, cols: str = "*", count: str | None = None, head: bool = False):
        if self._mode == "select":
            self._cols = cols or "*"
        self._count = count
        self._head = head
        return self

    def insert(self, values):
        self._mode = "insert"
        self._payload = values if isinstance(values, list) else [values]
        return self

    def upsert(self, values, on_conflict: str | None = None, **_kw):
        self._mode = "upsert"
        self._payload = values if isinstance(values, list) else [values]
        self._on_conflict = on_conflict
        return self

    def _resolve_conflict_target(self, tcols: list[str]) -> str | None:
        """Real ON CONFLICT target for a requested set of columns, or None.

        Returns an index's exact column/expression list when a UNIQUE index on
        this table covers precisely those columns but spells them differently
        (a COALESCE expression index). Returns None for ordinary column
        indexes, so the generated SQL is unchanged for every normal table.

        Matching is on the SET of column names, because PostgREST callers write
        `on_conflict` in whatever order reads well while the index has its own.

        Cached per (table, columns) — this costs a sqlite_master read and
        upserts run on hot paths.
        """
        if not tcols:
            return None
        key = (id(self._db), self._table, tuple(sorted(c.lower() for c in tcols)))
        if key in _CONFLICT_TARGET_CACHE:
            return _CONFLICT_TARGET_CACHE[key]

        resolved: str | None = None
        try:
            rows = self._db.query(
                "SELECT sql FROM sqlite_master WHERE type='index' "
                "AND tbl_name = ? AND sql IS NOT NULL",
                [self._table], allow_unscoped=True,
                reason="python-compat: resolve ON CONFLICT target")
            wanted = sorted(c.lower() for c in tcols)
            for row in rows:
                ddl = str(row.get("sql") or "")
                if not re.search(r"CREATE\s+UNIQUE\s+INDEX", ddl, re.I):
                    continue
                o, c = ddl.find("("), ddl.rfind(")")
                if o < 0 or c <= o:
                    continue
                inner = ddl[o + 1:c]
                # Only expression indexes need rewriting.
                if "COALESCE" not in inner.upper() and "(" not in inner:
                    continue
                # Strip string literals FIRST. The transpiler's sentinel is the
                # literal text "__null__", and an identifier regex happily
                # matches `u001f__null__` inside it — which makes the column set
                # look wrong and silently defeats this whole lookup. That exact
                # mistake shipped once on the TypeScript side.
                bare = re.sub(r"'(?:[^']|'')*'", "''", inner)
                words = [w.lower() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", bare)]
                cols_seen = sorted({w for w in words
                                    if w not in ("coalesce", "lower", "upper",
                                                 "nullif", "ifnull")})
                if cols_seen == wanted:
                    resolved = inner.strip()
                    break
        except Exception:  # noqa: BLE001 — never let this break the write path
            resolved = None
        _CONFLICT_TARGET_CACHE[key] = resolved
        return resolved

    def update(self, values: dict):
        self._mode = "update"
        self._payload = [values]
        return self

    def delete(self):
        self._mode = "delete"
        return self

    # -- filters
    @staticmethod
    def _ident(name: str) -> str:
        """Validate a SQL identifier, then quote it.

        Values in this builder are always bound (`?`); identifiers cannot be, so
        table and column names reach the statement by interpolation. Before
        2026-08-15 that interpolation was unguarded — `_q` returned `f'"{col}"'`
        with no validation and no escaping, so a name carrying a double quote
        closed the quoted identifier and the rest of the string was parsed as SQL.
        The TypeScript twin of this builder already regex-guarded both; the Python
        side did not, and this file sits on every DB call in the harness.

        An allowlist, not a denylist: anything that is not a plain identifier is
        refused rather than escaped-and-hoped. Call sites pass literals from our
        own code, so a rejection here means a bug in the caller, not a legitimate
        name we failed to anticipate — and it fails loudly instead of composing
        attacker-influenced SQL. Point 6 of the 20-Point Vibe-Security Matrix.
        """
        # Delegates to lib.db_turso.quote_ident — ONE guard for the whole data
        # path. Codex's audit of the first fix showed why this must not be a
        # local copy: a guard that lives in the shim leaves every direct
        # get_db().insert(...) caller unprotected, and the shim is only one of them.
        return quote_ident(name)

    def _q(self, col: str) -> str:
        if "->" in col:
            segs = col.replace("->>", "->").split("->")
            root, path = segs[0], "$." + ".".join(segs[1:])
            # `root` is an identifier; `path` lands inside a single-quoted SQL
            # string literal, so it needs literal-escaping (doubling) rather than
            # identifier validation — a segment containing an apostrophe would
            # otherwise terminate that literal.
            root = self._ident(root)[1:-1]
            path = path.replace("'", "''")
            # json_valid guard, not a bare json_extract. SQLite raises "malformed
            # JSON" and aborts the WHOLE statement if ANY scanned row holds
            # non-JSON text in that column -- one bad row makes the query return
            # nothing instead of returning the good rows. Postgres's ->> yields
            # NULL for such a row and keeps going, so this matches the semantics
            # the callers were written against.
            #
            # dashboard_email_consumer._fetch_queued wraps its query in
            # try/except, prints to stderr and returns []. PM2 discards stderr,
            # so without this a single malformed row silently stops the email
            # queue draining, with no error anywhere.
            return (f'CASE WHEN json_valid("{root}") '
                    f"THEN json_extract(\"{root}\", '{path}') END")
        return self._ident(col)

    def _op(self, col: str, op: str, value: Any):
        if op in OPS:
            v = 1 if value is True else 0 if value is False else value
            self._conds.append((f"{self._q(col)} {OPS[op]} ?", [_to_sql(v)]))
        elif op in ("like", "ilike"):
            pat = str(value).replace("*", "%")
            if op == "ilike":
                self._conds.append((f"lower({self._q(col)}) LIKE ?", [pat.lower()]))
            else:
                self._conds.append((f"{self._q(col)} LIKE ?", [pat]))
        elif op == "is":
            v = value if not isinstance(value, str) else value.lower()
            if v is None or v == "null":
                self._conds.append((f"{self._q(col)} IS NULL", []))
            elif v in (True, "true"):
                self._conds.append((f"{self._q(col)} = 1", []))
            elif v in (False, "false"):
                self._conds.append((f"{self._q(col)} = 0", []))
            elif v == "not.null":
                self._conds.append((f"{self._q(col)} IS NOT NULL", []))
            else:
                raise CompatError(f"unsupported is.{value}")
        elif op == "in":
            vals = list(value)
            ph = ", ".join("?" for _ in vals)
            self._conds.append((f"{self._q(col)} IN ({ph})", [_to_sql(v) for v in vals]))
        elif op in ("cs", "contains"):
            items = value if isinstance(value, (list, tuple)) else [value]
            for it in items:
                self._conds.append((
                    f"EXISTS (SELECT 1 FROM json_each({self._q(col)}) WHERE json_each.value = ?)",
                    [_to_sql(it)]))
        else:
            raise CompatError(f"unsupported operator {op!r}")
        return self

    def eq(self, c, v): return self._op(c, "eq", v)          # noqa: E704
    def neq(self, c, v): return self._op(c, "neq", v)        # noqa: E704
    def gt(self, c, v): return self._op(c, "gt", v)          # noqa: E704
    def gte(self, c, v): return self._op(c, "gte", v)        # noqa: E704
    def lt(self, c, v): return self._op(c, "lt", v)          # noqa: E704
    def lte(self, c, v): return self._op(c, "lte", v)        # noqa: E704
    def like(self, c, v): return self._op(c, "like", v)      # noqa: E704
    def ilike(self, c, v): return self._op(c, "ilike", v)    # noqa: E704
    def is_(self, c, v): return self._op(c, "is", v)         # noqa: E704
    def in_(self, c, v): return self._op(c, "in", v)         # noqa: E704
    def contains(self, c, v): return self._op(c, "cs", v)    # noqa: E704

    @property
    def not_(self):
        """Supabase postgrest-py negation modifier: .not_.is_("col", "null")
        becomes `col IS NOT NULL`.  Returns a thin proxy that wraps the next
        filter call in NOT(...) and then hands control back to self."""
        return _CompatNot(self)

    def filter(self, c, op, v):
        if op.startswith("not."):
            inner = CompatQuery(self._db, self._table)._op(c, op[4:], v)
            sql, args = inner._conds[-1]
            self._conds.append((f"NOT ({sql})", args))
            return self
        return self._op(c, op, v)

    def match(self, obj: dict):
        for c, v in obj.items():
            self.eq(c, v)
        return self

    def or_(self, expr: str):
        parts = []
        args: list[Any] = []
        for seg in expr.split(","):
            col, op, raw = seg.split(".", 2)
            lit: Any = raw
            if raw == "true":
                lit = True
            elif raw == "false":
                lit = False
            elif raw == "null":
                lit = None
            probe = CompatQuery(self._db, self._table)
            probe._op(col, op, lit)
            sql, a = probe._conds[-1]
            parts.append(sql)
            args.extend(a)
        self._conds.append(("(" + " OR ".join(parts) + ")", args))
        return self

    # -- modifiers
    def order(self, col: str, desc: bool = False, **_kw):
        self._order.append(f"{self._q(col)} {'DESC' if desc else 'ASC'}")
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def range(self, a: int, b: int):
        self._offset, self._limit = a, b - a + 1
        return self

    def single(self):
        self._single = "single"
        return self

    def maybe_single(self):
        self._single = "maybe"
        return self

    # -- execution
    def _where(self) -> tuple[str, list[Any]]:
        if not self._conds:
            return "", []
        return " WHERE " + " AND ".join(s for s, _ in self._conds), \
               [a for _, aa in self._conds for a in aa]

    def execute(self) -> SimpleNamespace:
        reason = f"python-compat: {_caller()}"
        if self._mode == "select":
            where, args = self._where()
            count = None
            if self._count:
                count = self._db.query(
                    f'SELECT count(*) AS n FROM "{self._table}"{where}', args,
                    allow_unscoped=True, reason=reason)[0]["n"]
                if getattr(self, "_head", False):
                    return SimpleNamespace(data=None, count=count)
            cols = self._cols if self._cols == "*" else ", ".join(
                self._q(c.strip()) for c in self._cols.split(","))
            sql = f'SELECT {cols} FROM "{self._table}"{where}'
            if self._order:
                sql += " ORDER BY " + ", ".join(self._order)
            if self._limit is not None:
                sql += f" LIMIT {int(self._limit)}"
            if self._offset is not None:
                sql += f" OFFSET {int(self._offset)}"
            rows = [_row_out(r) for r in self._db.query(sql, args, allow_unscoped=True,
                                                        reason=reason)]
            if self._single == "single":
                if len(rows) != 1:
                    raise CompatError(
                        f"single() expected exactly 1 row, got {len(rows)} "
                        f"({self._table})")
                return SimpleNamespace(data=rows[0], count=count)
            if self._single == "maybe":
                return SimpleNamespace(data=rows[0] if rows else None, count=count)
            return SimpleNamespace(data=rows, count=count)

        if self._mode in ("insert", "upsert"):
            rows = self._payload or []
            if not rows:
                return SimpleNamespace(data=[], count=None)
            cols = sorted({k for r in rows for k in r})
            col_sql = ", ".join(self._ident(c) for c in cols)
            one = "(" + ", ".join("?" for _ in cols) + ")"
            conflict = ""
            if self._mode == "upsert":
                target = ""
                tcols: list[str] = []
                if self._on_conflict:
                    tcols = [c.strip() for c in self._on_conflict.split(",")]
                    # SQLite matches an ON CONFLICT target against an index's
                    # columns AND EXPRESSIONS, exactly. Postgres
                    # `UNIQUE ... NULLS NOT DISTINCT` was transpiled into an
                    # EXPRESSION index — UNIQUE (email, COALESCE(tenant_id,'…'))
                    # — which a bare column list does not match, so the whole
                    expr = self._resolve_conflict_target(tcols)
                    target = (f"({expr})" if expr
                              else "(" + ", ".join(self._ident(c) for c in tcols) + ")")
                elif "id" in cols:
                    tcols = ["id"]
                    target = '("id")'
                setters = ", ".join(f"{self._ident(c)} = excluded.{self._ident(c)}"
                                    for c in cols if c not in tcols)
                conflict = (f" ON CONFLICT {target} DO UPDATE SET {setters}"
                            if setters else f" ON CONFLICT {target} DO NOTHING")
            sql = (f'INSERT INTO "{self._table}" ({col_sql}) VALUES '
                   + ", ".join(one for _ in rows) + conflict + " RETURNING *")
            args = [_to_sql(r.get(c)) for r in rows for c in cols]
            out = [_row_out(r) for r in self._db.query(sql, args, allow_unscoped=True,
                                                       reason=reason)]
            self._db.commit()
            return SimpleNamespace(data=out, count=None)

        if self._mode == "update":
            where, args = self._where()
            if not where:
                raise CompatError("update without filters refused")
            values = self._payload[0]
            sets = ", ".join(f"{self._ident(c)} = ?" for c in values)
            sql = f'UPDATE "{self._table}" SET {sets}{where} RETURNING *'
            out = [_row_out(r) for r in self._db.query(
                sql, [_to_sql(v) for v in values.values()] + args,
                allow_unscoped=True, reason=reason)]
            self._db.commit()
            return SimpleNamespace(data=out, count=None)

        if self._mode == "delete":
            where, args = self._where()
            if not where:
                raise CompatError("delete without filters refused")
            out = [_row_out(r) for r in self._db.query(
                f'DELETE FROM "{self._table}"{where} RETURNING *', args,
                allow_unscoped=True, reason=reason)]
            self._db.commit()
            return SimpleNamespace(data=out, count=None)

        raise CompatError(f"unknown mode {self._mode}")


# ------------------------------------------------------------------ RPC ports
# Each is a faithful port of database/rpc_sources/bravo__<name>.sql. SQLite has
# no advisory locks / SKIP LOCKED, so atomicity comes from single-statement
# conditional UPDATEs (a CAS is atomic in SQLite) and insert-then-verify dedupe.

def _rpc_reserve_send_slot(db: TursoDB, p: dict) -> dict:
    """reserve_send_slot: advisory-lock dedupe -> insert-then-verify dedupe.

    The Postgres version serialises per (lead, channel) with an advisory lock.
    Lock-free equivalent: always insert our reservation, then read the EARLIEST
    'reserving' row in the window for the pair. If it is ours we won; if not we
    withdraw ours and report the earlier one as existing. Two racers converge on
    the same winner because both read the same earliest row.
    """
    reason = "python-compat rpc: reserve_send_slot"
    lead_id = p.get("p_lead_id")
    channel = p.get("p_channel")
    window_min = int(p.get("p_window_minutes") or 0)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=window_min)).isoformat()

    new_id = str(uuid.uuid4())
    created = _now()
    db.execute(
        'INSERT INTO "lead_interactions" (id, lead_id, type, channel, created_at, '
        "subject, content, agent_source, cooldown_until, metadata, actor_user_id) "
        "VALUES (?, ?, 'reserving', ?, ?, ?, ?, ?, ?, ?, ?)",
        [new_id, lead_id, channel, created,
         (p.get("p_subject") or "")[:500],
         (p.get("p_content_preview") or "")[:1000],
         p.get("p_agent_source"),
         _to_sql(p.get("p_cooldown_until")),
         _to_sql(p.get("p_metadata") or {}),
         p.get("p_actor_user_id")],
        allow_unscoped=True, reason=reason)
    db.commit()

    rows = db.query(
        'SELECT id, created_at FROM "lead_interactions" '
        "WHERE lead_id = ? AND channel = ? AND type = 'reserving' AND created_at >= ? "
        "ORDER BY created_at ASC, id ASC LIMIT 1",
        [lead_id, channel, cutoff], allow_unscoped=True, reason=reason)
    winner = rows[0] if rows else None

    if winner and winner["id"] != new_id:
        db.execute('DELETE FROM "lead_interactions" WHERE id = ?', [new_id],
                   allow_unscoped=True, reason=reason)
        db.commit()
        return {"lock_acquired": True, "existing_id": winner["id"],
                "reservation_id": None, "reservation_created_at": None}
    return {"lock_acquired": True, "existing_id": None,
            "reservation_id": new_id, "reservation_created_at": created}


def _rpc_claim_events(db: TursoDB, p: dict) -> list[dict]:
    """claim_events: FOR UPDATE SKIP LOCKED -> per-row CAS claim loop."""
    reason = "python-compat rpc: claim_events"
    agent = p.get("p_agent")
    p_max = int(p.get("p_max") or 10)
    vis = int(p.get("p_visibility_seconds") or 30)
    now = _now()
    until = (datetime.now(timezone.utc) + timedelta(seconds=vis)).isoformat()

    candidates = db.query(
        'SELECT id FROM "agent_events" '
        "WHERE status = 'pending' AND (target_agent = ? OR target_agent IS NULL) "
        "AND (visibility_until IS NULL OR visibility_until <= ?) "
        "ORDER BY published_at LIMIT ?",
        [agent, now, p_max * 2], allow_unscoped=True, reason=reason)

    claimed: list[dict] = []
    for c in candidates:
        # RETURNING, not rowcount: a remote Hrana cursor reports rowcount as
        # -1/None often enough that db_turso.claim() was hardened against it.
        # Trusting it here would build an empty `claimed` list while the UPDATEs
        # really did land -- the events end up marked 'processing', claimed by
        # nobody, and are never handled until reap_stuck_events happens to
        # rescue them.
        won = _returning(
            db,
            'UPDATE "agent_events" SET status = ?, processed_by = ?, visibility_until = ? '
            "WHERE id = ? AND status = 'pending' RETURNING id",
            ["processing", agent, until, c["id"]], reason)
        if won:
            claimed.append(c["id"])
        if len(claimed) >= p_max:
            break
    db.commit()
    if not claimed:
        return []
    ph = ", ".join("?" for _ in claimed)
    return [_row_out(r) for r in db.query(
        f'SELECT * FROM "agent_events" WHERE id IN ({ph})', claimed,
        allow_unscoped=True, reason=reason)]


def _rpc_ack_event(db: TursoDB, p: dict) -> bool:
    # RETURNING rather than rowcount -- see the note in _rpc_claim_events. A
    # false negative here makes a consumer believe its ack failed and reprocess
    # an event that was in fact already marked done.
    won = _returning(
        db,
        'UPDATE "agent_events" SET status = ?, processed_at = ?, processed_by = ? '
        "WHERE id = ? AND status IN ('processing', 'pending') RETURNING id",
        ["done", _now(), p.get("p_agent"), p.get("p_event_id")],
        "python-compat rpc: ack_event")
    db.commit()
    return bool(won)


def _rpc_fail_event(db: TursoDB, p: dict) -> str:
    reason = "python-compat rpc: fail_event"
    eid = p.get("p_event_id")
    max_retries = int(p.get("p_max_retries") or 3)
    db.execute(
        'UPDATE "agent_events" SET retry_count = retry_count + 1, last_error = ?, '
        "processed_by = ? WHERE id = ?",
        [p.get("p_error"), p.get("p_agent"), eid], allow_unscoped=True, reason=reason)
    rows = db.query('SELECT retry_count FROM "agent_events" WHERE id = ?', [eid],
                    allow_unscoped=True, reason=reason)
    new_count = rows[0]["retry_count"] if rows else 0
    new_status = "dead" if new_count >= max_retries else "pending"
    db.execute('UPDATE "agent_events" SET status = ?, visibility_until = NULL WHERE id = ?',
               [new_status, eid], allow_unscoped=True, reason=reason)
    db.commit()
    return new_status


def _rpc_mark_event_consumed(db: TursoDB, p: dict) -> bool:
    """consumed_by was text[]; in Turso it is a JSON array in TEXT."""
    reason = "python-compat rpc: mark_event_consumed"
    eid, agent = p.get("p_event_id"), p.get("p_agent")
    rows = db.query('SELECT consumed_by FROM "agent_events" WHERE id = ?', [eid],
                    allow_unscoped=True, reason=reason)
    if not rows:
        return False
    consumed = _from_sql(rows[0]["consumed_by"]) or []
    if agent in consumed:
        return False
    consumed.append(agent)
    db.execute('UPDATE "agent_events" SET consumed_by = ? WHERE id = ?',
               [json.dumps(consumed), eid], allow_unscoped=True, reason=reason)
    db.commit()
    return True


def _rpc_reap_stuck_events(db: TursoDB, p: dict) -> int:
    cur = db.execute(
        'UPDATE "agent_events" SET status = ?, visibility_until = NULL, '
        "retry_count = retry_count + 1, "
        "last_error = COALESCE(last_error, '') || ' | visibility-timeout-reaped' "
        "WHERE status = 'processing' AND visibility_until <= ?",
        ["pending", _now()], allow_unscoped=True,
        reason="python-compat rpc: reap_stuck_events")
    db.commit()
    return max(0, getattr(cur, "rowcount", 0))


def _rpc_record_inbound_from_n8n(db: TursoDB, p: dict) -> dict:
    """Port of record_inbound_from_n8n — the */5-min inbound email chokepoint.

    Upsert lead by email -> insert interaction -> publish inbound.classified on
    the event bus, returning the same jsonb handles. Steps run in sequence with
    a commit at the end; a failure raises (matching the PL/pgSQL RAISE) rather
    than half-logging silently.
    """
    reason = "python-compat rpc: record_inbound_from_n8n"
    email = (p.get("p_from_email") or "").strip().lower()
    if not email or "@" not in email:
        raise CompatError(
            "record_inbound_from_n8n: from_email is required and must look like an email")
    from_name = (p.get("p_from_name") or "").strip() or None
    name = from_name or email.split("@", 1)[0]
    now = p.get("p_received_at") or _now()
    classification = p.get("p_classification") or {}

    rows = db.query('SELECT id FROM "leads" WHERE email = ? LIMIT 1', [email],
                    allow_unscoped=True, reason=reason)
    lead_was_new = not rows
    if lead_was_new:
        lead_id = str(uuid.uuid4())
        db.execute(
            'INSERT INTO "leads" (id, name, email, status, source, created_at, '
            "updated_at, last_contacted_at) VALUES (?, ?, ?, 'new', 'inbound_n8n', ?, ?, ?)",
            [lead_id, name, email, now, now, now], allow_unscoped=True, reason=reason)
    else:
        lead_id = rows[0]["id"]
        db.execute('UPDATE "leads" SET last_contacted_at = ?, updated_at = ? WHERE id = ?',
                   [now, now, lead_id], allow_unscoped=True, reason=reason)

    interaction_id = str(uuid.uuid4())
    subject = (p.get("p_subject") or "").strip() or None
    db.execute(
        'INSERT INTO "lead_interactions" (id, lead_id, type, channel, subject, content, '
        "agent_source, metadata, created_at) VALUES (?, ?, 'email_received', 'email', "
        "?, ?, 'n8n_inbound', ?, ?)",
        [interaction_id, lead_id, subject, (p.get("p_content") or "")[:2000],
         json.dumps({
             "from_identity": email, "from_name": from_name,
             "thread_id": p.get("p_thread_id"), "message_id": p.get("p_message_id"),
             "received_at": now, "classification": classification,
             "source_workflow": "oasis_inbound_qualifier",
         }, separators=(",", ":")), now],
        allow_unscoped=True, reason=reason)

    priority = str(classification.get("priority", "unknown"))
    intent = str(classification.get("intent", "unknown"))
    severity = "warn" if (priority == "hot"
                          or intent in ("unsubscribe", "objection", "booking")) else "info"
    event_id = str(uuid.uuid4())
    db.execute(
        'INSERT INTO "agent_events" (id, event_type, publisher_agent, severity, payload, '
        "correlation_id, published_at) VALUES (?, 'inbound.classified', 'n8n', ?, ?, ?, ?)",
        [event_id, severity, json.dumps({
            "interaction_id": interaction_id, "lead_id": lead_id,
            "lead_was_new": lead_was_new, "from_identity": email,
            "from_name": from_name, "subject": subject,
            "thread_id": p.get("p_thread_id"), "message_id": p.get("p_message_id"),
            "classification": classification,
        }, separators=(",", ":")), interaction_id, now],
        allow_unscoped=True, reason=reason)
    db.commit()
    return {"status": "ok", "lead_id": lead_id, "lead_was_new": lead_was_new,
            "interaction_id": interaction_id, "event_id": event_id,
            "severity": severity, "received_at": now}


def _returning(db: TursoDB, sql: str, args: list, reason: str) -> list[dict]:
    """Run a statement with RETURNING and map its rows to dicts.

    Everything that needs to know whether a conditional UPDATE actually matched
    goes through here rather than reading cursor.rowcount. Remote Hrana cursors
    report rowcount as -1/None often enough that db_turso.claim() was hardened
    against exactly that, and a claim loop that trusts it silently reports "I
    claimed nothing" while the UPDATEs really did land -- rows are then marked
    in-flight and never processed by anyone. RETURNING is authoritative: a row
    comes back if and only if the row was updated. SQLite has supported it since
    3.35; Turso is 3.45.
    """
    cur = db.execute(sql, args, allow_unscoped=True, reason=reason)
    try:
        rows = cur.fetchall()
    except Exception:  # noqa: BLE001 - a statement that returned nothing
        return []
    desc = getattr(cur, "description", None)
    if not desc:
        return []
    cols = [d[0] for d in desc]
    return [dict(zip(cols, r)) for r in (rows or [])]


def _rpc_claim_sequence_state_row(db: TursoDB, p: dict) -> list[dict]:
    """claim_sequence_state_row: the drip engine's race guard.

    Source: SunBiz-Agent database/046_sequence_state_atomic_claim.sql. Two
    workers (or a daemon overlapping a PM2 restart across a tick boundary) can
    both read the same scheduled row and both physically dispatch the send --
    send_gateway's cooldown is downstream and only catches it after the second
    message has left for the lead. The claim is the guard.

    Without this port every candidate row raises CompatError, sequence_runner
    catches it per row and continues, and execution_tick processes ZERO rows on
    every 10-second tick forever while pm2 reports the daemon healthy.

    A non-empty return means this caller won and may dispatch.
    """
    reason = "python-compat rpc: claim_sequence_state_row"
    rows = _returning(
        db,
        'UPDATE "sequence_state" SET claimed_at = ?, claimed_by = ? '
        "WHERE id = ? AND status = 'scheduled' AND claimed_at IS NULL "
        "RETURNING *",
        [_now(), p.get("claimer") or "sequence_runner", p.get("row_id")],
        reason)
    db.commit()
    return [_row_out(r) for r in rows]


def _rpc_release_sequence_state_claim(db: TursoDB, p: dict) -> None:
    """Clear a claim so the row is picked up again on the next tick.

    Called after a cooldown / transient reschedule. Terminal statuses do not
    need it -- the claimable index only matches status='scheduled'. Missing this
    port would strand every cooldowned row as permanently claimed.
    """
    db.execute('UPDATE "sequence_state" SET claimed_at = NULL, claimed_by = NULL '
               "WHERE id = ?", [p.get("row_id")], allow_unscoped=True,
               reason="python-compat rpc: release_sequence_state_claim")
    db.commit()
    return None


def _rpc_query_sql(db: TursoDB, p: dict) -> list[dict]:
    """query_sql: read-only raw SQL, the bridge's primary database tool.

    supabase_tool.py `query` calls this and sys.exit(2)s when it raises, so
    without the port every raw-SQL question asked through the dashboard chat
    (the claude-bridge daemon) dies.

    allow_unscoped is deliberately NOT set: the sqlglot tenant guard in
    db_turso judges the statement, which is a stricter boundary than the
    Postgres original had -- there the caller's RLS context did the work, and
    Turso has no RLS to fall back on.
    """
    sql = (p.get("sql_query") or p.get("query") or p.get("sql") or "").strip()
    if not sql:
        raise CompatError("query_sql called with no SQL")
    return db.query(sql, [], reason="python-compat rpc: query_sql")


def _rpc_exec_sql(db: TursoDB, p: dict) -> dict:
    """exec_sql: statement execution used by the migration applier.

    apply_migration.py treats a False return as "RPC unavailable" and falls
    through to the Supabase Management API -- which means DDL lands in Supabase
    while the ledger records it against Turso. After cancellation that branch
    fails outright. Porting it keeps migrations on the backend the ledger names.
    """
    sql = (p.get("sql") or p.get("sql_query") or "").strip()
    if not sql:
        raise CompatError("exec_sql called with no SQL")
    db.execute(sql, [], allow_unscoped=True, reason="python-compat rpc: exec_sql")
    db.commit()
    return {"status": "ok"}


def _rpc_patch_tenant_record_data(db: TursoDB, p: dict) -> dict:
    """patch_tenant_record_data: shallow merge into tenant_records.data.

    Postgres did `data = data || patch` (jsonb concat). SQLite's json_patch is
    the RFC-7386 merge, which matches for the flat objects this is called with
    and additionally deletes keys whose value is null -- the same thing jsonb
    concat does not do, so nulls are filtered out first to keep the semantics
    identical.

    Without this, pause_lead succeeds and resume_lead silently does nothing:
    the lead stays paused with every surface reporting the resume worked.
    """
    reason = "python-compat rpc: patch_tenant_record_data"
    rec_id = p.get("p_id") or p.get("record_id") or p.get("id")
    tenant_id = p.get("p_tenant_id") or p.get("tenant_id")
    patch = p.get("p_patch") or p.get("patch") or {}
    if isinstance(patch, str):
        patch = _from_sql(patch) or {}
    # jsonb `||` overwrites with null rather than deleting; json_patch deletes.
    patch = {k: v for k, v in dict(patch).items() if v is not None}

    sql = ('UPDATE "tenant_records" SET data = json_patch(COALESCE(data, \'{}\'), ?) '
           "WHERE id = ?")
    args: list = [json.dumps(patch, separators=(",", ":")), rec_id]
    if tenant_id:
        sql += " AND tenant_id = ?"
        args.append(tenant_id)
    rows = _returning(db, sql + " RETURNING id", args, reason)
    db.commit()
    if not rows:
        raise CompatError(
            f"patch_tenant_record_data matched no row (id={rec_id!r}, "
            f"tenant_id={tenant_id!r}). Refusing to report success for a patch "
            f"that changed nothing.")
    return {"status": "ok", "id": rows[0].get("id")}


def _rpc_ping_integration(db: TursoDB, p: dict) -> None:
    """ping_integration: the heartbeat behind EVERY integrations_health row.

    Source: database/rpc_sources/bravo__ping_integration__5arg.sql.

    Its absence from this registry is why health monitoring went dark fleet-wide
    at the cutover and nobody noticed. integration_health.ping() is best-effort
    by design -- it catches everything, prints to stderr and returns False -- so
    an unported RPC produced no exception, no alert, and a frozen
    integrations_health table that still LOOKED populated because the old rows
    were still there. Every daemon reported healthy by virtue of saying nothing.

    resolve_tenant_for_profile() is a plpgsql helper; the tenant is resolved
    here with the equivalent lookup instead of porting a second function whose
    only caller is this one.
    """
    reason = "python-compat rpc: ping_integration"
    profile_id = p.get("p_profile_id")
    service = p.get("p_service")
    status = p.get("p_status") or "healthy"
    err = p.get("p_error")
    meta = p.get("p_metadata")
    if isinstance(meta, str):
        meta = _from_sql(meta) or {}
    now = _now()

    rows = db.query('SELECT tenant_id FROM "user_profiles" WHERE id = ?',
                    [profile_id], allow_unscoped=True, reason=reason)
    tenant_id = rows[0]["tenant_id"] if rows else None

    # COALESCE(EXCLUDED.tenant_id, existing) — a profile that cannot be resolved
    # must not blank a tenant_id that is already correct.
    db.execute(
        'INSERT INTO "integrations_health" '
        "(tenant_id, profile_id, service, status, last_ping_at, last_error, "
        " metadata, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(profile_id, service) DO UPDATE SET "
        '  tenant_id = COALESCE(excluded.tenant_id, "integrations_health".tenant_id), '
        "  status = excluded.status, last_ping_at = ?, "
        "  last_error = excluded.last_error, metadata = excluded.metadata, "
        "  updated_at = ?",
        [tenant_id, profile_id, service, status, now, err,
         json.dumps(meta or {}, separators=(",", ":")), now, now, now],
        allow_unscoped=True, reason=reason)
    db.commit()
    return None


def _rpc_shop_out_next_round_number(db: TursoDB, p: dict) -> int:
    """shop_out_next_round_number: the next round for a lead's shop-out.

    Source: database/rpc_sources/bravo__shop_out_next_round_number__2arg.sql.

    AUTHORIZATION. The Postgres version branches on auth.role()/auth.uid() and
    refuses non-members of the tenant. There is no auth context here: a Turso
    token is a full-database credential, so every caller through this shim is
    service-role equivalent — which is the branch the original takes for its
    only real callers (server-side daemons). The tenant argument is still
    applied to the query, so the ANSWER is tenant-scoped even though the
    caller's membership is not re-checked. Do not expose this RPC to a browser.

    pg_advisory_xact_lock is dropped deliberately: it serialised concurrent
    callers for the same (tenant, lead) so two rounds could not take the same
    number. SQLite serialises writers globally, so the read is already
    consistent with respect to other writes through this connection.
    """
    reason = "python-compat rpc: shop_out_next_round_number"
    rows = db.query(
        'SELECT COALESCE(MAX(round_number), 0) + 1 AS n FROM "shopping_threads" '
        "WHERE tenant_id = ? AND lead_id = ?",
        [p.get("p_tenant_id"), p.get("p_lead_id")], reason=reason)
    return int(rows[0]["n"]) if rows else 1


def _rpc_shop_out_patch_lender(db: TursoDB, p: dict):
    """shop_out_patch_lender: merge a patch into one lender inside lenders[].

    Source: database/rpc_sources/bravo__shop_out_patch_lender__3arg.sql.

    Postgres located the element with jsonb_array_elements WITH ORDINALITY and
    rewrote it via jsonb_set(..., existing || patch). Two things carry over
    exactly:

      * the merge is jsonb `||` — a SHALLOW merge that KEEPS null values.
        json_patch would delete null-valued keys, so the merge happens in
        Python. Wiping a lender field by patching it to null is a real
        operation here (e.g. clearing a declined reason).
      * a miss returns None, and so does a lender_id that is not in the array —
        the original deliberately makes "no such round" and "no such lender"
        indistinguishable.

    See the authorization note on shop_out_next_round_number; it applies here
    too, except that this one is a WRITE, so it must never be reachable from a
    browser-held credential.
    """
    reason = "python-compat rpc: shop_out_patch_lender"
    round_id = p.get("p_round_id")
    lender_id = p.get("p_lender_id")
    patch = p.get("p_patch") or {}
    if isinstance(patch, str):
        patch = _from_sql(patch) or {}

    rows = db.query('SELECT lenders FROM "shopping_threads" WHERE id = ?',
                    [round_id], allow_unscoped=True, reason=reason)
    if not rows:
        return None
    lenders = _from_sql(rows[0]["lenders"]) or []
    if not isinstance(lenders, list):
        return None

    idx = next((i for i, el in enumerate(lenders)
                if isinstance(el, dict) and el.get("lender_id") == lender_id), None)
    if idx is None:
        return None

    lenders[idx] = {**(lenders[idx] or {}), **dict(patch)}   # jsonb `||`

    out = _returning(
        db,
        'UPDATE "shopping_threads" SET lenders = ?, updated_at = ? '
        "WHERE id = ? RETURNING *",
        [json.dumps(lenders, separators=(",", ":")), _now(), round_id], reason)
    db.commit()
    return _row_out(out[0]) if out else None


def _rpc_materialize_today_plan(db: TursoDB, p: dict):
    """materialize_today_plan: get-or-create today's plan for a profile.

    Source: database/rpc_sources/bravo__materialize_today_plan__2arg.sql.
    Driven by a daily Vercel cron (/api/cron/materialize-plans, 03:00).

    The original is insert-or-no-op: ON CONFLICT DO NOTHING returns no row when
    the plan already exists, and a follow-up SELECT fetches the existing id, so
    EVERY caller gets a real id and none sees a duplicate-key error. Preserved
    exactly — returning None on the second call of the day would make the cron
    look broken on every run after the first.

    EXTRACT(DOW) is 0=Sunday..6=Saturday. Python's weekday() is 0=Monday, so it
    is converted rather than used directly; getting this wrong silently applies
    the weekday template on a Saturday.
    """
    reason = "python-compat rpc: materialize_today_plan"
    profile_id = p.get("p_profile_id")
    target = p.get("p_target_date")
    if not target:
        target = datetime.now(timezone.utc).date().isoformat()
    target = str(target)[:10]

    d = datetime.strptime(target, "%Y-%m-%d")
    dow = (d.weekday() + 1) % 7            # Python Mon=0 -> Postgres Sun=0
    kind = "weekend" if dow in (0, 6) else "weekday"

    prof = db.query('SELECT tenant_id FROM "user_profiles" WHERE id = ?',
                    [profile_id], allow_unscoped=True, reason=reason)
    tenant_id = prof[0]["tenant_id"] if prof else None
    if not tenant_id:
        raise CompatError("profile has no tenant_id")

    tpl_rows = db.query(
        'SELECT mission, target_calls, target_emails, target_bookings, schedule '
        'FROM "plan_templates" WHERE profile_id = ? AND kind = ? AND enabled = 1 '
        "LIMIT 1", [profile_id, kind], allow_unscoped=True, reason=reason)
    t = tpl_rows[0] if tpl_rows else {}

    new_id = str(uuid.uuid4())
    inserted = _returning(
        db,
        'INSERT INTO "daily_plans" (id, tenant_id, profile_id, plan_date, mission, '
        " target_calls, target_emails, target_bookings, schedule) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(profile_id, plan_date) DO NOTHING RETURNING id",
        [new_id, tenant_id, profile_id, target,
         t.get("mission") or "Daily ops",
         t.get("target_calls") or 0,
         t.get("target_emails") or 0,
         t.get("target_bookings") if t.get("target_bookings") is not None else 1,
         _to_sql(t.get("schedule") if t.get("schedule") is not None else [])],
        reason)
    db.commit()
    if inserted:
        return inserted[0].get("id")

    existing = db.query(
        'SELECT id FROM "daily_plans" WHERE profile_id = ? AND plan_date = ?',
        [profile_id, target], allow_unscoped=True, reason=reason)
    return existing[0]["id"] if existing else None


RPC_REGISTRY = {
    "ping_integration": _rpc_ping_integration,
    "shop_out_next_round_number": _rpc_shop_out_next_round_number,
    "shop_out_patch_lender": _rpc_shop_out_patch_lender,
    "materialize_today_plan": _rpc_materialize_today_plan,
    "record_inbound_from_n8n": _rpc_record_inbound_from_n8n,
    "reserve_send_slot": _rpc_reserve_send_slot,
    "claim_events": _rpc_claim_events,
    "ack_event": _rpc_ack_event,
    "fail_event": _rpc_fail_event,
    "mark_event_consumed": _rpc_mark_event_consumed,
    "reap_stuck_events": _rpc_reap_stuck_events,
    "claim_sequence_state_row": _rpc_claim_sequence_state_row,
    "release_sequence_state_claim": _rpc_release_sequence_state_claim,
    "query_sql": _rpc_query_sql,
    "exec_sql": _rpc_exec_sql,
    "patch_tenant_record_data": _rpc_patch_tenant_record_data,
}


class _RpcQuery:
    """Matches supabase-py's lazy rpc: client.rpc(name, params).execute()."""

    def __init__(self, db: TursoDB, name: str, params: dict | None):
        self._db, self._name, self._params = db, name, params or {}

    def execute(self) -> SimpleNamespace:
        fn = RPC_REGISTRY.get(self._name)
        if fn is None:
            raise CompatError(
                f'rpc("{self._name}") has no Turso port. PL/pgSQL did not migrate; '
                f"port it into RPC_REGISTRY (source: database/rpc_sources/) rather "
                f"than calling Supabase."
            )
        return SimpleNamespace(data=fn(self._db, self._params))


class _Refuser:
    def __init__(self, surface: str):
        self._surface = surface

    def __getattr__(self, item):
        raise CompatError(
            f"supabase.{self._surface}.{item} is not available on the Turso compat "
            f"client — {self._surface} did not migrate. If this call is essential, "
            f"the module must be ported explicitly."
        )


class TursoSupabaseCompat:
    """Drop-in for supabase-py's Client, backed by the bravo-empire Turso DB."""

    def __init__(self, db: TursoDB | None = None):
        if db is None:
            url, token, mode = resolve_project_target("bravo")
            db = TursoDB(url, token, mode)
        self._db = db
        self.auth = _Refuser("auth")
        # .storage used to be a _Refuser too. That was the right fail-closed
        # default while there was nowhere for the bytes to come from, and the
        # wrong answer once there was: three runtime paths read objects
        # (send_gateway shop-out attachments, extraction_consumer's application
        # PDF, the SunBiz tenant export), and a refusal there means a funder gets
        # an email with no contract attached. Cloudflare R2 holds every migrated
        # object at `<supabase-bucket>/<path>`, so .storage now points at it.
        # Building the surface touches neither credentials nor the network — an
        # unconfigured R2 fails at the read, naming the missing keys, rather than
        # breaking every process that merely constructs a client.
        self.storage = r2_storage_surface()

    def table(self, name: str) -> CompatQuery:
        return CompatQuery(self._db, name)

    # supabase-py alias
    def from_(self, name: str) -> CompatQuery:
        return CompatQuery(self._db, name)

    def rpc(self, name: str, params: dict | None = None) -> _RpcQuery:
        return _RpcQuery(self._db, name, params)


# Supabase project ref -> Turso project key. Refs verified live 2026-08-05;
# same table as core/turso_schema_transpiler.PROJECTS, kept here so this module
# has no import cycle back into scripts/core.
_REF_TO_PROJECT = {
    "phctllmtsogkovoilwos": "bravo",
    "xugwrhvaoihyidtdgwkq": "breeze",
    "jqybbrtzpvmefgzzdagz": "nostalgic",
    "xusnasmzoxkaimyjqbie": "propflow",
    "skgrbweyscysyetubemg": "oasis",
}

# Project names accepted by the .turso.compat URL shim — mirrors
# lib.db_turso.PROJECT_ENV_VARS, which resolve_project_target() validates
# against. Kept as a set so `https://<project>.turso.compat` fallback URLs
# (built by integrations/supabase_tool.py when a product's legacy Supabase
# keys are absent) resolve to a real database instead of raising NameError.
_TARGETS = frozenset(_REF_TO_PROJECT.values())

# One client per project; TursoDB introspects the schema on connect (a PRAGMA
# per table, 118 tenant-scoped tables on bravo alone), so rebuilding per call
# would put hundreds of round trips in front of every query.
_CLIENT_CACHE: dict[str, TursoSupabaseCompat] = {}


def _project_for_url(url: str) -> str:
    """Which Turso database does this Supabase URL mean?

    This used to be ignored entirely: create_client(url, key) discarded both
    arguments and always returned bravo. For the ~49 bravo-scoped call sites
    that was invisibly fine. For anything pointed at breeze, propflow, oasis or
    nostalgic it was a silent wrong-database read — and only loud when the table
    happened not to exist in bravo (which is how it was caught: a breeze query
    for `interactions` died with "no such table"). Where a name exists in BOTH
    schemas — leads, documents, webhook_events, automation_logs — it would have
    returned another product's rows with no error at all.
    """
    m = re.search(r"https?://([a-z0-9]{20})\.supabase\.co", url or "", re.I)
    if not m:
        m_compat = re.search(r"https?://([a-z0-9_-]+)\.turso\.compat", url or "", re.I)
        if m_compat:
            target_proj = m_compat.group(1).lower()
            if target_proj in _TARGETS:
                return target_proj
        # No URL at all or bare turso.compat is the harness's own shorthand for "the bravo db".
        if not (url or "").strip() or "turso.compat" in (url or "").lower():
            return "bravo"
        raise ValueError(
            f"turso compat: cannot tell which database {url!r} refers to. "
            f"Pass a Supabase project URL, or construct "
            f"TursoSupabaseCompat(TursoDB(*resolve_project_target('<project>'))) "
            f"explicitly.")
    ref = m.group(1).lower()
    project = _REF_TO_PROJECT.get(ref)
    if not project:
        # Refusing beats guessing: defaulting to bravo is the original bug.
        raise ValueError(
            f"turso compat: Supabase project ref {ref!r} is not mapped to a "
            f"Turso database. Add it to _REF_TO_PROJECT rather than letting it "
            f"fall through to bravo.")
    return project


def create_client(url: str = "", key: str = "", *a, **kw) -> TursoSupabaseCompat:
    """Signature-compatible replacement for supabase.create_client."""
    project = _project_for_url(url)
    cached = _CLIENT_CACHE.get(project)
    if cached is not None:
        return cached
    turso_url, token, mode = resolve_project_target(project)
    client = TursoSupabaseCompat(TursoDB(turso_url, token, mode))
    _CLIENT_CACHE[project] = client
    log.info("Turso compat client issued", caller=_caller(), project=project)
    return client
