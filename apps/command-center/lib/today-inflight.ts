/**
 * Tiny client-side counter for in-flight Today-page mutations. The Finalize
 * button reads this to refuse firing while any TodayBlockToggle PATCH is
 * still landing — otherwise the Finalize PATCH can race the toggle PATCH
 * and the streak computer ends up reading a stale schedule against a fresh
 * finalized_at.
 *
 * Module-scoped, browser-only. No SSR concerns because both consumers are
 * "use client". Subscribers are notified synchronously.
 */
let inflight = 0;
const subs = new Set<(count: number) => void>();

export function beginInflight(): () => void {
  inflight += 1;
  notify();
  let released = false;
  return () => {
    if (released) return;
    released = true;
    inflight = Math.max(0, inflight - 1);
    notify();
  };
}

export function subscribeInflight(fn: (count: number) => void): () => void {
  subs.add(fn);
  fn(inflight);
  return () => {
    subs.delete(fn);
  };
}

function notify() {
  for (const fn of subs) fn(inflight);
}
