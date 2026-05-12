import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { Code2 } from "lucide-react";

export const dynamic = "force-dynamic";

export default function EmbedPage() {
  return (
    <ComingSoon
      title="Embed"
      subtitle="Embeddable lead-capture widgets for Sun's website"
      icon={Code2}
      phase2Bullets={[
        "Generate a JotForm-style script snippet Sun can paste on their site",
        "Lead-capture form posts to the same Supabase tenant_id-scoped pipeline (emits SUNBIZ_LEAD_SOURCED)",
        "Customize colors, fields, qualification gates per embed",
        "Per-domain tracking — see which page on Sun's site converts highest",
      ]}
      related={[{ href: "/leads", label: "Leads" }, { href: "/import", label: "Import" }]}
    />
  );
}
