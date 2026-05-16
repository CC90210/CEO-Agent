"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Save,
  Sparkles,
  Trash2,
} from "lucide-react";
import { CATEGORY_LABELS, type AgentCategory } from "@/lib/agents/library";

type EditingAgent = {
  slug: string;
  name: string;
  category: AgentCategory;
  short_description: string;
  description: string;
  base_prompt: string;
  required_tools: string[];
  suggested_model: string;
  is_public: boolean;
};

type Props = {
  tenantSlug: string;
  editing: EditingAgent | null;
};

function slugifyClient(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 62) || "agent";
}

export function CustomAgentBuilder({ tenantSlug, editing }: Props) {
  const router = useRouter();
  const isEdit = !!editing;

  const [name, setName] = useState(editing?.name || "");
  const [category, setCategory] = useState<AgentCategory>(editing?.category || "custom");
  const [intent, setIntent] = useState("");
  const [shortDesc, setShortDesc] = useState(editing?.short_description || "");
  const [description, setDescription] = useState(editing?.description || "");
  const [basePrompt, setBasePrompt] = useState(editing?.base_prompt || "");
  const [toolsText, setToolsText] = useState((editing?.required_tools || []).join(", "));
  const [suggestedModel, setSuggestedModel] = useState(editing?.suggested_model || "");
  const [isPublic, setIsPublic] = useState(editing?.is_public ?? false);

  const [slugManuallyEdited, setSlugManuallyEdited] = useState(false);
  const [manualSlug, setManualSlug] = useState(editing?.slug || "");
  const derivedSlug = name ? slugifyClient(name) : "";
  const slug = isEdit ? editing!.slug : (slugManuallyEdited ? manualSlug : derivedSlug);

  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const tools = useMemo(
    () =>
      toolsText
        .split(/[,\n]+/)
        .map((t) => t.trim().toLowerCase().replace(/\s+/g, "_"))
        .filter((t) => /^[a-z][a-z0-9_]{0,62}$/.test(t)),
    [toolsText]
  );

  async function generate() {
    if (!name.trim() || !intent.trim()) {
      setError("Fill in the name and a description before generating.");
      return;
    }
    setGenerating(true);
    setError(null);
    setFlash(null);
    try {
      const res = await fetch("/api/agents/generate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name, category, description: intent }),
      });
      const data = (await res.json()) as
        | {
            ok: true;
            base_prompt: string;
            short_description: string;
            description: string;
            required_tools: string[];
            suggested_model: string;
          }
        | { ok: false; error: string; message?: string };
      if (!data.ok) {
        setError(data.message || data.error);
        return;
      }
      setBasePrompt(data.base_prompt);
      setShortDesc(data.short_description);
      setDescription(data.description);
      setToolsText(data.required_tools.join(", "));
      setSuggestedModel(data.suggested_model);
      setFlash("Draft generated. Review + edit, then save.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "network_error");
    } finally {
      setGenerating(false);
    }
  }

  async function save() {
    setSaving(true);
    setError(null);
    setFlash(null);
    try {
      const payload = {
        slug,
        name: name.trim(),
        category,
        short_description: shortDesc.trim(),
        description: description.trim() || undefined,
        base_prompt: basePrompt.trim(),
        required_tools: tools,
        suggested_model: suggestedModel.trim() || undefined,
        is_public: isPublic,
      };
      const res = await fetch(isEdit ? `/api/agents/${slug}` : "/api/agents", {
        method: isEdit ? "PATCH" : "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = (await res.json()) as
        | { ok: true; agent: { slug: string } }
        | { ok: false; error: string; message?: string; field?: string; reason?: string };
      if (!data.ok) {
        const detail =
          data.error === "validation"
            ? `${data.field || "field"}: ${data.reason || data.message}`
            : data.message || data.error;
        setError(detail);
        return;
      }
      setFlash(isEdit ? "Saved." : "Created. Redirecting to the marketplace...");
      router.push(`/t/${tenantSlug}/marketplace/${data.agent.slug}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "network_error");
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!isEdit) return;
    if (!confirm(`Delete agent "${name}"? This cannot be undone.`)) return;
    setDeleting(true);
    setError(null);
    try {
      const res = await fetch(`/api/agents/${slug}`, { method: "DELETE" });
      const data = (await res.json()) as { ok: boolean; error?: string; message?: string };
      if (!data.ok) {
        setError(data.message || data.error || "delete_failed");
        return;
      }
      // Invalidate the marketplace page's RSC cache; without this the
      // just-deleted agent reappears in the cached list.
      router.refresh();
      router.push(`/t/${tenantSlug}/marketplace`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "network_error");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
      {/* Form pane */}
      <div className="space-y-4 rounded-2xl border border-bg-border bg-bg-elev/40 p-5">
        <Field label="Agent name" required>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Outreach Sniper"
            disabled={isEdit}
            className="w-full rounded-xl border border-bg-border bg-bg-deep/80 px-3 py-2 text-sm text-fg focus:border-accent/50 focus:outline-none disabled:opacity-60"
          />
        </Field>

        <Field
          label="URL slug"
          hint={`Marketplace URL: /t/${tenantSlug}/marketplace/${slug || "<slug>"}`}
        >
          <input
            type="text"
            value={slug}
            onChange={(e) => {
              setSlugManuallyEdited(true);
              setManualSlug(e.target.value.toLowerCase());
            }}
            placeholder={derivedSlug || "agent-slug"}
            disabled={isEdit}
            className="w-full rounded-xl border border-bg-border bg-bg-deep/80 px-3 py-2 text-sm font-mono text-fg focus:border-accent/50 focus:outline-none disabled:opacity-60"
          />
        </Field>

        <Field label="Category" required>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as AgentCategory)}
            className="w-full rounded-xl border border-bg-border bg-bg-deep/80 px-3 py-2 text-sm text-fg focus:border-accent/50 focus:outline-none"
          >
            {(Object.keys(CATEGORY_LABELS) as AgentCategory[]).map((k) => (
              <option key={k} value={k}>
                {CATEGORY_LABELS[k]}
              </option>
            ))}
          </select>
        </Field>

        {!isEdit && (
          <Field label="Describe what this agent should do" hint="A few sentences. The AI uses this to draft the system prompt.">
            <textarea
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
              rows={4}
              placeholder="Cold-outreach agent for real estate buyer's agents. Pulls leads from our website forms, drafts SMS in my voice, never sounds like a script. Asks 3 qualification questions before booking a showing."
              className="w-full resize-y rounded-xl border border-bg-border bg-bg-deep/80 px-3 py-2 text-sm text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none"
            />
            <button
              type="button"
              onClick={generate}
              disabled={!name.trim() || !intent.trim() || generating}
              className="btn-send mt-2 inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
            >
              {generating ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
              {generating ? "Drafting..." : "Generate draft with AI"}
            </button>
          </Field>
        )}

        <Field label="Short description" hint="One sentence shown on the marketplace tile." required>
          <input
            type="text"
            value={shortDesc}
            onChange={(e) => setShortDesc(e.target.value)}
            placeholder="Cold-outreach agent for real estate buyer's agents."
            className="w-full rounded-xl border border-bg-border bg-bg-deep/80 px-3 py-2 text-sm text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none"
          />
        </Field>

        <Field label="Detail description" hint="2-4 sentences on the agent's detail page.">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            className="w-full resize-y rounded-xl border border-bg-border bg-bg-deep/80 px-3 py-2 text-sm text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none"
          />
        </Field>

        <Field
          label="Required tools"
          hint="Comma- or newline-separated lower_snake_case slugs. The runtime will surface these for the operator to wire up."
        >
          <input
            type="text"
            value={toolsText}
            onChange={(e) => setToolsText(e.target.value)}
            placeholder="supabase_query, twilio_sms, search_repo"
            className="w-full rounded-xl border border-bg-border bg-bg-deep/80 px-3 py-2 text-sm font-mono text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none"
          />
        </Field>

        <Field label="Suggested model" hint="Optional. Empty = tenant default.">
          <input
            type="text"
            value={suggestedModel}
            onChange={(e) => setSuggestedModel(e.target.value)}
            placeholder="claude-sonnet-4-6"
            className="w-full rounded-xl border border-bg-border bg-bg-deep/80 px-3 py-2 text-sm font-mono text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none"
          />
        </Field>

        <label className="flex items-center gap-2 text-sm text-fg">
          <input
            type="checkbox"
            checked={isPublic}
            onChange={(e) => setIsPublic(e.target.checked)}
          />
          Public — share with other tenants in the marketplace
        </label>

        {flash && (
          <div className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-100 inline-flex items-start gap-2">
            <CheckCircle2 className="h-3.5 w-3.5 mt-0.5" />
            <span>{flash}</span>
          </div>
        )}
        {error && (
          <div className="rounded-xl border border-red-400/30 bg-red-400/10 px-3 py-2 text-xs text-red-200 inline-flex items-start gap-2">
            <AlertCircle className="h-3.5 w-3.5 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <div className="flex items-center gap-2 pt-2 border-t border-bg-border">
          <button
            type="button"
            onClick={save}
            disabled={!name.trim() || !shortDesc.trim() || !basePrompt.trim() || saving}
            className="btn-send inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs"
          >
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
            {isEdit ? "Save changes" : "Create agent"}
          </button>
          {isEdit && (
            <button
              type="button"
              onClick={remove}
              disabled={deleting}
              className="btn-secondary inline-flex items-center gap-1.5 !px-3 !py-1.5 text-xs hover:!border-red-400/50 hover:!text-red-300"
            >
              {deleting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
              Delete
            </button>
          )}
        </div>
      </div>

      {/* Prompt pane */}
      <div className="space-y-2 rounded-2xl border border-bg-border bg-bg-elev/40 p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-fg-dim font-bold">System prompt</div>
            <div className="text-sm font-bold text-fg">Base prompt</div>
          </div>
          <span className="text-[10px] text-fg-dim">{basePrompt.length} chars</span>
        </div>
        <textarea
          value={basePrompt}
          onChange={(e) => setBasePrompt(e.target.value)}
          rows={22}
          placeholder="Generate a draft on the left, or write this from scratch. Use {{tenant.brand.name}} as a placeholder. 30-16000 characters."
          className="w-full resize-none rounded-xl border border-bg-border bg-bg-deep/80 px-4 py-3 text-sm font-mono text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none leading-relaxed"
        />
        <p className="text-[11px] text-fg-dim leading-relaxed">
          The base prompt is shared across all tenants who enable this agent. Tenant-specific tweaks (e.g. brand voice, persona overlay) belong on the subscription panel, not here.
        </p>
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-sm font-semibold text-fg">
        {label}
        {required && <span className="ml-1 text-accent">*</span>}
      </span>
      {children}
      {hint && <span className="block text-[11px] text-fg-dim">{hint}</span>}
    </label>
  );
}
