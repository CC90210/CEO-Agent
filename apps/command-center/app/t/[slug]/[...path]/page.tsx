import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Construction } from "lucide-react";
import { Card, PageHeader, Tag } from "@/components/Card";
import { getManifest, manifestExists } from "@/lib/manifest/loader";

export const dynamic = "force-dynamic";

/**
 * Catch-all renderer for `/t/<slug>/<...path>`.
 *
 * Phase 1 scope: validates the tenant slug and acknowledges the requested
 * page from the manifest, but doesn't yet render the page kind (table /
 * kanban / dashboard / form). Phase 2 swaps the placeholder for a
 * manifest-kind dispatcher that consumes `pages[]` + `data_model[]` and
 * delegates to <ManifestTable />, <ManifestKanban />, <ManifestForm />,
 * <ManifestDashboard />.
 *
 * Why this exists in Phase 1: routing, slug isolation, and the URL contract
 * land NOW so any consumer (links from the AI editor, marketplace surfaces,
 * onboarding wizard) can rely on the shape today. Behaviour follows in 2.
 */
export default async function TenantCatchAllPage({
  params,
}: {
  params: Promise<{ slug: string; path: string[] }>;
}) {
  const { slug, path } = await params;
  const normalised = slug.toLowerCase();
  if (!(await manifestExists(normalised))) notFound();

  const manifest = await getManifest(normalised);
  const subPath = path.join("/");
  const pageDef = manifest.pages?.find((p) => p.path === subPath);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title={pageDef?.label || subPath || "Untitled page"}
        subtitle={`${manifest.brand.name} · ${pageDef?.kind || "not yet defined"}`}
        action={
          <Link
            href={`/t/${normalised}`}
            className="btn-secondary inline-flex items-center gap-2 !px-3 !py-1.5 text-xs"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to tenant
          </Link>
        }
      />

      <Card>
        <div className="flex items-start gap-4">
          <div className="mt-1 flex h-10 w-10 items-center justify-center rounded-xl border border-accent/30 bg-accent/10 text-accent">
            <Construction className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-fg font-bold">Manifest renderer — Phase 2</div>
            <p className="mt-1 text-sm text-fg-muted leading-relaxed">
              The route <span className="font-mono text-accent">/t/{normalised}/{subPath}</span> is reserved.
              The Phase 2 renderer will dispatch on{" "}
              <span className="font-mono text-fg">{pageDef ? `kind="${pageDef.kind}"` : "the manifest page definition"}</span>{" "}
              and render the corresponding primitive component.
            </p>
            {pageDef ? (
              <div className="mt-4 grid gap-2 text-xs text-fg-dim">
                <div>
                  <Tag tone="accent">page</Tag>
                  <span className="ml-2 font-mono text-fg">{pageDef.path}</span>
                </div>
                <div>
                  <Tag tone="neutral">kind</Tag>
                  <span className="ml-2 font-mono text-fg">{pageDef.kind}</span>
                </div>
                {pageDef.entity && (
                  <div>
                    <Tag tone="neutral">entity</Tag>
                    <span className="ml-2 font-mono text-fg">{pageDef.entity}</span>
                  </div>
                )}
              </div>
            ) : (
              <p className="mt-3 text-xs text-fg-dim">
                No <span className="font-mono">pages[]</span> entry matches <span className="font-mono">{subPath}</span> in this manifest yet.
                The AI editor (Phase 2) is where you&apos;ll add it.
              </p>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
