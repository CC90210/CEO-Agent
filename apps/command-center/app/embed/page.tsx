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
        "New website leads will land in the same Solara pipeline as every other lead.",
        "Customize colors, fields, and qualification questions per form.",
        "See which page on Sun's site converts best.",
      ]}
      related={[{ href: "/leads", label: "Leads" }, { href: "/import", label: "Import" }]}
    />
  );
}
