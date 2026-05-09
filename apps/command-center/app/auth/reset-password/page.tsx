"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { getBrowserSupabase } from "@/lib/supabase-browser";
import { OasisLogo } from "@/components/brand/OasisLogo";

/**
 * Where the password-reset email's link lands. Supabase's reset email
 * sends users here with a recovery token in the URL fragment. We let
 * Supabase parse the fragment via getSession(), then show a form for
 * the new password.
 */
export default function ResetPasswordPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [pwd, setPwd] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [sessionReady, setSessionReady] = useState(false);

  // The reset link puts the recovery token in the URL fragment;
  // @supabase/ssr browser client picks it up automatically via auth state events.
  useEffect(() => {
    const supa = getBrowserSupabase();
    // Force session pickup in case the URL fragment hasn't been parsed yet
    supa.auth.getSession().then(({ data }) => {
      if (data.session) setSessionReady(true);
    });
    const { data: sub } = supa.auth.onAuthStateChange((event) => {
      if (event === "PASSWORD_RECOVERY" || event === "SIGNED_IN") {
        setSessionReady(true);
      }
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  // Treat any error in the URL search params as a hard fail (Supabase appends ?error=...)
  const urlError = searchParams.get("error_description") || searchParams.get("error");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (pwd !== confirm) {
      setErr("Passwords don't match.");
      return;
    }
    if (pwd.length < 8) {
      setErr("Use at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      const supa = getBrowserSupabase();
      const { error } = await supa.auth.updateUser({ password: pwd });
      if (error) {
        setErr(error.message);
        return;
      }
      setDone(true);
      setTimeout(() => router.push("/"), 1200);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-bg flex items-center justify-center px-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-3 mb-4">
            <OasisLogo size={44} priority />
            <div className="text-fg font-bold tracking-tight text-lg">OASIS AI</div>
          </div>
          <h1 className="text-2xl font-bold text-fg">Set a new password</h1>
          <p className="text-fg-muted text-sm mt-2">
            One-time link from your inbox got you here. Pick something memorable.
          </p>
        </div>

        <div className="bg-bg-panel border border-bg-border rounded-xl p-6 shadow-card">
          {urlError ? (
            <div className="text-sm text-status-hot bg-status-hot/10 border border-status-hot/30 rounded-md px-3 py-3">
              <div className="font-bold mb-1">Reset link failed</div>
              <div className="text-fg-muted">{urlError}</div>
              <Link
                href="/forgot-password"
                className="text-accent hover:underline mt-2 inline-block"
              >
                Request a new link →
              </Link>
            </div>
          ) : done ? (
            <div className="text-sm text-status-engaged bg-status-engaged/10 border border-status-engaged/30 rounded-md px-3 py-3">
              Password updated. Signing you in…
            </div>
          ) : !sessionReady ? (
            <div className="text-sm text-fg-muted text-center py-3">
              Verifying reset link…
            </div>
          ) : (
            <form onSubmit={onSubmit} className="space-y-3">
              <div>
                <label className="text-xs uppercase tracking-wider font-bold text-fg-muted">
                  New password
                </label>
                <input
                  type="password"
                  value={pwd}
                  onChange={(e) => setPwd(e.target.value)}
                  required
                  className="mt-1.5 w-full bg-bg-elev border border-bg-border rounded-md px-3 py-2.5 text-fg focus:border-accent focus:outline-none"
                  autoComplete="new-password"
                  autoFocus
                />
              </div>
              <div>
                <label className="text-xs uppercase tracking-wider font-bold text-fg-muted">
                  Confirm
                </label>
                <input
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required
                  className="mt-1.5 w-full bg-bg-elev border border-bg-border rounded-md px-3 py-2.5 text-fg focus:border-accent focus:outline-none"
                  autoComplete="new-password"
                />
              </div>
              {err && (
                <div className="text-sm text-status-hot bg-status-hot/10 border border-status-hot/30 rounded-md px-3 py-2">
                  {err}
                </div>
              )}
              <button
                type="submit"
                disabled={busy}
                className="w-full bg-accent text-bg font-bold py-2.5 rounded-md hover:bg-accent-muted transition-colors disabled:opacity-50"
              >
                {busy ? "Updating…" : "Set password & sign in"}
              </button>
            </form>
          )}
        </div>

        <p className="text-center text-sm text-fg-muted mt-6">
          <Link href="/login" className="text-accent hover:underline font-medium">
            Back to sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
