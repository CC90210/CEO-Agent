/**
 * LeadDocumentsPanel — operator-facing list of files prospects uploaded
 * against this lead. Server component: reads lead_documents directly with
 * the service-role client after verifying tenant scope, then renders a
 * client island for the "View" button which mints a signed URL on click.
 *
 * Lives on /pipeline/[id] (and any future lead detail surface) so the
 * operator can see + download bank statements / ID / proof-of-ownership
 * without leaving the dashboard.
 */
import { FileText, ImageIcon } from "lucide-react";
import { Card } from "@/components/Card";
import { getServiceSupabase } from "@/lib/supabase-server";
import { LeadDocumentDownloadButton } from "./LeadDocumentDownloadButton";

type LeadDocumentRow = {
  id: string;
  filename: string;
  mime_type: string | null;
  size_bytes: number | null;
  doc_type: string;
  uploaded_by: string | null;
  uploaded_at: string;
};

function humanSize(bytes: number | null): string {
  if (!bytes || bytes <= 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function docTypeLabel(docType: string): string {
  // Mirrors the classifier enum in database/049 §lead_documents.
  switch (docType) {
    case "bank_statements_3mo":
      return "Bank statements (3 months)";
    case "drivers_license":
      return "Driver's license";
    case "proof_of_ownership":
      return "Proof of ownership";
    case "void_cheque":
      return "Void cheque";
    case "business_license":
      return "Business license";
    case "tax_returns":
      return "Tax returns";
    case "unclassified":
      return "Other / unclassified";
    default:
      return docType.replace(/_/g, " ");
  }
}

export async function LeadDocumentsPanel({
  tenantId,
  leadId,
}: {
  tenantId: string;
  leadId: string;
}) {
  const db = getServiceSupabase();
  const { data, error } = await db
    .from("lead_documents")
    .select("id, filename, mime_type, size_bytes, doc_type, uploaded_by, uploaded_at")
    .eq("tenant_id", tenantId)
    .eq("lead_id", leadId)
    .order("uploaded_at", { ascending: false });

  if (error) {
    return (
      <Card>
        <div className="text-sm text-rose-400">
          Couldn&apos;t load documents: {error.message}
        </div>
      </Card>
    );
  }

  const docs = (data || []) as LeadDocumentRow[];

  return (
    <Card>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-bold uppercase tracking-wider text-fg-muted">
          Documents ({docs.length})
        </h3>
      </div>
      {docs.length === 0 ? (
        <div className="text-xs text-fg-dim italic py-3 text-center">
          No documents yet. Files uploaded through the application form will
          show up here.
        </div>
      ) : (
        <ul className="divide-y divide-bg-border">
          {docs.map((doc) => {
            const isImage = (doc.mime_type || "").startsWith("image/");
            return (
              <li
                key={doc.id}
                className="flex items-center gap-3 py-2.5 text-sm"
              >
                <div className="shrink-0 text-fg-dim">
                  {isImage ? (
                    <ImageIcon className="w-4 h-4" />
                  ) : (
                    <FileText className="w-4 h-4" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-fg truncate">{doc.filename}</div>
                  <div className="text-[11px] text-fg-dim">
                    {docTypeLabel(doc.doc_type)} · {humanSize(doc.size_bytes)} ·{" "}
                    {new Date(doc.uploaded_at).toLocaleString()}
                    {doc.uploaded_by ? ` · ${doc.uploaded_by}` : ""}
                  </div>
                </div>
                <LeadDocumentDownloadButton
                  documentId={doc.id}
                  filename={doc.filename}
                />
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

