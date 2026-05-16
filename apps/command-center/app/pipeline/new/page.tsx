/**
 * /pipeline/new — create a new OASIS lead.
 *
 * Reuses ManifestRecordForm against OASIS_SEED.lead. The "+ New lead"
 * CTA on the /pipeline kanban deep-links here. On submit the form
 * redirects back to /pipeline.
 */

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { PageHeader, Card } from "@/components/Card";
import { ManifestRecordForm } from "@/components/manifest/ManifestRecordForm";
import { OASIS_SEED } from "@/lib/manifest/seeds";
import { getActiveProfile } from "@/lib/queries";
import { safe } from "@/lib/api-helpers";

export const dynamic = "force-dynamic";

export default async function PipelineNewLeadPage() {
  const leadEntity = OASIS_SEED.data_model?.find((e) => e.name === "lead");
  const profile = await safe("pipeline.new.profile", getActiveProfile(), null);
  const tenantId = profile?.tenant_id || null;

  if (!leadEntity) {
    return (
      <div className="space-y-4 animate-fade-in">
        <PageHeader title="New lead" subtitle="Lead entity not defined" />
        <Card>
          <div className="text-sm text-fg-muted">
            OASIS_SEED has no `lead` entity. Edit lib/manifest/seeds.ts.
          </div>
        </Card>
      </div>
    );
  }
  if (!tenantId) {
    return (
      <div className="space-y-4 animate-fade-in">
        <PageHeader title="New lead" subtitle="Sign in to add a lead." />
      </div>
    );
  }

  return (
    <div className="space-y-4 animate-fade-in">
      <PageHeader
        title="New lead"
        subtitle="Drop the contact into the pipeline. Defaults to the 'new' stage."
        action={
          <Link
            href="/pipeline"
            className="btn-secondary inline-flex items-center gap-2 !px-3 !py-1.5 text-xs"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to pipeline
          </Link>
        }
      />
      <ManifestRecordForm
        tenantSlug="oasis"
        entity={leadEntity}
        backPath="pipeline"
        backHref="/pipeline"
      />
    </div>
  );
}
