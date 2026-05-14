import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { PageHeader, Tag } from "@/components/Card";
import { CustomAgentBuilder } from "@/components/marketplace/CustomAgentBuilder";
import { getAgentBySlug } from "@/lib/agents/loader";
import { manifestExists } from "@/lib/manifest/loader";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export default async function MarketplaceBuildPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ edit?: string }>;
}) {
  const { slug } = await params;
  const { edit } = await searchParams;
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
  const isAdmin =
    !!profile && (profile.is_owner || profile.team_role === "admin" || profile.team_role === "owner");

  let editing: Awaited<ReturnType<typeof getAgentBySlug>> = null;
  if (edit && profile?.tenant_id) {
    const existing = await getAgentBySlug(edit, profile.tenant_id);
    if (existing && !existing.is_oasis_managed && existing.tenant_id === profile.tenant_id) {
      editing = existing;
    }
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title={editing ? `Edit · ${editing.name}` : "Build a custom agent"}
        subtitle={
          editing
            ? "Update the underlying agent definition. Tenant personalizations are kept separately on the manifest."
            : "Describe what the agent should do. The AI drafts the system prompt, suggested tools, and a model recommendation. You review + edit before saving."
        }
        action={
          <div className="flex items-center gap-2">
            {editing && <Tag tone="neutral">editing</Tag>}
            <Link
              href={`/t/${normalised}/marketplace`}
              className="btn-secondary inline-flex items-center gap-2 !px-3 !py-1.5 text-xs"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Marketplace
            </Link>
          </div>
        }
      />

      {!isAdmin ? (
        <div className="rounded-2xl border border-amber-300/30 bg-amber-300/10 p-5 text-sm text-amber-100 leading-relaxed">
          Building agents requires an admin or owner role on this tenant.
        </div>
      ) : (
        <CustomAgentBuilder
          tenantSlug={normalised}
          editing={
            editing
              ? {
                  slug: editing.slug,
                  name: editing.name,
                  category: editing.category,
                  short_description: editing.short_description,
                  description: editing.description || "",
                  base_prompt: editing.base_prompt,
                  required_tools: editing.required_tools,
                  suggested_model: editing.suggested_model || "",
                  is_public: editing.is_public,
                }
              : null
          }
        />
      )}
    </div>
  );
}
