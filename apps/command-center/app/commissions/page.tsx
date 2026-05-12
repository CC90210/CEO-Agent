import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { DollarSign } from "lucide-react";

export const dynamic = "force-dynamic";

export default function CommissionsPage() {
  return (
    <ComingSoon
      title="Commissions"
      subtitle="Booked commission ledger · by lender / agent / TAR band"
      icon={DollarSign}
      phase2Bullets={[
        "Migration 043: commissions table (deal_id, agent_user_id, lender_id, amount_usd, status: pending|paid|clawed_back)",
        "Auto-booked on SUNBIZ_DEAL_FUNDED with computed amount from lender commission %",
        "Renewals book a second commission when the renewal closes (upside on the same merchant relationship)",
        "Period summaries (MTD, YTD, by-rep) with CSV export",
        "Reconciliation against lender remittances",
      ]}
      related={[
        { href: "/funded-deals", label: "Funded Deals" },
        { href: "/renewals", label: "Renewals" },
        { href: "/lenders", label: "Lenders" },
      ]}
    />
  );
}
