import { NextResponse, type NextRequest } from "next/server";
import { DEMO_CLIENT_PROFILE_COOKIE } from "@/lib/client-profiles";
import { getSessionUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const user = await getSessionUser();
  if (!user) {
    return NextResponse.redirect(new URL("/login", req.url));
  }

  const res = NextResponse.redirect(new URL("/", req.url));
  res.cookies.set(DEMO_CLIENT_PROFILE_COOKIE, "sun", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  return res;
}
