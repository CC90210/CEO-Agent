/**
 * Auth middleware — gates every page behind a Supabase session.
 *
 * Public routes: auth pages, public webhooks, install scripts, brand assets.
 * Everything else redirects to /login when there's no session.
 */

import { NextResponse, type NextRequest } from "next/server";
import { createServerClient } from "@supabase/ssr";

const PUBLIC_PATH_PREFIXES = [
  "/login",
  "/signup",
  "/forgot-password",
  "/auth/callback",
  "/auth/reset-password",
  "/api/inbound",          // n8n inbound webhook (Bearer-auth gated inside the route)
  "/api/auth/signout",
  "/api/auth/provision",   // legacy + setup-wizard provision (Bearer-auth gated inside)
  "/api/cron",
  "/api/webhook",          // public webhooks for clients (HMAC/Bearer gated inside)
  "/_next",
  "/favicon",
];

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

  // Always allow public paths
  if (isPublic(pathname)) return NextResponse.next();

  const url = process.env.BRAVO_SUPABASE_URL;
  const anon =
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
    process.env.BRAVO_SUPABASE_ANON_KEY;
  // If env not configured (preview/local), let it through — page-level guards still run
  if (!url || !anon) return NextResponse.next();

  const res = NextResponse.next();
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
    const loginUrl = new URL("/login", req.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return res;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
