import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { BadgeDollarSign } from "lucide-react";

export const dynamic = "force-dynamic";

export default function FundedDealsPage() {
  return (
    <ComingSoon
      title="Funded Deals"
      subtitle="Wired deals · the heart of the operation"
      icon={BadgeDollarSign}
      phase2Bullets={[
        "Migration 041: funded_deals table (merchant_name, contact_name, lender_id, funded_amount_usd, factor_rate, funded_at, next_renewal_date, est_commission_usd)",
        "Filter by lender, TAR band, month-to-date, year-to-date",
        "Per-deal timeline: application → offer → funded → renewal lifecycle",
        "Emits SUNBIZ_DEAL_FUNDED on insert (kicks renewal scheduling + commission booking)",
        "Renewal scanner (PM2 nightly) reads from here to surface the /renewals view",
      ]}
      related={[
        { href: "/renewals", label: "Renewals" },
        { href: "/commissions", label: "Commissions" },
      ]}
    />
  );
}
