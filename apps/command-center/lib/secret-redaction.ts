/**
 * Secret redaction — server-only.
 *
 * Any string headed for chat_messages (assistantText, error messages),
 * structured logs, or SSE error events is funnelled through `redactSecrets()`
 * first. Risk vectors:
 *
 *   1. Provider error bodies (OpenAI/Anthropic/OpenRouter/Google) can echo
 *      back portions of the request, which include the API key in headers
 *      OR (Google) the URL query string.
 *   2. The model itself could echo a key it saw in a tool result or context.
 *   3. Streaming errors get persisted to `chat_messages.error` — Supabase
 *      table, accessible to anyone with read on that row.
 *
 * Strategy: snapshot every credential-shaped env var value at module init,
 * sort by length DESC (so we don't half-scrub a value that contains another
 * value as substring), replace each occurrence with `[REDACTED:NAME]`.
 *
 * This is defense-in-depth. Provider APIs SHOULD never echo keys; the model
 * SHOULD never repeat secrets. But "should never" is the wrong reliability
 * floor for credentials.
 */

const CRED_NAME_PAT = /(KEY|TOKEN|SECRET|PASSWORD|API|DSN|WEBHOOK)$/;
const ENV_NAME_PAT = /^[A-Z][A-Z0-9_]{2,63}$/;
const MIN_REDACTABLE_LEN = 12;

let cachedPairs: Array<[string, string]> | null = null;

function loadPairs(): Array<[string, string]> {
  if (cachedPairs) return cachedPairs;
  const out: Map<string, string> = new Map();
  for (const [k, v] of Object.entries(process.env)) {
    if (typeof v !== "string" || v.length < MIN_REDACTABLE_LEN) continue;
    if (!ENV_NAME_PAT.test(k)) continue;
    if (!CRED_NAME_PAT.test(k)) continue;
    out.set(k, v);
  }
  cachedPairs = Array.from(out.entries()).sort(
    (a, b) => b[1].length - a[1].length
  );
  return cachedPairs;
}

export function redactSecrets(text: string | null | undefined): string {
  if (!text) return text ?? "";
  let out = String(text);
  for (const [name, value] of loadPairs()) {
    if (value && out.includes(value)) {
      out = out.split(value).join(`[REDACTED:${name}]`);
    }
  }
  return out;
}

/** Strip `?key=...` and `&api_key=...` query params from URL-shaped substrings. */
export function redactUrlKeyParams(text: string | null | undefined): string {
  if (!text) return text ?? "";
  return String(text)
    .replace(/([?&])(key|api_key|apikey|access_token)=[^&\s"'<>]+/gi, "$1$2=[REDACTED]");
}

export function redactAll(text: string | null | undefined): string {
  return redactSecrets(redactUrlKeyParams(text));
}
