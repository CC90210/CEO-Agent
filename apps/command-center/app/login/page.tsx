"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { getBrowserSupabase } from "@/lib/supabase-browser";

export default function LoginPage() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const supa = getBrowserSupabase();
      const { error } = await supa.auth.signInWithPassword({ email, password });
      if (error) {
        setErr(error.message);
        return;
      }
      router.push(next);
      router.refresh();
    } catch (ex: unknown) {
      setErr(ex instanceof Error ? ex.message : "Sign in failed");
    } finally {
      setBusy(false);
    }
  }

  async function onGoogle() {
    setBusy(true);
    setErr(null);
    try {
      const supa = getBrowserSupabase();
      const { error } = await supa.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`,
        },
      });
      if (error) setErr(error.message);
    } catch (ex: unknown) {
      setErr(ex instanceof Error ? ex.message : "OAuth failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-bg flex items-center justify-center px-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-md bg-gradient-to-br from-accent to-accent-muted flex items-center justify-center text-bg font-black shadow-glow">
              O
            </div>
            <div className="text-fg font-bold tracking-tight">OASIS AI</div>
          </div>
          <h1 className="text-2xl font-bold text-fg">Sign in to Command Center</h1>
          <p className="text-fg-muted text-sm mt-2">
            The operating system for your AI agents.
          </p>
        </div>

        <div className="bg-bg-panel border border-bg-border rounded-xl p-6 shadow-card">
          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="text-xs uppercase tracking-wider font-bold text-fg-muted">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="mt-1.5 w-full bg-bg-elev border border-bg-border rounded-md px-3 py-2.5 text-fg focus:border-accent focus:outline-none"
                placeholder="you@oasisai.work"
                autoComplete="email"
              />
            </div>
            <div>
              <div className="flex justify-between items-center">
                <label className="text-xs uppercase tracking-wider font-bold text-fg-muted">
                  Password
                </label>
                <Link
                  href="/forgot-password"
                  className="text-xs text-accent hover:underline"
                >
                  Forgot?
                </Link>
              </div>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="mt-1.5 w-full bg-bg-elev border border-bg-border rounded-md px-3 py-2.5 text-fg focus:border-accent focus:outline-none"
                autoComplete="current-password"
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
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <div className="my-5 flex items-center gap-3">
            <div className="h-px flex-1 bg-bg-border" />
            <span className="text-xs text-fg-dim uppercase tracking-wider">or</span>
            <div className="h-px flex-1 bg-bg-border" />
          </div>

          <button
            onClick={onGoogle}
            disabled={busy}
            className="w-full bg-bg-elev border border-bg-border text-fg font-medium py-2.5 rounded-md hover:bg-bg-hover transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09Z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.99.66-2.25 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23Z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18a10.97 10.97 0 0 0 0 9.86l3.66-2.84Z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38Z"
              />
            </svg>
            Continue with Google
          </button>
        </div>

        <p className="text-center text-sm text-fg-muted mt-6">
          New to OASIS?{" "}
          <Link href="/signup" className="text-accent hover:underline font-medium">
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}
