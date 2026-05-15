import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/supabase-server";
import { LoginForm } from "./LoginForm";

export const dynamic = "force-dynamic";

/**
 * Self-healing /login: if the caller already has a valid session, bounce
 * them straight to their `?next=` target (or "/"). Catches the case where
 * middleware or some other layer kicked a signed-in user back to /login —
 * happened to CC on a preview deploy where clicking a Quick Action landed
 * on /login despite an active session. Rather than make them re-sign-in,
 * recognize they're already authed and forward them.
 *
 * Auth-state check is server-side so it runs BEFORE the form renders —
 * no flash of the sign-in UI for already-authed users.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams?: Promise<{ next?: string }>;
}) {
  const params = (await searchParams) || {};
  const user = await getSessionUser().catch(() => null);
  if (user) {
    const next = typeof params.next === "string" && params.next.startsWith("/")
      ? params.next
      : "/";
    redirect(next);
  }
  return <LoginForm />;
}
