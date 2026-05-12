import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { Upload } from "lucide-react";

export const dynamic = "force-dynamic";

export default function ImportPage() {
  return (
    <ComingSoon
      title="Import"
      subtitle="CSV ingestion · bulk lead + contact loading"
      icon={Upload}
      phase2Bullets={[
        "CSV upload UI with column mapping (Name / Phone / Email / Business / Revenue / TAR-band)",
        "Server-side dedup against existing leads + contacts on phone + email hashes",
        "Backed by /api/import/upload which feeds deal_tracker.py ingest worker in the Sun Biz Agent",
        "Progress + error report per row (CSV out)",
        "Audit log via SUNBIZ_LEAD_SOURCED events (one per new row)",
      ]}
      related={[{ href: "/leads", label: "Leads" }]}
    />
  );
}
