import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { DollarSign } from "lucide-react";

export const dynamic = "force-dynamic";

export default function CommissionsPage() {
  return (
    <ComingSoon
      title="Commissions"
      subtitle="Booked commissions by lender, deal, and rep"
      icon={DollarSign}
      phase2Bullets={[
        "Commissions will be tied back to the exact deal, lender, and team member.",
        "New funded deals can create the expected commission automatically.",
        "Renewals can book a second commission on the same merchant relationship.",
        "Summaries will show month-to-date, year-to-date, and by-rep totals.",
        "Reconciliation will help compare expected commissions against lender payments.",
      ]}
      related={[
        { href: "/funded-deals", label: "Funded Deals" },
        { href: "/renewals", label: "Renewals" },
        { href: "/lenders", label: "Lenders" },
      ]}
    />
  );
}
