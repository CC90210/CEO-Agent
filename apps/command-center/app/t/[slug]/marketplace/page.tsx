import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowRight, Plus, Sparkles } from "lucide-react";
import { Card, PageHeader, Tag } from "@/components/Card";
import { listAgents } from "@/lib/agents/loader";
import { CATEGORY_LABELS, type AgentCategory } from "@/lib/agents/library";
import { getManifest, manifestExists } from "@/lib/manifest/loader";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Marketplace browse — `/t/<slug>/marketplace[?category=<cat>]`.
 *
 * Renders the agent library as a grid. Enabled agents (those already in the
 * tenant manifest) get a "Enabled" badge so the operator can see at a
 * glance what's already wired up; detail-page Enable / Disable wiring lives
 * one click away in `[agent-slug]/page.tsx`.
 */
export default async function MarketplaceBrowsePage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ category?: string }>;
}) {
  const { slug } = await params;
  const { category } = await searchParams;
  const normalised = slug.toLowerCase();
  if (!(await manifestExists(normalised))) notFound();

  const user = await getSessionUser();
  const manifest = await getManifest(normalised);

  const service = getServiceSupabase();
  const profileRes = user
    ? await service
        .from("user_profiles")
        .select("tenant_id")
        .eq("auth_user_id", user.id)
        .maybeSingle()
    : { data: null };
  const tenantId = (profileRes.data as { tenant_id: string | null } | null)?.tenant_id || null;

  const filterCategory =
    category && category in CATEGORY_LABELS ? (category as AgentCategory) : undefined;
  const agents = await listAgents({ category: filterCategory, tenant_id: tenantId });

  const enabledSlugs = new Set(
    manifest.agents.filter((a) => a.enabled).map((a) => a.slug.toLowerCase())
  );

  // Category chip list — order them so platform categories surface first.
  const CATEGORY_ORDER: AgentCategory[] = [
    "ceo", "cfo", "cmo", "coo", "operations",
    "sales", "support", "research", "content",
    "engineering", "finance", "legal",
    "industry_real_estate", "industry_funding", "industry_ecommerce", "industry_agency",
    "custom",
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Agent Marketplace"
        subtitle={`Browse, enable, and personalize agents for ${manifest.brand.name}.`}
        action={
          <Link
            href={`/t/${normalised}/marketplace/build`}
            className="btn-send inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
          >
            <Plus className="h-3.5 w-3.5" />
            Build custom
          </Link>
        }
      />

      <nav className="flex flex-wrap gap-2">
        <Link
          href={`/t/${normalised}/marketplace`}
          className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-all ${
            !filterCategory
              ? "bg-accent text-bg-deep"
              : "border border-bg-border bg-bg-elev/50 text-fg-muted hover:border-accent/40 hover:bg-bg-elev/80"
          }`}
        >
          All
        </Link>
        {CATEGORY_ORDER.map((cat) => (
          <Link
            key={cat}
            href={`/t/${normalised}/marketplace?category=${cat}`}
            className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-all ${
              filterCategory === cat
                ? "bg-accent text-bg-deep"
                : "border border-bg-border bg-bg-elev/50 text-fg-muted hover:border-accent/40 hover:bg-bg-elev/80"
            }`}
          >
            {CATEGORY_LABELS[cat]}
          </Link>
        ))}
      </nav>

      {agents.length === 0 ? (
        <Card>
          <div className="text-sm text-fg-muted text-center py-8">
            No agents in this category yet.{" "}
            <Link href={`/t/${normalised}/marketplace/build`} className="text-accent hover:underline">
              Build one
            </Link>
            .
          </div>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {agents.map((agent) => {
            const isEnabled = enabledSlugs.has(agent.slug);
            return (
              <Link
                key={agent.slug}
                href={`/t/${normalised}/marketplace/${agent.slug}`}
                className="group block"
              >
                <Card>
                  <div className="flex items-start gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-accent/25 bg-accent/10 text-accent group-hover:bg-accent group-hover:text-bg transition-all">
                      <Sparkles className="h-5 w-5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-bold text-fg group-hover:text-accent transition-colors">
                          {agent.name}
                        </span>
                        {agent.is_oasis_managed && <Tag tone="accent">platform</Tag>}
                        {!agent.is_public && <Tag tone="neutral">private</Tag>}
                        {isEnabled && <Tag tone="engaged">enabled</Tag>}
                      </div>
                      <div className="text-[10px] uppercase tracking-[0.16em] text-fg-dim font-bold mt-1">
                        {CATEGORY_LABELS[agent.category]}
                      </div>
                      <p className="text-sm text-fg-muted mt-2 leading-relaxed line-clamp-3">
                        {agent.short_description}
                      </p>
                      <div className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-accent">
                        {isEnabled ? "Manage" : "Enable for this tenant"}{" "}
                        <ArrowRight className="h-3 w-3" />
                      </div>
                    </div>
                  </div>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
