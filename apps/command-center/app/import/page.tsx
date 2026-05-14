import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { Upload } from "lucide-react";

export const dynamic = "force-dynamic";

export default function ImportPage() {
  return (
    <ComingSoon
      title="Import"
      subtitle="Bulk lead and contact loading"
      icon={Upload}
      phase2Bullets={[
        "Upload a spreadsheet and match columns like name, phone, email, business, revenue, and funding band.",
        "Solara will check for duplicates before adding new records.",
        "Each import will show progress, skipped rows, and anything that needs review.",
        "A clean report will be available after each upload.",
        "New records will flow into the same lead pipeline the team uses every day.",
      ]}
      related={[{ href: "/leads", label: "Leads" }]}
    />
  );
}
