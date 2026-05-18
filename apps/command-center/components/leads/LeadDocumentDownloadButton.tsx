"use client";

import { useState } from "react";
import { Loader2, ExternalLink } from "lucide-react";

export function LeadDocumentDownloadButton({
  documentId,
  filename,
}: {
  documentId: string;
  filename: string;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function open() {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`/api/lead-documents/${documentId}`, {
        method: "GET",
      });
      const body = (await r.json()) as {
        ok?: boolean;
        url?: string;
        error?: string;
      };
      if (!r.ok || !body.ok || !body.url) {
        setError(body.error || `http_${r.status}`);
        return;
      }
      // Open the signed URL in a new tab. The browser handles preview vs
      // download based on the file's Content-Type.
      window.open(body.url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(err instanceof Error ? err.message : "network_error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      {error && (
        <span className="text-[11px] text-rose-400" title={error}>
          {error}
        </span>
      )}
      <button
        type="button"
        onClick={open}
        disabled={loading}
        title={`Open ${filename}`}
        className="inline-flex items-center gap-1 rounded-md border border-bg-border bg-bg-elev px-2 py-1 text-[11px] font-bold text-fg hover:border-accent/40 disabled:opacity-50"
      >
        {loading ? (
          <Loader2 className="w-3 h-3 animate-spin" />
        ) : (
          <ExternalLink className="w-3 h-3" />
        )}
        View
      </button>
    </div>
  );
}

