import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { UsersRound } from "lucide-react";

export const dynamic = "force-dynamic";

export default function TeamPage() {
  return (
    <ComingSoon
      title="Team"
      subtitle="User management for Sun Biz Funding"
      icon={UsersRound}
      phase2Bullets={[
        "Invite teammates via email (Supabase Auth invitation flow)",
        "Role assignment: admin (everything) / loan-officer (deals + commissions) / processor (applications + offers) / read-only (reporting only)",
        "Per-user commission attribution (when an offer they own funds, the commission books to them)",
        "Activity log: who closed which deal, sent which blast, approved which offer",
      ]}
      related={[{ href: "/settings", label: "Settings" }]}
    />
  );
}
