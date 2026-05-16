"use client";

/**
 * LeadsImportClient — operator-facing CSV import for the Leads pipeline.
 *
 * Three-step flow:
 *   1. Paste CSV text or drop a .csv file. We parse it client-side so
 *      the operator sees the column mapping before any network round-
 *      trip. Empty/header-only inputs surface as a "looks empty" hint
 *      instead of crashing.
 *   2. Preview pane shows the first 10 rows in their mapped form (Name,
 *      Email, Phone, Company, Source, Notes), plus a count of total
 *      parseable rows. Operator picks which columns to dedup on.
 *   3. Click Import → POST /api/leads/import. Surface the inserted /
 *      skipped-duplicate / skipped-malformed counts inline plus a
 *      router.refresh() so the /leads page picks up the new rows
 *      immediately when the operator clicks back.
 *
 * Column mapping: we accept any reasonable header variants
 * (Full Name / Name / Contact, Phone / Phone Number / Cell, etc.).
 * No row-level operator-edit-the-cells UX yet — that would be Phase 13.
 * For now: garbage-in-garbage-out on bad CSVs; the dedup gate + the
 * `skipped_malformed` counter guard against the worst outcomes.
 */

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Upload,
  AlertCircle,
  CheckCircle2,
  Loader2,
  ArrowRight,
  FileSpreadsheet,
  Trash2,
} from "lucide-react";

type ParsedRow = {
  name: string | null;
  email: string | null;
  phone: string | null;
  company: string | null;
  source: string | null;
  notes: string | null;
};

type ImportResult = {
  ok: boolean;
  inserted?: number;
  skipped_duplicate?: number;
  skipped_malformed?: number;
  duplicate_keys?: string[];
  errors?: string[];
  message?: string;
  error?: string;
};

const SAMPLE = `Name,Email,Phone,Company,Source,Notes
Hunter Smith,hunter@hunterconstruction.com,+1 555 123 4567,Hunter Construction,linkedin_outreach,Roofing co — 18 months in biz
Mike Reyes,mike@reyesmotors.net,(727) 555-9911,Reyes Motors,referral,Used cars dealer
`;

/** Map operator-typed header → our canonical field name. Lowercase
 *  exact match with a few common aliases. Returns null when the
 *  header doesn't match any known field. */
function mapHeader(h: string): keyof ParsedRow | null {
  const n = h.trim().toLowerCase().replace(/[_\s-]/g, "");
  switch (n) {
    case "name":
    case "fullname":
    case "contact":
    case "contactname":
      return "name";
    case "email":
    case "emailaddress":
    case "e-mail":
      return "email";
    case "phone":
    case "phonenumber":
    case "cell":
    case "mobile":
    case "tel":
      return "phone";
    case "company":
    case "business":
    case "businessname":
    case "merchant":
    case "businessname2":
      return "company";
    case "source":
    case "lead source":
    case "leadsource":
    case "channel":
      return "source";
    case "notes":
    case "note":
    case "comment":
    case "comments":
      return "notes";
    default:
      return null;
  }
}

/**
 * Tiny CSV parser. Handles quoted fields with embedded commas + escaped
 * quotes ("") and CRLF/LF line endings. We avoid the heavyweight csv
 * libraries because (a) the operator's input is small (≤5k rows) and
 * (b) we'd rather ship one client bundle without a 30KB CSV dep when
 * 90% of inputs are vanilla comma-separated.
 */
function parseCsv(text: string): { headers: string[]; rows: string[][] } {
  const out: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += c;
      }
      continue;
    }
    if (c === '"') {
      inQuotes = true;
    } else if (c === ",") {
      row.push(field);
      field = "";
    } else if (c === "\n" || c === "\r") {
      row.push(field);
      field = "";
      if (row.length > 1 || row[0] !== "") out.push(row);
      row = [];
      if (c === "\r" && text[i + 1] === "\n") i++;
    } else {
      field += c;
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    if (row.length > 1 || row[0] !== "") out.push(row);
  }
  const headers = out.shift() || [];
  return { headers, rows: out };
}

export function LeadsImportClient() {
  const router = useRouter();
  const [csv, setCsv] = useState("");
  const [defaultSource, setDefaultSource] = useState("csv_import");
  const [dedupEmail, setDedupEmail] = useState(true);
  const [dedupPhone, setDedupPhone] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const parsed = useMemo(() => {
    if (!csv.trim()) return null;
    const { headers, rows } = parseCsv(csv);
    if (headers.length === 0) return { headers: [], rows: [], mapped: [] as ParsedRow[] };
    const colMap: Array<keyof ParsedRow | null> = headers.map(mapHeader);
    const mapped: ParsedRow[] = rows.map((cells) => {
      const r: ParsedRow = {
        name: null,
        email: null,
        phone: null,
        company: null,
        source: null,
        notes: null,
      };
      cells.forEach((val, idx) => {
        const k = colMap[idx];
        if (!k) return;
        r[k] = (val || "").trim() || null;
      });
      return r;
    });
    return { headers, rows, mapped, colMap };
  }, [csv]);

  const recognizedColumns = useMemo(() => {
    if (!parsed) return 0;
    return parsed.colMap?.filter((c) => c !== null).length || 0;
  }, [parsed]);

  async function handleFile(file: File) {
    const text = await file.text();
    setCsv(text);
    setResult(null);
    setError(null);
  }

  async function doImport() {
    if (!parsed || parsed.mapped.length === 0) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    const dedup_by = [
      ...(dedupEmail ? ["email"] : []),
      ...(dedupPhone ? ["phone"] : []),
    ];
    try {
      const res = await fetch("/api/leads/import", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          rows: parsed.mapped,
          dedup_by,
          default_source: defaultSource.trim() || "csv_import",
        }),
      });
      const data = (await res.json()) as ImportResult;
      if (!data.ok) {
        setError(data.message || data.error || `http_${res.status}`);
      } else {
        setResult(data);
        // Invalidate the /leads RSC cache so the operator sees the new
        // rows on their next navigation.
        router.refresh();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "network_error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Step 1: Input */}
      <section className="rounded-xl border border-bg-border bg-bg-elev/40 p-5 space-y-4">
        <header>
          <div className="font-bold text-fg flex items-center gap-2">
            <FileSpreadsheet className="w-4 h-4 text-accent" />
            Paste your CSV (or drop a file)
          </div>
          <p className="text-xs text-fg-muted mt-1 leading-relaxed">
            Expected columns: Name, Email, Phone, Company, Source, Notes. Header
            names are matched loosely — &quot;Full Name&quot;, &quot;business&quot;, &quot;cell&quot; all
            work. Unknown columns are dropped silently.
          </p>
        </header>

        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={async (e) => {
            e.preventDefault();
            const f = e.dataTransfer.files?.[0];
            if (f) await handleFile(f);
          }}
        >
          <textarea
            value={csv}
            onChange={(e) => {
              setCsv(e.target.value);
              setResult(null);
              setError(null);
            }}
            placeholder={SAMPLE}
            spellCheck={false}
            rows={10}
            className="w-full rounded-lg border border-bg-border bg-bg-deep px-3 py-2 text-xs font-mono text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none"
          />
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <label className="inline-flex items-center gap-2 text-xs text-fg-muted cursor-pointer">
            <Upload className="w-3.5 h-3.5" />
            <span>Upload .csv</span>
            <input
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (f) await handleFile(f);
              }}
            />
          </label>
          <button
            type="button"
            onClick={() => setCsv(SAMPLE)}
            className="text-xs text-fg-dim hover:text-accent"
          >
            Insert sample
          </button>
          {csv && (
            <button
              type="button"
              onClick={() => {
                setCsv("");
                setResult(null);
                setError(null);
              }}
              className="inline-flex items-center gap-1 text-xs text-fg-dim hover:text-rose-400"
            >
              <Trash2 className="w-3 h-3" /> Clear
            </button>
          )}
        </div>
      </section>

      {/* Step 2: Preview */}
      {parsed && parsed.headers.length > 0 && (
        <section className="rounded-xl border border-bg-border bg-bg-elev/40 p-5 space-y-3">
          <header className="flex items-center justify-between">
            <div className="font-bold text-fg">
              Preview · {parsed.mapped.length} row{parsed.mapped.length === 1 ? "" : "s"}
            </div>
            <div className="text-xs text-fg-muted">
              {recognizedColumns} of {parsed.headers.length} column{parsed.headers.length === 1 ? "" : "s"} recognized
            </div>
          </header>

          {recognizedColumns === 0 && (
            <div className="rounded-lg border border-status-warm/40 bg-status-warm/10 p-3 text-xs text-status-warm flex items-start gap-2">
              <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              <div>
                None of your CSV headers matched a known field. Rename at least
                one of: <span className="font-mono">Name</span> /{" "}
                <span className="font-mono">Email</span> /{" "}
                <span className="font-mono">Phone</span> /{" "}
                <span className="font-mono">Company</span>.
              </div>
            </div>
          )}

          <div className="overflow-x-auto rounded-lg border border-bg-border">
            <table className="w-full text-xs">
              <thead className="bg-bg-elev/60 text-fg-dim text-[10px] uppercase tracking-wider">
                <tr>
                  <th className="px-3 py-1.5 text-left font-bold">Name</th>
                  <th className="px-3 py-1.5 text-left font-bold">Email</th>
                  <th className="px-3 py-1.5 text-left font-bold">Phone</th>
                  <th className="px-3 py-1.5 text-left font-bold">Company</th>
                  <th className="px-3 py-1.5 text-left font-bold">Source</th>
                </tr>
              </thead>
              <tbody>
                {parsed.mapped.slice(0, 10).map((r, i) => (
                  <tr key={i} className="border-t border-bg-border">
                    <td className="px-3 py-1.5 text-fg">{r.name || <span className="text-fg-dim">—</span>}</td>
                    <td className="px-3 py-1.5 text-fg-muted font-mono">
                      {r.email || <span className="text-fg-dim">—</span>}
                    </td>
                    <td className="px-3 py-1.5 text-fg-muted font-mono">
                      {r.phone || <span className="text-fg-dim">—</span>}
                    </td>
                    <td className="px-3 py-1.5 text-fg-muted">
                      {r.company || <span className="text-fg-dim">—</span>}
                    </td>
                    <td className="px-3 py-1.5 text-fg-dim text-[10px]">{r.source || defaultSource}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {parsed.mapped.length > 10 && (
              <div className="px-3 py-2 text-[11px] text-fg-dim italic border-t border-bg-border">
                + {parsed.mapped.length - 10} more row{parsed.mapped.length - 10 === 1 ? "" : "s"} (not shown)
              </div>
            )}
          </div>

          <div className="grid sm:grid-cols-2 gap-3 pt-2 border-t border-bg-border">
            <label className="block">
              <span className="text-[10px] uppercase tracking-wider text-fg-dim block mb-1">
                Default source (when blank in CSV)
              </span>
              <input
                type="text"
                value={defaultSource}
                onChange={(e) => setDefaultSource(e.target.value)}
                placeholder="csv_import"
                className="w-full rounded-lg border border-bg-border bg-bg-deep px-3 py-1.5 text-sm text-fg"
              />
            </label>
            <div className="block">
              <span className="text-[10px] uppercase tracking-wider text-fg-dim block mb-1">
                Skip duplicates by
              </span>
              <div className="flex items-center gap-3 text-sm text-fg">
                <label className="inline-flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={dedupEmail}
                    onChange={(e) => setDedupEmail(e.target.checked)}
                  />
                  Email
                </label>
                <label className="inline-flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={dedupPhone}
                    onChange={(e) => setDedupPhone(e.target.checked)}
                  />
                  Phone
                </label>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Step 3: Action + result */}
      {parsed && parsed.mapped.length > 0 && recognizedColumns > 0 && (
        <section className="flex items-center gap-3">
          <button
            type="button"
            onClick={doImport}
            disabled={submitting}
            className="btn-send inline-flex items-center gap-2 !px-5 !py-2 text-sm disabled:opacity-50"
          >
            {submitting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <ArrowRight className="w-4 h-4" />
            )}
            Import {parsed.mapped.length} lead{parsed.mapped.length === 1 ? "" : "s"}
          </button>
          {result?.ok && (
            <Link
              href="/leads"
              className="btn-secondary inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
            >
              View leads →
            </Link>
          )}
        </section>
      )}

      {error && (
        <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-400 inline-flex items-start gap-2">
          <AlertCircle className="w-4 h-4 mt-0.5" />
          <div>
            <div className="font-bold">Import failed</div>
            <div className="text-xs mt-0.5">{error}</div>
          </div>
        </div>
      )}

      {result?.ok && (
        <div className="rounded-xl border border-status-engaged/40 bg-status-engaged/10 p-4 space-y-2">
          <div className="flex items-center gap-2 text-status-engaged font-bold text-sm">
            <CheckCircle2 className="w-4 h-4" />
            Import complete
          </div>
          <div className="grid sm:grid-cols-3 gap-3 text-sm">
            <Stat label="Inserted" value={result.inserted || 0} tone="text-status-engaged" />
            <Stat label="Skipped (duplicate)" value={result.skipped_duplicate || 0} tone="text-accent" />
            <Stat label="Skipped (malformed)" value={result.skipped_malformed || 0} tone="text-status-warm" />
          </div>
          {(result.duplicate_keys || []).length > 0 && (
            <details className="text-xs text-fg-muted">
              <summary className="cursor-pointer text-fg-dim hover:text-fg">
                Show first {(result.duplicate_keys || []).length} duplicate keys
              </summary>
              <div className="mt-1 max-h-32 overflow-y-auto font-mono space-y-0.5 pl-3">
                {(result.duplicate_keys || []).map((k, i) => (
                  <div key={i}>{k}</div>
                ))}
              </div>
            </details>
          )}
          {(result.errors || []).length > 0 && (
            <details className="text-xs text-fg-muted">
              <summary className="cursor-pointer text-status-warm hover:text-fg">
                {(result.errors || []).length} malformed row{(result.errors || []).length === 1 ? "" : "s"}
              </summary>
              <ul className="mt-1 max-h-32 overflow-y-auto font-mono space-y-0.5 pl-3">
                {(result.errors || []).map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="rounded-lg border border-bg-border bg-bg-deep/60 p-3">
      <div className={`text-2xl font-bold ${tone || "text-fg"}`}>{value.toLocaleString()}</div>
      <div className="text-[10px] uppercase tracking-wider text-fg-dim mt-0.5">{label}</div>
    </div>
  );
}
