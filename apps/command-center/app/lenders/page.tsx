import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { Landmark } from "lucide-react";

export const dynamic = "force-dynamic";

export default function LendersPage() {
  return (
    <ComingSoon
      title="Lenders"
      subtitle="Funder directory, terms, and commission notes"
      icon={Landmark}
      phase2Bullets={[
        "Keep each lender's contact, terms, rate range, funding fit, and commission notes in one place.",
        "See how many applications go to each lender and how often they win.",
        "Track industry exclusions so Solara avoids poor-fit submissions.",
        "Store contract dates, rate sheets, and document templates per lender.",
      ]}
      related={[
        { href: "/offers", label: "Offers" },
        { href: "/commissions", label: "Commissions" },
      ]}
    />
  );
}
