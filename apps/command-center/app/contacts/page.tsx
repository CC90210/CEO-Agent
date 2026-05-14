import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { BookUser } from "lucide-react";

export const dynamic = "force-dynamic";

export default function ContactsPage() {
  return (
    <ComingSoon
      title="Contacts"
      subtitle="Engaged merchants and active relationships"
      icon={BookUser}
      phase2Bullets={[
        "Leads can become contacts once someone replies or submits an application.",
        "Each contact will show SMS and email history in one place.",
        "Applications, offers, funded deals, and renewals will connect back to the same merchant.",
        "Solara will surface funding-fit notes inline.",
      ]}
      related={[
        { href: "/leads", label: "Leads" },
        { href: "/applications", label: "Applications" },
      ]}
    />
  );
}
