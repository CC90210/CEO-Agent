/**
 * Mirror of bravo_cli/agent_roots.py for dashboard awareness.
 *
 * The dashboard doesn't need to RESOLVE these paths (the bridge does that
 * locally). It just needs to know the canonical layout so it can show the
 * operator which agents would be paired locally if they ran the bridge.
 */

export const AGENT_REPO_HINTS: Record<string, string> = {
  bravo: "~/Business-Empire-Agent",
  atlas: "~/APPS/CFO-Agent",
  maven: "~/CMO-Agent",
  aura: "~/AURA",
  hermes: "~/hermes",
};

/** Endpoint the local bridge serves chat from. */
export const BRIDGE_CHAT_BASE = "http://127.0.0.1:9100";
