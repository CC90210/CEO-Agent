import { Card } from "@/components/Card";
import type { ManifestPageDef } from "@/lib/manifest/schema";

type Props = {
  page: ManifestPageDef;
};

/**
 * Inline-markdown page — for manifest entries with kind="markdown".
 * Content comes from `page.config.body` (a markdown string). Phase 5.2
 * adds a loader that pulls markdown from `docs/playbooks/<path>.md` so
 * operators can keep their playbook in the repo and the page just
 * references it by slug.
 *
 * Renders as plain prose for now (no markdown parser) because the only
 * v1 caller is the manifest editor surfacing static guidance. We add a
 * real parser when the first tenant asks for headers/lists/links.
 */
export function ManifestMarkdown({ page }: Props) {
  const body =
    (typeof page.config?.body === "string" && page.config.body) ||
    "_This page has no markdown body yet. Add `config.body` via the AI editor._";

  return (
    <Card title={page.label}>
      <div className="prose prose-invert max-w-none text-fg-muted leading-relaxed whitespace-pre-wrap">
        {body}
      </div>
    </Card>
  );
}
