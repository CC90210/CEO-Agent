import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Settings } from "lucide-react";
import { Card, PageHeader, Tag } from "@/components/Card";
import { AgentChat } from "@/components/agents/AgentChat";
import { getAgentBySlug } from "@/lib/agents/loader";
import { CATEGORY_LABELS } from "@/lib/agents/library";
import { getManifest, manifestExists } from "@/lib/manifest/loader";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export default async function TenantAgentChatPage({
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
        .select("tenant_id")
        .eq("auth_user_id", user.id)
        .maybeSingle()
    : { data: null };
  const tenantId = (profileRes.data as { tenant_id: string | null } | null)?.tenant_id || null;

  const agentDef = await getAgentBySlug(agent, tenantId);
  if (!agentDef) notFound();
  if (!agentDef.is_public && agentDef.tenant_id !== tenantId) notFound();

  const manifest = await getManifest(normalised);
  const binding = manifest.agents.find((a) => a.slug === agentDef.slug);
  const displayName = binding?.display_name || agentDef.name;

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title={displayName}
        subtitle={CATEGORY_LABELS[agentDef.category]}
        action={
          <div className="flex items-center gap-2">
            {binding?.enabled ? (
              binding.primary ? (
                <Tag tone="engaged">primary</Tag>
              ) : (
                <Tag tone="engaged">enabled</Tag>
              )
            ) : (
              <Tag tone="warm">not subscribed</Tag>
            )}
            <Link
              href={`/t/${normalised}/marketplace/${agentDef.slug}`}
              className="btn-secondary inline-flex items-center gap-2 !px-3 !py-1.5 text-xs"
            >
              <Settings className="h-3.5 w-3.5" />
              Configure
            </Link>
            <Link
              href={`/t/${normalised}`}
              className="btn-secondary inline-flex items-center gap-2 !px-3 !py-1.5 text-xs"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Tenant
            </Link>
          </div>
        }
      />

      {!binding?.enabled && (
        <Card>
          <div className="text-sm text-fg-muted leading-relaxed">
            This agent isn&apos;t enabled on {manifest.brand.name} yet. You can chat with it right
            now to see how it sounds — but for it to show in the sidebar and remember preferences,{" "}
            <Link
              href={`/t/${normalised}/marketplace/${agentDef.slug}`}
              className="text-accent hover:underline"
            >
              enable it in the marketplace
            </Link>
            .
          </div>
        </Card>
      )}

      <AgentChat
        tenantSlug={normalised}
        agentSlug={agentDef.slug}
        agentName={displayName}
        agentSubtitle={CATEGORY_LABELS[agentDef.category]}
        greeting={agentDef.short_description}
      />
    </div>
  );
}
