import { Card, EmptyState, Tag } from "@/components/Card";
import { QuickActionsGrid } from "@/components/reasoning/QuickActionsGrid";
import { quickActionsFor } from "@/lib/quick-actions";
import type { TenantManifest } from "@/lib/manifest/schema";

/**
 * Manifest-aware Reasoning surface for /t/<slug>/reasoning. Filters the
 * QUICK_ACTIONS catalog by the tenant's enabled agents (manifest.agents
 * where enabled=true) and feeds the existing QuickActionsGrid. Mirrors the
 * top-level /reasoning page's shape so an OASIS operator and a SunBiz
 * operator get the same UX inside their own tenant namespace.
 *
 * No client component needed — QuickActionsGrid is "use client" and handles
 * its own interactivity.
 */
export function ManifestReasoning({
  manifest,
  tenantSlug,
}: {
  manifest: TenantManifest;
  tenantSlug: string;
}) {
  const enabled = manifest.agents.filter((a) => a.enabled).map((a) => a.slug.toLowerCase());
  const actions = quickActionsFor(enabled);

  return (
    <Card
      title="Quick actions"
      subtitle="Each one drops a prompt into chat with the right agent already selected. Hit Enter to send."
      action={
        <Tag tone="accent">
          {actions.length} actions · {enabled.length} agents
        </Tag>
      }
    >
      {actions.length === 0 ? (
        <EmptyState
          message={
            enabled.length === 0
              ? `No agents enabled yet. Switch one on from Settings → Agents.`
              : `No quick actions for ${enabled.join(", ")} yet — they'll appear here as we add more.`
          }
        />
      ) : (
        <QuickActionsGrid actions={actions} />
      )}
    </Card>
  );
}
