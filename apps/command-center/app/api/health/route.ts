import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/**
 * Liveness probe for the Docker healthcheck (and any uptime monitor).
 * Intentionally NOT gated by Caddy basic auth — Caddyfile carves out
 * `/api/health` so probes don't need credentials.
 */
export function GET() {
  return NextResponse.json({
    status: "ok",
    service: "command-center",
    ts: new Date().toISOString(),
  });
}
