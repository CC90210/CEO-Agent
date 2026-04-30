"use client";

import { useState } from "react";
import { getBrowserSupabase } from "@/lib/supabase-browser";

export function ChangePasswordForm() {
  const [pwd, setPwd] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
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
      setMsg("Password updated.");
      setPwd("");
      setConfirm("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3 max-w-md">
      <div>
        <label className="text-xs uppercase tracking-wider font-bold text-fg-muted">
          New password
        </label>
        <input
          type="password"
          value={pwd}
          onChange={(e) => setPwd(e.target.value)}
          required
          className="mt-1.5 w-full bg-bg-elev border border-bg-border rounded-md px-3 py-2 text-fg focus:border-accent focus:outline-none"
          autoComplete="new-password"
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
          className="mt-1.5 w-full bg-bg-elev border border-bg-border rounded-md px-3 py-2 text-fg focus:border-accent focus:outline-none"
          autoComplete="new-password"
        />
      </div>
      {err && (
        <div className="text-sm text-status-hot bg-status-hot/10 border border-status-hot/30 rounded-md px-3 py-2">
          {err}
        </div>
      )}
      {msg && (
        <div className="text-sm text-status-engaged bg-status-engaged/10 border border-status-engaged/30 rounded-md px-3 py-2">
          {msg}
        </div>
      )}
      <button
        type="submit"
        disabled={busy}
        className="bg-accent text-bg font-bold py-2 px-4 rounded-md hover:bg-accent-muted transition-colors disabled:opacity-50"
      >
        {busy ? "Updating…" : "Update password"}
      </button>
    </form>
  );
}
