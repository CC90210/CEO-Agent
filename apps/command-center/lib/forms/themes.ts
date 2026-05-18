/**
 * Form theme presets — SunBiz-branded looks for the public form page.
 *
 * Replaces the raw branding JSON textarea with a picker. Each theme maps
 * to a FormBranding object (primary_color, accent_color, headline style).
 * The names mirror the layout HTML files in ~/SunBiz-Agent/docs/ so the
 * operator can mentally connect the form page to the marketing surfaces
 * they already know.
 *
 * Outreach + email-only templates from that repo (ads, consolidation_blast,
 * grid_* campaigns, urgency_fast_funding, social_proof_testimonial) are
 * deliberately excluded — they're not form layouts and including them
 * would confuse operators who just want a clean intake form.
 */
import type { FormBranding } from "./types";

export type FormTheme = {
  /** Stable key written into the branding object so the next load picks it back up. */
  id: string;
  /** Operator-facing name. */
  label: string;
  /** One-line description shown under the name. */
  description: string;
  /** Applied wholesale when the operator picks this theme. */
  branding: FormBranding;
};

export const FORM_THEMES: FormTheme[] = [
  {
    id: "sunbiz_standard",
    label: "SunBiz Standard",
    description: "Default SunBiz Funding intake — blue + warm gold accents.",
    branding: {
      primary_color: "#0ea5e9",
      accent_color: "#FFB81C",
      headline: "Tell us about your business",
      subheadline:
        "A few quick questions, then upload the documents we need to underwrite.",
      thanks_message:
        "Thanks — we received your application. A funding specialist will reach out within one business day.",
    },
  },
  {
    id: "minimal_clean",
    label: "Minimal Clean",
    description: "Neutral palette, big type. Good when the brand is already known.",
    branding: {
      primary_color: "#111827",
      accent_color: "#0ea5e9",
      headline: "Apply for funding",
      subheadline: "Three minutes. No credit pull.",
      thanks_message: "We've got it. Watch your inbox.",
    },
  },
  {
    id: "premium_executive",
    label: "Premium Executive",
    description: "Deep navy + brass — for high-revenue accounts.",
    branding: {
      primary_color: "#1e293b",
      accent_color: "#b45309",
      headline: "Executive Funding Application",
      subheadline:
        "Verified underwriting in 24 hours. Confidential intake.",
      thanks_message:
        "Your application is in. A senior funding officer will reach out personally.",
    },
  },
  {
    id: "problem_solution",
    label: "Problem · Solution",
    description: "Direct, copy-led layout for cold inbound traffic.",
    branding: {
      primary_color: "#dc2626",
      accent_color: "#0ea5e9",
      headline: "Get funded in days, not months",
      subheadline:
        "Tell us where you're stuck. We'll match you with capital that fits.",
      thanks_message:
        "Got it. We'll come back with a path forward within one business day.",
    },
  },
];

export function getFormTheme(id: string | null | undefined): FormTheme | null {
  if (!id) return null;
  return FORM_THEMES.find((t) => t.id === id) || null;
}

/**
 * Detects which preset (if any) matches the current branding, so the
 * builder can highlight the active theme even on a form created before
 * the picker existed. Match is by primary_color + headline because those
 * are the two fields most likely to be unique across themes.
 */
export function inferActiveThemeId(
  branding: FormBranding | null | undefined,
): string | null {
  if (!branding) return null;
  for (const t of FORM_THEMES) {
    if (
      t.branding.primary_color === branding.primary_color &&
      t.branding.headline === branding.headline
    ) {
      return t.id;
    }
  }
  return null;
}
