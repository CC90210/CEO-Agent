/**
 * In-memory token-bucket rate limiter.
 *
 * Per-tenant ceiling on /api/chat to keep a runaway script from burning
 * through the platform key in the operator-fallback path. Buckets live in
 * the serverless-function instance memory; Vercel reuses warm instances
 * for ~minutes, so this is "good enough" without a Redis dependency.
 *
 * For client-tenant deploys with their own keys, the upstream provider is
 * the real ceiling — this limiter mainly protects YOUR platform key when
 * an admin bypasses BYO via operatorFallback().
 *
 * Replace with @upstash/ratelimit + @upstash/redis if you ever need
 * cross-instance accuracy or a dashboard view of who's hitting limits.
 */

type Bucket = {
  tokens: number;
  refilledAt: number;
};

const buckets = new Map<string, Bucket>();

export type RateLimitDecision =
  | { allowed: true; remaining: number; resetIn: number }
  | { allowed: false; remaining: 0; resetIn: number };

export function rateLimit(opts: {
  key: string;
  capacity: number;     // max tokens in the bucket
  refillPerSec: number; // tokens added per second
  cost?: number;        // tokens consumed by THIS call (default 1)
}): RateLimitDecision {
  const cost = opts.cost ?? 1;
  const now = Date.now();
  const existing = buckets.get(opts.key);
  let tokens: number;
  if (!existing) {
    tokens = opts.capacity;
  } else {
    const elapsedSec = (now - existing.refilledAt) / 1000;
    tokens = Math.min(opts.capacity, existing.tokens + elapsedSec * opts.refillPerSec);
  }
  if (tokens >= cost) {
    tokens -= cost;
    buckets.set(opts.key, { tokens, refilledAt: now });
    return {
      allowed: true,
      remaining: Math.floor(tokens),
      resetIn: Math.ceil((opts.capacity - tokens) / opts.refillPerSec),
    };
  }
  buckets.set(opts.key, { tokens, refilledAt: now });
  return {
    allowed: false,
    remaining: 0,
    resetIn: Math.ceil((cost - tokens) / opts.refillPerSec),
  };
}
