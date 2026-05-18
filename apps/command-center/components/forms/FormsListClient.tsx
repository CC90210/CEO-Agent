"use client";

/**
 * FormsListClient — table + "New form" button for /forms (Phase 3.3).
 *
 * Server component above passes initialRows; this client component
 * handles the create flow (POST /api/forms with a starter stub then
 * redirect to the editor) and per-row toggle/delete.
 */

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Plus, Edit3, ToggleLeft, ToggleRight, Trash2, ExternalLink, Loader2, Copy, Check } from "lucide-react";
import { getFormTheme } from "@/lib/forms/themes";

type FormRow = {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

/** Today's date in YYYY-MM-DD for default form names. */
function todayStamp(): string {
  return new Date().toISOString().slice(0, 10);
}

// Starter template — every new form ships with a file-upload step out of
// the box so SunBiz operators don't have to remember to add one. The
// document field names (bank_statements_3mo / drivers_license /
// proof_of_ownership) match the doc_type classifier in migration 049 so
// submit-side storage keys land in the right bucket without a second
// pass. Branding is sourced from the sunbiz_standard theme so the picker
// highlights it as active immediately and the two sources can't drift.
function starterBranding(tenantLogoUrl: string | null) {
  const base = getFormTheme("sunbiz_standard")!.branding;
  return tenantLogoUrl ? { ...base, logo_url: tenantLogoUrl } : base;
}

const STARTER_FORM_TEMPLATE = {
  steps: [
    {
      key: "basic",
      title: "Tell us about your business",
      description: "A few quick questions to get started.",
      fields: [
        { name: "business_name", label: "Business name", type: "text", required: true },
        { name: "contact_name", label: "Your name", type: "text", required: true },
        { name: "email", label: "Email", type: "email", required: true },
        { name: "phone", label: "Phone", type: "phone", required: true },
        { name: "monthly_revenue", label: "Monthly revenue", type: "currency" },
      ],
    },
    {
      key: "documents",
      title: "Upload your documents",
      description:
        "We need three files to underwrite your application. Each one's required.",
      fields: [
        {
          name: "bank_statements_3mo",
          label: "Last 3 months of bank statements",
          help: "PDF preferred. One file per month is fine.",
          type: "file_upload",
          required: true,
          accept: ["application/pdf", "image/*"],
        },
        {
          name: "drivers_license",
          label: "Photo of your driver's license",
          help: "Front of card, clear and readable.",
          type: "file_upload",
          required: true,
          accept: ["image/*", "application/pdf"],
        },
        {
          name: "proof_of_ownership",
          label: "Proof of business ownership",
          help: "Articles of incorporation, EIN letter, or business license.",
          type: "file_upload",
          required: true,
          accept: ["application/pdf", "image/*"],
        },
      ],
    },
  ],
  step_outcomes: { "0": "sent_application" },
  on_complete_stage: "submitted",
  enabled: true,
};

export function FormsListClient({
  initialRows,
  tenantLogoUrl,
}: {
  initialRows: FormRow[];
  tenantLogoUrl: string | null;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [rows, setRows] = useState(initialRows);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Flash message when the operator just saved and got bounced here from
  // the editor. Auto-clears after a few seconds and strips the query
  // param so a page refresh doesn't re-fire the toast.
  const [savedFlash, setSavedFlash] = useState(false);
  useEffect(() => {
    if (searchParams.get("saved") === "1") {
      setSavedFlash(true);
      const t = setTimeout(() => setSavedFlash(false), 3000);
      // Strip the query without refetching the RSC.
      router.replace("/forms", { scroll: false });
      return () => clearTimeout(t);
    }
  }, [searchParams, router]);

  async function createForm() {
    setCreating(true);
    setError(null);
    try {
      // Mint a unique slug — operator can change it before save (well,
      // can't, since slug is immutable, but the starter slug is OK).
      const slug = `form-${Date.now().toString(36)}`;
      const res = await fetch("/api/forms", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          ...STARTER_FORM_TEMPLATE,
          branding: starterBranding(tenantLogoUrl),
          name: `New form — ${todayStamp()}`,
          slug,
        }),
      });
      const data = (await res.json()) as { ok: boolean; form?: { id: string }; error?: string };
      if (!data.ok || !data.form) {
        setError(data.error || `http_${res.status}`);
        return;
      }
      router.push(`/forms/${data.form.id}/edit`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "network_error");
    } finally {
      setCreating(false);
    }
  }

  async function toggle(id: string, enabled: boolean) {
    const next = !enabled;
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, enabled: next } : r)));
    const res = await fetch(`/api/forms/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ enabled: next }),
    });
    if (!res.ok) {
      setRows((prev) => prev.map((r) => (r.id === id ? { ...r, enabled } : r)));
      return;
    }
    // Invalidate the cached /forms RSC payload so the next navigation
    // picks up the new toggle state (Next.js 15 router-cache fix).
    router.refresh();
  }

  // Per-row "Copy" feedback. Keyed by form id so the check icon only
  // appears on the row the operator just clicked.
  const [copiedId, setCopiedId] = useState<string | null>(null);
  async function copyEditorUrl(id: string) {
    try {
      const url = `${window.location.origin}/forms/${id}/edit`;
      await navigator.clipboard.writeText(url);
      setCopiedId(id);
      setTimeout(() => {
        setCopiedId((prev) => (prev === id ? null : prev));
      }, 1800);
    } catch {
      // Clipboard API blocked (rare — old browsers, insecure contexts).
      // Fall back to a window.prompt so the operator can still grab the
      // URL manually.
      window.prompt("Copy this URL:", `${window.location.origin}/forms/${id}/edit`);
    }
  }

  async function destroy(id: string, name: string) {
    if (!confirm(`Delete form "${name}"? This can't be undone.`)) return;
    const res = await fetch(`/api/forms/${id}`, { method: "DELETE" });
    if (!res.ok) {
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      setError(data.error || `delete failed (${res.status})`);
      return;
    }
    setRows((prev) => prev.filter((r) => r.id !== id));
    router.refresh();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-xs text-fg-muted">
          {rows.length} form{rows.length === 1 ? "" : "s"}
        </div>
        <button
          type="button"
          onClick={createForm}
          disabled={creating}
          className="inline-flex items-center gap-2 rounded-lg bg-accent text-bg-deep px-4 py-2 text-sm font-bold hover:bg-accent-bright disabled:opacity-50"
        >
          {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          New form
        </button>
      </div>

      {savedFlash && (
        <div className="rounded-lg border border-status-engaged/40 bg-status-engaged/10 px-3 py-2 text-sm text-status-engaged flex items-center gap-2">
          <Check className="w-4 h-4" />
          Form saved.
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-400">
          {error === "slug_taken"
            ? "Slug collision — try New form again (we'll mint a new one)."
            : `Couldn't create form: ${error}`}
        </div>
      )}

      {rows.length === 0 ? (
        <div className="rounded-xl border border-bg-border bg-bg-elev/40 p-8 text-center text-fg-muted">
          <div className="text-sm">No forms yet.</div>
          <div className="text-xs mt-1 text-fg-dim">
            Click <span className="text-fg">New form</span> to start designing one.
          </div>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-bg-border">
          <table className="w-full text-sm">
            <thead className="bg-bg-elev/50">
              <tr className="text-left text-[10px] uppercase tracking-wider text-fg-dim">
                <th className="px-4 py-2 font-bold">Name</th>
                <th className="px-4 py-2 font-bold">Slug</th>
                <th className="px-4 py-2 font-bold">Status</th>
                <th className="px-4 py-2 font-bold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-bg-border">
              {rows.map((r) => (
                <tr key={r.id} className="hover:bg-bg-elev/30">
                  <td className="px-4 py-3">
                    <div className="font-bold text-fg">{r.name}</div>
                    {r.description && (
                      <div className="text-xs text-fg-muted truncate max-w-md">
                        {r.description}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-fg-muted">{r.slug}</td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => toggle(r.id, r.enabled)}
                      className={`inline-flex items-center gap-1.5 text-xs ${
                        r.enabled ? "text-status-engaged" : "text-fg-dim"
                      }`}
                    >
                      {r.enabled ? (
                        <ToggleRight className="w-4 h-4" />
                      ) : (
                        <ToggleLeft className="w-4 h-4" />
                      )}
                      {r.enabled ? "Live" : "Disabled"}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-2">
                      <Link
                        href={`/forms/${r.id}/edit`}
                        className="inline-flex items-center gap-1 text-accent hover:text-accent-bright text-xs"
                      >
                        <Edit3 className="w-3 h-3" />
                        Edit
                      </Link>
                      <button
                        type="button"
                        onClick={() => copyEditorUrl(r.id)}
                        className="inline-flex items-center gap-1 text-fg-muted hover:text-fg text-xs"
                        title="Copy a link to this form's editor (share with a teammate or open on another device). For prospect-facing personalized links, open the form and use Mint link."
                      >
                        {copiedId === r.id ? (
                          <>
                            <Check className="w-3 h-3 text-status-engaged" />
                            Copied
                          </>
                        ) : (
                          <>
                            <Copy className="w-3 h-3" />
                            Copy link
                          </>
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => destroy(r.id, r.name)}
                        className="inline-flex items-center gap-1 text-rose-400 hover:text-rose-300 text-xs"
                      >
                        <Trash2 className="w-3 h-3" />
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="rounded-xl border border-bg-border bg-bg-elev/30 p-4 text-xs text-fg-muted leading-relaxed">
        <div className="font-bold text-fg mb-1 flex items-center gap-1.5">
          <ExternalLink className="w-3 h-3 text-accent" />
          Personalized links
        </div>
        Once a form is live, Solara can mint a per-lead URL via{" "}
        <code className="text-accent bg-bg-deep px-1 rounded">POST /api/forms/{`<id>`}/mint-link</code>
        {" "}with a <code className="text-accent">lead_id</code>. Drop the returned URL
        into an outreach SMS or email. Opening the link transitions the lead
        to <span className="font-mono text-fg">viewed_application</span>;
        submitting transitions per the form&apos;s <span className="font-mono text-fg">step_outcomes</span> map.
      </div>
    </div>
  );
}
