"use strict";

/**
 * Shared HTTPS helpers used by provider-keys validation and the
 * update probe. Wraps node:https with the conventions both call sites
 * actually want: a tight default timeout, buffered body collection,
 * structured { status, headers, body } return.
 *
 * Why a shared module: the two callers were drifting (one had a
 * 15s timeout, the other 10s; one read content-length from headers,
 * the other didn't) which is exactly the kind of duplication that
 * grows bugs. Single source of truth, both consumers point here.
 */

const https = require("node:https");

const DEFAULT_TIMEOUT_MS = 12_000;

/**
 * Low-level request. Returns { status, headers, body } where body is the
 * raw response string. Caller decides whether to JSON.parse.
 *
 * options: anything node:https.request accepts (hostname/path/method/headers).
 * body:    optional string/Buffer; sets content-length automatically.
 * opts:    { timeoutMs?: number }
 */
function httpsRequest(options, body, opts = {}) {
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  return new Promise((resolve, reject) => {
    const headers = { ...(options.headers || {}) };
    if (body !== undefined && body !== null && headers["content-length"] === undefined) {
      headers["content-length"] = Buffer.byteLength(body);
    }
    const req = https.request({ ...options, headers }, (res) => {
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => {
        resolve({
          status: res.statusCode || 0,
          headers: res.headers,
          body: Buffer.concat(chunks).toString("utf8"),
        });
      });
    });
    req.on("error", reject);
    req.setTimeout(timeoutMs, () => {
      req.destroy(new Error("request_timeout"));
    });
    if (body !== undefined && body !== null) req.write(body);
    req.end();
  });
}

/**
 * Convenience wrapper for "GET this URL, parse the response as JSON,
 * reject on non-2xx." Used by the update probe.
 */
async function httpsGetJson(url, headers = {}, opts = {}) {
  const parsed = new URL(url);
  const res = await httpsRequest(
    {
      method: "GET",
      hostname: parsed.hostname,
      path: `${parsed.pathname}${parsed.search}`,
      port: parsed.port || 443,
      headers: { "user-agent": "OASIS-AI-Desktop", ...headers },
    },
    null,
    opts
  );
  if (res.status < 200 || res.status >= 300) {
    throw new Error(`http_${res.status}:${res.body.slice(0, 200)}`);
  }
  return JSON.parse(res.body);
}

module.exports = {
  DEFAULT_TIMEOUT_MS,
  httpsGetJson,
  httpsRequest,
};
