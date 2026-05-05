/**
 * Single source of truth for the OASIS C-Suite agent registry.
 *
 * Used by /agents and /settings pages, the chat widget, the onboarding wizard,
 * and the sidebar. Add or rename an agent here once; everything updates.
 */

export type AgentInfo = {
  key: string;
  label: string;             // Capitalized display name
  role: string;              // Long descriptor — used by Settings
  tagline: string;           // Short descriptor — used by chat header + onboarding
  location: string;          // Repo / runtime path
  /** RGB triplet (no rgb() wrapper) — drives chat-container glow + pill colors. */
  colorRgb: string;
  /** Tailwind text-* class for inline labels. */
  textClass: string;
};

export const AGENT_REGISTRY: Record<string, AgentInfo> = {
  bravo: {
    key: "bravo",
    label: "Bravo",
    role: "Lead architect · business ops · content voice",
    tagline: "Lead architect · ops · voice",
    location: "this repo",
    colorRgb: "0, 212, 255",
    textClass: "text-accent",
  },
  atlas: {
    key: "atlas",
    label: "Atlas",
    role: "CFO · finance · tax · trading · budget",
    tagline: "CFO · finance · tax · trading",
    location: "C:\\Users\\User\\APPS\\CFO-Agent",
    colorRgb: "52, 211, 153",
    textClass: "text-emerald-400",
  },
  maven: {
    key: "maven",
    label: "Maven",
    role: "CMO · content production · paid ads · funnels",
    tagline: "CMO · content · ads · funnels",
    location: "C:\\Users\\User\\CMO-Agent",
    colorRgb: "244, 114, 182",
    textClass: "text-pink-400",
  },
  aura: {
    key: "aura",
    label: "Aura",
    role: "Life · home · habits · voice",
    tagline: "Life · home · habits · voice",
    location: "C:\\Users\\User\\AURA",
    colorRgb: "192, 132, 252",
    textClass: "text-purple-400",
  },
  hermes: {
    key: "hermes",
    label: "Hermes",
    role: "Commerce agent · POS · EDI · chargebacks",
    tagline: "Commerce · POS · EDI",
    location: "C:\\Users\\User\\hermes",
    colorRgb: "251, 191, 36",
    textClass: "text-amber-400",
  },
};

export const ALL_AGENT_KEYS = Object.keys(AGENT_REGISTRY);

export function getAgentInfo(key: string): AgentInfo {
  return (
    AGENT_REGISTRY[key] || {
      key,
      label: key.charAt(0).toUpperCase() + key.slice(1),
      role: "Custom agent",
      tagline: "Custom agent",
      location: "—",
      colorRgb: "0, 212, 255",
      textClass: "text-accent",
    }
  );
}
