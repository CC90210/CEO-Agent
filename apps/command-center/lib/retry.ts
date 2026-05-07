/**
 * Jittered exponential backoff for HTTP fetches that can transiently fail
 * (provider outages, rate limits, network blips). The chat path used to die
 * on the first 5xx with a raw error — now it retries up to 3 times before
 * surfacing a friendly "provider_temporarily_unavailable" to the operator.
 *
 * Usage:
 *   const res = await fetchWithRetry("https://...", { method: "POST", body });
 *
 * Retries on: HTTP 408 / 425 / 429 / 5xx, and on any thrown error (network
 * errors, DNS failures, AbortError from connection timeouts). Does NOT retry
 * on 4xx (other than the codes above) — those are caller errors.
 *
 * `attempts` defaults to 3; `baseMs` defaults to 2000 → schedule is 2s, 4s,
 * 8s with ±20% jitter.
 */

const RETRYABLE_STATUS = new Set([408, 425, 429, 500, 502, 503, 504, 522, 524]);

export type RetryOptions = {
  attempts?: number;
  baseMs?: number;
  /** If set, called on each retry with (attemptIndex, status?, error?). */
  onRetry?: (attempt: number, status?: number, error?: unknown) => void;
};

export async function fetchWithRetry(
  input: RequestInfo | URL,
  init?: RequestInit,
  opts: RetryOptions = {}
): Promise<Response> {
  const attempts = opts.attempts ?? 3;
  const baseMs = opts.baseMs ?? 2000;

  let lastError: unknown = null;
  let lastStatus: number | undefined;

  for (let i = 0; i < attempts; i++) {
    try {
      const res = await fetch(input, init);
      if (res.ok || !RETRYABLE_STATUS.has(res.status)) return res;
      lastStatus = res.status;
      // Drain body so the connection can be reused. Best-effort.
      try {
        await res.body?.cancel();
      } catch {
        // ignore
      }
      if (i === attempts - 1) return res;
      opts.onRetry?.(i, res.status);
    } catch (err) {
      lastError = err;
      if (i === attempts - 1) throw err;
      opts.onRetry?.(i, undefined, err);
    }

    const delayMs = baseMs * 2 ** i;
    const jitter = (Math.random() - 0.5) * 0.4 * delayMs; // ±20%
    await new Promise((r) => setTimeout(r, Math.max(0, delayMs + jitter)));
  }

  // Belt + suspenders — loop body returns or throws on the final attempt.
  if (lastError) throw lastError;
  throw new Error(`fetch_failed_after_${attempts}_attempts:${lastStatus ?? "unknown"}`);
}

export const PROVIDER_RETRYABLE_STATUS = RETRYABLE_STATUS;
