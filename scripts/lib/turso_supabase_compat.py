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

WHAT IS NOT PROVIDED: .auth and .storage raise with guidance (auth flows are the
apps' concern; harness code never used them). Realtime channels likewise.

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
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.db_turso import TursoDB, resolve_project_target  # noqa: E402
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


class CompatQuery:
    """postgrest-py builder over TursoDB. Terminal call is .execute()."""

    def __init__(self, db: TursoDB, table: str):
        self._db = db
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

    def update(self, values: dict):
        self._mode = "update"
        self._payload = [values]
        return self

    def delete(self):
        self._mode = "delete"
        return self

    # -- filters
    def _q(self, col: str) -> str:
        if "->" in col:
            segs = col.replace("->>", "->").split("->")
            root, path = segs[0], "$." + ".".join(segs[1:])
            return f"json_extract(\"{root}\", '{path}')"
        return f'"{col}"'

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
                f'"{c.strip()}"' if "->" not in c else self._q(c.strip())
                for c in self._cols.split(","))
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
            col_sql = ", ".join(f'"{c}"' for c in cols)
            one = "(" + ", ".join("?" for _ in cols) + ")"
            conflict = ""
            if self._mode == "upsert":
                target = ""
                tcols: list[str] = []
                if self._on_conflict:
                    tcols = [c.strip() for c in self._on_conflict.split(",")]
                    target = "(" + ", ".join(f'"{c}"' for c in tcols) + ")"
                setters = ", ".join(f'"{c}" = excluded."{c}"' for c in cols if c not in tcols)
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
            sets = ", ".join(f'"{c}" = ?' for c in values)
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
        cur = db.execute(
            'UPDATE "agent_events" SET status = ?, processed_by = ?, visibility_until = ? '
            "WHERE id = ? AND status = 'pending'",
            ["processing", agent, until, c["id"]], allow_unscoped=True, reason=reason)
        if getattr(cur, "rowcount", 0) > 0:
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
    cur = db.execute(
        'UPDATE "agent_events" SET status = ?, processed_at = ?, processed_by = ? '
        "WHERE id = ? AND status IN ('processing', 'pending')",
        ["done", _now(), p.get("p_agent"), p.get("p_event_id")],
        allow_unscoped=True, reason="python-compat rpc: ack_event")
    db.commit()
    return getattr(cur, "rowcount", 0) > 0


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


RPC_REGISTRY = {
    "record_inbound_from_n8n": _rpc_record_inbound_from_n8n,
    "reserve_send_slot": _rpc_reserve_send_slot,
    "claim_events": _rpc_claim_events,
    "ack_event": _rpc_ack_event,
    "fail_event": _rpc_fail_event,
    "mark_event_consumed": _rpc_mark_event_consumed,
    "reap_stuck_events": _rpc_reap_stuck_events,
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
        self.storage = _Refuser("storage")

    def table(self, name: str) -> CompatQuery:
        return CompatQuery(self._db, name)

    # supabase-py alias
    def from_(self, name: str) -> CompatQuery:
        return CompatQuery(self._db, name)

    def rpc(self, name: str, params: dict | None = None) -> _RpcQuery:
        return _RpcQuery(self._db, name, params)


def create_client(url: str = "", key: str = "", *a, **kw) -> TursoSupabaseCompat:
    """Signature-compatible replacement for supabase.create_client."""
    log.info("Turso compat client issued", caller=_caller())
    return TursoSupabaseCompat()
