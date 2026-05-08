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
  /**
   * True for the C-suite agents shown on /agents AGENT FAMILY card.
   * False for backend executors (Codex) that power agents but aren't
   * standalone "personas" CC interacts with directly. Defaults true
   * when the field is absent so the registry stays backward-compatible.
   */
  family?: boolean;
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
  // Registry key stays "life-preservation" so filesystem paths
  // (~/life-preservation, tmp/agent_inbox routing, sibling_repos, etc.)
  // remain stable. Only the human-facing label changed to "Lumen".
  "life-preservation": {
    key: "life-preservation",
    label: "Lumen",
    role: "Memory keeper · holds the voice and presence of loved ones",
    tagline: "Memory · voice · legacy",
    location: "C:\\Users\\User\\life-preservation",
    colorRgb: "248, 213, 145", // soft amber — like a small light
    textClass: "text-amber-200",
  },
  // Backend delegation executor — powers custom agents, not a standalone
  // persona. family:false hides it from the AGENT FAMILY card on /agents.
  codex: {
    key: "codex",
    label: "Codex",
    role: "Backend executor · powers custom agents · not standalone",
    tagline: "Backend · delegation",
    location: "OpenAI Codex",
    colorRgb: "148, 163, 184",
    textClass: "text-slate-400",
    family: false,
  },
};

export const ALL_AGENT_KEYS = Object.keys(AGENT_REGISTRY);

/**
 * Subset of ALL_AGENT_KEYS that should appear on the /agents AGENT FAMILY
 * card. Excludes backend executors (Codex) — they power agents but aren't
 * the personas CC interacts with directly.
 */
export const FAMILY_AGENT_KEYS = ALL_AGENT_KEYS.filter(
  (k) => AGENT_REGISTRY[k].family !== false
);

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
