import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { BookUser } from "lucide-react";

export const dynamic = "force-dynamic";

export default function ContactsPage() {
  return (
    <ComingSoon
      title="Contacts"
      subtitle="Engaged merchants · converted from leads"
      icon={BookUser}
      phase2Bullets={[
        "Migration 038: contacts table (separate from leads — leads convert to contacts on first reply/application)",
        "Per-contact SMS + email history (deduplicated across providers)",
        "Linked applications, offers, funded deals, renewals from one merchant view",
        "TAR-band classification displayed inline",
      ]}
      related={[
        { href: "/leads", label: "Leads" },
        { href: "/applications", label: "Applications" },
      ]}
    />
  );
}
