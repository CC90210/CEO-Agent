/**
 * turso-postgrest — a supabase-js-compatible query builder over libSQL/Turso.
 *
 * WHY. The empire has ~4,100 `.from(...)` call sites across five apps, all
 * speaking the supabase-js PostgREST builder dialect. Rewriting every call site
 * against a new API is weeks of mechanical risk; implementing the dialect the
 * apps already speak over the new backend means only the client FACTORY changes.
 * This file is that implementation, sized to the surface the apps actually use
 * (measured, not guessed — see the migration notes in Business-Empire-Agent):
 *
 *   from().select/insert/update/upsert/delete
 *   filters: eq neq gt gte lt lte like ilike is in not or match filter contains
 *   modifiers: order limit range single maybeSingle count(exact|estimated)+head
 *   embeds:  alias:rel!inner(cols), rel(cols) — one level, both directions
 *   upsert:  onConflict
 *
 * NOT provided, on purpose:
 *   auth / storage / channel  — keep the real Supabase client for those (or
 *                               their replacements) — this is the DATA plane.
 *   rpc()                     — throws with the RPC name; each RPC is a
 *                               deliberate port, not a silent shim.
 *
 * SEMANTIC DELTAS vs PostgREST (documented, not hidden):
 *   - booleans arrive as 0/1 (SQLite has no bool). Truthiness works; strict
 *     `=== true` comparisons do not. Grep for those when wiring an app.
 *   - JSON columns are TEXT; values that parse as JSON objects/arrays are
 *     returned parsed (matching PostgREST's nested shapes). A TEXT column whose
 *     content merely LOOKS like JSON would also parse — acceptable here because
 *     the transpiled schema only stores JSON in ex-jsonb columns.
 *   - `count: "estimated"` is executed as exact (SQLite COUNT is cheap at this
 *     scale).
 */

import type { Client, InValue } from "@libsql/client";

// ---------------------------------------------------------------- result types

export interface PgError {
  message: string;
  code: string;
  details: string | null;
  hint: string | null;
}

export interface PgResponse<T> {
  data: T | null;
  error: PgError | null;
  count: number | null;
  status: number;
  statusText: string;
}

const err = (message: string, code = "TURSO_ADAPTER"): PgError => ({
  message, code, details: null, hint: null,
});

// ------------------------------------------------------------------- FK cache

interface FkEdge { fromTable: string; fromCols: string[]; toTable: string; toCols: string[] }

const fkCache = new Map<string, FkEdge[]>();

async function foreignKeysOf(client: Client, table: string): Promise<FkEdge[]> {
  const hit = fkCache.get(table);
  if (hit) return hit;
  const res = await client.execute(`PRAGMA foreign_key_list("${table.replace(/"/g, '""')}")`);
  const byId = new Map<number, FkEdge>();
  for (const row of res.rows as any[]) {
    const id = Number(row.id);
    const e = byId.get(id) ?? { fromTable: table, fromCols: [], toTable: String(row.table), toCols: [] };
    e.fromCols.push(String(row.from));
    e.toCols.push(String(row.to));
    byId.set(id, e);
  }
  const edges = [...byId.values()];
  fkCache.set(table, edges);
  return edges;
}

// --------------------------------------------------------------- select parse

interface Embed { alias: string; table: string; inner: boolean; columns: string }

/** Split a PostgREST column list on top-level commas (parens nest). */
function splitTop(s: string): string[] {
  const out: string[] = [];
  let depth = 0, cur = "";
  for (const ch of s) {
    if (ch === "(") depth++;
    if (ch === ")") depth--;
    if (ch === "," && depth === 0) { out.push(cur.trim()); cur = ""; continue; }
    cur += ch;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

function parseSelect(sel: string): { base: string[]; embeds: Embed[] } {
  const base: string[] = [];
  const embeds: Embed[] = [];
  for (const part of splitTop(sel)) {
    // [\s\S] instead of the dotAll flag: nostalgic-requests targets pre-ES2018
    // and the adapter must compile unchanged in every app it is copied into.
    const m = part.match(/^(?:([\w$]+):)?([\w$]+)(!\w+)?\(([\s\S]*)\)$/);
    if (m) {
      embeds.push({
        alias: m[1] ?? m[2],
        table: m[2],
        inner: m[3] === "!inner",
        columns: m[4].trim() || "*",
      });
    } else {
      base.push(part);
    }
  }
  return { base, embeds };
}

// ----------------------------------------------------------------- value maps

function toSql(v: unknown): InValue {
  if (v === undefined || v === null) return null;
  if (typeof v === "boolean") return v ? 1 : 0;
  if (v instanceof Date) return v.toISOString();
  if (typeof v === "object") return JSON.stringify(v);
  return v as InValue;
}

function fromSql(v: unknown): unknown {
  if (typeof v === "string" && (v.startsWith("{") || v.startsWith("["))) {
    try { return JSON.parse(v); } catch { return v; }
  }
  if (typeof v === "bigint") return Number(v);
  return v;
}

function rowOut(row: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(row)) out[k] = fromSql(v);
  return out;
}

// ------------------------------------------------------------ filter compiler

interface Cond { sql: string; args: InValue[] }

const OPS: Record<string, string> = {
  eq: "=", neq: "<>", gt: ">", gte: ">=", lt: "<", lte: "<=",
  like: "LIKE", ilike: "LIKE",
};

function q(col: string): string {
  // guard against injection via column names — PostgREST identifiers only
  if (!/^[\w$.]+$/.test(col)) throw new Error(`invalid column identifier: ${col}`);
  const bare = col.includes(".") ? col.split(".").pop()! : col;
  return `"${bare}"`;
}

function compileOp(col: string, op: string, value: unknown): Cond {
  if (op === "in") {
    const arr = Array.isArray(value) ? value : String(value).replace(/^\(|\)$/g, "").split(",");
    const ph = arr.map(() => "?").join(", ");
    return { sql: `${q(col)} IN (${ph})`, args: arr.map(toSql) };
  }
  if (op === "is") {
    const v = typeof value === "string" ? value.toLowerCase() : value;
    if (v === null || v === "null") return { sql: `${q(col)} IS NULL`, args: [] };
    if (v === "not.null") return { sql: `${q(col)} IS NOT NULL`, args: [] };
    if (v === true || v === "true") return { sql: `${q(col)} = 1`, args: [] };
    if (v === false || v === "false") return { sql: `${q(col)} = 0`, args: [] };
    throw new Error(`unsupported is. value: ${String(value)}`);
  }
  if (op === "cs" || op === "contains") {
    // array/jsonb containment on a JSON-encoded TEXT column
    const items = Array.isArray(value) ? value : [value];
    const conds = items.map(() =>
      `EXISTS (SELECT 1 FROM json_each(${q(col)}) WHERE json_each.value = ?)`);
    return { sql: `(${conds.join(" AND ")})`, args: items.map(toSql) };
  }
  const sqlOp = OPS[op];
  if (!sqlOp) throw new Error(`unsupported operator: ${op}`);
  let v = value;
  if (op === "like" || op === "ilike") v = String(value).replace(/\*/g, "%");
  const colExpr = op === "ilike" ? `lower(${q(col)})` : q(col);
  const valExpr = op === "ilike" ? String(v).toLowerCase() : v;
  return { sql: `${colExpr} ${sqlOp} ?`, args: [toSql(valExpr)] };
}

/** PostgREST .or() grammar: "a.eq.1,b.like.*x*,and(c.gt.2,d.lt.5)" */
function compileOrGroup(expr: string, joiner: "OR" | "AND" = "OR"): Cond {
  const parts = splitTop(expr);
  const conds: Cond[] = parts.map((p) => {
    const grp = p.match(/^(and|or)\(([\s\S]*)\)$/);
    if (grp) return compileOrGroup(grp[2], grp[1].toUpperCase() as "OR" | "AND");
    const m = p.match(/^([\w$.]+)\.(not\.)?([a-z]+)\.([\s\S]*)$/);
    if (!m) throw new Error(`cannot parse or() segment: ${p}`);
    const c = compileOp(m[1], m[3], m[4]);
    return m[2] ? { sql: `NOT (${c.sql})`, args: c.args } : c;
  });
  return {
    sql: `(${conds.map((c) => c.sql).join(` ${joiner} `)})`,
    args: conds.flatMap((c) => c.args),
  };
}

// ------------------------------------------------------------------ builder

type Row = Record<string, unknown>;

export class TursoQueryBuilder implements PromiseLike<PgResponse<any>> {
  private mode: "select" | "insert" | "update" | "upsert" | "delete" = "select";
  private selectStr = "*";
  private conds: Cond[] = [];
  private orderBys: { col: string; asc: boolean }[] = [];
  private limitN: number | null = null;
  private offsetN: number | null = null;
  private singleMode: "single" | "maybe" | null = null;
  private countMode: "exact" | "estimated" | "planned" | null = null;
  private headMode = false;
  private payload: Row[] | null = null;
  private onConflictCols: string | null = null;
  private returning = false;

  constructor(private client: Client, private table: string) {
    if (!/^[\w$]+$/.test(table)) throw new Error(`invalid table name: ${table}`);
  }

  // ---- verbs
  select(cols = "*", opts?: { count?: "exact" | "estimated" | "planned"; head?: boolean }) {
    if (this.mode === "select") this.selectStr = cols;
    else this.returning = true; // insert/update/upsert/delete ... .select()
    if (opts?.count) this.countMode = opts.count;
    if (opts?.head) this.headMode = true;
    return this;
  }
  insert(values: Row | Row[]) { this.mode = "insert"; this.payload = Array.isArray(values) ? values : [values]; return this; }
  upsert(values: Row | Row[], opts?: { onConflict?: string; ignoreDuplicates?: boolean }) {
    this.mode = "upsert";
    this.payload = Array.isArray(values) ? values : [values];
    this.onConflictCols = opts?.onConflict ?? null;
    if (opts?.ignoreDuplicates) this.onConflictCols = `IGNORE:${this.onConflictCols ?? ""}`;
    return this;
  }
  update(values: Row) { this.mode = "update"; this.payload = [values]; return this; }
  delete() { this.mode = "delete"; return this; }

  // ---- filters
  eq(c: string, v: unknown) { this.conds.push(compileOp(c, "eq", v)); return this; }
  neq(c: string, v: unknown) { this.conds.push(compileOp(c, "neq", v)); return this; }
  gt(c: string, v: unknown) { this.conds.push(compileOp(c, "gt", v)); return this; }
  gte(c: string, v: unknown) { this.conds.push(compileOp(c, "gte", v)); return this; }
  lt(c: string, v: unknown) { this.conds.push(compileOp(c, "lt", v)); return this; }
  lte(c: string, v: unknown) { this.conds.push(compileOp(c, "lte", v)); return this; }
  like(c: string, v: string) { this.conds.push(compileOp(c, "like", v)); return this; }
  ilike(c: string, v: string) { this.conds.push(compileOp(c, "ilike", v)); return this; }
  is(c: string, v: unknown) { this.conds.push(compileOp(c, "is", v)); return this; }
  in(c: string, v: unknown[]) { this.conds.push(compileOp(c, "in", v)); return this; }
  contains(c: string, v: unknown) { this.conds.push(compileOp(c, "cs", v)); return this; }
  not(c: string, op: string, v: unknown) {
    const inner = compileOp(c, op, v);
    this.conds.push({ sql: `NOT (${inner.sql})`, args: inner.args });
    return this;
  }
  or(expr: string) { this.conds.push(compileOrGroup(expr)); return this; }
  filter(c: string, op: string, v: unknown) {
    const m = op.match(/^not\.(.+)$/);
    return m ? this.not(c, m[1], v) : (this.conds.push(compileOp(c, op, v)), this);
  }
  match(obj: Row) { for (const [c, v] of Object.entries(obj)) this.eq(c, v); return this; }

  // ---- modifiers
  order(c: string, opts?: { ascending?: boolean }) {
    this.orderBys.push({ col: c, asc: opts?.ascending !== false });
    return this;
  }
  limit(n: number) { this.limitN = n; return this; }
  range(from: number, to: number) { this.offsetN = from; this.limitN = to - from + 1; return this; }
  single() { this.singleMode = "single"; this.limitN = this.limitN ?? 2; return this; }
  maybeSingle() { this.singleMode = "maybe"; this.limitN = this.limitN ?? 2; return this; }
  throwOnError() { return this; } // errors already reject nothing; kept for API compat

  // ---- execution
  then<R1 = PgResponse<any>, R2 = never>(
    onfulfilled?: ((value: PgResponse<any>) => R1 | PromiseLike<R1>) | null,
    onrejected?: ((reason: unknown) => R2 | PromiseLike<R2>) | null,
  ): PromiseLike<R1 | R2> {
    return this.run().then(onfulfilled, onrejected);
  }

  private whereSql(): Cond {
    if (!this.conds.length) return { sql: "", args: [] };
    return {
      sql: " WHERE " + this.conds.map((c) => c.sql).join(" AND "),
      args: this.conds.flatMap((c) => c.args),
    };
  }

  private async run(): Promise<PgResponse<any>> {
    try {
      switch (this.mode) {
        case "select": return await this.runSelect();
        case "insert":
        case "upsert": return await this.runWrite();
        case "update": return await this.runUpdate();
        case "delete": return await this.runDelete();
      }
    } catch (e: any) {
      return { data: null, error: err(e?.message ?? String(e)), count: null, status: 400, statusText: "Bad Request" };
    }
  }

  private finalizeRows(rows: Row[], count: number | null): PgResponse<any> {
    if (this.singleMode) {
      if (rows.length > 1)
        return { data: null, error: err("JSON object requested, multiple (or no) rows returned", "PGRST116"), count, status: 406, statusText: "Not Acceptable" };
      if (rows.length === 0) {
        if (this.singleMode === "maybe")
          return { data: null, error: null, count, status: 200, statusText: "OK" };
        return { data: null, error: err("JSON object requested, multiple (or no) rows returned", "PGRST116"), count, status: 406, statusText: "Not Acceptable" };
      }
      return { data: rows[0], error: null, count, status: 200, statusText: "OK" };
    }
    return { data: rows, error: null, count, status: 200, statusText: "OK" };
  }

  private async runSelect(): Promise<PgResponse<any>> {
    const { base, embeds } = parseSelect(this.selectStr);
    const where = this.whereSql();

    let count: number | null = null;
    if (this.countMode) {
      const res = await this.client.execute({
        sql: `SELECT count(*) AS n FROM "${this.table}"${where.sql}`, args: where.args });
      count = Number((res.rows[0] as any).n);
      if (this.headMode)
        return { data: null, error: null, count, status: 200, statusText: "OK" };
    }

    const colSql = !base.length || base.includes("*")
      ? "*"
      : [...new Set([...base, ...(embeds.length ? await this.embedKeyCols(embeds) : [])])]
          .map(q).join(", ");
    let sql = `SELECT ${colSql} FROM "${this.table}"${where.sql}`;
    if (this.orderBys.length)
      sql += " ORDER BY " + this.orderBys.map((o) => `${q(o.col)} ${o.asc ? "ASC" : "DESC"}`).join(", ");
    if (this.limitN != null) sql += ` LIMIT ${Number(this.limitN)}`;
    if (this.offsetN != null) sql += ` OFFSET ${Number(this.offsetN)}`;

    const res = await this.client.execute({ sql, args: where.args });
    let rows = (res.rows as any[]).map(rowOut);
    if (embeds.length && rows.length) rows = await this.attachEmbeds(rows, embeds);
    else if (embeds.length) rows = [];
    return this.finalizeRows(rows, count);
  }

  /** Base-table FK columns needed to resolve belongs-to embeds. */
  private async embedKeyCols(embeds: Embed[]): Promise<string[]> {
    const fks = await foreignKeysOf(this.client, this.table);
    const cols: string[] = [];
    for (const e of embeds) {
      const edge = fks.find((f) => f.toTable === e.table);
      if (edge) cols.push(...edge.fromCols);
    }
    return cols;
  }

  private async attachEmbeds(rows: Row[], embeds: Embed[]): Promise<Row[]> {
    const baseFks = await foreignKeysOf(this.client, this.table);
    for (const e of embeds) {
      const belongsTo = baseFks.find((f) => f.toTable === e.table);
      if (belongsTo) {
        // Composite-FK embeds are refused, not approximated: joining on
        // fromCols[0] alone (typically tenant_id) would match parents across
        // tenants — silently wrong rows, the worst failure mode this migration
        // has. Six such FKs exist in bravo (marketing_* tables); any query
        // embedding across them must be written as an explicit join instead.
        if (belongsTo.fromCols.length > 1) throw new Error(
          `embedded select across composite FK ${this.table}(${belongsTo.fromCols.join(",")}) -> ` +
          `${e.table} is not supported — write an explicit two-step query`);
        const keyCol = belongsTo.fromCols[0];
        const refCol = belongsTo.toCols[0];
        const keys = [...new Set(rows.map((r) => r[keyCol]).filter((v) => v != null))];
        const map = new Map<unknown, Row>();
        if (keys.length) {
          const ph = keys.map(() => "?").join(", ");
          const sub = await this.client.execute({
            sql: `SELECT ${e.columns === "*" ? "*" : splitTop(e.columns).map(q).join(", ") + `, ${q(refCol)}`} FROM "${e.table}" WHERE ${q(refCol)} IN (${ph})`,
            args: keys.map(toSql),
          });
          for (const r of (sub.rows as any[]).map(rowOut)) map.set(r[refCol], r);
        }
        rows = rows.flatMap((r) => {
          const hit = r[keyCol] != null ? map.get(r[keyCol]) ?? null : null;
          if (e.inner && !hit) return []; // !inner drops non-matching rows
          return [{ ...r, [e.alias]: hit }];
        });
        continue;
      }
      const childFks = await foreignKeysOf(this.client, e.table);
      const hasMany = childFks.find((f) => f.toTable === this.table);
      if (!hasMany) throw new Error(
        `no FK path between ${this.table} and ${e.table} — embedded select unsupported here`);
      if (hasMany.fromCols.length > 1) throw new Error(
        `embedded select across composite FK ${e.table}(${hasMany.fromCols.join(",")}) -> ` +
        `${this.table} is not supported — write an explicit two-step query`);
      const refCol = hasMany.toCols[0];
      const childCol = hasMany.fromCols[0];
      const keys = [...new Set(rows.map((r) => r[refCol]).filter((v) => v != null))];
      const groups = new Map<unknown, Row[]>();
      if (keys.length) {
        const ph = keys.map(() => "?").join(", ");
        const sub = await this.client.execute({
          sql: `SELECT ${e.columns === "*" ? "*" : splitTop(e.columns).map(q).join(", ") + `, ${q(childCol)}`} FROM "${e.table}" WHERE ${q(childCol)} IN (${ph})`,
          args: keys.map(toSql),
        });
        for (const r of (sub.rows as any[]).map(rowOut)) {
          const g = groups.get(r[childCol]) ?? [];
          g.push(r);
          groups.set(r[childCol], g);
        }
      }
      rows = rows.flatMap((r) => {
        const kids = groups.get(r[refCol]) ?? [];
        if (e.inner && !kids.length) return [];
        return [{ ...r, [e.alias]: kids }];
      });
    }
    return rows;
  }

  private async runWrite(): Promise<PgResponse<any>> {
    const rows = this.payload!;
    if (!rows.length)
      return { data: [], error: null, count: null, status: 201, statusText: "Created" };
    const cols = [...new Set(rows.flatMap((r) => Object.keys(r)))];
    const colSql = cols.map(q).join(", ");
    const oneRow = `(${cols.map(() => "?").join(", ")})`;
    let conflict = "";
    if (this.mode === "upsert") {
      const ignore = this.onConflictCols?.startsWith("IGNORE:");
      const target = (ignore ? this.onConflictCols!.slice(7) : this.onConflictCols) || "";
      const targetCols = target ? target.split(",").map((c) => c.trim()) : [];
      const targetSql = targetCols.length ? `(${targetCols.map(q).join(", ")})` : "";
      // The conflict-target columns are excluded from SET: they are equal by
      // definition, and updating them is at best a no-op write.
      const setCols = cols.filter((c) => !targetCols.includes(c));
      conflict = ignore || !setCols.length
        ? ` ON CONFLICT ${targetSql} DO NOTHING`
        : ` ON CONFLICT ${targetSql} DO UPDATE SET ` +
          setCols.map((c) => `${q(c)} = excluded.${q(c)}`).join(", ");
    }
    const sql = `INSERT INTO "${this.table}" (${colSql}) VALUES ${rows.map(() => oneRow).join(", ")}${conflict}` +
      (this.returning ? " RETURNING *" : "");
    const args = rows.flatMap((r) => cols.map((c) => toSql(r[c])));
    const res = await this.client.execute({ sql, args });
    const data = this.returning ? (res.rows as any[]).map(rowOut) : null;
    return this.finalizeRows(data ?? [], null);
  }

  private async runUpdate(): Promise<PgResponse<any>> {
    const values = this.payload![0];
    const cols = Object.keys(values);
    const where = this.whereSql();
    if (!where.sql) throw new Error("update without filters refused — it would touch every row");
    const sql = `UPDATE "${this.table}" SET ${cols.map((c) => `${q(c)} = ?`).join(", ")}${where.sql}` +
      (this.returning ? " RETURNING *" : "");
    const res = await this.client.execute({
      sql, args: [...cols.map((c) => toSql(values[c])), ...where.args] });
    return this.finalizeRows(this.returning ? (res.rows as any[]).map(rowOut) : [], null);
  }

  private async runDelete(): Promise<PgResponse<any>> {
    const where = this.whereSql();
    if (!where.sql) throw new Error("delete without filters refused — it would empty the table");
    const sql = `DELETE FROM "${this.table}"${where.sql}` + (this.returning ? " RETURNING *" : "");
    const res = await this.client.execute({ sql, args: where.args });
    return this.finalizeRows(this.returning ? (res.rows as any[]).map(rowOut) : [], null);
  }
}

// ------------------------------------------------------------------- factory

export interface TursoPostgrest {
  from(table: string): TursoQueryBuilder;
  rpc(name: string, args?: Record<string, unknown>): never;
}

export function createTursoPostgrest(client: Client): TursoPostgrest {
  return {
    from: (table: string) => new TursoQueryBuilder(client, table),
    rpc: (name: string) => {
      throw new Error(
        `rpc("${name}") has no Turso equivalent — PL/pgSQL did not migrate. ` +
        `Port this RPC as an explicit query or server function (see the RPC ` +
        `inventory in the migration notes).`);
    },
  };
}
