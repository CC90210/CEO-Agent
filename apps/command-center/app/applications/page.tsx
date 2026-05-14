import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { FileText } from "lucide-react";

export const dynamic = "force-dynamic";

export default function ApplicationsPage() {
  return (
    <ComingSoon
      title="Applications"
      subtitle="Funding applications from JotForm, processors, and your team"
      icon={FileText}
      phase2Bullets={[
        "New applications appear here as Solara receives them.",
        "Each application gets a clear status: new, in review, offers out, declined, or funded.",
        "Every file gets a document checklist so nothing slips through the cracks.",
        "The sidebar count updates automatically as the pipeline changes.",
      ]}
      related={[
        { href: "/import", label: "Bulk Import" },
        { href: "/offers", label: "Offers" },
      ]}
    />
  );
}
