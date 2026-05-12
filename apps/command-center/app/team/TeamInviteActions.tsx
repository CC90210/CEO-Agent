"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

type ActiveInvite = {
  id: string;
  email: string | null;
  team_role: string;
  expires_at: string;
};

const INVITABLE_ROLES = [
  { value: "admin", label: "Admin (everything)" },
  { value: "loan_officer", label: "Loan officer" },
  { value: "processor", label: "Processor" },
  { value: "read_only", label: "Read only" },
  { value: "member", label: "Member" },
];

export function TeamInviteActions({
  activeInvites,
}: {
  activeInvites: ActiveInvite[];
}) {
  const router = useRouter();
  const [role, setRole] = useState("member");
  const [email, setEmail] = useState("");
  const [pending, startTransition] = useTransition();
  const [issuedToken, setIssuedToken] = useState<string | null>(null);
  const [issuedExpiry, setIssuedExpiry] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setError(null);
    setIssuedToken(null);
    setCopied(false);
    try {
      const res = await fetch("/api/team/invites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, email: email.trim() || null }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        setError(data.error || "Failed to create invite.");
        return;
      }
      setIssuedToken(data.invite.raw_token);
      setIssuedExpiry(data.invite.expires_at);
      setEmail("");
      startTransition(() => router.refresh());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create invite.");
    }
  }

  async function revoke(id: string) {
    if (!confirm("Revoke this invite?")) return;
    const res = await fetch(`/api/team/invites/${id}`, { method: "DELETE" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      alert(data.error || "Revoke failed.");
      return;
    }
    startTransition(() => router.refresh());
  }

  const inviteLink = issuedToken
    ? `${typeof window !== "undefined" ? window.location.origin : ""}/invite/${issuedToken}`
    : null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-[1fr_12rem_8rem] gap-3 items-end">
        <label className="block">
          <span className="text-xs uppercase tracking-wider text-fg-dim">
            Email (optional)
          </span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="teammate@company.com"
            className="mt-1 w-full bg-bg-elevated text-fg border border-bg-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent"
          />
        </label>
        <label className="block">
          <span className="text-xs uppercase tracking-wider text-fg-dim">Role</span>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="mt-1 w-full bg-bg-elevated text-fg border border-bg-border rounded px-3 py-2 text-sm"
          >
            {INVITABLE_ROLES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={generate}
          disabled={pending}
          className="bg-accent text-bg font-semibold py-2 px-3 rounded text-sm hover:opacity-90 disabled:opacity-50"
        >
          {pending ? "..." : "Generate link"}
        </button>
      </div>

      {error && (
        <div className="text-sm text-status-attention bg-bg-elevated border border-bg-border rounded px-3 py-2">
          {error}
        </div>
      )}

      {inviteLink && (
        <div className="rounded border border-accent/40 bg-bg-elevated p-3 space-y-2">
          <div className="text-xs uppercase tracking-wider text-accent font-mono">
            One-time link · copy now
          </div>
          <div className="flex items-center gap-2">
            <input
              readOnly
              value={inviteLink}
              className="flex-1 bg-bg text-fg border border-bg-border rounded px-2 py-1.5 text-xs font-mono"
              onFocus={(e) => e.currentTarget.select()}
            />
            <button
              type="button"
              onClick={async () => {
                if (!inviteLink) return;
                try {
                  await navigator.clipboard.writeText(inviteLink);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 2000);
                } catch {
                  setCopied(false);
                }
              }}
              className="bg-bg-elevated border border-bg-border text-fg text-xs py-1.5 px-3 rounded hover:border-accent"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <div className="text-xs text-fg-muted">
            Expires{" "}
            {issuedExpiry
              ? new Date(issuedExpiry).toLocaleString()
              : "in 7 days"}
            . This token will not be shown again — store it now.
          </div>
        </div>
      )}

      {activeInvites.length > 0 && (
        <div className="pt-2">
          <div className="text-xs uppercase tracking-wider text-fg-dim mb-2">
            Active invites
          </div>
          <ul className="divide-y divide-bg-border">
            {activeInvites.map((inv) => (
              <li
                key={inv.id}
                className="grid grid-cols-[1fr_8rem_8rem_5rem] gap-3 py-2 items-center"
              >
                <span className="text-sm text-fg">
                  {inv.email || "(open link)"}
                </span>
                <span className="text-sm text-fg-muted">{inv.team_role}</span>
                <span className="text-xs text-fg-dim">
                  expires {new Date(inv.expires_at).toLocaleDateString()}
                </span>
                <button
                  type="button"
                  onClick={() => revoke(inv.id)}
                  className="text-xs text-fg-muted hover:text-fg underline-offset-2 hover:underline"
                >
                  Revoke
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function RemoveMemberClientButton({ profileId }: { profileId: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  async function remove() {
    if (!confirm("Remove this member from the tenant?")) return;
    const res = await fetch(
      `/api/team/members?profile_id=${encodeURIComponent(profileId)}`,
      { method: "DELETE" }
    );
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      alert(data.error || "Remove failed.");
      return;
    }
    startTransition(() => router.refresh());
  }

  return (
    <button
      type="button"
      onClick={remove}
      disabled={pending}
      className="text-xs text-fg-muted hover:text-fg underline-offset-2 hover:underline disabled:opacity-50"
    >
      {pending ? "..." : "Remove"}
    </button>
  );
}
