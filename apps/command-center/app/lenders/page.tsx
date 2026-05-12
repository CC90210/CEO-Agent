import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { Landmark } from "lucide-react";

export const dynamic = "force-dynamic";

export default function LendersPage() {
  return (
    <ComingSoon
      title="Lenders"
      subtitle="Funder registry · term ranges, TAR bands accepted, commission %"
      icon={Landmark}
      phase2Bullets={[
        "Migration 046: lenders table (name, primary_contact, term_range_months, factor_rate_range, tar_bands_accepted, commission_pct)",
        "Per-lender pipeline view: how many applications routed, win rate, average factor rate",
        "Exclusion rules per industry (Real Estate, Cannabis, Auto Sales — Sun's existing exclusion list)",
        "Contract dates, rate sheets, document templates per lender",
      ]}
      related={[
        { href: "/offers", label: "Offers" },
        { href: "/commissions", label: "Commissions" },
      ]}
    />
  );
}
