/**
 * OAuth + email-confirm callback. Exchanges the magic ?code= param for a
 * session cookie, then redirects to the requested next page.
 *
 * Invite callbacks redeem into the inviter's tenant and skip fresh-tenant
 * provisioning. Non-invite OAuth/email-confirm signups provision directly
 * from the authenticated Supabase user; no browser-supplied auth_user_id is
 * trusted.
 */

import { NextResponse, type NextRequest } from "next/server";
import { createServerClient } from "@supabase/ssr";
import { provisionAuthenticatedUser } from "@/lib/auth-provisioning";
import { getServiceSupabase } from "@/lib/supabase-server";
import { redeemInvite } from "@/lib/team";

const PENDING_INVITE_COOKIE = "pending_invite_token";

export async function GET(req: NextRequest) {
  const { searchParams, origin } = req.nextUrl;
  const code = searchParams.get("code");
  const next = searchParams.get("next") || "/";
  const brandHint = searchParams.get("brand")?.trim() || "";
  const fullNameHint = searchParams.get("full_name")?.trim() || "";
  const inviteHint = searchParams.get("invite")?.trim() || "";

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
          res.cookies.set({ name, value, ...options }),
        );
      },
    },
  });

  const { data, error } = await supa.auth.exchangeCodeForSession(code);
  if (error || !data.user) {
    return NextResponse.redirect(
      `${origin}/login?err=${encodeURIComponent(error?.message || "session_failed")}`,
    );
  }

  const pendingInviteToken = inviteHint || req.cookies.get(PENDING_INVITE_COOKIE)?.value;
  if (pendingInviteToken) {
    res.cookies.set({ name: PENDING_INVITE_COOKIE, value: "", maxAge: 0, path: "/" });
    const redeemed = await redeemInvite(pendingInviteToken, data.user.id);
    if (redeemed.ok) return res;
  }

  try {
    if (!data.user.email) throw new Error("missing_email");
    await provisionAuthenticatedUser({
      db: getServiceSupabase(),
      authUserId: data.user.id,
      email: data.user.email,
      fullName:
        fullNameHint ||
        (data.user.user_metadata?.full_name as string) ||
        (data.user.user_metadata?.name as string) ||
        (data.user.email?.split("@")[0] ?? "User"),
      brand: brandHint || (data.user.user_metadata?.brand as string) || "OASIS AI",
    });
  } catch {
    // Don't block sign-in if provisioning hiccups; Settings can re-trigger.
  }

  return res;
}
