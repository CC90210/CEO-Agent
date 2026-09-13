"use strict";
/*
 * limit_detector.js â€” pure classification helpers for the Claude Spillover proxy (CONTRACT.md Â§5).
 *
 * No I/O, no clock reads (the caller passes nowMs), no dependencies. Everything here is a pure
 * function of its arguments so the proxy and the tests agree on exactly one rule set.
 *
 *   classify({status, headers, bodyText, nowMs}, [clamps]) -> {kind, claim, reset_at, reset_source, clamped, reason}
 *     kind = "subscription_limit" : account-wide five_hour / seven_day usage limit. The only kind that spills.
 *            "model_limit"        : same shape but a model-scoped claim (seven_day_opus, ...). Never spilled.
 *            "transient"          : every other 429, and 529.
 *            "none"               : anything else.
 *     reset_at is epoch seconds, taken from the first source that parses:
 *       1. anthropic-ratelimit-unified-reset (epoch seconds or RFC 3339), shifted by the clock skew
 *          (nowMs - Date header) so a server timestamp becomes a local one;
 *       2. retry-after (delta seconds, or an HTTP-date shifted by the same skew);
 *       3. now + 1800.
 *     It is then clamped to [now + reset_clamp_min_sec, now + reset_clamp_max_sec].
 *
 *   parseEntrypoint(ua)    "claude-cli/<ver> (external, <entrypoint>[, ...])" -> "<entrypoint>", else null.
 *   claudeCodeVersion(ua)  "claude-cli/2.1.268 (...)" -> "2.1.268", else null.
 *   isOAuthBearer(auth)    true only for "Bearer sk-ant-oat..." (a claude.ai login).
 *   estimateTokens(body)   JSON-aware estimate: text and tool-schema JSON at ~3.5 chars/token; base64
 *                          payloads and image blocks are not counted as text (flat per-media cost instead).
 *   unifiedTelemetry(h)    the anthropic-ratelimit-unified-* values the events log records.
 */

const SUBSCRIPTION_CLAIMS = new Set(["five_hour", "seven_day"]);
const DEFAULT_RESET_SEC = 1800;
const DEFAULT_CLAMP_MIN_SEC = 60;
const DEFAULT_CLAMP_MAX_SEC = 691200;
const CHARS_PER_TOKEN = 3.5;
// A flat cost per image or base64 document. Anthropic bills an image at up to ~1600 tokens; the
// base64 text itself never reaches the model as tokens, so counting its characters would be wrong.
const MEDIA_TOKENS = 1600;
const EPOCH_MS_THRESHOLD = 1e11; // an all-digit reset above this is epoch milliseconds, not seconds

const UA_RE = /^claude-cli\/([^\s(]+)\s*\(([^)]*)\)/;
const VERSION_RE = /^claude-cli\/(\d+\.\d+\.\d+)/;
const OAUTH_BEARER_RE = /^bearer\s+sk-ant-oat/i;
const DIGITS_RE = /^\d+(\.\d+)?$/;

/** First value of a lowercase-keyed header, trimmed; null when absent. */
function headerValue(headers, name) {
  if (!headers) return null;
  const raw = headers[name];
  if (raw === undefined || raw === null) return null;
  const value = Array.isArray(raw) ? raw[0] : raw;
  return value === undefined || value === null ? null : String(value).trim();
}

function lowerHeader(headers, name) {
  const v = headerValue(headers, name);
  return v === null ? null : v.toLowerCase();
}

/** error.type from an Anthropic error body, or null when the body is not that shape. */
function errorTypeOf(bodyText) {
  if (typeof bodyText !== "string" || bodyText === "") return null;
  try {
    const parsed = JSON.parse(bodyText);
    return parsed && parsed.error && typeof parsed.error.type === "string" ? parsed.error.type : null;
  } catch {
    return null;
  }
}

/** Epoch seconds from "1790000000", "1790000000123" (ms) or an RFC 3339 / HTTP-date string. */
function parseTimestampSec(value) {
  if (value === null || value === "") return null;
  if (DIGITS_RE.test(value)) {
    const n = Number(value);
    return n > EPOCH_MS_THRESHOLD ? n / 1000 : n;
  }
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms / 1000 : null;
}

/** Seconds our clock is ahead of the server's, from the Date header; 0 when it is absent or bad. */
function clockSkewSec(headers, nowMs) {
  const date = headerValue(headers, "date");
  if (!date) return 0;
  const serverMs = Date.parse(date);
  return Number.isFinite(serverMs) ? (nowMs - serverMs) / 1000 : 0;
}

function parseRetryAfterSec(value, nowSec, skewSec) {
  if (value === null || value === "") return null;
  if (DIGITS_RE.test(value)) return nowSec + Number(value);
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms / 1000 + skewSec : null;
}

function computeReset(headers, nowMs, clamps) {
  const nowSec = nowMs / 1000;
  const skewSec = clockSkewSec(headers, nowMs);
  let resetSec = null;
  let source = null;

  const unified = parseTimestampSec(headerValue(headers, "anthropic-ratelimit-unified-reset"));
  if (unified !== null) {
    resetSec = unified + skewSec;
    source = "unified-reset";
  } else {
    const retryAfter = parseRetryAfterSec(headerValue(headers, "retry-after"), nowSec, skewSec);
    if (retryAfter !== null) {
      resetSec = retryAfter;
      source = "retry-after";
    }
  }
  if (resetSec === null) {
    resetSec = nowSec + DEFAULT_RESET_SEC;
    source = "default";
  }

  const minSec = nowSec + clamps.minSec;
  const maxSec = nowSec + clamps.maxSec;
  const bounded = Math.min(Math.max(resetSec, minSec), maxSec);
  return { reset_at: Math.ceil(bounded), reset_source: source, clamped: bounded !== resetSec };
}

function clampsFrom(opts) {
  const o = opts || {};
  const minSec = Number.isFinite(o.reset_clamp_min_sec) ? o.reset_clamp_min_sec : DEFAULT_CLAMP_MIN_SEC;
  const maxSec = Number.isFinite(o.reset_clamp_max_sec) ? o.reset_clamp_max_sec : DEFAULT_CLAMP_MAX_SEC;
  return { minSec, maxSec };
}

function verdict(kind, reason, extra) {
  return Object.assign({ kind, claim: null, reset_at: null, reset_source: null, clamped: false, reason }, extra);
}

/**
 * Classify one Anthropic response. `headers` is a lowercase-keyed object (Node's res.headers).
 * `opts` may carry {reset_clamp_min_sec, reset_clamp_max_sec} from config; defaults are Â§3's.
 */
function classify(input, opts) {
  const { status, headers, bodyText } = input || {};
  const nowMs = Number.isFinite(input && input.nowMs) ? input.nowMs : Date.now();

  if (status === 529) return verdict("transient", "529 overloaded");
  if (status !== 429) return verdict("none", `status ${status}`);

  const unifiedStatus = lowerHeader(headers, "anthropic-ratelimit-unified-status");
  if (unifiedStatus !== "rejected") return verdict("transient", `unified-status ${unifiedStatus || "absent"}`);
  if (errorTypeOf(bodyText) !== "rate_limit_error") return verdict("transient", "error.type is not rate_limit_error");
  if (lowerHeader(headers, "anthropic-ratelimit-unified-fallback") === "available") {
    return verdict("transient", "unified-fallback available");
  }
  if (lowerHeader(headers, "anthropic-ratelimit-unified-overage-in-use") === "true") {
    return verdict("transient", "overage in use");
  }
  const claim = lowerHeader(headers, "anthropic-ratelimit-unified-representative-claim");
  if (!claim) return verdict("transient", "no representative claim");

  const reset = computeReset(headers, nowMs, clampsFrom(opts));
  if (SUBSCRIPTION_CLAIMS.has(claim)) {
    return verdict("subscription_limit", `unified rejected, claim ${claim}`, Object.assign({ claim }, reset));
  }
  return verdict("model_limit", `model-scoped claim ${claim}`, Object.assign({ claim }, reset));
}

/**
 * The entrypoint from Claude Code's User-Agent, e.g. "claude-cli/2.1.268 (external, cli)" -> "cli".
 * Only the "external" user type is recognised; anything else returns null, which is never eligible.
 */
function parseEntrypoint(ua) {
  if (typeof ua !== "string") return null;
  const m = UA_RE.exec(ua.trim());
  if (!m) return null;
  const parts = m[2].split(",").map((p) => p.trim());
  if (parts[0] !== "external" || !parts[1]) return null;
  return parts[1];
}

function claudeCodeVersion(ua) {
  if (typeof ua !== "string") return null;
  const m = VERSION_RE.exec(ua.trim());
  return m ? m[1] : null;
}

function isOAuthBearer(authHeader) {
  return typeof authHeader === "string" && OAUTH_BEARER_RE.test(authHeader.trim());
}

function walkText(node, acc) {
  if (node === null || node === undefined) return;
  if (typeof node === "string") { acc.chars += node.length; return; }
  if (typeof node !== "object") return;
  if (Array.isArray(node)) { for (const item of node) walkText(item, acc); return; }
  if (node.type === "image" || node.type === "redacted_thinking") return;
  if (node.type === "base64" && typeof node.data === "string") return;
  if (typeof node.text === "string") acc.chars += node.text.length;
  if (node.type === "tool_result" && node.content !== undefined) walkText(node.content, acc);
  if (node.type === "tool_use" && node.input !== undefined) acc.chars += JSON.stringify(node.input).length;
  if (node.type === "tool_reference" && typeof node.tool_name === "string") acc.chars += node.tool_name.length;
}

/** Rough token count for user-visible text and tool schemas; binary media payloads are skipped. */
function estimateTokens(bodyObj) {
  const acc = { chars: 0 };
  if (!bodyObj || typeof bodyObj !== "object") return 0;
  walkText(bodyObj.system, acc);
  walkText(bodyObj.messages, acc);
  if (Array.isArray(bodyObj.tools)) {
    for (const tool of bodyObj.tools) acc.chars += JSON.stringify(tool).length;
  }
  return Math.ceil(acc.chars / CHARS_PER_TOKEN);
}
/** The unified-* values the events log records; null when the response carries none of them. */
function unifiedTelemetry(headers) {
  const out = {
    status: headerValue(headers, "anthropic-ratelimit-unified-status"),
    claim: headerValue(headers, "anthropic-ratelimit-unified-representative-claim"),
    reset: headerValue(headers, "anthropic-ratelimit-unified-reset"),
    fallback: headerValue(headers, "anthropic-ratelimit-unified-fallback"),
    overage_status: headerValue(headers, "anthropic-ratelimit-unified-overage-status"),
  };
  return Object.values(out).some((v) => v !== null) ? out : null;
}

module.exports = {
  classify,
  parseEntrypoint,
  claudeCodeVersion,
  isOAuthBearer,
  estimateTokens,
  unifiedTelemetry,
  SUBSCRIPTION_CLAIMS,
  MEDIA_TOKENS,
  CHARS_PER_TOKEN,
};

