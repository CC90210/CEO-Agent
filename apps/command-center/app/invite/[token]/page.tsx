/**
 * /invite/[token] — landing page for tenant invites.
 *
 * Phase A of the master multi-tenant infra plan (2026-05-17).
 *
 * Flow:
 *   1. Server-renders a preview of the invite (tenant name + role + expiry)
 *      via the preview_tenant_invite RPC (migration 051). The token is
 *      SHA-256 hashed in-process — the raw token NEVER leaves the URL
 *      and is never logged.
 *   2. If the invite is invalid / expired / revoked, renders a clean
 *      "this link's no longer active" card with a Sign In CTA.
 *   3. If valid, renders the tenant name + role + a clear "Continue"
 *      flow: if the recipient already has an account, Sign In path
 *      with the token preserved in the URL; if not, Sign Up path with
 *      the token + the pinned email pre-filled.
 *
 * The token survives across the auth handshake via the URL (?invite=
 * query param on /signup and /login). The signup/login forms call a
 * server route to redeem it once auth succeeds. Cookies were considered
 * but URL-bound state plays better with the existing Supabase magic-link
 * flow + is debuggable in a sealed incognito session.
 *
 * Public route — added to PUBLIC_PATH_PREFIXES in middleware.ts so
 * unauthed recipients can actually see it.
 */

import Link from "next/link";
import { createHash } from "node:crypto";
import { getServiceSupabase, getSessionUser } from "@/lib/supabase-server";
import { OasisLogo } from "@/components/brand/OasisLogo";
import { AlertCircle, ArrowRight, CheckCircle2, Mail, Shield } from "lucide-react";
import { InviteRedeemForSignedInUser } from "./InviteRedeemForSignedInUser";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Preview = {
  tenant_id: string;
  tenant_name: string;
  team_role: string;
  expires_at: string;
  email_pinned: string | null;
};

const ROLE_LABEL: Record<string, string> = {
  admin: "Admin",
  loan_officer: "Loan Officer",
  processor: "Processor",
  read_only: "Read-Only Viewer",
  member: "Member",
  owner: "Owner",
};

function hashToken(raw: string): string {
  return createHash("sha256").update(raw).digest("hex");
}

async function loadPreview(rawToken: string): Promise<Preview | null> {
  if (!rawToken || rawToken.length < 16) return null;
  try {
    const db = getServiceSupabase();
    const { data, error } = await db.rpc("preview_tenant_invite", {
      p_token_hash: hashToken(rawToken),
    });
    if (error || !data) return null;
    return data as Preview;
  } catch {
    return null;
  }
}

export default async function InviteLanding({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const [preview, user] = await Promise.all([loadPreview(token), getSessionUser()]);

  return (
    <div className="min-h-screen bg-bg-deep flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-md space-y-4">
        <div className="flex justify-center mb-6">
          <OasisLogo />
        </div>

        {!preview ? (
          <InvalidCard />
        ) : user ? (
          // Already signed in — show a one-click redeem CTA (client component
          // handles the POST + routing). Saves the round-trip of forcing
          // them through /login when they're already there.
          <InviteRedeemForSignedInUser
            token={token}
            tenantName={preview.tenant_name}
            roleLabel={ROLE_LABEL[preview.team_role] || preview.team_role}
            email={user.email || ""}
          />
        ) : (
          <ValidCard token={token} preview={preview} />
        )}

        {!user && (
          <div className="text-center text-[11px] text-fg-dim mt-6">
            Already have an account?{" "}
            <Link
              href={`/login?invite=${encodeURIComponent(token)}`}
              className="text-accent hover:text-accent/80 underline underline-offset-2"
            >
              Sign in
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}

function InvalidCard() {
  return (
    <div className="rounded-2xl border border-amber-500/40 bg-amber-500/5 p-6">
      <div className="flex items-start gap-3">
        <AlertCircle className="w-6 h-6 text-amber-400 shrink-0 mt-0.5" />
        <div className="space-y-2">
          <h1 className="text-lg font-bold text-fg">This invite isn&apos;t active</h1>
          <p className="text-sm text-fg-muted leading-relaxed">
            The link you used has expired, been revoked, or was already redeemed. Ask whoever sent it
            to generate a fresh one — invites are single-use and good for 7 days by default.
          </p>
        </div>
      </div>
    </div>
  );
}

function ValidCard({ token, preview }: { token: string; preview: Preview }) {
  const roleLabel = ROLE_LABEL[preview.team_role] || preview.team_role;
  const expiresMs = Date.parse(preview.expires_at);
  const daysLeft = Number.isNaN(expiresMs)
    ? null
    : Math.max(0, Math.ceil((expiresMs - Date.now()) / (24 * 60 * 60 * 1000)));

  return (
    <div className="rounded-2xl border border-accent/40 bg-accent/5 p-6 space-y-5">
      <div className="flex items-center gap-3">
        <div className="rounded-full bg-accent/15 border border-accent/30 p-2">
          <CheckCircle2 className="w-5 h-5 text-accent" />
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wider font-bold text-fg-dim">
            You&apos;re invited to join
          </div>
          <h1 className="text-xl font-bold text-fg leading-tight">{preview.tenant_name}</h1>
        </div>
      </div>

      <ul className="space-y-2 text-sm">
        <li className="flex items-center gap-2 text-fg-muted">
          <Shield className="w-4 h-4 text-fg-dim shrink-0" />
          Role: <span className="font-semibold text-fg">{roleLabel}</span>
        </li>
        {preview.email_pinned && (
          <li className="flex items-center gap-2 text-fg-muted">
            <Mail className="w-4 h-4 text-fg-dim shrink-0" />
            Pinned to: <span className="font-mono text-fg">{preview.email_pinned}</span>
          </li>
        )}
        {daysLeft !== null && (
          <li className="text-[11px] text-fg-dim ml-6">
            Expires in {daysLeft} day{daysLeft === 1 ? "" : "s"}
          </li>
        )}
      </ul>

      <Link
        href={
          preview.email_pinned
            ? `/signup?invite=${encodeURIComponent(token)}&email=${encodeURIComponent(preview.email_pinned)}`
            : `/signup?invite=${encodeURIComponent(token)}`
        }
        className="block w-full text-center rounded-lg bg-accent text-bg-deep font-bold py-2.5 text-sm hover:bg-accent/90 transition-colors"
      >
        Continue → Create account
        <ArrowRight className="w-4 h-4 inline-block ml-1.5 align-text-bottom" />
      </Link>

      <p className="text-[11px] text-fg-dim leading-relaxed">
        By accepting, you&apos;ll join {preview.tenant_name} with {roleLabel} permissions. You can leave
        the workspace at any time from your profile settings.
      </p>
    </div>
  );
}
