import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { FileText } from "lucide-react";

export const dynamic = "force-dynamic";

export default function ApplicationsPage() {
  return (
    <ComingSoon
      title="Applications"
      subtitle="Funding applications · merchant-submitted via JotForm or processor"
      icon={FileText}
      phase2Bullets={[
        "Migration 039: applications table (FK to contacts; status flow new → in-review → offers-out → declined/funded)",
        "JotForm webhook ingestion (already running in Sun Biz Agent; surfaces new apps via SUNBIZ_APPLICATION_SUBMITTED event)",
        "Per-application document checklist with upload",
        "Sidebar count badge auto-populates from applications.count",
      ]}
      related={[
        { href: "/import", label: "Bulk Import" },
        { href: "/offers", label: "Offers" },
      ]}
    />
  );
}
