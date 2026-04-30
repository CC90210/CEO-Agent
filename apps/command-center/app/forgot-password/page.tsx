"use client";

import { useState } from "react";
import Link from "next/link";
import { getBrowserSupabase } from "@/lib/supabase-browser";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const supa = getBrowserSupabase();
      const { error } = await supa.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/auth/reset-password`,
      });
      if (error) {
        setErr(error.message);
        return;
      }
      setSent(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-bg flex items-center justify-center px-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-fg">Reset your password</h1>
          <p className="text-fg-muted text-sm mt-2">
            We'll email you a link to set a new one.
          </p>
        </div>

        <div className="bg-bg-panel border border-bg-border rounded-xl p-6 shadow-card">
          {sent ? (
            <div className="text-sm text-status-engaged bg-status-engaged/10 border border-status-engaged/30 rounded-md px-3 py-3">
              Check your inbox for a password-reset link.
            </div>
          ) : (
            <form onSubmit={onSubmit} className="space-y-3">
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
                  autoComplete="email"
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
                {busy ? "Sending…" : "Send reset link"}
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
