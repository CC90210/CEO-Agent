"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getBrowserSupabase } from "@/lib/supabase-browser";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [brand, setBrand] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const supa = getBrowserSupabase();
      const { data, error } = await supa.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: `${window.location.origin}/auth/callback`,
          data: { full_name: fullName, brand: brand || "OASIS AI" },
        },
      });
      if (error) {
        setErr(error.message);
        return;
      }
      // Provision tenant + profile via API route (uses service role server-side)
      if (data.user) {
        const r = await fetch("/api/auth/provision", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            auth_user_id: data.user.id,
            email,
            full_name: fullName,
            brand: brand || "OASIS AI",
          }),
        });
        if (!r.ok) {
          const body = await r.json().catch(() => ({}));
          setErr(body.error || "Provisioning failed");
          return;
        }
      }

      router.push("/onboarding");
      router.refresh();
    } catch (ex: unknown) {
      setErr(ex instanceof Error ? ex.message : "Sign up failed");
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
          redirectTo: `${window.location.origin}/auth/callback?signup=1`,
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
    <div className="min-h-screen bg-bg flex items-center justify-center px-6 py-12">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-3 mb-4">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/oasis-logo.svg"
              alt="OASIS AI"
              width={44}
              height={44}
              className="rounded-md shadow-glow ring-1 ring-accent/30"
            />
            <div className="text-fg font-bold tracking-tight text-lg">OASIS AI</div>
          </div>
          <h1 className="text-2xl font-bold text-fg">Create your Command Center</h1>
          <p className="text-fg-muted text-sm mt-2">
            Your isolated workspace. Multi-agent. Profile-driven.
          </p>
        </div>

        <div className="bg-bg-panel border border-bg-border rounded-xl p-6 shadow-card">
          <form onSubmit={onSubmit} className="space-y-3">
            <Field label="Full name" value={fullName} onChange={setFullName} required autoComplete="name" />
            <Field label="Email" type="email" value={email} onChange={setEmail} required autoComplete="email" />
            <Field
              label="Brand or company name"
              value={brand}
              onChange={setBrand}
              placeholder="OASIS AI"
              autoComplete="organization"
            />
            <Field
              label="Password"
              type="password"
              value={password}
              onChange={setPassword}
              required
              autoComplete="new-password"
              hint="Minimum 8 characters."
            />

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
              {busy ? "Creating account…" : "Create account"}
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
            className="w-full bg-bg-elev border border-bg-border text-fg font-medium py-2.5 rounded-md hover:bg-bg-hover transition-colors disabled:opacity-50"
          >
            Sign up with Google
          </button>
        </div>

        <p className="text-center text-sm text-fg-muted mt-6">
          Already have an account?{" "}
          <Link href="/login" className="text-accent hover:underline font-medium">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}

function Field({
  label,
  type = "text",
  value,
  onChange,
  required,
  placeholder,
  autoComplete,
  hint,
}: {
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  placeholder?: string;
  autoComplete?: string;
  hint?: string;
}) {
  return (
    <div>
      <label className="text-xs uppercase tracking-wider font-bold text-fg-muted">
        {label}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        placeholder={placeholder}
        autoComplete={autoComplete}
        className="mt-1.5 w-full bg-bg-elev border border-bg-border rounded-md px-3 py-2.5 text-fg focus:border-accent focus:outline-none"
      />
      {hint && <div className="text-xs text-fg-dim mt-1">{hint}</div>}
    </div>
  );
}
