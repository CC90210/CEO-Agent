/**
 * GET /api/integrations/registry — canonical integration list.
 *
 * Returns the same data the dashboard renders on /integrations: service
 * slug, category, label, env_key (when api_key style), so the bridge
 * daemon can scan .env.agents for known env_keys without carrying its
 * own hardcoded copy of the registry. Single source of truth in
 * lib/integrations-registry.ts; this endpoint just serializes it.
 *
 * Public (no auth) since the data is static + non-sensitive — service
 * names + env-var names that the operator already sees on /integrations.
 * No tenant data leaks. Cached for 5 minutes via Cache-Control to keep
 * bridge fetch overhead low.
 */

import { NextResponse } from "next/server";
import { KNOWN_INTEGRATIONS } from "@/lib/integrations-registry";

export const runtime = "nodejs";
export const dynamic = "force-static"; // pure data, no per-request state

export async function GET() {
  // Project just the fields the bridge needs. env_key is optional —
  // entries without it aren't api-key style integrations.
  const entries = KNOWN_INTEGRATIONS.map((i) => ({
    service: i.service,
    label: i.label,
    category: i.category,
    connection_kind: i.connection_kind,
    env_key: i.env_key || null,
    setup_complexity: i.setup_complexity,
  }));
  return NextResponse.json(
    { ok: true, count: entries.length, entries },
    {
      headers: {
        "cache-control": "public, max-age=300, s-maxage=300",
      },
    }
  );
}
