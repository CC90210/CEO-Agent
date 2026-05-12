import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { HandCoins } from "lucide-react";

export const dynamic = "force-dynamic";

export default function OffersPage() {
  return (
    <ComingSoon
      title="Offers"
      subtitle="Lender offers · per-application, 0..N with TAR-band routing"
      icon={HandCoins}
      phase2Bullets={[
        "Migration 040: offers table (application_id, lender_id, amount, factor_rate, term_months, status)",
        "TAR-band overlap support — a merchant may receive offers from multiple bands simultaneously",
        "Stack-aware presentation: choose best APR-equivalent for the merchant",
        "Accept/decline flow with audit trail; accepted offer auto-creates the funded_deal row",
        "Emits SUNBIZ_OFFER_PRESENTED on save",
      ]}
      related={[
        { href: "/applications", label: "Applications" },
        { href: "/funded-deals", label: "Funded Deals" },
        { href: "/lenders", label: "Lenders" },
      ]}
    />
  );
}
