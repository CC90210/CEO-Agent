import { NextResponse, type NextRequest } from "next/server";
import { DEMO_CLIENT_PROFILE_COOKIE } from "@/lib/client-profiles";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const res = NextResponse.redirect(new URL("/", req.url));
  res.cookies.set(DEMO_CLIENT_PROFILE_COOKIE, "", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
  return res;
}
