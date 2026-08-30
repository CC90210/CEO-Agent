#!/usr/bin/env node
/**
 * turso_bridge_smoke.mjs — data-plane and bridge integrity against LIVE Workers.
 *
 * The gate that answers "did the migration keep the database working?", which
 * `fleet_health_check.py` deliberately does not: that tool asks whether a
 * hostname reaches the app. This one asks whether the app can still reach its
 * data. A migrated Worker that boots, serves HTML and answers 200 while its
 * libsql client silently fails is exactly the shape both tools exist to catch,
 * and only this one can see it.
 *
 * EVIDENCE TIERS — every probe declares how strong its proof is, because
 * treating them as equal is how a smoke test starts lying:
 *
 *   data   A JSON body whose shape only a completed query produces
 *          (`{"threads":[]}`). A broken client 500s instead. STRONGEST.
 *   boot   An auth rejection (401/403) from a route that imports the DB client.
 *          Proves the module graph — including the driver — initialised, which
 *          is the thing bundling breaks. It does NOT prove a query ran.
 *   parity Compare the Worker against a reference host. Used where a route is
 *          ALREADY failing on both stacks: ig-setter-pro's /api/analytics 500s
 *          on Vercel too, so asserting 200 would fail forever on a pre-existing
 *          condition and train everyone to ignore this script. What matters is
 *          that the two agree.
 *
 * Unauthenticated by design: no secret is read, so it is safe to run anywhere
 * and from CI.
 *
 *   node scripts/turso_bridge_smoke.mjs
 *   node scripts/turso_bridge_smoke.mjs --app propflow
 *   node scripts/turso_bridge_smoke.mjs --json
 *
 * Exit 0 = every probe passed or was legitimately skipped. Exit 1 = a real
 * failure. Undeployed Workers SKIP — "not migrated yet" is not a defect.
 */

const SUBDOMAIN = "oasisaisolutions";
const TIMEOUT_MS = 25_000;

/** @type {Record<string, {worker:string, engine:string, host?:string, reference?:string, probes:Array<any>}>} */
const TARGETS = {
  "ig-setter-pro": {
    worker: "ig-setter-pro",
    engine: "Turso (@libsql/client/web)",
    probes: [
      { path: "/api/threads", tier: "data", expect: (b) => Array.isArray(b?.threads),
        why: "a completed libsql read returns the array; a dead client 500s" },
      { path: "/api/stats", tier: "data", expect: (b) => b !== null && "stats" in b,
        why: "the stats key is only present once the query resolves" },
      { path: "/api/analytics", tier: "parity",
        why: "500s on Vercel too — agreement is the signal, not the status" },
    ],
  },
  propflow: {
    worker: "propflow",
    engine: "Turso (@libsql/client/web)",
    host: "propflow.pro",
    probes: [
      { path: "/api/auth/turso-me", tier: "data", expect: (b) => b !== null && "user" in b,
        why: "the Turso-backed session route answers with a user key" },
      { path: "/api/admin/stats", tier: "boot", expectStatus: [401, 403],
        why: "an auth rejection proves the route and its DB import initialised" },
    ],
  },
  tiktik: {
    worker: "tiktik",
    engine: "Supabase (fetch transport)",
    probes: [
      { path: "/api/cameras", tier: "boot", expectStatus: [401, 403],
        why: "auth-gated: rejection proves boot; a client failure would 500" },
      { path: "/api/center", tier: "boot", expectStatus: [401, 403] },
    ],
  },
  "oasis-command-center": {
    worker: "oasis-command-center",
    engine: "Turso (@libsql/client/web)",
    probes: [
      { path: "/api/forms/submit", tier: "boot", expectStatus: [400, 401, 405],
        why: "an invalid payload must reach the validator, not a parking page" },
      { path: "/login", tier: "boot", expectStatus: [200] },
      // Added 2026-08-30 after finding this BY HAND while the harness reported
      // the app "ok". lib/cron-auth.ts returns 401 when a bearer is missing but
      // 500 ("cron_not_configured") when CRON_SECRET itself is unset — so 401 is
      // the healthy answer and 500 means every one of the 28 cron routes is
      // dead. Reaching the app through a browser cannot see this; only asking
      // the route can.
      { path: "/api/cron/health-check", tier: "boot", expectStatus: [401],
        why: "500 here = CRON_SECRET unset = all 28 cron routes fail closed" },
      // HONEST LIMIT OF THE ABOVE: 401 proves the secret is CONFIGURED, not that
      // the crons WORK. The Worker's CRON_SECRET was rotated 2026-08-30 and the
      // GitHub driver still holds the old Vercel value, so nothing can currently
      // authenticate to these routes. A green run here is NOT evidence the cron
      // fleet is live — that is proven by a workflow_dispatch returning 2xx
      // after the alignment step in brain/WAVE3_OASIS_CC_RUNBOOK.md.
    ],
  },
};

// The VPS bridge is bearer-gated: 401 is the HEALTHY answer. Anything that is
// not an HTTP reply (tunnel down, DNS gone) is the failure this checks for.
const BRIDGE = { host: "bridge.oasisai.work", path: "/health", healthy: [401, 403, 200] };

const args = process.argv.slice(2);
const only = args.includes("--app") ? args[args.indexOf("--app") + 1] : null;
const asJson = args.includes("--json");

async function hit(url) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { signal: ctl.signal, headers: { "user-agent": "turso-bridge-smoke/1.0" } });
    const text = await res.text();
    let body = null;
    try { body = JSON.parse(text); } catch { /* HTML or empty is fine */ }
    return { status: res.status, body, text: text.slice(0, 200) };
  } catch (err) {
    return { status: 0, body: null, text: `CONNECT-FAIL ${String(err).slice(0, 80)}` };
  } finally {
    clearTimeout(t);
  }
}

async function deployedWorkers() {
  // workers.dev is a WILDCARD: an undeployed worker still resolves and answers
  // 404, so "it responded" cannot distinguish deployed from absent. Probe a
  // path that must 404 on an absent worker and 200/redirect on a live one.
  const live = new Set();
  await Promise.all(Object.entries(TARGETS).map(async ([slug, t]) => {
    const r = await hit(`https://${t.worker}.${SUBDOMAIN}.workers.dev/`);
    if (r.status !== 0 && r.status !== 404) live.add(slug);
  }));
  return live;
}

function judge(probe, r, ref) {
  if (probe.tier === "parity") {
    if (!ref) return { verdict: "SKIP", note: "no reference host configured" };
    return r.status === ref.status
      ? { verdict: "PASS", note: `both ${r.status}` }
      : { verdict: "FAIL", note: `worker ${r.status} vs reference ${ref.status}` };
  }
  if (r.status === 0) return { verdict: "FAIL", note: r.text };
  if (probe.expectStatus && !probe.expectStatus.includes(r.status)) {
    return { verdict: "FAIL", note: `status ${r.status}, expected ${probe.expectStatus.join("/")}` };
  }
  if (probe.tier === "data") {
    if (r.status >= 500) return { verdict: "FAIL", note: `${r.status} — the data plane is the usual cause` };
    if (probe.expect && !probe.expect(r.body)) {
      return { verdict: "FAIL", note: `shape mismatch: ${r.text.slice(0, 70)}` };
    }
  }
  return { verdict: "PASS", note: `${r.status}` };
}

const results = [];
const live = await deployedWorkers();

for (const [slug, t] of Object.entries(TARGETS)) {
  if (only && slug !== only) continue;
  const entry = { app: slug, engine: t.engine, checks: [] };
  if (!live.has(slug)) {
    entry.verdict = "SKIP — not deployed to Workers yet";
    results.push(entry);
    continue;
  }
  const base = `https://${t.host ?? `${t.worker}.${SUBDOMAIN}.workers.dev`}`;
  for (const probe of t.probes) {
    const r = await hit(base + probe.path);
    const ref = probe.tier === "parity" ? await hit(`https://${slug}.vercel.app${probe.path}`) : null;
    const j = judge(probe, r, ref);
    entry.checks.push({ path: probe.path, tier: probe.tier, ...j, why: probe.why });
  }
  entry.verdict = entry.checks.some((c) => c.verdict === "FAIL") ? "FAIL" : "ok";
  results.push(entry);
}

const bridge = await hit(`https://${BRIDGE.host}${BRIDGE.path}`);
const bridgeOk = BRIDGE.healthy.includes(bridge.status);
results.push({
  app: "vps-bridge", engine: "cloudflared tunnel -> VPS",
  verdict: bridgeOk ? "ok" : "FAIL",
  checks: [{ path: BRIDGE.path, tier: "boot", verdict: bridgeOk ? "PASS" : "FAIL",
             note: `${bridge.status}`, why: "bearer-gated: 401 IS the healthy answer" }],
});

if (asJson) {
  console.log(JSON.stringify(results, null, 2));
} else {
  for (const r of results) {
    console.log(`\n=== ${r.app}  ->  ${r.verdict}${r.engine ? `   [${r.engine}]` : ""}`);
    for (const c of r.checks ?? []) {
      console.log(`  ${c.verdict.padEnd(4)} ${c.tier.padEnd(6)} ${c.path.padEnd(30)} ${c.note ?? ""}`);
      if (c.verdict === "FAIL" && c.why) console.log(`       why this matters: ${c.why}`);
    }
  }
  const failed = results.filter((r) => r.verdict === "FAIL");
  const skipped = results.filter((r) => String(r.verdict).startsWith("SKIP"));
  console.log(`\n${results.length - failed.length - skipped.length} ok, ${failed.length} failed, ${skipped.length} skipped`);
}

process.exit(results.some((r) => r.verdict === "FAIL") ? 1 : 0);
