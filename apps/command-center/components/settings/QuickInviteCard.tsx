"use client";

/**
 * QuickInviteCard — inline invite-mint affordance for the Settings page.
 *
 * The Settings card has a "Manage team & invites →" link to /team for
 * the full mint/revoke/list UI. This component adds a quick role +
 * Generate path so an admin doesn't have to navigate away to send one
 * link. After mint, shows the URL with a Copy button — the operator
 * pastes it into Slack/email and is done. Matches CC's literal ask:
 * 'create a personalized link without leaving Settings'.
 *
 * Heavy lifting (active invite list, email field, revoke) stays at
 * /team — this is the 80% path for the most common use.
 */

import { useState } from "react";
import { Check, Copy, Loader2, Link as LinkIcon, AlertCircle } from "lucide-react";

const ROLE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "member", label: "Member" },
  { value: "loan_officer", label: "Loan officer" },
  { value: "processor", label: "Processor" },
  { value: "admin", label: "Admin" },
  { value: "read_only", label: "Read-only" },
];

export function QuickInviteCard() {
  const [role, setRole] = useState("member");
  const [busy, setBusy] = useState(false);
  const [issuedUrl, setIssuedUrl] = useState<string | null>(null);
  const [issuedExpiry, setIssuedExpiry] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setBusy(true);
    setError(null);
    setIssuedUrl(null);
    setCopied(false);
    try {
      const res = await fetch("/api/team/invites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, email: null }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok || !data.invite?.raw_token) {
        setError(data.error || `Failed to create invite (http_${res.status}).`);
        return;
      }
      const url = `${window.location.origin}/invite/${data.invite.raw_token}`;
      setIssuedUrl(url);
      setIssuedExpiry(data.invite.expires_at);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create invite.");
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!issuedUrl) return;
    try {
      await navigator.clipboard.writeText(issuedUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      window.prompt("Copy this URL:", issuedUrl);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex-1 min-w-[12rem]">
          <span className="block text-[11px] uppercase tracking-wider text-fg-dim font-bold mb-1">
            Role
          </span>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            disabled={busy}
            className="w-full rounded-md border border-bg-border bg-bg-elev px-3 py-2 text-sm text-fg disabled:opacity-50"
          >
            {ROLE_OPTIONS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={generate}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-lg bg-accent text-bg-deep px-4 py-2 text-sm font-bold hover:bg-accent-bright disabled:opacity-50"
        >
          {busy ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <LinkIcon className="w-4 h-4" />
          )}
          Generate link
        </button>
      </div>

      {issuedUrl && (
        <div className="rounded-md border border-status-engaged/40 bg-status-engaged/10 p-3 space-y-2">
          <div className="text-xs text-status-engaged font-bold">
            Invite link ready{" "}
            {issuedExpiry && (
              <span className="text-fg-dim font-normal">
                — expires {new Date(issuedExpiry).toLocaleDateString()}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <code className="flex-1 rounded-md bg-bg-deep border border-bg-border px-2 py-1.5 font-mono text-[11px] text-fg-muted overflow-x-auto whitespace-nowrap">
              {issuedUrl}
            </code>
            <button
              type="button"
              onClick={copy}
              className="inline-flex items-center gap-1 rounded-md border border-bg-border bg-bg-elev px-2.5 py-1.5 text-xs font-bold text-fg hover:border-accent/40"
            >
              {copied ? (
                <>
                  <Check className="w-3 h-3 text-status-engaged" />
                  Copied
                </>
              ) : (
                <>
                  <Copy className="w-3 h-3" />
                  Copy
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 text-xs text-rose-400">
          <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
