"use client";

/**
 * Live pairing-status indicator for /onboarding. Polls /api/devices every
 * 5s after mount. The moment a fresh pairing (< 5 min old) appears, the
 * indicator flips from "waiting" to "paired" with a link to /agents.
 *
 * Stops polling once paired or after 5 minutes (operator can refresh
 * manually if their bridge isn't up by then — we don't keep beating on
 * the API endpoint forever).
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, Loader2 } from "lucide-react";

const FRESH_MS = 5 * 60 * 1000;
const POLL_MS = 5_000;
const MAX_POLL_MS = 5 * 60_000;

type Device = {
  id: string;
  label: string | null;
  last_seen_at: string | null;
  revoked_at: string | null;
};

export function PairingStatus({ initialPaired }: { initialPaired: boolean }) {
  const [paired, setPaired] = useState(initialPaired);
  const [device, setDevice] = useState<Device | null>(null);
  const [pollingSince] = useState(() => Date.now());

  useEffect(() => {
    if (paired) return;
    let stopped = false;

    async function check() {
      try {
        const r = await fetch("/api/devices", { cache: "no-store" });
        if (!r.ok) return;
        const j = (await r.json()) as { devices?: Device[] };
        const fresh = (j.devices || []).find(
          (d) =>
            !d.revoked_at &&
            d.last_seen_at &&
            Date.now() - new Date(d.last_seen_at).getTime() < FRESH_MS,
        );
        if (fresh && !stopped) {
          setPaired(true);
          setDevice(fresh);
        }
      } catch {
        // Network blip — keep polling
      }
    }

    check();
    const iv = setInterval(() => {
      if (Date.now() - pollingSince > MAX_POLL_MS) {
        clearInterval(iv);
        return;
      }
      check();
    }, POLL_MS);
    return () => {
      stopped = true;
      clearInterval(iv);
    };
  }, [paired, pollingSince]);

  if (paired) {
    return (
      <div className="rounded-xl border border-status-engaged/40 bg-status-engaged/5 p-4 flex items-center gap-3">
        <CheckCircle2 className="w-5 h-5 text-status-engaged flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-bold text-fg">Your machine is paired.</div>
          <div className="text-xs text-fg-muted">
            {device?.label || "Bridge"} is online — chat has full repo access.
          </div>
        </div>
        <Link href="/agents" className="btn-send text-sm">
          Open chat <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-bg-border bg-bg-elev/60 p-4 flex items-center gap-3">
      <Loader2 className="w-5 h-5 text-accent animate-spin flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-bold text-fg">Waiting for the bridge to come online…</div>
        <div className="text-xs text-fg-muted">
          Run the install one-liner from <Link href="/configure" className="text-accent hover:underline">configure</Link>. This pill flips green within ~30s of the bridge starting.
        </div>
      </div>
    </div>
  );
}
