"use strict";

/**
 * provider-keys.js — convenience layer over secure-store for the
 * desktop's provider-credential scope. Encapsulates the canonical
 * scope/name pairs and the live-validation calls used by the first-run
 * window and the "Reset API key" menu.
 *
 * Scope is "provider". Stored secrets:
 *   provider:anthropic_api_key
 *   provider:openrouter_api_key
 *   provider:openai_api_key
 *   provider:google_api_key
 *
 * The bridge sidecar reads whichever provider the operator configured
 * via env vars at spawn time — see bridge-runtime.js / main.js bridge
 * env composition. The Command Center's per-tenant agent_model_config
 * remains the authoritative store for cloud chat; this file only
 * concerns the desktop bridge's first-run + key-rotation flows.
 */

const https = require("node:https");
const { deleteSecret, getSecret, setSecret } = require("./secure-store");

const SCOPE = "provider";

const PROVIDERS = ["anthropic", "openrouter", "openai", "google"];

function storeKeyFor(provider) {
  return `${provider}_api_key`;
}

function isKnownProvider(provider) {
  return PROVIDERS.includes(provider);
}

function getProviderKey(provider) {
  if (!isKnownProvider(provider)) return null;
  try {
    return getSecret(SCOPE, storeKeyFor(provider));
  } catch {
    return null;
  }
}

function setProviderKey(provider, value) {
  if (!isKnownProvider(provider)) {
    throw new Error(`unknown_provider:${provider}`);
  }
  if (typeof value !== "string" || value.trim().length < 8) {
    throw new Error("invalid_key_format");
  }
  setSecret(SCOPE, storeKeyFor(provider), value.trim());
}

function clearProviderKey(provider) {
  if (!isKnownProvider(provider)) return;
  deleteSecret(SCOPE, storeKeyFor(provider));
}

function listConfiguredProviders() {
  return PROVIDERS.filter((p) => getProviderKey(p));
}

/**
 * Pick the provider the bridge should boot with. Order of preference
 * matches the Command Center's PROVIDER_REGISTRY ordering: openrouter
 * (one key, many models) → anthropic → openai → google.
 */
function pickDefaultProvider() {
  for (const p of ["openrouter", "anthropic", "openai", "google"]) {
    if (getProviderKey(p)) return p;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Live validation — sends a tiny test request to the provider's REST API
// to confirm the key is shaped correctly AND accepted. Returns a structured
// result the first-run window can render. Never logs the key.
// ---------------------------------------------------------------------------

function httpsRequest(options, body) {
  return new Promise((resolve, reject) => {
    const req = https.request(options, (res) => {
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => {
        const text = Buffer.concat(chunks).toString("utf8");
        resolve({ status: res.statusCode || 0, body: text });
      });
    });
    req.on("error", reject);
    req.setTimeout(15_000, () => {
      req.destroy(new Error("validation_timeout"));
    });
    if (body) req.write(body);
    req.end();
  });
}

async function validateAnthropicKey(key) {
  const body = JSON.stringify({
    model: "claude-haiku-4-5",
    max_tokens: 4,
    messages: [{ role: "user", content: "hi" }],
  });
  try {
    const res = await httpsRequest(
      {
        hostname: "api.anthropic.com",
        path: "/v1/messages",
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-api-key": key,
          "anthropic-version": "2023-06-01",
          "content-length": Buffer.byteLength(body),
        },
      },
      body
    );
    if (res.status === 200) return { ok: true, model: "claude-haiku-4-5" };
    if (res.status === 401) return { ok: false, reason: "invalid_key" };
    if (res.status === 429) return { ok: false, reason: "rate_limited" };
    return { ok: false, reason: `http_${res.status}` };
  } catch (err) {
    return { ok: false, reason: err instanceof Error ? err.message : "network_error" };
  }
}

async function validateOpenRouterKey(key) {
  try {
    const res = await httpsRequest({
      hostname: "openrouter.ai",
      path: "/api/v1/models",
      method: "GET",
      headers: { authorization: `Bearer ${key}` },
    });
    if (res.status === 200) return { ok: true };
    if (res.status === 401) return { ok: false, reason: "invalid_key" };
    return { ok: false, reason: `http_${res.status}` };
  } catch (err) {
    return { ok: false, reason: err instanceof Error ? err.message : "network_error" };
  }
}

async function validateOpenAIKey(key) {
  try {
    const res = await httpsRequest({
      hostname: "api.openai.com",
      path: "/v1/models",
      method: "GET",
      headers: { authorization: `Bearer ${key}` },
    });
    if (res.status === 200) return { ok: true };
    if (res.status === 401) return { ok: false, reason: "invalid_key" };
    return { ok: false, reason: `http_${res.status}` };
  } catch (err) {
    return { ok: false, reason: err instanceof Error ? err.message : "network_error" };
  }
}

async function validateGoogleKey(key) {
  try {
    const res = await httpsRequest({
      hostname: "generativelanguage.googleapis.com",
      path: `/v1beta/models?key=${encodeURIComponent(key)}`,
      method: "GET",
    });
    if (res.status === 200) return { ok: true };
    if (res.status === 401 || res.status === 403) return { ok: false, reason: "invalid_key" };
    return { ok: false, reason: `http_${res.status}` };
  } catch (err) {
    return { ok: false, reason: err instanceof Error ? err.message : "network_error" };
  }
}

async function validateProviderKey(provider, key) {
  if (!isKnownProvider(provider)) {
    return { ok: false, reason: "unknown_provider" };
  }
  if (typeof key !== "string" || key.trim().length < 8) {
    return { ok: false, reason: "invalid_format" };
  }
  switch (provider) {
    case "anthropic": return validateAnthropicKey(key);
    case "openrouter": return validateOpenRouterKey(key);
    case "openai": return validateOpenAIKey(key);
    case "google": return validateGoogleKey(key);
    default: return { ok: false, reason: "unsupported" };
  }
}

/**
 * Compose the env-var subset the bridge sidecar expects so it can call
 * the configured provider without reaching back into Electron's process.
 * Returns null when no provider is configured.
 */
function composeBridgeEnv() {
  const anthropic = getProviderKey("anthropic");
  const openrouter = getProviderKey("openrouter");
  const openai = getProviderKey("openai");
  const google = getProviderKey("google");
  const env = {};
  if (anthropic) env.ANTHROPIC_API_KEY = anthropic;
  if (openrouter) env.OPENROUTER_API_KEY = openrouter;
  if (openai) env.OPENAI_API_KEY = openai;
  if (google) env.GOOGLE_API_KEY = google;
  if (Object.keys(env).length === 0) return null;
  const def = pickDefaultProvider();
  if (def) env.OASIS_DEFAULT_PROVIDER = def;
  return env;
}

module.exports = {
  PROVIDERS,
  clearProviderKey,
  composeBridgeEnv,
  getProviderKey,
  listConfiguredProviders,
  pickDefaultProvider,
  setProviderKey,
  validateProviderKey,
};
