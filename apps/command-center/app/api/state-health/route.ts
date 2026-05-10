import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const STATE_API_URL = process.env.STATE_API_URL || "http://state-api:8500";

/**
 * Server-side proxy to the V6.0 state-api FastAPI service.
 *
 * The dashboard never speaks SQLite directly — it would have to bind-mount
 * state/empire_state.db into the Next.js container, breaking the read-only
 * sandbox contract. Instead, scripts/state_api.py is its own service with
 * a read-only mount of state/, and this route proxies its JSON.
 *
 * In local-dev outside Docker, set STATE_API_URL=http://127.0.0.1:8500.
 */
export async function GET() {
  try {
    const res = await fetch(`${STATE_API_URL}/status`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      return NextResponse.json(
        { error: `state-api returned ${res.status}`, available: false },
        { status: 200 },
      );
    }
    const body = await res.json();
    return NextResponse.json({ available: true, ...body });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "state-api unreachable";
    return NextResponse.json(
      { error: msg, available: false, hint: "Is `state-api` daemon running? Try: docker compose -f infra/docker-compose.local.yml up -d state-api" },
      { status: 200 },
    );
  }
}
