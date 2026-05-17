"use client";

/**
 * InviteRedeemForSignedInUser — one-click redeem CTA for the /invite/<token>
 * landing page when the operator is already authenticated.
 *
 * Saves the round-trip through /login for users who pasted the link in a
 * tab where they're already signed in. Wires straight to the
 * /api/auth/redeem-invite route + bounces to the welcome wizard on
 * first-redeem, dashboard on returning-user.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2, CheckCircle2, AlertCircle, Mail, Shield } from "lucide-react";
import { getBrowserSupabase } from "@/lib/supabase-browser";

type Props = {
  token: string;
  tenantName: string;
  roleLabel: string;
  email: string;
};

export function InviteRedeemForSignedInUser({ token, tenantName, roleLabel, email }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function redeem() {
    setBusy(true);
    setError(null);
    try {
      const supa = getBrowserSupabase();
      const { data } = await supa.auth.getUser();
      if (!data.user) {
        setError("Not signed in. Refresh and try again.");
        setBusy(false);
        return;
      }
      const r = await fetch("/api/auth/redeem-invite", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          auth_user_id: data.user.id,
          raw_token: token,
        }),
      });
      const body = (await r.json().catch(() => ({}))) as {
        ok?: boolean;
        error?: string;
        message?: string;
        first_login?: boolean;
      };
      if (!r.ok || !body.ok) {
        setError(body.message || body.error || `Redeem failed (${r.status})`);
        setBusy(false);
        return;
      }
      router.push(body.first_login ? "/onboarding/welcome" : "/");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Redeem failed");
      setBusy(false);
    }
  }

  return (
    <div className="rounded-2xl border border-accent/40 bg-accent/5 p-6 space-y-5">
      <div className="flex items-center gap-3">
        <div className="rounded-full bg-accent/15 border border-accent/30 p-2">
          <CheckCircle2 className="w-5 h-5 text-accent" />
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wider font-bold text-fg-dim">
            Confirm your invite
          </div>
          <h1 className="text-xl font-bold text-fg leading-tight">{tenantName}</h1>
        </div>
      </div>

      <ul className="space-y-2 text-sm">
        <li className="flex items-center gap-2 text-fg-muted">
          <Shield className="w-4 h-4 text-fg-dim shrink-0" />
          Role: <span className="font-semibold text-fg">{roleLabel}</span>
        </li>
        <li className="flex items-center gap-2 text-fg-muted">
          <Mail className="w-4 h-4 text-fg-dim shrink-0" />
          As: <span className="font-mono text-fg">{email}</span>
        </li>
      </ul>

      <button
        type="button"
        onClick={redeem}
        disabled={busy}
        className="w-full rounded-lg bg-accent text-bg-deep font-bold py-2.5 text-sm hover:bg-accent/90 transition-colors inline-flex items-center justify-center gap-2 disabled:opacity-60"
      >
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />}
        {busy ? "Joining…" : `Join ${tenantName}`}
      </button>

      {error && (
        <div className="flex items-start gap-2 text-[12px] text-red-300 bg-red-500/10 border border-red-500/30 rounded-md p-2">
          <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          {error}
        </div>
      )}

      <p className="text-[11px] text-fg-dim leading-relaxed">
        You&apos;ll keep your current account ({email}) and gain access to this workspace. If you want
        to join from a different email, sign out first.
      </p>
    </div>
  );
}
