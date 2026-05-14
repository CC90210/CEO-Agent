import { ComingSoon } from "@/components/sunbiz/ComingSoon";
import { HandCoins } from "lucide-react";

export const dynamic = "force-dynamic";

export default function OffersPage() {
  return (
    <ComingSoon
      title="Offers"
      subtitle="Lender offers organized by application"
      icon={HandCoins}
      phase2Bullets={[
        "Lender offers will sit under the application they belong to.",
        "Solara will support multiple offers on the same merchant when more than one funding band applies.",
        "Side-by-side comparisons will help pick the cleanest option for the merchant.",
        "Accepted offers will move into funded deals automatically after review.",
        "Every accept or decline decision will keep a clear history.",
      ]}
      related={[
        { href: "/applications", label: "Applications" },
        { href: "/funded-deals", label: "Funded Deals" },
        { href: "/lenders", label: "Lenders" },
      ]}
    />
  );
}
