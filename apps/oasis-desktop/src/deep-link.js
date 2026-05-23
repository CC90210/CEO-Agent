"use strict";

/**
 * deep-link.js — oasis:// protocol handler.
 *
 * The desktop registers `oasis://` as a default protocol client. When the
 * user signs in on the dashboard in their normal browser, the dashboard
 * fires a link of the form:
 *
 *   oasis://pair?code=ABC-DEF-GHJ
 *
 * The OS routes that link to OASIS AI:
 *   - macOS:  via `open-url` event on the app object
 *   - Windows/Linux: via argv on a second-instance event
 *
 * This module parses inbound deep-links and dispatches them to the right
 * handler. The pair-code path reuses bridge_pair_codes/redeem so the
 * security model (15-min TTL, single-use, machine_fingerprint dedupe)
 * is identical to manual paste-the-code.
 */

const http = require("node:http");
const https = require("node:https");
const fs = require("node:fs");
const os = require("node:os");
const { URL } = require("node:url");
const {
  BRIDGE_TOKEN_FILE,
  BRIDGE_META_FILE,
  ensureOasisHome,
} = require("./bridge-paths");

const PROTOCOL = "oasis";
const PAIR_CODE_REGEX = /^[A-Z0-9]{3}-[A-Z0-9]{3}-[A-Z0-9]{3}$/;

function parseDeepLink(rawUrl) {
  if (typeof rawUrl !== "string") return null;
  let parsed;
  try {
    parsed = new URL(rawUrl);
  } catch {
    return null;
  }
  if (parsed.protocol !== `${PROTOCOL}:`) return null;
  const host = (parsed.host || parsed.hostname || "").toLowerCase();
  const path = parsed.pathname || "";
  const action = host || path.replace(/^\//, "").split("/")[0] || "";
  const params = Object.fromEntries(parsed.searchParams.entries());
  return { action, params };
}

function machineFingerprint() {
  const sys = process.platform === "win32" ? "Windows" : process.platform === "darwin" ? "Darwin" : "Linux";
  let machine;
  if (sys === "Windows") {
    machine = process.arch === "x64" ? "AMD64" : process.arch === "arm64" ? "ARM64" : process.arch;
  } else if (sys === "Darwin") {
    machine = process.arch === "x64" ? "x86_64" : "arm64";
  } else {
    machine = process.arch === "x64" ? "x86_64" : process.arch;
  }
  return `${sys}|${machine}|${os.hostname()}`;
}

function defaultMachineLabel() {
  const user = (os.userInfo().username || "").trim();
  const host = (os.hostname() || "machine").split(".")[0];
  return user ? `${user}'s ${host}` : host;
}

function postJson(urlString, body, timeoutMs = 12_000) {
  return new Promise((resolve) => {
    let urlObj;
    try {
      urlObj = new URL(urlString);
    } catch {
      resolve({ status: 0, error: "bad_url", body: null });
      return;
    }
    const payload = JSON.stringify(body);
    const opts = {
      method: "POST",
      hostname: urlObj.hostname,
      port: urlObj.port || (urlObj.protocol === "https:" ? 443 : 80),
      path: urlObj.pathname + (urlObj.search || ""),
      headers: {
        "content-type": "application/json",
        "content-length": Buffer.byteLength(payload),
      },
      timeout: timeoutMs,
    };
    const transport = urlObj.protocol === "https:" ? https : http;
    const req = transport.request(opts, (res) => {
      let chunks = "";
      res.setEncoding("utf-8");
      res.on("data", (d) => { chunks += d; });
      res.on("end", () => {
        let parsed = null;
        try { parsed = JSON.parse(chunks); } catch { parsed = null; }
        resolve({ status: res.statusCode || 0, body: parsed });
      });
    });
    req.on("error", (err) => resolve({ status: 0, error: err.message, body: null }));
    req.on("timeout", () => req.destroy(new Error("timeout")));
    req.write(payload);
    req.end();
  });
}

function saveBridgeToken(token, meta) {
  try {
    ensureOasisHome();
    fs.writeFileSync(BRIDGE_TOKEN_FILE, token, { mode: 0o600 });
    if (meta) fs.writeFileSync(BRIDGE_META_FILE, JSON.stringify(meta, null, 2), { mode: 0o600 });
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "write_failed" };
  }
}

async function redeemPairCode({ code, commandCenterUrl }) {
  const normalized = String(code || "").trim().toUpperCase();
  if (!PAIR_CODE_REGEX.test(normalized)) {
    return { ok: false, error: "bad_code_format", message: "Pair codes look like ABC-DEF-GHJ." };
  }
  if (!commandCenterUrl) {
    return { ok: false, error: "no_dashboard_url" };
  }
  const label = defaultMachineLabel();
  const fingerprint = machineFingerprint();
  const url = new URL("/api/auth/pair-code/redeem", commandCenterUrl).toString();
  const res = await postJson(url, { code: normalized, machine: { label, fingerprint } });
  if (res.status === 200 && res.body?.ok && res.body?.bridge?.token) {
    const meta = {
      pairing_id: res.body.bridge.pairing_id || null,
      tenant_id: res.body.tenant_id || null,
      dashboard_url: res.body.bridge.dashboard_url || commandCenterUrl.toString(),
      machine_label: label,
      paired_at: new Date().toISOString(),
      source: "deep-link",
    };
    const save = saveBridgeToken(res.body.bridge.token, meta);
    if (!save.ok) return { ok: false, error: "token_write_failed", message: save.error };
    return {
      ok: true,
      tenant_id: meta.tenant_id,
      dashboard_url: meta.dashboard_url,
      machine_label: meta.machine_label,
      // Magic-link transports a Supabase session into the Electron cookie
      // jar so the dashboard renders authenticated on first paint. Null
      // when the redeem endpoint couldn't mint it (degraded UX, not a
      // pairing failure).
      magic_link_url: res.body?.session?.magic_link_url || null,
    };
  }
  if (res.status === 404 || res.status === 410) {
    return { ok: false, error: "invalid_code", message: "Code expired or already used. Generate a fresh one." };
  }
  if (res.status === 429) {
    return { ok: false, error: "rate_limited", message: "Too many attempts. Wait a minute and try again." };
  }
  return { ok: false, error: "redeem_failed", message: res.body?.error || res.error || `Pair endpoint returned ${res.status}.` };
}

/**
 * Drain a list of pending URLs picked up before the app finished booting
 * (macOS `open-url` can fire before whenReady; second-instance argv can
 * arrive while ensureProviderConfigured is still awaiting the wizard).
 */
function makeDeepLinkBuffer() {
  const queue = [];
  let drain = null;
  return {
    push(rawUrl) {
      if (drain) {
        drain(rawUrl);
        return;
      }
      queue.push(rawUrl);
    },
    onReady(handler) {
      drain = handler;
      while (queue.length) {
        const url = queue.shift();
        try { handler(url); } catch { /* swallow */ }
      }
    },
  };
}

module.exports = {
  PROTOCOL,
  parseDeepLink,
  redeemPairCode,
  makeDeepLinkBuffer,
};
