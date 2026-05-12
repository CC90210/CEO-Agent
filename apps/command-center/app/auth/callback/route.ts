/**
 * OAuth + email-confirm callback. Exchanges the magic ?code= param for a session
 * cookie, then redirects to the requested next page (or /).
 *
 * For brand-new OAuth signups, also calls /api/auth/provision to create the
 * tenant + profile if they don't already exist.
 */

import { NextResponse, type NextRequest } from "next/server";
import { createServerClient } from "@supabase/ssr";
import { redeemInvite } from "@/lib/team";

const PENDING_INVITE_COOKIE = "pending_invite_token";

export async function GET(req: NextRequest) {
  const { searchParams, origin } = req.nextUrl;
  const code = searchParams.get("code");
  const next = searchParams.get("next") || "/";
  const brandHint = searchParams.get("brand")?.trim() || "";
  const fullNameHint = searchParams.get("full_name")?.trim() || "";

  // NOTE: Supabase password-recovery emails redirect users straight to the
  // forgot-password redirectTo (set to /auth/reset-password) with the token
  // in the URL fragment — they do NOT pass through this callback. So we only
  // handle OAuth + email-confirm code exchange here.
  if (!code) return NextResponse.redirect(`${origin}/login?err=missing_code`);

  const url = process.env.BRAVO_SUPABASE_URL!;
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

  const res = NextResponse.redirect(`${origin}${next}`);

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

  const { data, error } = await supa.auth.exchangeCodeForSession(code);
  if (error || !data.user) {
    return NextResponse.redirect(`${origin}/login?err=${encodeURIComponent(error?.message || "session_failed")}`);
  }

  // If the user is redeeming an invite, attach them to the inviter's tenant
  // instead of provisioning a new one. The /invite/[token] route stores the
  // raw token in a short-lived cookie when the user wasn't yet authed.
  const pendingInviteToken = req.cookies.get(PENDING_INVITE_COOKIE)?.value;
  if (pendingInviteToken) {
    res.cookies.set({ name: PENDING_INVITE_COOKIE, value: "", maxAge: 0, path: "/" });
    const redeemed = await redeemInvite(pendingInviteToken, data.user.id);
    if (redeemed.ok) {
      // Skip provision — the redeemer is now a member of the inviter's tenant.
      return res;
    }
    // Fall through to provision if the invite was invalid; the user still gets signed in.
  }

  // Best-effort provision: if no profile yet (OAuth first signup), create tenant + profile.
  try {
    const provisionRes = await fetch(`${origin}/api/auth/provision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        auth_user_id: data.user.id,
        email: data.user.email,
        full_name:
          fullNameHint ||
          (data.user.user_metadata?.full_name as string) ||
          (data.user.user_metadata?.name as string) ||
          (data.user.email?.split("@")[0] ?? "User"),
        brand: brandHint || (data.user.user_metadata?.brand as string) || "OASIS AI",
      }),
    });
    // Idempotent — already-provisioned returns ok too
    void provisionRes;
  } catch {
    // Don't block sign-in if provisioning hiccups; Settings page can re-trigger.
  }

  return res;
}
