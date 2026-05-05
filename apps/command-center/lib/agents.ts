/**
 * Single source of truth for the OASIS C-Suite agent registry.
 *
 * Used by /agents and /settings pages. Add or rename an agent here once;
 * both pages update.
 */

export type AgentInfo = {
  key: string;
  role: string;
  location: string;
};

export const AGENT_REGISTRY: Record<string, AgentInfo> = {
  bravo: {
    key: "bravo",
    role: "Lead architect · business ops · content voice",
    location: "this repo",
  },
  atlas: {
    key: "atlas",
    role: "CFO · finance · tax · trading · budget",
    location: "C:\\Users\\User\\APPS\\CFO-Agent",
  },
  maven: {
    key: "maven",
    role: "CMO · content production · paid ads · funnels",
    location: "C:\\Users\\User\\CMO-Agent",
  },
  aura: {
    key: "aura",
    role: "Life · home · habits · voice",
    location: "C:\\Users\\User\\AURA",
  },
  hermes: {
    key: "hermes",
    role: "Commerce agent · POS · EDI · chargebacks",
    location: "C:\\Users\\User\\hermes",
  },
};

export const ALL_AGENT_KEYS = Object.keys(AGENT_REGISTRY);

export function getAgentInfo(key: string): AgentInfo {
  return (
    AGENT_REGISTRY[key] || {
      key,
      role: "Custom agent",
      location: "—",
    }
  );
}
