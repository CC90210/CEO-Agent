import { NextResponse, type NextRequest } from "next/server";
import { getSessionUser } from "@/lib/supabase-server";
import { redeemInvite } from "@/lib/team";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PENDING_COOKIE = "pending_invite_token";
const PENDING_COOKIE_MAX_AGE = 60 * 60 * 24; // 24h

export async function GET(req: NextRequest, ctx: { params: Promise<{ token: string }> }) {
  const { token } = await ctx.params;
  const { origin } = req.nextUrl;

  if (!token || token.length < 16) {
    return NextResponse.redirect(`${origin}/login?err=invalid_invite`);
  }

  const user = await getSessionUser();

  if (!user) {
    const res = NextResponse.redirect(`${origin}/login?next=${encodeURIComponent("/")}`);
    res.cookies.set({
      name: PENDING_COOKIE,
      value: token,
      maxAge: PENDING_COOKIE_MAX_AGE,
      path: "/",
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
    });
    return res;
  }

  const result = await redeemInvite(token, user.id);
  if (!result.ok) {
    return NextResponse.redirect(
      `${origin}/login?err=${encodeURIComponent(result.error)}`
    );
  }

  const res = NextResponse.redirect(`${origin}/`);
  res.cookies.set({ name: PENDING_COOKIE, value: "", maxAge: 0, path: "/" });
  return res;
}
