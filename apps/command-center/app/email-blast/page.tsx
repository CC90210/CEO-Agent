import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { Mail } from "lucide-react";

export const dynamic = "force-dynamic";

export default function EmailBlastPage() {
  return (
    <ComingSoon
      title="Email Blast"
      subtitle="Bulk outbound campaigns · Gmail SMTP · CAN-SPAM compliant"
      icon={Mail}
      phase2Bullets={[
        "Campaign creator UI: pick template, recipient list (CSV or tenant-scoped contacts query), preview merge vars",
        "Backed by /api/email-blast/send which shells the Sun Biz Agent's email_blast.py (already production-grade in Marketing-Agent)",
        "Rate-limited 15 sends/min (Gmail caps at 2,000/day on Workspace, 500/day personal)",
        "Per-recipient delivery tracking, opens, unsubscribes",
        "6 HTML templates already shipped: business capital tiers, urgency fast funding, problem-solution, premium executive, etc.",
        "Emits SUNBIZ_EMAIL_BLAST_DISPATCHED on campaign start",
      ]}
      related={[{ href: "/templates", label: "Templates" }, { href: "/sms", label: "SMS" }]}
    />
  );
}
