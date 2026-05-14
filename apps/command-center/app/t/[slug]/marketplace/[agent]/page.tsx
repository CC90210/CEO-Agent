import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Sparkles } from "lucide-react";
import { Card, PageHeader, Tag } from "@/components/Card";
import { AgentSubscriptionPanel } from "@/components/marketplace/AgentSubscriptionPanel";
import { getAgentBySlug } from "@/lib/agents/loader";
import { CATEGORY_LABELS } from "@/lib/agents/library";
import { getManifest, manifestExists } from "@/lib/manifest/loader";
import { getManifestRow } from "@/lib/manifest/persistence";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export default async function MarketplaceDetailPage({
  params,
}: {
  params: Promise<{ slug: string; agent: string }>;
}) {
  const { slug, agent } = await params;
  const normalised = slug.toLowerCase();
  if (!(await manifestExists(normalised))) notFound();

  const user = await getSessionUser();
  const service = getServiceSupabase();
  const profileRes = user
    ? await service
        .from("user_profiles")
        .select("tenant_id, team_role, is_owner")
        .eq("auth_user_id", user.id)
        .maybeSingle()
    : { data: null };
  const profile = profileRes.data as
    | { tenant_id: string | null; team_role: string; is_owner: boolean }
    | null;
  const tenantId = profile?.tenant_id || null;

  const agentDef = await getAgentBySlug(agent, tenantId);
  if (!agentDef) notFound();

  const manifest = await getManifest(normalised);
  const row = await getManifestRow(normalised).catch(() => null);
  const version = row?.version ?? 0;

  const binding = manifest.agents.find((a) => a.slug === agentDef.slug);
  const isAdmin =
    !!profile && (profile.is_owner || profile.team_role === "admin" || profile.team_role === "owner");

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title={agentDef.name}
        subtitle={CATEGORY_LABELS[agentDef.category]}
        action={
          <Link
            href={`/t/${normalised}/marketplace`}
            className="btn-secondary inline-flex items-center gap-2 !px-3 !py-1.5 text-xs"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Marketplace
          </Link>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-4">
          <Card>
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-accent/30 bg-accent/10 text-accent">
                <Sparkles className="h-6 w-6" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold text-lg text-fg">{agentDef.name}</span>
                  {agentDef.is_oasis_managed && <Tag tone="accent">platform</Tag>}
                  {!agentDef.is_public && <Tag tone="neutral">private</Tag>}
                  {binding?.enabled && <Tag tone="engaged">enabled</Tag>}
                </div>
                <p className="mt-3 text-sm text-fg-muted leading-relaxed">
                  {agentDef.description || agentDef.short_description}
                </p>
              </div>
            </div>
          </Card>

          <Card title="Base prompt" subtitle="The system prompt this agent uses by default.">
            <pre className="whitespace-pre-wrap break-words rounded-xl border border-bg-border bg-bg-deep/60 p-4 text-xs font-mono text-fg-muted leading-relaxed max-h-72 overflow-y-auto">
{agentDef.base_prompt}
            </pre>
          </Card>

          {(agentDef.required_tools.length > 0 || agentDef.suggested_model) && (
            <Card>
              <div className="grid gap-3 sm:grid-cols-2">
                {agentDef.suggested_model && (
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.16em] text-fg-dim font-bold">
                      Suggested model
                    </div>
                    <div className="mt-1 text-sm font-mono text-fg">{agentDef.suggested_model}</div>
                  </div>
                )}
                {agentDef.required_tools.length > 0 && (
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.16em] text-fg-dim font-bold">
                      Required tools
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {agentDef.required_tools.map((t) => (
                        <span
                          key={t}
                          className="rounded-md border border-bg-border bg-bg-elev/60 px-2 py-0.5 text-[10px] font-mono text-fg-muted"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Card>
          )}
        </div>

        <AgentSubscriptionPanel
          tenantSlug={normalised}
          agentSlug={agentDef.slug}
          defaultDisplayName={agentDef.name}
          binding={binding ? {
            display_name: binding.display_name,
            enabled: binding.enabled,
            primary: !!binding.primary,
            prompt_overlay: binding.prompt_overlay,
          } : null}
          manifestVersion={version}
          canEdit={isAdmin}
          canBuildCustom={!agentDef.is_oasis_managed && agentDef.tenant_id === tenantId}
        />
      </div>
    </div>
  );
}
