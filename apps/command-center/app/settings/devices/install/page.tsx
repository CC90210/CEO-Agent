/**
 * /settings/devices/install — dedicated wizard page for the bridge install
 * flow. The same pairing flow lives inside DevicesEditor's "Install" button
 * on /settings, but deep-linking from "API key mode is great, but you want
 * full Claude Code? Install the bridge →" is much cleaner against its own
 * URL than against a modal-trigger button.
 *
 * Server-component shell — auth + headline copy. The actual pairing UX is
 * a client component (InstallBridgeWizard) so the polling, OS detection,
 * and clipboard interactions can run client-side.
 */

import Link from "next/link";
import { ArrowLeft, Cloud, Cpu } from "lucide-react";
import { PageHeader } from "@/components/Card";
import { getSessionUser } from "@/lib/supabase-server";
import { redirect } from "next/navigation";
import { InstallBridgeWizard } from "./InstallBridgeWizard";

export const dynamic = "force-dynamic";

export default async function BridgeInstallPage() {
  const user = await getSessionUser();
  if (!user) redirect("/login?next=/settings/devices/install");

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Install the local bridge"
        subtitle="Give your agents full Claude Code parity — file system, bash, every MCP — by pairing this machine to your tenant."
        action={
          <Link
            href="/settings#devices"
            className="text-xs text-fg-muted hover:text-fg inline-flex items-center gap-1"
          >
            <ArrowLeft className="w-3 h-3" /> Back to Settings
          </Link>
        }
      />

      {/* Side-by-side capability comparison so the operator sees exactly
          what installing the bridge unlocks vs. cloud-only mode. */}
      <div className="grid sm:grid-cols-2 gap-4">
        <div className="rounded-xl border border-bg-border bg-bg-elev/40 p-5">
          <div className="flex items-center gap-2 mb-2">
            <Cloud className="w-4 h-4 text-fg-muted" />
            <div className="text-xs font-bold uppercase tracking-wider text-fg-muted">
              Cloud only (API key)
            </div>
          </div>
          <div className="text-sm text-fg mb-2">What you have now</div>
          <ul className="text-xs text-fg-muted space-y-1.5 leading-relaxed">
            <li>• Native Anthropic tool_use loop</li>
            <li>• Records read / write / search / delete</li>
            <li>• http_get and http_post against public URLs</li>
            <li>• Integration status + lead lookup</li>
            <li className="text-fg-dim italic">
              No local file access, no shell, no MCPs
            </li>
          </ul>
        </div>
        <div className="rounded-xl border border-accent/30 bg-accent/5 p-5">
          <div className="flex items-center gap-2 mb-2">
            <Cpu className="w-4 h-4 text-accent" />
            <div className="text-xs font-bold uppercase tracking-wider text-accent">
              Local bridge (Claude Code CLI)
            </div>
          </div>
          <div className="text-sm text-fg mb-2">What the install unlocks</div>
          <ul className="text-xs text-fg-muted space-y-1.5 leading-relaxed">
            <li>• Read / Edit / Write / Bash / Glob / Grep on your repos</li>
            <li>• All Claude Code MCPs (Playwright, Supabase, Context7…)</li>
            <li>• Python scripts and scheduled cron jobs</li>
            <li>• Real SMS / email sends via your local .env.agents</li>
            <li className="text-accent">
              Uses your Claude Code subscription (no per-token API charges)
            </li>
          </ul>
        </div>
      </div>

      <InstallBridgeWizard />
    </div>
  );
}
