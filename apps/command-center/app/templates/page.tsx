import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { FileCode2 } from "lucide-react";

export const dynamic = "force-dynamic";

export default function TemplatesPage() {
  return (
    <ComingSoon
      title="Templates"
      subtitle="Email + SMS template library · merge-var aware"
      icon={FileCode2}
      phase2Bullets={[
        "Edit-in-place editor over the 6 HTML email templates already shipped in Marketing-Agent's templates/email/ (business_capital_tiers, urgency_fast_funding, problem_solution, premium_executive, minimal_clean, grid_restaurant_hospitality)",
        "SMS template library: pre-approved bodies with TCPA-compliant opt-out language already baked in",
        "Merge-var preview against a real contact row",
        "Per-template send stats (open rate, reply rate, application rate)",
      ]}
      related={[
        { href: "/email-blast", label: "Email Blast" },
        { href: "/sms", label: "SMS" },
      ]}
    />
  );
}
