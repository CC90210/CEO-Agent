"use client";

/**
 * BrandLogoCard — operator uploads their brand logo once in Settings →
 * Branding. The URL is saved on tenants.logo_url and auto-applied to
 * every new form's intake page, public preview, and any future place
 * the dashboard renders tenant identity.
 *
 * Owners / admins can change it; everyone else sees the current logo
 * read-only (the API enforces — the UI just hides the upload control).
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Upload, Trash2, AlertCircle } from "lucide-react";

type Props = {
  initialLogoUrl: string | null;
  canManage: boolean;
};

export function BrandLogoCard({ initialLogoUrl, canManage }: Props) {
  const router = useRouter();
  const [logoUrl, setLogoUrl] = useState<string | null>(initialLogoUrl);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/tenant/logo", { method: "POST", body: fd });
      const body = (await res.json()) as {
        ok?: boolean;
        logo_url?: string;
        error?: string;
        hint?: string;
      };
      if (!res.ok || !body.ok || !body.logo_url) {
        setError(body.hint || body.error || `http_${res.status}`);
        return;
      }
      setLogoUrl(body.logo_url);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "network_error");
    } finally {
      setBusy(false);
      // Reset the input so picking the same file twice still fires onChange.
      e.target.value = "";
    }
  }

  async function clear() {
    if (!confirm("Remove your brand logo?")) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/tenant/logo", { method: "DELETE" });
      const body = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        error?: string;
      };
      if (!res.ok || !body.ok) {
        setError(body.error || `http_${res.status}`);
        return;
      }
      setLogoUrl(null);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-4">
        <div className="h-16 w-16 rounded-md border border-bg-border bg-bg-deep flex items-center justify-center overflow-hidden">
          {logoUrl ? (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img
              src={logoUrl}
              alt="Brand logo"
              className="max-h-full max-w-full"
            />
          ) : (
            <span className="text-[10px] text-fg-dim uppercase tracking-wider">
              No logo
            </span>
          )}
        </div>
        <div className="text-xs text-fg-muted leading-relaxed flex-1">
          Upload once here. Every new form, public application page, and
          anywhere else the dashboard shows your brand will pick it up
          automatically. PNG, JPG, WEBP, SVG, or GIF — under 2 MB.
        </div>
      </div>

      {canManage && (
        <div className="flex items-center gap-2">
          <label className="inline-flex items-center gap-2 rounded-lg border border-bg-border bg-bg-elev px-3 py-1.5 text-xs font-bold text-fg cursor-pointer hover:border-accent/40">
            {busy ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Upload className="w-3.5 h-3.5" />
            )}
            {logoUrl ? "Replace logo" : "Upload logo"}
            <input
              type="file"
              className="sr-only"
              accept="image/png,image/jpeg,image/webp,image/svg+xml,image/gif"
              onChange={onPick}
              disabled={busy}
            />
          </label>
          {logoUrl && (
            <button
              type="button"
              onClick={clear}
              disabled={busy}
              className="inline-flex items-center gap-1 rounded-lg border border-rose-500/40 text-rose-400 px-3 py-1.5 text-xs font-bold hover:bg-rose-500/10 disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Remove
            </button>
          )}
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 text-xs text-rose-400">
          <AlertCircle className="w-3.5 h-3.5" />
          {error}
        </div>
      )}
    </div>
  );
}
