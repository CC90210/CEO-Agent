/**
 * Auth middleware — gates every page behind a Supabase session.
 *
 * Public routes: auth pages, public webhooks, install scripts, brand assets.
 * Everything else redirects to /login when there's no session.
 */

import { NextResponse, type NextRequest } from "next/server";
import { createServerClient } from "@supabase/ssr";

const PUBLIC_PATH_PREFIXES = [
  "/welcome",              // public marketing landing
  "/configure",            // public agent configurator (pre-signup)
  "/login",
  "/signup",
  "/forgot-password",
  "/auth/callback",
  "/auth/reset-password",
  "/api/inbound",          // n8n inbound webhook (Bearer-auth gated inside the route)
  "/api/auth/signout",
  "/api/auth/provision",   // legacy + setup-wizard provision (Bearer-auth gated inside)
  "/api/auth/pair",        // setup-wizard pairing (Bearer-auth gated inside)
  "/api/bridge",           // local-bridge daemon heartbeat (Bearer token gated inside)
  "/api/integrations/registry",  // canonical service+env_key list — used by the bridge to decide what to ping; non-sensitive (names only, no values), 5min Cache-Control
  "/api/exec-override",    // external caller fallback for override approvals (HMAC auth inside)
  "/api/outbound/log",     // outbound logging from local backend (HMAC auth inside)
  "/api/event-feed",       // OASIS Town poller reads recent agent_events (read-only, no secrets in payloads). Option B "public for proof-of-life" per 2026-05-10 directive; HMAC hardening deferred.

  "/api/cron",
  "/api/webhook",          // public webhooks for clients (HMAC/Bearer gated inside)
  "/_next",
  "/favicon",
];

const MARKETING_REDIRECT_TARGET = "/welcome"; // unauthed home goes here, not login

// Public static-asset extensions. Anything served from /public with one of
// these suffixes is allowed without auth — install scripts (curl|bash) and
// brand assets MUST be reachable anonymously.
const PUBLIC_FILE_EXTENSIONS = [
  ".sh", ".ps1",                              // install one-liners
  ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",  // images
  ".txt", ".webmanifest", ".xml", ".json",    // robots / manifests
  ".woff", ".woff2", ".ttf",                  // fonts
];

function isPublic(pathname: string): boolean {
  if (PUBLIC_PATH_PREFIXES.some((p) => pathname.startsWith(p))) return true;
  const lower = pathname.toLowerCase();
  return PUBLIC_FILE_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Pass pathname through as a header so the root layout can decide whether
  // to render the dashboard shell vs full-bleed (marketing/auth) chrome.
  const requestHeaders = new Headers(req.headers);
  requestHeaders.set("x-pathname", pathname);

  // Always allow public paths
  if (isPublic(pathname)) {
    return NextResponse.next({ request: { headers: requestHeaders } });
  }

  const url = process.env.BRAVO_SUPABASE_URL;
  const anon =
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
    process.env.BRAVO_SUPABASE_ANON_KEY;
  // If env not configured (preview/local), let it through — page-level guards still run
  if (!url || !anon) return NextResponse.next({ request: { headers: requestHeaders } });

  const res = NextResponse.next({ request: { headers: requestHeaders } });
  const supa = createServerClient(url, anon, {
    cookies: {
      getAll() {
        return req.cookies.getAll();
      },
      setAll(toSet) {
        toSet.forEach(({ name, value, options }) =>
          res.cookies.set({ name, value, ...options })
        );
      },
    },
  });

  const { data, error } = await supa.auth.getUser();
  if (error || !data.user) {
    // For /api/* requests return 401 JSON so client fetch() sees a real
    // error (not an HTML redirect that breaks .json()). For pages,
    // redirect to /login.
    if (pathname.startsWith("/api/")) {
      return NextResponse.json(
        { ok: false, error: "unauthorized" },
        { status: 401 }
      );
    }
    // For the home page, send unauthed visitors to the marketing landing.
    // For deep links into the app, send them to login with a return path.
    if (pathname === "/" || pathname === "") {
      return NextResponse.redirect(new URL(MARKETING_REDIRECT_TARGET, req.url));
    }
    const loginUrl = new URL("/login", req.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // Onboarding gate: if the user signed up but never finished the wizard
  // (closed the tab between /signup and /onboarding's "Finish" button),
  // force-route them back to /onboarding for any non-API page request.
  //
  // Performance: a per-request DB query through the user-JWT supa client
  // adds ~30-80ms to every page load. Optimization: cache the "onboarded"
  // decision in an HttpOnly cookie. First page load after sign-in still
  // hits DB; every subsequent load is cookie-only. If the user clears
  // cookies, the next page hits DB and re-sets the cookie.
  //
  // The cookie value is non-sensitive — it's purely a UX redirect gate.
  // A spoofed cookie just lets the user bypass /onboarding (no security
  // impact). HttpOnly + SameSite=Lax keeps casual JS / cross-site reads
  // out, even though there's no real secret to protect here.
  //
  // Exempted paths:
  //   - /onboarding itself (and sub-paths) — the wizard's destination
  //   - /api/* — the wizard's own writes (PATCH /api/profile etc) must
  //     not get bounced
  //   - public path set (handled above by isPublic)
  //
  // Failures fall through silently: a broken gate is worse than a missed
  // redirect.
  const ONBOARDED_COOKIE = "oasis_onboarded";
  const onboardedHint = req.cookies.get(ONBOARDED_COOKIE)?.value;
  const checkOnboarding =
    !pathname.startsWith("/api/") &&
    pathname !== "/onboarding" &&
    !pathname.startsWith("/onboarding/") &&
    onboardedHint !== "1";

  if (checkOnboarding) {
    try {
      const { data: profile } = await supa
        .from("user_profiles")
        .select("onboarding_completed_at")
        .eq("auth_user_id", data.user.id)
        .maybeSingle();
      if (profile && profile.onboarding_completed_at == null) {
        return NextResponse.redirect(new URL("/onboarding", req.url));
      }
      if (profile && profile.onboarding_completed_at) {
        // Cache the decision so subsequent page loads skip the DB query.
        // 30-day TTL is plenty — the only thing that invalidates it is
        // the user explicitly resetting their profile, which would also
        // require them to re-onboard. Path=/ so every route sees it.
        res.cookies.set(ONBOARDED_COOKIE, "1", {
          httpOnly: true,
          sameSite: "lax",
          secure: true,
          maxAge: 60 * 60 * 24 * 30,
          path: "/",
        });
      }
    } catch {
      // If the profile query fails (transient DB), let the page render —
      // page-level guards still run and the worst case is the user sees
      // an empty dashboard instead of being trapped on /onboarding.
    }
  }

  return res;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
