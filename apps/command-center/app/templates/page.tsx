import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { FileCode2 } from "lucide-react";

export const dynamic = "force-dynamic";

export default function TemplatesPage() {
  return (
    <ComingSoon
      title="Templates"
      subtitle="Email and SMS templates for approved follow-up"
      icon={FileCode2}
      phase2Bullets={[
        "Edit approved email templates directly from the Command Center.",
        "SMS templates will include compliant opt-out language by default.",
        "Preview each message with a real contact before sending.",
        "Track opens, replies, and application results per template.",
      ]}
      related={[
        { href: "/email-blast", label: "Email Blast" },
        { href: "/sms", label: "SMS" },
      ]}
    />
  );
}
