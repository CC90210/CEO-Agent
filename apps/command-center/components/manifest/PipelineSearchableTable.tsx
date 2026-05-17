"use client";

/**
 * PipelineSearchableTable — the records-list under each pipeline page
 * (Lead Pipeline + Opportunity Pipeline) with a live search box.
 *
 * Salesforce shows a quick-filter "Search this list" input above every
 * pipeline list view. Adon's team uses it to jump straight to a
 * specific deal by company name, contact, phone, or email. We do the
 * same — typed query filters the visible rows in-memory across every
 * column the entity exposes, plus the linked-record id.
 *
 * Why no external library: fuse.js / flexsearch are overkill for a
 * 500-row pipeline. A plain lowercase substring match across all
 * stringifiable values handles "by name", "by phone digits",
 * "by domain", and partial company-name matches cleanly. Adding a
 * fuzzy-distance algorithm here would surface "almost-matches" the
 * operator didn't ask for — a tighter exact-substring search is what
 * "find lead by name" actually means in funding-broker workflow.
 *
 * The search input lives in the same row as the "+ New <entity>" CTA,
 * matching the screenshot CC referenced. Filter resets on stage
 * change because the URL stage param triggers a fresh server render
 * which re-instantiates this component with new rows.
 */

import { useMemo, useState } from "react";
import Link from "next/link";
import type { StageMeta } from "@/lib/sunbiz-stage-meta";
import { formatPipelineCell, type PipelineColumn } from "@/lib/pipeline-display";

type Row = { id: string; data: Record<string, unknown> };

type Props = {
  slug: string;
  entityName: string;
  entityLabel: string;
  stageField: string;
  rows: Row[];
  columns: PipelineColumn[];
  /** Resolves the stage chip's color from the row's stage value. */
  findStage: (key: string) => StageMeta | undefined;
  /** href base for record-detail links + "+ New" CTA */
  linkBase: string;
  /** Stage filter label rendered in the empty-state message. */
  activeStageLabel: string;
};

/**
 * Build a flat searchable haystack for one row — every stringifiable
 * value lowercased + joined. We index `id`, every column value, and the
 * raw stage so a query like "funded" matches by stage as well as name.
 * Phone digits get a digits-only twin so "5551234" matches "(555) 123-4..."
 */
function rowHaystack(row: Row, columns: PipelineColumn[], stageField: string): string {
  const parts: string[] = [row.id];
  for (const c of columns) {
    const v = row.data[c.key];
    if (v == null) continue;
    parts.push(String(v));
  }
  const stage = row.data[stageField];
  if (stage != null) parts.push(String(stage));
  // Digits-only twin for phone matching: a user typing "5551234"
  // should match phones written as "(555) 123-4567" or "555.123.4567"
  // without the operator needing to know the stored format.
  const phone = row.data.phone;
  if (typeof phone === "string") parts.push(phone.replace(/\D/g, ""));
  return parts.join(" ").toLowerCase();
}

export function PipelineSearchableTable({
  slug: _slug,
  entityName,
  entityLabel,
  stageField,
  rows,
  columns,
  findStage,
  linkBase,
  activeStageLabel,
}: Props) {
  const [query, setQuery] = useState("");

  const haystacks = useMemo(
    () => rows.map((r) => rowHaystack(r, columns, stageField)),
    [rows, columns, stageField],
  );

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    // Match digits-only twin for numeric queries — typing "5551234"
    // should match the same rows as typing "5551234" against the phone
    // column's raw value.
    const qDigits = q.replace(/\D/g, "");
    return rows.filter((_, i) => {
      const h = haystacks[i];
      if (h.includes(q)) return true;
      if (qDigits.length >= 4 && h.includes(qDigits)) return true;
      return false;
    });
  }, [query, rows, haystacks]);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Search ${entityLabel.toLowerCase()}s by name, email, phone…`}
            className="w-full rounded-md border border-bg-border bg-bg-deep px-3 py-1.5 text-sm text-fg placeholder:text-fg-dim focus:border-accent focus:outline-none"
            aria-label={`Search ${entityLabel.toLowerCase()}s`}
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-fg-dim hover:text-fg text-xs"
              aria-label="Clear search"
            >
              ×
            </button>
          )}
        </div>
        <Link
          href={`${linkBase}/new`}
          className="shrink-0 inline-flex items-center gap-1 rounded-md bg-accent/15 hover:bg-accent/25 border border-accent/40 text-accent px-3 py-1.5 text-[12px] font-semibold whitespace-nowrap"
        >
          + New {entityLabel.toLowerCase()}
        </Link>
      </div>

      {query && (
        <div className="text-[11px] text-fg-dim">
          {visible.length === 0
            ? `No ${entityLabel.toLowerCase()}s match "${query}"`
            : `${visible.length} match${visible.length === 1 ? "" : "es"} for "${query}"`}
        </div>
      )}

      {visible.length === 0 && !query && (
        <div className="rounded-2xl border border-bg-border bg-bg-deep/40 p-6 text-center text-sm text-fg-dim italic">
          No records in {activeStageLabel}.
        </div>
      )}

      {visible.length > 0 && (
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
              {visible.map((r) => {
                const stage = String(r.data[stageField] || "");
                const stageMeta = findStage(stage);
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
      )}
    </div>
  );
}
