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
  "/download",             // public OASIS Desktop downloads
  "/configure",            // public agent configurator (pre-signup)
  "/demo/sun",             // public Sun Biz review shell; demo data only
  "/login",
  "/signup",
  "/forgot-password",
  "/auth/callback",
  "/auth/reset-password",
  "/invite",               // Tenant-invite landing /invite/<token>. Token is opaque; preview RPC validates server-side (Phase A, master multi-tenant infra plan, 2026-05-17).
  "/api/inbound",          // n8n inbound webhook (Bearer-auth gated inside the route)
  "/api/auth/signout",
  "/api/auth/provision",   // legacy + setup-wizard provision (Bearer-auth gated inside)
  "/api/auth/pair",        // setup-wizard pairing (Bearer-auth gated inside)
  "/api/demo/sun",         // sets Sun demo shell cookie; never exposes live tenant data
  "/api/download/desktop", // public OS-aware desktop download redirect
  "/api/bridge",           // local-bridge daemon heartbeat (Bearer token gated inside)
  "/api/integrations/registry",  // canonical service+env_key list — used by the bridge to decide what to ping; non-sensitive (names only, no values), 5min Cache-Control
  "/api/exec-override",    // external caller fallback for override approvals (HMAC auth inside)
  "/api/outbound/log",     // outbound logging from local backend (HMAC auth inside)
  "/api/event-feed",       // OASIS Town poller reads recent agent_events (read-only, no secrets in payloads). Option B "public for proof-of-life" per 2026-05-10 directive; HMAC hardening deferred.
  "/api/quests",           // OASIS Town Quest Log polls ACTIVE_TASKS.md mirror. Read-only, public for Phase 5 proof-of-life.
  "/api/track",            // Email-open tracking pixel (Phase 19 SunBiz CRM, 2026-05-17). Must be public — mail clients fetch the pixel without a session. Route resolves tenant_id by lookup against the interaction row (never trusts the URL parameter) and always returns a 1x1 GIF, so 401-gating it would silently break every operator's open-rate tracking. Migration 050 dedupes by (outbound_message_id, ip_hash) so a known reservation_id can't be replayed to inflate row counts.

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

  // Phase 6b/7 — redirect routes still folded into bigger surfaces.
  // Reasoning + Health + Overrides came back to top-level nav in
  // Phase 7 (CC found the Phase 2 trim too aggressive). The remaining
  // three really are merged elsewhere and shouldn't be reachable at
  // their old URLs:
  //   /feed → /operations         (Activity Tape is the same stream)
  //   /playbook → /settings       (reference under Settings)
  //   /integrations → /settings   (setup under Settings)
  const REDIRECT_MAP: Record<string, string> = {
    "/feed": "/operations",
    "/playbook": "/settings",
    "/integrations": "/settings",
  };
  if (pathname in REDIRECT_MAP) {
    return NextResponse.redirect(new URL(REDIRECT_MAP[pathname], req.url));
  }

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

  // Cross-tenant view leak hardening (2026-05-16):
  //
  // The `oasis_demo_client_profile` cookie was originally a Sun Biz pitch
  // surface — anonymous prospects hitting /demo/sun get the SunBiz shell
  // for 8 hours. Failure mode: an authenticated operator who once touched
  // /demo/sun came back signed in, and the stale cookie hijacked their
  // shell into SunBiz for the remaining cookie TTL even though their auth
  // was their real OASIS account (RLS still protected the data; only the
  // chrome was wrong, but it routed `/api/sms/send` etc. as SunBiz which
  // is a real integrity hazard).
  //
  // Rule: an authenticated user on a non-/demo path gets the cookie
  // cleared on the response. /demo/sun itself is exempted so the
  // anonymous preview keeps working. The layout has a defense-in-depth
  // copy of this rule for the page render, but the middleware clear is
  // the durable one — Server Component cookie writes silently no-op in
  // some Next 15 contexts, so the layout-side clear can't be relied on.
  if (
    !error &&
    data.user &&
    !pathname.startsWith("/demo/sun") &&
    req.cookies.get("oasis_demo_client_profile")?.value
  ) {
    res.cookies.set("oasis_demo_client_profile", "", {
      maxAge: 0,
      path: "/",
    });
  }

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
        .select("onboarding_completed_at, invited_by")
        .eq("auth_user_id", data.user.id)
        .maybeSingle();
      if (profile && profile.onboarding_completed_at == null) {
        // New signups land on the industry-template wizard by default.
        // The legacy /onboarding flow (Anthropic-key + C-suite picker) is
        // operator-only — non-operator hits to /onboarding get bounced to
        // /onboarding/wizard by the page itself (see lib/operator-credentials.ts
        // isOperatorEmail). Sending everyone to /onboarding/wizard first
        // avoids the bounce and keeps the C-suite picker invisible to
        // client tenants who shouldn't see it.
        return NextResponse.redirect(
          new URL(profile.invited_by ? "/onboarding/welcome" : "/onboarding/wizard", req.url),
        );
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
