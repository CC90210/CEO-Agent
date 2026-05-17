/**
 * PipelineRecordTable — the table that renders below a chevron bar on
 * the Lead Pipeline and Opportunity Pipeline pages.
 *
 * Pure table. Search lives ABOVE it as the universal PageSearchBar
 * client component, which writes ?q= to the URL; the server-side
 * filter runs through `filterRowsByQuery` before we get here. This
 * keeps the search mechanism identical across every list surface
 * (chevron pipeline pages + Kanban entity pages + flat table pages):
 * one URL state, one matcher, one debounced input.
 *
 * (Pre-2026-05-17 this component carried its own local search input
 * with useState. That split search behaviour into two systems —
 * shareable-URL on most pages, ephemeral-client-state on these two.
 * Consolidated; this is now a server-friendly render-only component.)
 */

import Link from "next/link";
import type { StageMeta } from "@/lib/sunbiz-stage-meta";
import { formatPipelineCell, type PipelineColumn } from "@/lib/pipeline-display";

type Row = { id: string; data: Record<string, unknown> };

type Props = {
  entityLabel: string;
  stageField: string;
  rows: Row[];
  columns: PipelineColumn[];
  /**
   * Pre-resolved map of stage key -> StageMeta. Plain object so it
   * serializes across the server/client boundary cleanly.
   */
  stageMap: Record<string, StageMeta>;
  /** href base for record-detail links. */
  linkBase: string;
  /** Stage filter label rendered in the empty-state message. */
  activeStageLabel: string;
  /** Active search query (for the empty-state copy only). */
  query?: string | null;
};

export function PipelineSearchableTable({
  entityLabel,
  stageField,
  rows,
  columns,
  stageMap,
  linkBase,
  activeStageLabel,
  query,
}: Props) {
  if (rows.length === 0) {
    const hasQuery = !!(query && query.trim());
    return (
      <div className="rounded-2xl border border-bg-border bg-bg-deep/40 p-6 text-center text-sm text-fg-dim italic">
        {hasQuery
          ? `No ${entityLabel.toLowerCase()}s match "${query}" in ${activeStageLabel}.`
          : `No records in ${activeStageLabel}.`}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-2xl border border-bg-border bg-bg-deep/30">
      <table className="w-full text-[12.5px]">
        <thead>
          <tr className="text-left text-fg-dim border-b border-bg-border">
            {columns.map((c) => (
              <th key={c.key} className="px-3 py-2 font-medium">{c.label}</th>
            ))}
            <th className="px-3 py-2 font-medium">Stage</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const stage = String(r.data[stageField] || "");
            const stageMeta = stageMap[stage];
            return (
              <tr key={r.id} className="border-b border-bg-border/40 last:border-b-0 hover:bg-bg-elev/30">
                {columns.map((c, idx) => (
                  <td key={c.key} className={`px-3 py-2 ${idx === 0 ? "font-medium text-fg" : "text-fg-muted"}`}>
                    {idx === 0 ? (
                      <Link href={`${linkBase}/${r.id}`} className="hover:underline">
                        {formatPipelineCell(r.data[c.key], c.key)}
                      </Link>
                    ) : (
                      formatPipelineCell(r.data[c.key], c.key)
                    )}
                  </td>
                ))}
                <td className="px-3 py-2">
                  {stageMeta ? (
                    <span
                      className="inline-block px-2 py-0.5 rounded text-[11px] font-semibold"
                      style={{ background: stageMeta.bg, color: stageMeta.fg }}
                    >
                      {stageMeta.label}
                    </span>
                  ) : (
                    <span className="text-fg-dim font-mono">{stage || "—"}</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
