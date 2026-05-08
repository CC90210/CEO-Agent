/**
 * A5: Cron auth gate — require BOTH a matching CRON_SECRET bearer token AND
 * Vercel's `x-vercel-cron: 1` header. Either alone is insufficient. Vercel's
 * cron infrastructure sends both automatically when the route is wired in
 * vercel.json crons. An external caller who learns CRON_SECRET still cannot
 * forge `x-vercel-cron: 1` from outside Vercel's edge — the platform strips
 * client-supplied versions of that header on the way in.
 *
 * Returns null on success; otherwise a 401/500 NextResponse the route can
 * return directly.
 */

import { NextResponse, type NextRequest } from "next/server";

export function checkCronAuth(req: NextRequest): NextResponse | null {
  const expected = process.env.CRON_SECRET;
  if (!expected) {
    // Misconfiguration is a hard failure — refuse to run rather than
    // silently bypassing auth.
    return NextResponse.json(
      { error: "cron_not_configured", detail: "CRON_SECRET is not set." },
      { status: 500 }
    );
  }
  const auth = req.headers.get("authorization") || "";
  if (auth !== `Bearer ${expected}`) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  // Allow a local-dev escape hatch — but only when explicitly opted in.
  // Without this, you'd have to fake the Vercel header on every test curl.
  const allowLocal = process.env.CRON_ALLOW_LOCAL === "1";
  const vercelCron = req.headers.get("x-vercel-cron") === "1";
  if (!vercelCron && !allowLocal) {
    return NextResponse.json(
      { error: "unauthorized", detail: "missing_vercel_cron_header" },
      { status: 401 }
    );
  }
  return null;
}
