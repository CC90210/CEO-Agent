import { OnboardingWizardClient } from "@/components/onboarding/OnboardingWizardClient";

export const dynamic = "force-dynamic";

/**
 * /onboarding/wizard — industry-template onboarding flow.
 *
 * Renders full-bleed (no sidebar) because the layout exempts /onboarding
 * prefixes. The client component runs the 4-step state machine; the
 * finalize POST lives at /api/onboarding/wizard.
 */
export default function OnboardingWizardPage() {
  return <OnboardingWizardClient />;
}
