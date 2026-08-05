/**
 * Adapter conformance tests — every case mirrors a query shape that actually
 * exists in this repo (measured via grep, cited inline). Runs against a real
 * in-memory libSQL database, no mocks: the point is SQL semantics, and mocking
 * the database would test nothing.
 *
 * Run: node lib/__tests__/turso-postgrest.test.mjs
 */
import { createClient } from "@libsql/client";
import assert from "node:assert/strict";

// tsx-free loading: compile the single TS file on the fly via a tiny strip.
// The adapter deliberately uses erasable-only TS syntax, so stripping types is
// enough — no build step, no extra deps.
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import ts from "typescript";

const here = join(fileURLToPath(import.meta.url), "..");
const src = readFileSync(join(here, "..", "turso-postgrest.ts"), "utf8");
const js = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const tmp = mkdtempSync(join(tmpdir(), "tpg-"));
writeFileSync(join(tmp, "adapter.mjs"), js);
const { createTursoPostgrest } = await import(pathToFileURL(join(tmp, "adapter.mjs")).href);

const client = createClient({ url: ":memory:" });
const db = createTursoPostgrest(client);

// Schema mirrors the transpiler's output shapes: TEXT ids, tenant_id, JSON TEXT.
await client.executeMultiple(`
  CREATE TABLE tenants (id TEXT PRIMARY KEY, slug TEXT UNIQUE, enabled INTEGER DEFAULT 1);
  CREATE TABLE leads (
    id TEXT PRIMARY KEY, tenant_id TEXT REFERENCES tenants(id),
    email TEXT, status TEXT, score INTEGER, tags TEXT, meta TEXT,
    agent_source TEXT, created_at TEXT
  );
  CREATE TABLE esign_envelopes (id TEXT PRIMARY KEY, tenant_id TEXT, title TEXT);
  CREATE TABLE esign_signers (
    id TEXT PRIMARY KEY,
    envelope_id TEXT REFERENCES esign_envelopes(id),
    email TEXT, signed INTEGER DEFAULT 0
  );
  INSERT INTO tenants VALUES ('t1','oasis',1),('t2','sunbiz',1),('t3','disabled',0);
  INSERT INTO leads VALUES
    ('l1','t1','a@x.com','warm',80,'["vip","inbound"]','{"src":"form"}','sequence:s1','2026-08-01T00:00:00Z'),
    ('l2','t1','b@x.com','cold',20,'["outbound"]','{}','cold:c1','2026-08-02T00:00:00Z'),
    ('l3','t2','c@y.com','warm',60,'[]','{}','manual','2026-08-03T00:00:00Z'),
    ('l4',NULL,'orphan@z.com','dead',0,'[]','{}',NULL,'2026-08-04T00:00:00Z');
  INSERT INTO esign_envelopes VALUES ('e1','t1','MSA');
  INSERT INTO esign_signers VALUES ('s1','e1','a@x.com',1),('s2','e1','b@x.com',0);
`);

let passed = 0;
const test = async (name, fn) => {
  try { await fn(); passed++; console.log(`  ok  ${name}`); }
  catch (e) { console.error(`FAIL  ${name}\n      ${e.message}`); process.exitCode = 1; }
};

// --- basic select + filters (the bread and butter: 3,001 .eq calls repo-wide)
await test("select + eq", async () => {
  const { data, error } = await db.from("leads").select("*").eq("tenant_id", "t1");
  assert.equal(error, null);
  assert.equal(data.length, 2);
});

await test("order + limit + range", async () => {
  const { data } = await db.from("leads").select("id").order("created_at", { ascending: false }).limit(2);
  assert.deepEqual(data.map((r) => r.id), ["l4", "l3"]);
  const { data: page2 } = await db.from("leads").select("id").order("created_at").range(2, 3);
  assert.equal(page2.length, 2);
});

await test("single / maybeSingle semantics incl. PGRST116", async () => {
  const one = await db.from("leads").select("*").eq("id", "l1").single();
  assert.equal(one.data.email, "a@x.com");
  const none = await db.from("leads").select("*").eq("id", "nope").maybeSingle();
  assert.equal(none.data, null); assert.equal(none.error, null);
  const bad = await db.from("leads").select("*").eq("id", "nope").single();
  assert.equal(bad.error.code, "PGRST116");
  const many = await db.from("leads").select("*").eq("status", "warm").single();
  assert.equal(many.error.code, "PGRST116");
});

// --- count: exact + head (27 call sites use exactly this)
await test('count "exact" + head:true returns count with null data', async () => {
  const { count, data, error } = await db.from("leads")
    .select("id", { count: "exact", head: true }).eq("tenant_id", "t1");
  assert.equal(error, null); assert.equal(count, 2); assert.equal(data, null);
});

// --- .or() PostgREST grammar with * wildcards (real string from lead queries)
await test(".or() with like.* segments", async () => {
  const { data } = await db.from("leads").select("id")
    .or("agent_source.like.sequence:*,agent_source.like.cold:*");
  assert.deepEqual(data.map((r) => r.id).sort(), ["l1", "l2"]);
});

// --- in / is / not / neq / gte
await test("in + is null + not", async () => {
  const { data: inRes } = await db.from("leads").select("id").in("status", ["warm", "cold"]);
  assert.equal(inRes.length, 3);
  const { data: orphans } = await db.from("leads").select("id").is("tenant_id", null);
  assert.deepEqual(orphans.map((r) => r.id), ["l4"]);
  const { data: notWarm } = await db.from("leads").select("id").not("status", "eq", "warm").in("id", ["l1", "l2"]);
  assert.deepEqual(notWarm.map((r) => r.id), ["l2"]);
});

// --- ilike case-insensitivity
await test("ilike is case-insensitive", async () => {
  const { data } = await db.from("leads").select("id").ilike("email", "A@X.COM");
  assert.deepEqual(data.map((r) => r.id), ["l1"]);
});

// --- JSON TEXT columns come back parsed (PostgREST returns nested objects)
await test("json columns are parsed on the way out", async () => {
  const { data } = await db.from("leads").select("*").eq("id", "l1").single();
  assert.deepEqual(data.tags, ["vip", "inbound"]);
  assert.deepEqual(data.meta, { src: "form" });
});

// --- contains on a JSON-encoded array column
await test("contains on JSON array column", async () => {
  const { data } = await db.from("leads").select("id").contains("tags", ["vip"]);
  assert.deepEqual(data.map((r) => r.id), ["l1"]);
});

// --- embeds: belongs-to with alias + !inner (the tenant:tenants!inner(slug) shape)
await test("belongs-to embed with alias and !inner drops unmatched rows", async () => {
  const { data } = await db.from("leads").select("id, tenant:tenants!inner(slug)");
  assert.equal(data.length, 3, "l4 (NULL tenant) must be dropped by !inner");
  assert.equal(data.find((r) => r.id === "l1").tenant.slug, "oasis");
});

await test("belongs-to embed without !inner keeps rows with null", async () => {
  const { data } = await db.from("leads").select("id, tenant:tenants(slug)");
  assert.equal(data.length, 4);
  assert.equal(data.find((r) => r.id === "l4").tenant, null);
});

// --- embeds: has-many (the esign_signers(...) shape)
await test("has-many embed returns arrays", async () => {
  const { data } = await db.from("esign_envelopes").select("id, title, esign_signers(id, email)");
  assert.equal(data[0].esign_signers.length, 2);
});

// --- insert / update / upsert / delete with .select() returning
await test("insert returning", async () => {
  const { data, error } = await db.from("leads")
    .insert({ id: "l5", tenant_id: "t2", email: "new@y.com", status: "cold", score: 5 })
    .select();
  assert.equal(error, null);
  assert.equal(data[0].email, "new@y.com");
});

await test("update requires a filter and applies it", async () => {
  const { error } = await db.from("leads").update({ status: "hot" }).eq("id", "l5").select();
  assert.equal(error, null);
  const check = await db.from("leads").select("status").eq("id", "l5").single();
  assert.equal(check.data.status, "hot");
  const unfiltered = await db.from("leads").update({ status: "x" });
  assert.match(unfiltered.error.message, /refused/);
});

await test("upsert with onConflict updates in place (34 call sites use this)", async () => {
  // Real app usage sends the natural key + changed fields, never a fresh PK —
  // the transpiled schemas mint ids via DEFAULT. Mirror that shape.
  const { error } = await db.from("tenants")
    .upsert({ id: "t1", slug: "oasis", enabled: 0 }, { onConflict: "slug" });
  assert.equal(error, null);
  const t = await db.from("tenants").select("*").eq("slug", "oasis").single();
  assert.equal(t.data.enabled, 0);
  assert.equal(t.data.id, "t1", "conflict on slug must UPDATE the existing row");
  // and a NEW slug inserts rather than updates
  const ins = await db.from("tenants")
    .upsert({ id: "t9", slug: "brand-new", enabled: 1 }, { onConflict: "slug" });
  assert.equal(ins.error, null);
  const nine = await db.from("tenants").select("id").eq("slug", "brand-new").single();
  assert.equal(nine.data.id, "t9");
});

await test("delete requires a filter and applies it", async () => {
  const { error } = await db.from("leads").delete().eq("id", "l5");
  assert.equal(error, null);
  const gone = await db.from("leads").select("*").eq("id", "l5").maybeSingle();
  assert.equal(gone.data, null);
  const unfiltered = await db.from("leads").delete();
  assert.match(unfiltered.error.message, /refused/);
});

// --- booleans stored as 0/1 pass through comparisons via eq(true)
await test("eq(col, true) matches INTEGER 1", async () => {
  const { data } = await db.from("tenants").select("slug").eq("enabled", true);
  assert.equal(data.length, 2);
});

// --- composite-FK embeds must refuse, never mis-join on the first column
await test("composite-FK embed is refused loudly", async () => {
  await client.executeMultiple(`
    CREATE TABLE assets (tenant_id TEXT, id TEXT, name TEXT,
      PRIMARY KEY (tenant_id, id));
    CREATE TABLE metrics (tenant_id TEXT, asset_id TEXT, v INTEGER,
      FOREIGN KEY (tenant_id, asset_id) REFERENCES assets (tenant_id, id));
    INSERT INTO assets VALUES ('t1','a1','ad'),('t2','a1','other-tenant-ad');
    INSERT INTO metrics VALUES ('t1','a1',5);
  `);
  const res = await db.from("metrics").select("v, assets(name)").eq("tenant_id", "t1");
  assert.ok(res.error, "must error rather than join on tenant_id alone");
  assert.match(res.error.message, /composite FK/);
});

// --- rpc must fail loudly with the name
await test("rpc throws naming the function", async () => {
  assert.throws(() => db.rpc("reserve_send_slot"), /reserve_send_slot/);
});

// --- JSON-path filters (production soft-delete guards use these)
await test("JSON-path ->> filter compiles to json_extract", async () => {
  const { data, error } = await db.from("leads").select("id")
    .is("meta->>src", null);
  assert.equal(error, null);
  const { data: hit } = await db.from("leads").select("id").eq("meta->>src", "form");
  assert.deepEqual(hit.map((r) => r.id), ["l1"]);
});

// --- typed literals in the or() grammar (silent-wrong before: 'true' as string)
await test("or() boolean/null/number literals are typed, not strings", async () => {
  const { data } = await db.from("tenants").select("slug").or("enabled.eq.true");
  assert.ok(data.length >= 1, "boolean literal must match INTEGER 1 rows");
  const { data: nulls } = await db.from("leads").select("id").or("tenant_id.is.null");
  assert.deepEqual(nulls.map((r) => r.id), ["l4"]);
  const { data: nums } = await db.from("leads").select("id").or("score.gte.80");
  assert.deepEqual(nums.map((r) => r.id), ["l1"]);
});

// --- ambiguous embeds must refuse (two FKs to the same parent)
await test("two FKs to the same parent table refuse the embed", async () => {
  await client.executeMultiple(`
    CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT);
    CREATE TABLE tickets (
      id TEXT PRIMARY KEY,
      creator_id TEXT REFERENCES users(id),
      assignee_id TEXT REFERENCES users(id)
    );
    INSERT INTO users VALUES ('u1','ann'),('u2','bob');
    INSERT INTO tickets VALUES ('k1','u1','u2');
  `);
  const res = await db.from("tickets").select("id, users(name)");
  assert.ok(res.error, "must refuse rather than pick a PRAGMA-ordered edge");
  assert.match(res.error.message, /ambiguous embed/);
});

// --- injection guards
await test("hostile identifiers are rejected", async () => {
  const res = await db.from("leads").select('id"; DROP TABLE leads; --');
  assert.ok(res.error, "hostile select list must error, not execute");
  const still = await db.from("leads").select("id").limit(1);
  assert.equal(still.error, null, "table must still exist");
});

console.log(`\n${passed} passed${process.exitCode ? " — WITH FAILURES" : ", 0 failed"}`);
