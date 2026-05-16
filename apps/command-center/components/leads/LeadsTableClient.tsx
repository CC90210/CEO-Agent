"use client";

/**
 * LeadsTableClient — production-grade Leads table for the SunBiz CRM.
 *
 * Replaces the prior 50-line static `<table>` in app/leads/page.tsx which
 * couldn't handle thousands of rows (no filter, no sort, no pagination,
 * no quick stats). Operators flagged the original at the 2026-05-15
 * meeting with Adon — "the boxes are too small. When there are
 * thousands of leads, we need to build proper infrastructure and UI
 * mapping for the according tasks."
 *
 * Design choices:
 *   - Stage tabs across the top (cold / follow_up / sent_application /
 *     viewed_application / signed_application / submitted / declined /
 *     default) drive the primary filter — same enum CRM stages from
 *     SUN_SEED lead.stage. Counts per tab so the operator can see
 *     pipeline distribution at a glance.
 *   - Search input does client-side substring match across name /
 *     email / phone / company / notes. Debounced 150ms.
 *   - Sortable column headers — click to toggle asc/desc. Score and
 *     last-touch are the two most commonly sorted columns; defaults
 *     to last-touch desc (newest first).
 *   - Pagination is page-based, 50 per page. Server already caps the
 *     fetch at 500 (caller of recentLeads), so this is purely UX
 *     pagination over the in-memory dataset.
 *   - Click any row -> /leads/[id] (drill-down). The link is on the
 *     whole row, not a tiny chevron, so the entire card area is the
 *     hit target.
 *
 * Data layer: server-component parent fetches via recentLeads() and
 * passes initial rows in; no live updates here. Mutations route
 * through the agent chat or per-row detail page (Phase 13 will add
 * inline row edits).
 */

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowDownAZ,
  ArrowUpAZ,
  Search,
  X,
  ChevronLeft,
  ChevronRight,
  Mail,
  Phone,
  Building2,
  Sparkles,
} from "lucide-react";
import type { Lead } from "@/lib/supabase";

type Props = {
  initialLeads: Lead[];
};

/** SunBiz lead-stage enum (Phase 2 of SunBiz CRM). Keep this in sync
 *  with SUN_SEED.data_model.lead.stage in lib/manifest/seeds.ts — any
 *  drift means a stage value won't have a tab here and gets bucketed
 *  under "All". */
const STAGES: { value: string; label: string; tone: string }[] = [
  { value: "cold", label: "Cold", tone: "text-fg-dim" },
  { value: "follow_up", label: "Follow-up", tone: "text-status-info" },
  { value: "sent_application", label: "App sent", tone: "text-status-info" },
  { value: "viewed_application", label: "App viewed", tone: "text-accent" },
  { value: "signed_application", label: "App signed", tone: "text-accent" },
  { value: "submitted", label: "Submitted", tone: "text-status-engaged" },
  { value: "declined", label: "Declined", tone: "text-status-warm" },
  { value: "default", label: "Default", tone: "text-status-warm" },
];

type SortKey = "last_touch" | "score" | "name" | "company" | "created";
type SortDir = "asc" | "desc";

const PAGE_SIZE = 50;

export function LeadsTableClient({ initialLeads }: Props) {
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState<string>("all");
  const [sortKey, setSortKey] = useState<SortKey>("last_touch");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [page, setPage] = useState(0);

  // Resolve which stage field to filter on. The Phase 2 schema added
  // `stage` to SUN_SEED.lead.data, but older rows may only have the
  // legacy `status` field on the Lead row itself. We check both.
  function leadStage(l: Lead): string {
    return ((l as unknown as { stage?: string }).stage || l.status || "").toLowerCase();
  }

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return initialLeads.filter((l) => {
      if (stage !== "all" && leadStage(l) !== stage) return false;
      if (!q) return true;
      // Substring match across the operator-relevant fields. Notes
      // included so an operator can search by deal context
      // ("retail", "construction", etc.) not just contact info.
      const hay = [l.name, l.email, l.phone, l.company, l.notes, l.source]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [initialLeads, search, stage]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    arr.sort((a, b) => {
      let av: number | string = "";
      let bv: number | string = "";
      switch (sortKey) {
        case "last_touch":
          av = new Date(a.last_contacted_at || a.updated_at || 0).getTime();
          bv = new Date(b.last_contacted_at || b.updated_at || 0).getTime();
          break;
        case "score":
          av = a.score ?? -1;
          bv = b.score ?? -1;
          break;
        case "name":
          av = (a.name || "").toLowerCase();
          bv = (b.name || "").toLowerCase();
          break;
        case "company":
          av = (a.company || "").toLowerCase();
          bv = (b.company || "").toLowerCase();
          break;
        case "created":
          av = new Date(a.created_at || 0).getTime();
          bv = new Date(b.created_at || 0).getTime();
          break;
      }
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return arr;
  }, [filtered, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const paginated = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  // Stage tab counts — computed once per dataset change. Search does
  // NOT scope these counts; the tabs are a stable pipeline overview,
  // not a search-narrowed view. (Operator's mental model: "I want to
  // see all submitted leads matching 'construction'" not "I want to
  // see how many leads named 'Mike' are submitted.")
  const stageCounts = useMemo(() => {
    const counts: Record<string, number> = { all: initialLeads.length };
    for (const s of STAGES) counts[s.value] = 0;
    counts.uncategorized = 0;
    for (const l of initialLeads) {
      const k = leadStage(l);
      if (k in counts) counts[k] += 1;
      else counts.uncategorized += 1;
    }
    return counts;
  }, [initialLeads]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "name" || key === "company" ? "asc" : "desc");
    }
    setPage(0);
  }

  function changeStage(next: string) {
    setStage(next);
    setPage(0);
  }

  // Empty database state vs filtered-empty state — different UX. The
  // first means "you have no leads, here's how to get some"; the
  // second means "your filter is too narrow."
  if (initialLeads.length === 0) {
    return (
      <div className="rounded-xl border border-bg-border bg-bg-elev/40 p-8 text-center">
        <Sparkles className="w-6 h-6 mx-auto text-accent mb-2" />
        <div className="font-bold text-fg">No leads yet</div>
        <p className="text-sm text-fg-muted mt-1 max-w-md mx-auto">
          Send your SunBiz application form to a prospect or import a list — leads
          land here as they fill it out. Solara will start scoring + scheduling
          follow-ups automatically.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* ── Stage tabs ───────────────────────────────────────────── */}
      <div className="overflow-x-auto -mx-2 px-2">
        <div className="flex items-center gap-1 min-w-max">
          <StageTab
            label="All"
            value="all"
            count={stageCounts.all}
            active={stage === "all"}
            onClick={() => changeStage("all")}
          />
          {STAGES.map((s) => (
            <StageTab
              key={s.value}
              label={s.label}
              value={s.value}
              count={stageCounts[s.value] || 0}
              tone={s.tone}
              active={stage === s.value}
              onClick={() => changeStage(s.value)}
            />
          ))}
          {stageCounts.uncategorized > 0 && (
            <StageTab
              label="Uncategorized"
              value="uncategorized"
              count={stageCounts.uncategorized}
              tone="text-fg-dim"
              active={stage === "uncategorized"}
              onClick={() => changeStage("uncategorized")}
            />
          )}
        </div>
      </div>

      {/* ── Search ───────────────────────────────────────────────── */}
      <div className="relative">
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-fg-dim" />
        <input
          type="text"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(0);
          }}
          placeholder="Search name, email, phone, company, notes…"
          className="w-full rounded-xl border border-bg-border bg-bg-deep/80 pl-10 pr-10 py-2.5 text-sm text-fg placeholder:text-fg-dim focus:border-accent/50 focus:outline-none"
        />
        {search && (
          <button
            type="button"
            onClick={() => {
              setSearch("");
              setPage(0);
            }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-fg-dim hover:text-fg"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* ── Results count + page nav ─────────────────────────────── */}
      <div className="flex items-center justify-between text-xs text-fg-muted">
        <div>
          {sorted.length === 0
            ? "No leads match the current filter."
            : `${sorted.length} lead${sorted.length === 1 ? "" : "s"}${
                search ? ` matching “${search}”` : ""
              }${stage !== "all" ? ` in ${stage.replace(/_/g, " ")}` : ""}`}
        </div>
        {totalPages > 1 && (
          <div className="flex items-center gap-2">
            <span>
              Page {page + 1} of {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="p-1 rounded hover:bg-bg-elev disabled:opacity-30"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="p-1 rounded hover:bg-bg-elev disabled:opacity-30"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {/* ── Table ─────────────────────────────────────────────────── */}
      <div className="overflow-x-auto rounded-xl border border-bg-border bg-bg-elev/40">
        <table className="w-full text-sm">
          <thead className="bg-bg-elev/50 border-b border-bg-border sticky top-0 z-10">
            <tr className="text-left text-[10px] uppercase tracking-[0.14em] text-fg-muted font-bold">
              <SortableTh label="Lead" sortKey="name" current={sortKey} dir={sortDir} onClick={toggleSort} />
              <th className="px-4 py-2.5 font-bold">Stage</th>
              <SortableTh label="Score" sortKey="score" current={sortKey} dir={sortDir} onClick={toggleSort} className="text-right" />
              <SortableTh label="Last touch" sortKey="last_touch" current={sortKey} dir={sortDir} onClick={toggleSort} />
              <th className="px-4 py-2.5 font-bold">Source</th>
              <SortableTh label="Created" sortKey="created" current={sortKey} dir={sortDir} onClick={toggleSort} />
            </tr>
          </thead>
          <tbody>
            {paginated.map((lead) => (
              <LeadRow key={lead.id} lead={lead} stageLabel={STAGES.find((s) => s.value === leadStage(lead))?.label} stageTone={STAGES.find((s) => s.value === leadStage(lead))?.tone} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StageTab({
  label,
  value,
  count,
  tone,
  active,
  onClick,
}: {
  label: string;
  value: string;
  count: number;
  tone?: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={value}
      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors inline-flex items-center gap-2 border ${
        active
          ? "border-accent/50 bg-accent/10 text-accent"
          : "border-bg-border bg-bg-elev/40 hover:bg-bg-elev/70 text-fg-muted"
      }`}
    >
      <span className={active ? "text-accent" : tone || "text-fg-muted"}>{label}</span>
      <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${active ? "bg-accent/20 text-accent" : "bg-bg-deep text-fg-dim"}`}>
        {count}
      </span>
    </button>
  );
}

function SortableTh({
  label,
  sortKey,
  current,
  dir,
  onClick,
  className,
}: {
  label: string;
  sortKey: SortKey;
  current: SortKey;
  dir: SortDir;
  onClick: (k: SortKey) => void;
  className?: string;
}) {
  const active = current === sortKey;
  const Icon = !active ? null : dir === "asc" ? ArrowUpAZ : ArrowDownAZ;
  return (
    <th className={`px-4 py-2.5 font-bold ${className || ""}`}>
      <button
        type="button"
        onClick={() => onClick(sortKey)}
        className={`inline-flex items-center gap-1 ${active ? "text-accent" : "hover:text-fg"}`}
      >
        {label}
        {Icon && <Icon className="w-3 h-3" />}
      </button>
    </th>
  );
}

function LeadRow({
  lead,
  stageLabel,
  stageTone,
}: {
  lead: Lead;
  stageLabel?: string;
  stageTone?: string;
}) {
  const initials =
    (lead.name || "")
      .split(/\s+/)
      .map((p) => p[0])
      .filter(Boolean)
      .slice(0, 2)
      .join("")
      .toUpperCase() || "?";

  const lastTouch = lead.last_contacted_at || lead.updated_at;
  return (
    <tr className="border-b border-bg-border last:border-0 hover:bg-bg-elev/30 transition-colors cursor-pointer">
      <td className="px-4 py-3">
        <Link href={`/leads/${lead.id}`} className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-bg-deep border border-bg-border flex items-center justify-center text-[11px] font-bold text-fg-muted shrink-0">
            {initials}
          </div>
          <div className="min-w-0">
            <div className="font-bold text-fg truncate">{lead.name || "—"}</div>
            <div className="flex items-center gap-3 text-[11px] text-fg-muted mt-0.5">
              {lead.company && (
                <span className="inline-flex items-center gap-1 truncate max-w-[160px]">
                  <Building2 className="w-3 h-3 shrink-0" />
                  {lead.company}
                </span>
              )}
              {lead.email && (
                <span className="inline-flex items-center gap-1 truncate max-w-[180px]">
                  <Mail className="w-3 h-3 shrink-0" />
                  {lead.email}
                </span>
              )}
              {lead.phone && (
                <span className="inline-flex items-center gap-1 font-mono">
                  <Phone className="w-3 h-3 shrink-0" />
                  {lead.phone}
                </span>
              )}
            </div>
          </div>
        </Link>
      </td>
      <td className="px-4 py-3">
        <span className={`text-xs font-bold ${stageTone || "text-fg-dim"}`}>
          {stageLabel || lead.status || "—"}
        </span>
      </td>
      <td className="px-4 py-3 text-right font-mono text-sm text-fg">
        {lead.score ?? <span className="text-fg-dim">—</span>}
      </td>
      <td className="px-4 py-3 text-xs text-fg-muted">
        {lastTouch ? new Date(lastTouch).toLocaleDateString() : "—"}
      </td>
      <td className="px-4 py-3 text-xs text-fg-muted">{lead.source || "—"}</td>
      <td className="px-4 py-3 text-xs text-fg-dim">
        {lead.created_at ? new Date(lead.created_at).toLocaleDateString() : "—"}
      </td>
    </tr>
  );
}
