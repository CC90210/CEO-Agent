"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw } from "lucide-react";

/**
 * Tiny client island that triggers a server re-render every 5 seconds so the
 * feed stays current without a websocket. The actual fetch happens in the
 * parent server component — we just call router.refresh().
 *
 * Uses useTransition so the spinner shows during the in-flight refresh and
 * the previous data stays visible (no layout flash).
 */
export function FeedRefresher() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [lastTick, setLastTick] = useState<number>(Date.now());

  useEffect(() => {
    const id = setInterval(() => {
      startTransition(() => {
        router.refresh();
        setLastTick(Date.now());
      });
    }, 5000);
    return () => clearInterval(id);
  }, [router]);

  const ago = Math.max(0, Math.round((Date.now() - lastTick) / 1000));

  return (
    <button
      onClick={() => {
        startTransition(() => {
          router.refresh();
          setLastTick(Date.now());
        });
      }}
      title="Refresh now"
      className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-bg-border text-[10px] font-bold uppercase tracking-wider text-fg-muted hover:text-fg hover:border-accent transition-all"
    >
      <RefreshCw
        size={12}
        className={pending ? "animate-spin" : ""}
      />
      <span>{pending ? "refreshing" : `${ago}s`}</span>
    </button>
  );
}
