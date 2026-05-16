/**
 * /pipeline/[id] — lead detail page on the empire side.
 *
 * Mirrors the record-detail logic in app/t/[slug]/[...path]/page.tsx but
 * routed under /pipeline so the OASIS CRM feels like one continuous
 * surface instead of bouncing the operator into the tenant route. Reuses
 * ManifestRecordForm in edit mode against the OASIS_SEED lead entity —
 * every field on the record is visible + editable on one screen with no
 * separate detail primitive.
 */

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { notFound } from "next/navigation";
import { PageHeader, Card } from "@/components/Card";
import { ManifestRecordForm } from "@/components/manifest/ManifestRecordForm";
import { OASIS_SEED } from "@/lib/manifest/seeds";
import { getRecord } from "@/lib/manifest/data";
import { getActiveProfile } from "@/lib/queries";
import { safe } from "@/lib/api-helpers";

export const dynamic = "force-dynamic";

export default async function PipelineLeadDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const leadEntity = OASIS_SEED.data_model?.find((e) => e.name === "lead");
  if (!leadEntity) notFound();

  const profile = await safe("pipeline.detail.profile", getActiveProfile(), null);
  const tenantId = profile?.tenant_id || null;
  if (!tenantId) {
    return (
      <div className="space-y-4 animate-fade-in">
        <PageHeader title="Pipeline" subtitle="Sign in to see leads." />
      </div>
    );
  }

  const record = await getRecord({
    tenant_id: tenantId,
    entity: "lead",
    id,
  }).catch(() => null);

  if (!record) {
    return (
      <div className="space-y-4 animate-fade-in">
        <PageHeader
          title="Lead not found"
          subtitle={`No lead with id ${id.slice(0, 8)}…`}
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
        <Card>
          <div className="text-sm text-fg-muted">
            The lead may have been deleted, or the link is stale. Use the
            pipeline kanban to find a live record.
          </div>
        </Card>
      </div>
    );
  }

  const title =
    (typeof record.data.name === "string" && record.data.name) ||
    (typeof record.data.company === "string" && record.data.company) ||
    `Lead ${id.slice(0, 8)}`;

  return (
    <div className="space-y-4 animate-fade-in">
      <PageHeader
        title={title}
        subtitle={`Lead · ${leadEntity.fields.length} fields`}
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
        initial={record.data}
        editId={id}
      />
    </div>
  );
}
